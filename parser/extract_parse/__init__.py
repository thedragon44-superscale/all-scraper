from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ocr_engine import OCREngine
from .text_analyzer import TextAnalyzer
from .schema_mapper import SchemaMapper, DocumentSchemaModel
from .geometry_utils import GeometryUtils
from .layout_cropper import LayoutCropper
from .pipeline import DocumentPipeline


class ExtractParseEngine:
    """Decoupled core extraction and parsing engine module with figure cropping & schema mapping."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.ocr_engine = OCREngine(tesseract_cmd=tesseract_cmd)
        self.text_analyzer = TextAnalyzer()

    def process_pages(
        self,
        image_paths: List[Path | str],
        document_name: str,
        image_output_dir: Optional[Path | str] = None,
        page_layouts: Optional[Dict[int, List[Tuple[int, int, int, int]]]] = None,
    ) -> Dict[str, Any]:
        """Processes a sequence of page images through OCR, layout figure cropping, NLP, and schema mapping."""
        total_pages = len(image_paths)
        schema_mapper = SchemaMapper(document_name=document_name, total_pages=total_pages)
        full_text_accumulator = []
        
        page_layouts = page_layouts or {}
        cropper = None
        if image_output_dir:
            cropper = LayoutCropper(image_output_dir)

        for page_idx, img_path in enumerate(image_paths, 1):
            path = Path(img_path)
            try:
                ocr_result = self.ocr_engine.extract_page_data(path)
                dimensions = ocr_result["page_dimensions"]
                text_blocks = ocr_result["text_blocks"]
            except Exception:
                dimensions = {"width": 1280, "height": 1024}
                text_blocks = []

            page_text = " ".join([b.get("text_content", "") for b in text_blocks])
            full_text_accumulator.append(f"--- PAGE {page_idx} ---\n{page_text}")

            # Process figure extraction and cropping if layout boxes and output dir are provided
            figure_blocks = []
            boxes = page_layouts.get(page_idx, [])
            if cropper and boxes:
                try:
                    raw_figures = cropper.process_page_layouts(
                        image_path=path,
                        page_number=page_idx,
                        layout_boxes=boxes
                    )
                    for fig in raw_figures:
                        matched_caption_id = self._find_associated_caption(fig["spatial_coordinates"], text_blocks)
                        fig_entry = {
                            "figure_id": fig["figure_id"],
                            "image_file_path": fig["image_file_path"],
                            "spatial_coordinates": fig["spatial_coordinates"],
                            "dimensions": fig["dimensions"],
                            "associated_caption_id": matched_caption_id
                        }
                        figure_blocks.append(fig_entry)
                except Exception:
                    pass

            analysis_meta = self.text_analyzer.analyze_page(text_blocks)

            schema_mapper.add_page_data(
                page_number=page_idx,
                page_dimensions=dimensions,
                text_blocks=text_blocks,
                figure_blocks=figure_blocks,
                analysis_metadata=analysis_meta,
            )

        return {
            "full_text": "\n\n".join(full_text_accumulator),
            "structured_schema": schema_mapper.build_document_schema(),
        }

    def _find_associated_caption(self, fig_coords: List[int], text_blocks: List[Dict[str, Any]]) -> Optional[str]:
        """Finds the nearest text block acting as a caption for the cropped figure."""
        fx0, fy0, fx1, fy1 = fig_coords
        best_block_id = None
        min_distance = float('inf')

        for block in text_blocks:
            text = block.get("text_content", "").lower()
            if any(kw in text for kw in ["fig", "figure", "diagram", "table", "illustration"]):
                bx0, by0, bx1, by1 = block["spatial_coordinates"]
                if by0 >= fy1:  # Below figure
                    distance = by0 - fy1
                    if distance < min_distance and distance < 150:
                        min_distance = distance
                        best_block_id = block.get("block_id")

        return best_block_id


__all__ = [
    "ExtractParseEngine",
    "OCREngine",
    "TextAnalyzer",
    "SchemaMapper",
    "GeometryUtils",
    "LayoutCropper",
    "DocumentPipeline",
]
