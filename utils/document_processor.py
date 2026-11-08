import os
import json
from pathlib import Path
from parser.extract_parse.ocr_engine import OCREngine
from parser.extract_parse.text_analyzer import TextAnalyzer
from parser.extract_parse.schema_mapper import SchemaMapper
from parser.extract_parse.layout_cropper import LayoutCropper

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

def process_pdf_to_structured_data(target_path: str):
    """
    Processes a selected folder (e.g., pdf/emv_book2 containing pre-extracted page images) 
    or a master PDF file using the advanced OCR, Layout, NLP, and Schema Mapping pipeline.
    """
    target = Path(target_path)
    if not target.exists():
        print(f"[!] Target path not found: {target_path}")
        return

    folder_name = target.stem if target.is_file() else target.name
    
    # Prompt for custom output folder name override
    try:
        custom_name = input(f"Enter custom folder name for parsed output [default: {folder_name}]: ").strip()
        if custom_name:
            folder_name = custom_name
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation cancelled.")
        return

    out_dir = Path("data") / "parsed_data" / folder_name
    img_dir = out_dir / "images"
    text_dir = out_dir / "text"
    
    out_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Initializing advanced pipeline for '{folder_name}' -> Output: {out_dir.resolve()}")

    ocr_engine = OCREngine()
    text_analyzer = TextAnalyzer()
    cropper = LayoutCropper(img_dir)

    page_images = []

    if target.is_dir():
        # Gather pre-existing page images from directory (e.g., PNGs, JPEGs)
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        page_images = sorted([p for p in target.iterdir() if p.suffix.lower() in image_extensions])
        
        if not page_images:
            # Check if directory contains a PDF file inside
            sub_pdfs = list(target.glob("*.pdf"))
            if sub_pdfs and PYMUPDF_AVAILABLE:
                print(f"[*] Found PDF inside directory, rendering pages to images...")
                doc = fitz.open(str(sub_pdfs[0]))
                for idx, page in enumerate(doc, 1):
                    pix = page.get_pixmap()
                    img_path = img_dir / f"page_{idx:03d}.png"
                    pix.save(str(img_path))
                    page_images.append(img_path)
    elif target.is_file() and target.suffix.lower() == ".pdf" and PYMUPDF_AVAILABLE:
        print(f"[*] Rendering PDF pages to images for advanced parsing...")
        doc = fitz.open(str(target))
        for idx, page in enumerate(doc, 1):
            pix = page.get_pixmap()
            img_path = img_dir / f"page_{idx:03d}.png"
            pix.save(str(img_path))
            page_images.append(img_path)

    total_pages = len(page_images)
    if total_pages == 0:
        print(f"[!] No valid page images or documents found in {target_path}")
        return

    schema_mapper = SchemaMapper(document_name=folder_name, total_pages=total_pages)
    full_text_accumulator = []

    for page_idx, img_path in enumerate(page_images, 1):
        print(f"[*] Processing page {page_idx}/{total_pages} via OCR & NLP...")
        
        # 1. OCR Data extraction (bounding boxes, text blocks, confidence)
        try:
            ocr_result = ocr_engine.extract_page_data(img_path)
            dimensions = ocr_result["page_dimensions"]
            text_blocks = ocr_result["text_blocks"]
        except Exception as e:
            print(f"    [!] OCR Error on page {page_idx}: {e}")
            dimensions = {"width": 1280, "height": 1024}
            text_blocks = []

        # Compile page text for raw text output
        page_text = " ".join([b["text_content"] for b in text_blocks])
        full_text_accumulator.append(f"--- PAGE {page_idx} ---\n{page_text}")

        # 2. Semantic NLP analysis (topics, key concepts, entities, summaries, intent)
        analysis_meta = text_analyzer.analyze_page(text_blocks)

        # 3. Add to Schema Mapper
        schema_mapper.add_page_data(
            page_number=page_idx,
            page_dimensions=dimensions,
            text_blocks=text_blocks,
            figure_blocks=[],  
            analysis_metadata=analysis_meta
        )

    # Save Unified Text Document
    txt_output_path = text_dir / f"{folder_name}_full.txt"
    txt_output_path.write_text("\n\n".join(full_text_accumulator), encoding="utf-8")

    # Save Validated Structured JSON Schema
    json_output_path = out_dir / f"{folder_name}_structured.json"
    schema_mapper.save_json(json_output_path)

    print(f"\n[+] Advanced Pipeline Complete!")
    print(f"    - Output Directory:      {out_dir.resolve()}")
    print(f"    - Unified Text Output:   {txt_output_path.name}")
    print(f"    - Structured JSON Map:   {json_output_path.name}")
