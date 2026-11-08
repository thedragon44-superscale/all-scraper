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

    def extract_layout_boxes(
        self, pdf_path: str | Path
    ) -> Dict[int, List[Tuple[int, int, int, int]]]:
        """Detects and extracts filtered layout bounding boxes (images and vector-drawn tables) 

        from a source PDF document with comprehensive terminal progress tracking and stack trace logging.

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

            # Wrap page iteration with a dedicated progress bar and diagnostics
            with tqdm(enumerate(doc, 1), total=total_pages, desc="Extracting Layouts", unit="page") as pbar:
                for idx, page in pbar:
                    pbar.set_postfix(page=f"{idx}/{total_pages}")
                    rects = []
                    page_rect = page.rect
                    page_area = page_rect.width * page_rect.height

                    # 1. Extract embedded raster images with explicit size/area rejection logging
                    try:
                        images = page.get_images(full=True)
                        for img_info in images:
                            xref = img_info[0]
                            for r in page.get_image_rects(xref):
                                box_width = r.x1 - r.x0
                                box_height = r.y1 - r.y0
                                box_area = box_width * box_height

                                if box_area > 0.75 * page_area or box_width > 0.95 * page_rect.width or box_height > 0.95 * page_rect.height:
                                    logger.debug(f"[Page {idx}] Discarded raster image (full-page wrapper): area={box_area:.1f}, dims=({box_width:.1f}x{box_height:.1f})")
                                    continue
                                if box_width < 20 or box_height < 20:
                                    logger.debug(f"[Page {idx}] Discarded raster image (too small/noise): dims=({box_width:.1f}x{box_height:.1f})")
                                    continue

                                rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract raster images: {e}")

                    # 2. Extract vector drawings to detect tables and structured bounding boxes
                    table_rects = []
                    try:
                        drawings = page.get_drawings()
                        for item in drawings:
                            if item.get("items"):
                                for sub in item["items"]:
                                    if sub[0] == "re":  # Rectangle path
                                        rx0, ry0, rx1, ry1 = sub[1]
                                        r_width = rx1 - rx0
                                        r_height = ry1 - ry0
                                        r_area = r_width * r_height
                                        if 0.01 * page_area < r_area < 0.7 * page_area:
                                            table_rects.append((int(rx0), int(ry0), int(rx1), int(ry1)))
                    except Exception as e:
                        logger.warning(f"[Page {idx}] Failed to extract vector drawings: {e}")

                    # Combine, deduplicate, and sort boxes by vertical position
                    combined_boxes = []
                    all_raw_rects = rects + table_rects
                    all_raw_rects.sort(key=lambda b: (b[1], b[0]))

                    for box in all_raw_rects:
                        is_duplicate = False
                        bx0, by0, bx1, by1 = box
                        for existing in combined_boxes:
                            ex0, ey0, ex1, ey1 = existing
                            if abs(bx0 - ex0) < 10 and abs(by0 - ey0) < 10 and abs(bx1 - ex1) < 10 and abs(by1 - ey1) < 10:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            combined_boxes.append(box)

                    if combined_boxes:
                        page_layouts[idx] = combined_boxes
                        logger.info(f"[Page {idx}] Accepted {len(combined_boxes)} layout/table bounding boxes.")

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
        x1 = max(x0, min(x1, width))
        y1 = max(y0, min(y1, height))

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
