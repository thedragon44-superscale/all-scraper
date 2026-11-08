from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json

from .ocr_engine import OCREngine
from .layout_cropper import LayoutCropper
from .text_analyzer import TextAnalyzer
from .schema_mapper import SchemaMapper

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


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
        """Scans the `pdf/` folder, lets the user select a target, customize the output folder name under `data/parsed_data`, renders/gathers images, and executes the pipeline."""
        print("\n========================================")
        print("     MASTER REFORMATTING & PARSING      ")
        print("========================================")

        pdf_root = Path("pdf")
        if not pdf_root.exists():
            print("[!] Root 'pdf/' directory not found.")
            return

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
        default_folder_name = selected_target.stem if selected_target.is_file() else selected_target.name

        try:
            custom_name = input(f"Enter custom output folder name inside 'data/parsed_data' [default: {default_folder_name}]: ").strip()
            if custom_name:
                default_folder_name = custom_name
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Operation cancelled.")
            return

        # Strictly structured paths inside data/parsed_data
        out_dir = Path("data") / "parsed_data" / default_folder_name
        img_dir = out_dir / "images"
        
        out_dir.mkdir(parents=True, exist_ok=True)
        img_dir.mkdir(parents=True, exist_ok=True)

        page_images = []

        if selected_target.is_dir():
            image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
            page_images = sorted([p for p in selected_target.iterdir() if p.suffix.lower() in image_extensions])
            
            if not page_images and (selected_target / "images").exists():
                page_images = sorted([p for p in (selected_target / "images").iterdir() if p.suffix.lower() in image_extensions])

            if not page_images:
                sub_pdfs = list(selected_target.glob("*.pdf"))
                if sub_pdfs and PYMUPDF_AVAILABLE:
                    print(f"[*] Found PDF inside directory, rendering pages to images...")
                    doc = fitz.open(str(sub_pdfs[0]))
                    for idx, page in enumerate(doc, 1):
                        pix = page.get_pixmap()
                        img_path = img_dir / f"page_{idx:03d}.png"
                        pix.save(str(img_path))
                        page_images.append(img_path)
        elif selected_target.is_file() and selected_target.suffix.lower() == ".pdf" and PYMUPDF_AVAILABLE:
            print(f"[*] Rendering PDF pages to images...")
            doc = fitz.open(str(selected_target))
            for idx, page in enumerate(doc, 1):
                pix = page.get_pixmap()
                img_path = img_dir / f"page_{idx:03d}.png"
                pix.save(str(img_path))
                page_images.append(img_path)

        if not page_images:
            print(f"[!] No valid page images or documents found for {selected_target.name}")
            return

        print(f"\n[*] Processing {len(page_images)} pages for '{default_folder_name}'...")
        print(f"[*] Output directory: {out_dir.resolve()}")

        pipeline = cls(output_dir=out_dir)
        
        # Run text extraction, figure cropping, and analysis
        schema_result = pipeline.process_document(
            document_name=default_folder_name,
            page_images=page_images,
            page_layouts=None
        )

        # Build full text accumulator
        full_text_accumulator = []
        for idx, img_path in enumerate(page_images, 1):
            try:
                ocr_data = pipeline.ocr_engine.extract_page_data(img_path)
                page_text = " ".join([b.get("text_content", "") for b in ocr_data.get("text_blocks", [])])
                full_text_accumulator.append(f"--- PAGE {idx} ---\n{page_text}")
            except Exception:
                pass

        # Save standard outputs
        txt_output_path = out_dir / "text.txt"
        txt_output_path.write_text("\n\n".join(full_text_accumulator), encoding="utf-8")

        json_output_path = out_dir / "json_schema.json"
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(schema_result, f, indent=2, ensure_ascii=False)

        print(f"\n[+] Processing Complete!")
        print(f"    - Output Folder:  {out_dir.resolve()}")
        print(f"    - Text File:      {txt_output_path.name}")
        print(f"    - JSON Schema:    {json_output_path.name}")
        print(f"    - Cropped Figures: {pipeline.figures_dir.resolve()}")
