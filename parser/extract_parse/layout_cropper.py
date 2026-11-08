from pathlib import Path
from typing import Any, Dict, List, Tuple
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

    def __init__(self, output_dir: str | Path):
        """Initializes the layout cropper.

        Args:
            output_dir: Directory where cropped figure assets will be saved.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _merge_overlapping_boxes(
        self, boxes: List[Tuple[int, int, int, int]], threshold: int = 20
    ) -> List[Tuple[int, int, int, int]]:
        """Clusters and merges overlapping or closely adjacent bounding boxes 

        to reconstruct unified table and diagram regions.
        """
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
        merged = [sorted_boxes[0]]

        for current in sorted_boxes[1:]:
            prev = merged[-1]
            px0, py0, px1, py1 = prev
            cx0, cy0, cx1, cy1 = current

            # Check for proximity or overlap
            if (cx0 <= px1 + threshold and cx1 >= px0 - threshold and
                cy0 <= py1 + threshold and cy1 >= py0 - threshold):
                # Union the boxes
                nx0 = min(px0, cx0)
                ny0 = min(py0, cy0)
                nx1 = max(px1, cx1)
                ny1 = max(py1, cy1)
                merged[-1] = (nx0, ny0, nx1, ny1)
            else:
                merged.append(current)

        return merged

    def extract_layout_boxes(
        self, pdf_path: str | Path
    ) -> Dict[int, List[Tuple[int, int, int, int]]]:
        """Detects and extracts filtered layout bounding boxes (raster images and vector-drawn tables) 

        from a source PDF document using path bounding boxes and spatial clustering.

        Args:
            pdf_path: Path to the source PDF file.

        Returns:
            A dictionary mapping 1-indexed page numbers to lists of bounding box tuples (x0, y0, x1, y1).
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

            with tqdm(enumerate(doc, 1), total=total_pages, desc="Extracting Layouts", unit="page") as pbar:
                for idx, page in pbar:
                    pbar.set_postfix(page=f"{idx}/{total_pages}")
                    raw_rects = []
                    page_rect = page.rect
                    page_area = page_rect.width * page_rect.height

                    # 1. Extract embedded raster images with strict area and dimension filtering
                    try:
                        images = page.get_images(full=True)
                        for img_info in images:
                            xref = img_info[0]
                            for r in page.get_image_rects(xref):
                                box_width = r.x1 - r.x0
                                box_height = r.y1 - r.y0
                                box_area = box_width * box_height

                                if box_area > 0.75 * page_area or box_width > 0.95 * page_rect.width or box_height > 0.95 * page_rect.height:
                                    logger.debug(f"[Page {idx}] Discarded raster image (full-page wrapper): area={box_area:.1f}")
                                    continue
                                if box_width < 25 or box_height < 25:
                                    continue

                                raw_rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract raster images: {e}")

                    # 2. Extract vector drawing paths using native path bounding boxes (`item["rect"]`)
                    try:
                        drawings = page.get_drawings()
                        for item in drawings:
                            r = item.get("rect")
                            if r:
                                r_width = r.x1 - r.x0
                                r_height = r.y1 - r.y0
                                r_area = r_width * r_height

                                # Filter out full-page background boxes and microscopic line artifacts
                                if r_area > 0.75 * page_area or r_width > 0.95 * page_rect.width or r_height > 0.95 * page_rect.height:
                                    continue
                                if r_width < 30 or r_height < 15:
                                    continue

                                raw_rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract vector drawings: {e}")

                    # 3. Cluster and merge overlapping or adjacent component boxes into clean tables/figures
                    merged_boxes = self._merge_overlapping_boxes(raw_rects, threshold=20)

                    if merged_boxes:
                        page_layouts[idx] = merged_boxes
                        logger.info(f"[Page {idx}] Accepted {len(merged_boxes)} layout/table bounding boxes.")

            logger.info(f"Successfully completed layout extraction across {len(page_layouts)} pages.")
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
        """Crops a specific bounding box region from a page image and saves it as a standalone asset."""
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
