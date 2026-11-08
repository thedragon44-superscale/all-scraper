from pathlib import Path
from typing import Any, Dict, List, Tuple
from PIL import Image

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

        from a source PDF document, discarding full-page wrappers.

        Args:
            pdf_path: Path to the source PDF file.

        Returns:
            A dictionary mapping 1-indexed page numbers to lists of bounding box tuples (x0, y0, x1, y1).
        """
        page_layouts: Dict[int, List[Tuple[int, int, int, int]]] = {}
        if not PYMUPDF_AVAILABLE:
            return page_layouts

        path = Path(pdf_path)
        if not path.exists():
            return page_layouts

        try:
            doc = fitz.open(str(path))
            for idx, page in enumerate(doc, 1):
                rects = []
                page_rect = page.rect
                page_area = page_rect.width * page_rect.height

                # 1. Extract embedded raster images with size/area filtering
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    for r in page.get_image_rects(xref):
                        box_width = r.x1 - r.x0
                        box_height = r.y1 - r.y0
                        box_area = box_width * box_height

                        # Discard boxes covering > 75% of page area or matching full page dimensions
                        if box_area > 0.75 * page_area or box_width > 0.95 * page_rect.width or box_height > 0.95 * page_rect.height:
                            continue
                        if box_width < 20 or box_height < 20:  # Skip tiny icons/noise artifacts
                            continue

                        rects.append((int(r.x0), int(r.y0), int(r.x1), int(r.y1)))

                # 2. Extract vector drawings to detect tables and structured bounding boxes
                drawings = page.get_drawings()
                table_rects = []
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
        except Exception:
            pass

        return page_layouts

    def crop_region(
        self,
        image_path: str | Path,
        bbox: Tuple[int, int, int, int],
        page_number: int,
        figure_index: int,
    ) -> Dict[str, Any]:
        """Crops a specific bounding box region from a page image and saves it as a

        standalone asset.

        Args:
            image_path: Path to the full-page scanned image.
            bbox: Bounding box coordinates as (x0, y0, x1, y1).
            page_number: Page number context for naming.
            figure_index: Unique index of the figure on the page.

        Returns:
            A dictionary containing the saved asset path, dimensions, and metadata.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Source image not found: {path}")

        image = Image.open(path)
        x0, y0, x1, y1 = bbox

        # Ensure valid crop boundaries
        width, height = image.size
        x0 = max(0, min(x0, width))
        y0 = max(0, min(y0, height))
        x1 = max(x0, min(x1, width))
        y1 = max(y0, min(y1, height))

        if x0 >= x1 or y0 >= y1:
            raise ValueError(f"Invalid bounding box dimensions: {bbox}")

        # Crop the specified region
        cropped_image = image.crop((x0, y0, x1, y1))
        crop_width, crop_height = cropped_image.size

        # Save cropped asset
        file_name = f"page_{page_number:03d}_fig_{figure_index:02d}.png"
        save_path = self.output_dir / file_name
        cropped_image.save(save_path, "PNG")

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
        """Processes multiple layout bounding boxes for a single page.

        Args:
            image_path: Path to the full-page scanned image.
            page_number: Page number context.
            layout_boxes: A list of bounding box tuples [(x0, y0, x1, y1), ...].

        Returns:
            A list of dictionaries representing the extracted figure assets.
        """
        extracted_figures = []
        for idx, bbox in enumerate(layout_boxes, start=1):
            figure_data = self.crop_region(
                image_path=image_path,
                bbox=bbox,
                page_number=page_number,
                figure_index=idx,
            )
            extracted_figures.append(figure_data)

        return extracted_figures
