from pathlib import Path
from typing import Any, Dict, List, Tuple
import logging
from PIL import Image
from tqdm import tqdm

from .geometry_utils import GeometryUtils

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

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


class LayoutCropper:

    # --- Refined Tunable Extraction Constants (Integrated with GeometryUtils) ---
    TOP_MARGIN_EXCLUSION = 100    # Strict pixel cutoff from top to strip browser toolbars/chrome
    BOTTOM_MARGIN_EXCLUSION = 50  # Strict pixel cutoff from bottom to strip browser status bars
    MIN_REGION_WIDTH = 150        # Strict minimum width (pt)
    MIN_REGION_HEIGHT = 80        # Strict minimum height (pt) to prevent single text line slicing
    MIN_REGION_AREA = 8000        # Strict minimum area (sq pt)
    MAX_REGION_AREA_RATIO = 0.70  # Max area fraction of the page (prevents canvas over-capture)
    MERGE_THRESHOLD = 35          # Clustering proximity gap (pt) for table grid cells
    OPENCV_MIN_BLOCK_AREA = 10000 # Strict OpenCV visual block area filter
    OCR_ANCHOR_MAX_HEIGHT = 450   # Expanded height window for OCR caption anchoring to capture full tables

    def __init__(self, output_dir: str | Path, scale_factor: float = 1.0):
        """Initializes the layout cropper with GeometryUtils integration."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scale_factor = scale_factor
        logger.info("Initialized LayoutCropper with GeometryUtils outer hull reconstruction.")

    def _qualifies_as_region(
        self, box: Tuple[int, int, int, int], page_rect: "fitz.Rect", page_area: float
    ) -> bool:
        """Strict post-cluster validation gate rejecting browser chrome, text lines, and canvas over-capture."""
        x0, y0, x1, y1 = box
        width = x1 - x0
        height = y1 - y0
        area = width * height

        # 1. Browser Chrome / Margin Exclusion check
        if y0 < self.TOP_MARGIN_EXCLUSION:
            return False
        if y1 > (page_rect.height - self.BOTTOM_MARGIN_EXCLUSION):
            return False

        # 2. Strict Dimensional & Area gates (prevents text-line slicing and canvas over-capture)
        if width < self.MIN_REGION_WIDTH or height < self.MIN_REGION_HEIGHT or area < self.MIN_REGION_AREA:
            return False
        if area >= self.MAX_REGION_AREA_RATIO * page_area:
            return False

        return True

    def _detect_opencv_grid_and_blocks(
        self, page: "fitz.Page", page_rect: "fitz.Rect"
    ) -> List[Tuple[int, int, int, int]]:
        """OpenCV grid extraction routed through GeometryUtils outer hull calculation."""
        boxes: List[Tuple[int, int, int, int]] = []
        if not OPENCV_AVAILABLE:
            return boxes

        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            
            if pix.n == 4:
                gray = cv2.cvtColor(img_data, cv2.COLOR_BGRA2GRAY)
            elif pix.n == 3:
                gray = cv2.cvtColor(img_data, cv2.COLOR_BGR2GRAY)
            else:
                gray = img_data

            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

            # Table Gridline Extraction
            h_kernel_len = max(1, thresh.shape[1] // 30)
            v_kernel_len = max(1, thresh.shape[0] // 30)
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))

            h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
            v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
            table_grid = cv2.add(h_lines, v_lines)

            contours, _ = cv2.findContours(table_grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            inv_scale = 0.5

            cell_boxes = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                cell_boxes.append((int(x * inv_scale), int(y * inv_scale), int((x + w) * inv_scale), int((y + h) * inv_scale)))

            # Use GeometryUtils to compute unified outer hulls for tables (preventing sub-cell slicing)
            table_hulls = GeometryUtils.compute_table_outer_hull(cell_boxes, page_rect.width, page_rect.height)
            boxes.extend(table_hulls)

            # Strict Visual Content Blocks (Diagrams)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            fig_contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in fig_contours:
                x, y, w, h = cv2.boundingRect(cnt)
                scaled_box = (int(x * inv_scale), int(y * inv_scale), int((x + w) * inv_scale), int((y + h) * inv_scale))
                box_area = (scaled_box[2] - scaled_box[0]) * (scaled_box[3] - scaled_box[1])
                
                if box_area < self.OPENCV_MIN_BLOCK_AREA:
                    continue
                if box_area >= self.MAX_REGION_AREA_RATIO * (page_rect.width * page_rect.height):
                    continue
                boxes.append(scaled_box)

        except Exception:
            logger.exception("OpenCV grid and block detection failed.")

        return boxes

    def _detect_ocr_anchored_regions(
        self, page: "fitz.Page", page_rect: "fitz.Rect"
    ) -> List[Tuple[int, int, int, int]]:
        """Strict OCR keyword anchoring with expanded search windows for complete table capture."""
        boxes: List[Tuple[int, int, int, int]] = []
        if not PYTESSERACT_AVAILABLE:
            return boxes

        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
            img = Image.frombytes("RGB", [pix.w, pix.h], pix.samples)
            
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            n_boxes = len(ocr_data["text"])
            
            for i in range(n_boxes):
                text = ocr_data["text"][i].strip().lower()
                if any(kw in text for kw in ["table", "figure", "fig."]):
                    x0 = ocr_data["left"][i]
                    y0 = ocr_data["top"][i]
                    w = ocr_data["width"][i]
                    
                    box_x0 = max(10, x0 - 20)
                    box_x1 = min(int(page_rect.width) - 10, int(page_rect.width) - 20)
                    box_y1 = max(self.TOP_MARGIN_EXCLUSION, y0 - 5)
                    box_y0 = max(self.TOP_MARGIN_EXCLUSION, box_y1 - self.OCR_ANCHOR_MAX_HEIGHT)
                    
                    if box_y1 > box_y0:
                        boxes.append((box_x0, box_y0, box_x1, box_y1))
        except Exception:
            logger.exception("OCR keyword anchoring failed.")

        return boxes

    def extract_layout_boxes(
        self, pdf_path: str | Path
    ) -> Dict[int, List[Tuple[int, int, int, int]]]:
        """Extracts and strictly filters layout boxes across all pages using GeometryUtils."""
        page_layouts: Dict[int, List[Tuple[int, int, int, int]]] = {}
        if not PYMUPDF_AVAILABLE:
            logger.error("PyMuPDF (fitz) is not available. Cannot extract layout boxes.")
            return page_layouts

        path = Path(pdf_path)
        if not path.exists():
            logger.error(f"Source PDF not found: {path}")
            return page_layouts

        logger.info(f"Starting geometry-guided layout extraction for: {path.name}")

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)

            with tqdm(
                enumerate(doc, 1), total=total_pages, desc="Extracting Layouts", unit="page"
            ) as pbar:
                for idx, page in pbar:
                    pbar.set_postfix(page=f"{idx}/{total_pages}")

                    page_rect = page.rect
                    page_area = page_rect.width * page_rect.height
                    raw_rects: List[Tuple[int, int, int, int]] = []

                    # 1. OpenCV Grid Outer Hulls & Visual Blocks
                    raw_rects.extend(self._detect_opencv_grid_and_blocks(page, page_rect))

                    # 2. OCR Anchored Regions
                    raw_rects.extend(self._detect_ocr_anchored_regions(page, page_rect))

                    # 3. Cluster & Merge via GeometryUtils
                    merged_boxes = GeometryUtils.merge_overlapping_boxes(raw_rects, threshold=self.MERGE_THRESHOLD)

                    # 4. Strict Post-cluster Gate
                    qualified = [
                        b for b in merged_boxes if self._qualifies_as_region(b, page_rect, page_area)
                    ]

                    if qualified:
                        scaled = [
                            tuple(int(round(v * self.scale_factor)) for v in b)
                            for b in qualified
                        ]
                        page_layouts[idx] = scaled
                        logger.info(f"[Page {idx}] Accepted {len(scaled)} geometry-validated layout boxes.")

            logger.info(f"Geometry-guided layout extraction complete: {len(page_layouts)} pages with regions.")
        except Exception:
            logger.exception("Critical error during layout box extraction.")

        return page_layouts

    def crop_region(
        self,
        image_path: str | Path,
        bbox: Tuple[int, int, int, int],
        page_number: int,
        figure_index: int,
    ) -> Dict[str, Any]:
        """Crops and saves validated strict region."""
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

        logger.debug(f"Saved asset: {save_path.name} (Dims: {crop_width}x{crop_height})")
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
        extracted_figures = []
        for idx, bbox in enumerate(layout_boxes, start=1):
            try:
                file_data = self.crop_region(
                    image_path=image_path,
                    bbox=bbox,
                    page_number=page_number,
                    figure_index=idx,
                )
                extracted_figures.append(file_data)
            except Exception as e:
                logger.warning(f"Failed to crop region {bbox} on page {page_number}: {e}")

        return extracted_figures
