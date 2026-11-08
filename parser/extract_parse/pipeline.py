from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json

from .ocr_engine import OCREngine
from .layout_cropper import LayoutCropper
from .text_analyzer import TextAnalyzer
from .schema_mapper import SchemaMapper


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
        page_layouts: Optional[Dict[int, List[Tuple[int, int, int, int]]]] = None
    ) -> Dict[str, Any]:
        """
        Processes a full multi-page document, extracting text, cropping figures,
        analyzing content, and building the validated JSON schema.
        """
        page_layouts = page_layouts or {}
        total_pages = len(page_images)
        mapper = SchemaMapper(document_name=document_name, total_pages=total_pages)

        for idx, img_path in enumerate(page_images, start=1):
            path = Path(img_path)
            
            # 1. Extract text blocks and dimensions via OCR
            try:
                ocr_result = self.ocr_engine.extract_page_data(path)
                page_dimensions = ocr_result["page_dimensions"]
                text_blocks = ocr_result["text_blocks"]
            except Exception:
                page_dimensions = {"width": 1280, "height": 1024}
                text_blocks = []

            # 2. Crop figures if layout bounding boxes are provided for this page
            boxes = page_layouts.get(idx, [])
            figure_blocks = []
            if boxes:
                try:
                    raw_figures = self.cropper.process_page_layouts(
                        image_path=path,
                        page_number=idx,
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

            # 3. Run NLP semantic analysis on text blocks
            analysis_metadata = self.analyzer.analyze_page(text_blocks)

            # 4. Add page data to SchemaMapper
            mapper.add_page_data(
                page_number=idx,
                page_dimensions=page_dimensions,
                text_blocks=text_blocks,
                figure_blocks=figure_blocks,
                analysis_metadata=analysis_metadata
            )

        return mapper.build_document_schema()

    def _find_associated_caption(self, fig_coords: List[int], text_blocks: List[Dict[str, Any]]) -> Optional[str]:
        """Finds the nearest text block directly below or above the figure acting as a caption."""
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

    @classmethod
    def interactive_run(cls):
        """Scans the `pdf/` folder for available document folders or files to choose from, and executes the pipeline."""
        print("\n========================================")
        print("     MASTER REFORMATTING & PARSING      ")
        print("========================================")

        pdf_root = Path("pdf")
        if not pdf_root.exists():
            print("[!] Root 'pdf/' directory not found.")
            return

        # Gather subdirectories and files in pdf/
        subdirs = sorted([d for d in pdf_root.iterdir() if d.is_dir() and not d.name.startswith('.')])
        pdfs = sorted(list(pdf_root.glob("*.pdf")))
        all_targets = subdirs + pdfs

        if not all_targets:
            print("[!] No folders or PDF files found in root 'pdf/' directory.")
            return

        print("\nAvailable Document Targets in 'pdf/':")
        for idx, t in enumerate(all_targets, 1):
            t_type = "Folder" if t.is_dir() else "PDF"
            print(f"  [{idx}] {t.name} ({t_type})")
        print("----------------------------------------")

        choice = input("Select a target number to process: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(all_targets)):
            print("[!] Invalid selection.")
            return

        selected_target = all_targets[int(choice) - 1]
        
        # Determine where the page images are
        image_dir = selected_target
        if selected_target.is_dir():
            if (selected_target / "images").exists() and (selected_target / "images").is_dir():
                image_dir = selected_target / "images"

        page_images = sorted(list(image_dir.glob("page_*.png")))
        if not page_images:
            page_images = sorted(list(image_dir.glob("*.png")))

        if not page_images:
            print(f"[!] No page images found in {image_dir}")
            return

        doc_name = selected_target.stem if selected_target.is_file() else selected_target.name
        output_dir = Path("data/output") / doc_name

        print(f"\n[*] Processing {len(page_images)} pages for document '{doc_name}'...")
        print(f"[*] Output schema and cropped figures will be saved to: {output_dir}")

        pipeline = cls(output_dir=output_dir)
        schema_result = pipeline.process_document(
            document_name=doc_name,
            page_images=page_images,
            page_layouts=None
        )

        # Save validated schema JSON
        output_json_path = output_dir / f"{doc_name}_schema.json"
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(schema_result, f, indent=2, ensure_ascii=False)

        print(f"\n[Success] Master reformatting complete!")
        print(f"[+] Validated JSON Schema saved to: {output_json_path}")
        print(f"[+] Cropped figures saved to: {pipeline.figures_dir}")
