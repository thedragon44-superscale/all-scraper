from pathlib import Path
from typing import Any, Dict, List, Tuple
from PIL import Image


class LayoutCropper:

    def __init__(self, output_dir: str | Path):
        """Initializes the layout cropper.

        Args:
            output_dir: Directory where cropped figure assets will be saved.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
