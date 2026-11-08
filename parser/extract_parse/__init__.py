from pathlib import Path
from typing import Any, Dict, List, Optional

from .ocr_engine import OCREngine
from .text_analyzer import TextAnalyzer
from .schema_mapper import SchemaMapper
from .layout_cropper import LayoutCropper


class ExtractParseEngine:
    """Decoupled core extraction and parsing engine module."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.ocr_engine = OCREngine(tesseract_cmd=tesseract_cmd)
        self.text_analyzer = TextAnalyzer()

    def process_pages(
        self,
        image_paths: List[Path | str],
        document_name: str,
        image_output_dir: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Processes a sequence of page images through OCR, NLP, and schema mapping."""
        total_pages = len(image_paths)
        schema_mapper = SchemaMapper(document_name=document_name, total_pages=total_pages)
        full_text_accumulator = []

        if image_output_dir:
            LayoutCropper(image_output_dir)

        for page_idx, img_path in enumerate(image_paths, 1):
            path = Path(img_path)
            try:
                ocr_result = self.ocr_engine.extract_page_data(path)
                dimensions = ocr_result["page_dimensions"]
                text_blocks = ocr_result["text_blocks"]
            except Exception:
                dimensions = {"width": 1280, "height": 1024}
                text_blocks = []

            page_text = " ".join([b["text_content"] for b in text_blocks])
            full_text_accumulator.append(f"--- PAGE {page_idx} ---\n{page_text}")

            analysis_meta = self.text_analyzer.analyze_page(text_blocks)

            schema_mapper.add_page_data(
                page_number=page_idx,
                page_dimensions=dimensions,
                text_blocks=text_blocks,
                figure_blocks=[],
                analysis_metadata=analysis_meta,
            )

        return {
            "full_text": "\n\n".join(full_text_accumulator),
            "structured_schema": schema_mapper.build_document_schema(),
        }
