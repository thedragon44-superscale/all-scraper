from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
from PIL import Image
from tqdm import tqdm

# Configure event logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LayoutCropper")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


class LayoutCropper:

    # --- Tunable extraction constants ---
    MIN_FRAGMENT_DIM = 2          # Raw-path floor: drops only invisible dots/hairlines
    MIN_REGION_SIZE = 40          # Post-cluster minimum width/height (pt) for tables/figures
    MAX_REGION_AREA_RATIO = 0.75  # Post-cluster max area as fraction of the page
    FULL_PAGE_WRAPPER_RATIO = 0.95  # Raw-level guard: length/area ratios that indicate full-page wrappers
    MERGE_THRESHOLD = 20          # Clustering proximity gap (pt)
    MIN_IMAGE_BOX_DIM = 25        # Smallest embedded raster worth considering (pt)
    TEXT_CHARS_SCANNED_PAGE = 20  # Below this char count a page is treated as scanned

    def __init__(self, output_dir: str | Path, scale_factor: float = 1.0):
        """Initializes the layout cropper.

        Args:
            output_dir: Directory where cropped figure assets will be saved.
            scale_factor: Multiplier converting PDF-point coordinates into the
                pixel space of the rendered page images. If pages were rendered
                with ``fitz.Matrix(zoom, zoom)``, pass the same ``zoom`` here so
                extracted boxes align with the raster assets.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scale_factor = scale_factor

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _overlaps(
        self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int], threshold: int
    ) -> bool:
        """Returns True if two boxes overlap or sit within `threshold` of each other."""
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return (
            bx0 <= ax1 + threshold and bx1 >= ax0 - threshold
            and by0 <= ay1 + threshold and by1 >= ay0 - threshold
        )

    def _union(
        self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))

    def _merge_overlapping_boxes(
        self, boxes: List[Tuple[int, int, int, int]], threshold: int = 20
    ) -> List[Tuple[int, int, int, int]]:
        """Iteratively clusters and merges overlapping or closely adjacent boxes.

        Runs repeated merge passes until the result is stable, so transitive
        chains (A~B, B~C but not A~C) collapse into a single region.
        """
        if not boxes:
            return []

        current = sorted(boxes, key=lambda b: (b[1], b[0]))
        changed = True
        while changed:
            changed = False
            merged: List[Tuple[int, int, int, int]] = []
            for box in current:
                if merged and self._overlaps(merged[-1], box, threshold):
                    merged[-1] = self._union(merged[-1], box)
                    changed = True
                else:
                    merged.append(box)
            current = merged

        return current

    def _is_scanned_page(self, page: "fitz.Page") -> bool:
        """Heuristic: a page with little/no text and a single large raster is a scan."""
        try:
            text_chars = len(page.get_text().strip())
        except Exception:
            text_chars = 0

        if text_chars >= self.TEXT_CHARS_SCANNED_PAGE:
            return False

        try:
            images = page.get_images(full=True)
        except Exception:
            return False

        if len(images) != 1:
            return False

        page_area = page.rect.width * page.rect.height
        try:
            rects = page.get_image_rects(images[0][0])
        except Exception:
            return False

        for r in rects:
            if (r.x1 - r.x0) * (r.y1 - r.y0) >= 0.9 * page_area:
                return True
        return False

    def _is_full_page_wrapper(
        self, r_width: float, r_height: float, r_area: float, page_rect: "fitz.Rect"
    ) -> bool:
        """True when a raw element is a full-page background/wrapper (e.g. a page scan)."""
        page_area = page_rect.width * page_rect.height
        return (
            r_area > self.FULL_PAGE_WRAPPER_RATIO * page_area
            or r_width > self.FULL_PAGE_WRAPPER_RATIO * page_rect.width
            or r_height > self.FULL_PAGE_WRAPPER_RATIO * page_rect.height
        )

    def _qualifies_as_region(
        self, box: Tuple[int, int, int, int], page_area: float
    ) -> bool:
        """Post-cluster gate: decides whether a merged region is a real table/figure."""
        width = box[2] - box[0]
        height = box[3] - box[1]
        area = width * height

        if width < self.MIN_REGION_SIZE or height < self.MIN_REGION_SIZE:
            return False
        if area >= self.MAX_REGION_AREA_RATIO * page_area:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def extract_layout_boxes(
        self, pdf_path: str | Path
    ) -> Dict[int, List[Tuple[int, int, int, int]]]:
        """Detects and extracts filtered layout bounding boxes (raster images and
        vector-drawn tables) from a source PDF.

        Raw fragments (grid lines, strokes) are collected permissively and only
        clustered afterward — the shape/size gate is applied POST-merge so table
        fragments survive to become part of a unified region.

        Args:
            pdf_path: Path to the source PDF file.

        Returns:
            A dictionary mapping 1-indexed page numbers to lists of bounding box
            tuples (x0, y0, x1, y1) expressed in the pixel space of the rendered
            page images (i.e. PDF points multiplied by ``self.scale_factor``).
        """
        page_layouts: Dict[int, List[Tuple[int, int, int, int]]] = {}
        if not PYMUPDF_AVAILABLE:
            logger.error("PyMuPDF (fitz) is not available. Cannot extract layout boxes.")
            return page_layouts

        path = Path(pdf_path)
        if not path.exists():
            logger.error(f"Source PDF not found: {path}")
            return page_layouts

        logger.info(f"Starting layout and table extraction for: {path.name}")

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)
            scanned_pages = 0

            with tqdm(
                enumerate(doc, 1), total=total_pages, desc="Extracting Layouts", unit="page"
            ) as pbar:
                for idx, page in pbar:
                    pbar.set_postfix(page=f"{idx}/{total_pages}")

                    # Skip scanned pages: the whole page is one raster, so there
                    # is nothing meaningful to crop beyond the scan itself.
                    if self._is_scanned_page(page):
                        scanned_pages += 1
                        logger.debug(f"[Page {idx}] Skipped (scanned/image-only page).")
                        continue

                    page_rect = page.rect
                    page_area = page_rect.width * page_rect.height
                    raw_rects: List[Tuple[int, int, int, int]] = []

                    # 1. Collect embedded raster images (permissive: minimal filtering)
                    try:
                        images = page.get_images(full=True)
                        for img_info in images:
                            xref = img_info[0]
                            try:
                                rects = page.get_image_rects(xref)
                            except Exception:
                                continue
                            for r in rects:
                                r_width = r.x1 - r.x0
                                r_height = r.y1 - r.y0

                                # Drop only full-page wrappers and tiny thumbnails
                                if self._is_full_page_wrapper(r_width, r_height, r_width * r_height, page_rect):
                                    continue
                                if r_width < self.MIN_IMAGE_BOX_DIM or r_height < self.MIN_IMAGE_BOX_DIM:
                                    continue

                                raw_rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract raster images: {e}")

                    # 2. Collect vector drawing fragments (grid lines, strokes, cells)
                    try:
                        drawings = page.get_drawings()
                        for item in drawings:
                            r = item.get("rect")
                            if not r:
                                continue
                            r_width = r.x1 - r.x0
                            r_height = r.y1 - r.y0

                            # Permissive raw floor: keep hairline fragments so the
                            # clustering stage can reconstruct tables from them.
                            if r_width < self.MIN_FRAGMENT_DIM or r_height < self.MIN_FRAGMENT_DIM:
                                continue
                            # Guard only against literal full-page backgrounds
                            if r_width > self.FULL_PAGE_WRAPPER_RATIO * page_rect.width and \
                               r_height > self.FULL_PAGE_WRAPPER_RATIO * page_rect.height:
                                continue

                            raw_rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract vector drawings: {e}")

                    # 3. Cluster fragments into unified table/figure regions
                    merged_boxes = self._merge_overlapping_boxes(raw_rects, threshold=self.MERGE_THRESHOLD)

                    # 4. POST-cluster gate: apply shape/size qualification here,
                    #    not on the raw fragments.
                    qualified = [
                        b for b in merged_boxes if self._qualifies_as_region(b, page_area)
                    ]

                    if qualified:
                        # Convert PDF-point coords to rendered-image pixel coords
                        scaled = [
                            tuple(int(round(v * self.scale_factor)) for v in b)
                            for b in qualified
                        ]
                        page_layouts[idx] = scaled
                        logger.info(f"[Page {idx}] Accepted {len(scaled)} layout/table bounding boxes.")

            logger.info(
                f"Layout extraction complete: {len(page_layouts)} pages with regions, "
                f"{scanned_pages} scanned pages skipped."
            )
        except Exception:
            logger.exception("Critical error during layout box extraction process.")

        return page_layouts

    def crop_region(
        self,
        image_path: str | Path,
        bbox: Tuple[int, int, int, int],
        page_number: int,
        figure_index: int,
    ) -> Dict[str, Any]:
        """Crops a specific bounding box region from a page image and saves it
        as a standalone asset."""
        path = Path(image_path)
        if not path.exists():
            logger.error(f"Source image not found: {path}")
            raise FileNotFoundError(f"Source image not found: {path}")

        image = Image.open(path)
        x0, y0, x1, y1 = bbox

        width, height = image.size
        x0 = max(0, min(x0, width))
        y0 = max(0, min(y0, height))
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))

        if x0 >= x1 or y0 >= y1:
            logger.warning(f"Invalid bounding box dimensions for page {page_number}, figure {figure_index}: {bbox}")
            raise ValueError(f"Invalid bounding box dimensions: {bbox}")

        cropped_image = image.crop((x0, y0, x1, y1))
        crop_width, crop_height = cropped_image.size

        file_name = f"page_{page_number:03d}_fig_{figure_index:02d}.png"
        save_path = self.output_dir / file_name
        cropped_image.save(save_path, "PNG")

        logger.debug(f"Saved cropped asset: {save_path.name} (Dims: {crop_width}x{crop_height})")
        return {
            "figure_id": f"fig_{page_number}_{figure_index}",
            "image_file_path": str(save_path.resolve()),
            "spatial_coordinates": [x0, y0, x1, y1],
            "dimensions": {"width": crop_width, "height": crop_height},
        }

    def process_page_layouts(
        self,
        image_path: str | Path,
        page_number: int,
        layout_boxes: List[Tuple[int, int, int, int]],
    ) -> List[Dict[str, Any]]:
        """Processes multiple layout bounding boxes for a single page."""
        extracted_figures = []
        for idx, bbox in enumerate(layout_boxes, start=1):
            try:
                figure_data = self.crop_region(
                    image_path=image_path,
                    bbox=bbox,
                    page_number=page_number,
                    figure_index=idx,
                )
                extracted_figures.append(figure_data)
            except Exception as e:
                logger.warning(f"Failed to crop region {bbox} on page {page_number}: {e}")

        return extracted_figures

