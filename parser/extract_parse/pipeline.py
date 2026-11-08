from pathlib import Path
from typing import Any, Dict, List, Tuple
from ocr_engine_3 import OCREngine
from layout_cropper_3 import LayoutCropper
from text_analyzer_2 import TextAnalyzer
from schema_mapper_2 import SchemaMapper

class DocumentPipeline:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.figures_dir = self.output_dir / "cropped_figures"
        
        # Initialize modules
        self.ocr_engine = OCREngine()
        self.cropper = LayoutCropper(output_dir=self.figures_dir)
        self.analyzer = TextAnalyzer()

    def process_document(
        self, 
        document_name: str, 
        page_images: List[str | Path], 
        page_layouts: Dict[int, List[Tuple[int, int, int, int]]]
    ) -> Dict[str, Any]:
        """
        Processes a full multi-page document, extracting text, cropping figures,
        analyzing content, and building the validated JSON schema.
        
        Args:
            document_name: Name of the document.
            page_images: List of file paths to full-page scanned images.
            page_layouts: Dict mapping 1-based page numbers to lists of figure bounding boxes (x0, y0, x1, y1).
        """
        total_pages = len(page_images)
        mapper = SchemaMapper(document_name=document_name, total_pages=total_pages)

        for idx, img_path in enumerate(page_images, start=1):
            path = Path(img_path)
            
            # 1. Extract text blocks and dimensions via OCR
            ocr_result = self.ocr_engine.extract_page_data(path)
            page_dimensions = ocr_result["page_dimensions"]
            text_blocks = ocr_result["text_blocks"]

            # 2. Crop figures if layout bounding boxes are provided for this page
            boxes = page_layouts.get(idx, [])
            figure_blocks = []
            if boxes:
                raw_figures = self.cropper.process_page_layouts(
                    image_path=path,
                    page_number=idx,
                    layout_boxes=boxes
                )
                
                # 3. Associate captions and map to FigureBlockModel structure
                for fig in raw_figures:
                    # Optional heuristic or spatial logic to find matching caption block
                    matched_caption_id = self._find_associated_caption(fig["spatial_coordinates"], text_blocks)
                    
                    fig_entry = {
                        "figure_id": fig["figure_id"],
                        "image_file_path": fig["image_file_path"],
                        "spatial_coordinates": fig["spatial_coordinates"],
                        "dimensions": fig["dimensions"],
                        "associated_caption_id": matched_caption_id
                    }
                    figure_blocks.append(fig_entry)

            # 4. Run NLP semantic analysis on text blocks
            analysis_metadata = self.analyzer.analyze_page(text_blocks)

            # 5. Add page data to SchemaMapper
            mapper.add_page_data(
                page_number=idx,
                page_dimensions=page_dimensions,
                text_blocks=text_blocks,
                figure_blocks=figure_blocks,
                analysis_metadata=analysis_metadata
            )

        return mapper.build_document_schema()

    def _find_associated_caption(self, fig_coords: List[int], text_blocks: List[Dict[str, Any]]) -> Optional[str]:
        """
        Finds the nearest text block directly below or above the figure acting as a caption.
        """
        fx0, fy0, fx1, fy1 = fig_coords
        best_block_id = None
        min_distance = float('inf')

        for block in text_blocks:
            text = block.get("text_content", "").lower()
            # Check if text block contains standard caption keywords
            if any(kw in text for kw in ["fig", "figure", "diagram", "table", "illustration"]):
                bx0, by0, bx1, by1 = block["spatial_coordinates"]
                
                # Check if caption is vertically close below or above the figure
                if by0 >= fy1:  # Below figure
                    distance = by0 - fy1
                    if distance < min_distance and distance < 150: # within 150 pixels
                        min_distance = distance
                        best_block_id = block["block_id"]

        return best_block_id
