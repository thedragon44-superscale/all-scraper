import os
import json
from pathlib import Path
from parser.extract_parse import ExtractParseEngine

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


def process_pdf_to_structured_data(target_path: str):
    """Orchestrates document selection, rendering, and decoupled parsing output."""
    target = Path(target_path)
    if not target.exists():
        print(f"[!] Target path not found: {target_path}")
        return

    folder_name = target.stem if target.is_file() else target.name
    
    try:
        custom_name = input(f"Enter custom folder name for parsed output [default: {folder_name}]: ").strip()
        if custom_name:
            folder_name = custom_name
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation cancelled.")
        return

    # Strictly structured output path
    out_dir = Path("data") / "parsed_data" / folder_name
    img_dir = out_dir / "images"
    
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Initializing processor for '{folder_name}' -> Output: {out_dir.resolve()}")

    page_images = []

    if target.is_dir():
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        page_images = sorted([p for p in target.iterdir() if p.suffix.lower() in image_extensions])
        
        if not page_images:
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
        print(f"[*] Rendering PDF pages to images...")
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

    # Call the decoupled extraction and parsing engine
    engine = ExtractParseEngine()
    result = engine.process_pages(page_images, document_name=folder_name, image_output_dir=img_dir)

    # Save exact required output files directly in the source-named folder
    txt_output_path = out_dir / "text.txt"
    txt_output_path.write_text(result["full_text"], encoding="utf-8")

    json_output_path = out_dir / "json_schema.json"
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(result["structured_schema"], f, indent=2, ensure_ascii=False)

    print(f"\n[+] Processing Complete!")
    print(f"    - Output Folder:  {out_dir.resolve()}")
    print(f"    - Images Subfolder: {img_dir.resolve()}")
    print(f"    - Text File:      {txt_output_path.name}")
    print(f"    - JSON Schema:    {json_output_path.name}")
