import os
import json
import re
from pathlib import Path
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

def process_pdf_to_structured_data(pdf_path: str):
    """
    Processes a master PDF into:
      1. A unified text file (.txt)
      2. Extracted image assets (.png)
      3. A granular hierarchical JSON breakdown (Page -> Sentence -> Word)
      Stored inside data/parsed_data/<custom_folder_name>/
    """
    if not PYMUPDF_AVAILABLE:
        print("[!] PyMuPDF is required for advanced text and image parsing. Run: pip install PyMuPDF")
        return

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"[!] PDF file not found: {pdf_path}")
        return

    default_name = pdf_file.stem
    
    # Prompt for custom output folder name
    try:
        custom_name = input(f"Enter custom folder name for parsed output [default: {default_name}]: ").strip()
        if not custom_name:
            folder_name = default_name
        else:
            folder_name = custom_name
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation cancelled.")
        return

    # Base path locked to data/parsed_data/
    out_dir = Path("data") / "parsed_data" / folder_name
    img_dir = out_dir / "images"
    text_dir = out_dir / "text"
    
    img_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Processing document '{default_name}' into '{out_dir.resolve()}'...")

    doc = fitz.open(str(pdf_file))
    
    full_text_accumulator = []
    structured_data = {
        "document_name": default_name,
        "total_pages": len(doc),
        "pages": []
    }
    
    total_images_extracted = 0

    for page_idx, page in enumerate(doc, 1):
        page_data = {
            "page_number": page_idx,
            "sentences": []
        }
        
        # 1. Extract Page Text
        page_text = page.get_text("text")
        full_text_accumulator.append(f"--- PAGE {page_idx} ---\n{page_text}")

        # Clean and split text into sentences using basic regex boundary rules
        raw_sentences = re.split(r'(?<=[.!?])\s+', page_text.strip())
        
        sentence_id = 1
        for sent in raw_sentences:
            clean_sent = sent.replace("\n", " ").strip()
            if not clean_sent:
                continue
                
            # Break sentence down word-by-word
            raw_words = re.findall(r'\b\w+\b', clean_sent)
            
            sentence_obj = {
                "sentence_id": sentence_id,
                "text": clean_sent,
                "word_count": len(raw_words),
                "words": [{"position": w_idx, "word": w} for w_idx, w in enumerate(raw_words, 1)]
            }
            page_data["sentences"].append(sentence_obj)
            sentence_id += 1

        structured_data["pages"].append(page_data)

        # 2. Extract Embedded Images / Page Visuals
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list, 1):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            image_filename = f"page_{page_idx:03d}_img_{img_index:02d}.png"
            image_path = img_dir / image_filename
            
            # Save image cleanly as PNG
            if image_ext != "png":
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(image_bytes))
                image.save(str(image_path), "PNG")
            else:
                image_path.write_bytes(image_bytes)
                
            total_images_extracted += 1

    # Write Unified Text Document
    txt_output_path = text_dir / f"{folder_name}_full.txt"
    txt_output_path.write_text("\n\n".join(full_text_accumulator), encoding="utf-8")

    # Write Granular Structural JSON Breakdown
    json_output_path = out_dir / f"{folder_name}_structured.json"
    json_output_path.write_text(json.dumps(structured_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[+] Reformatting Complete!")
    print(f"    - Output Directory:      {out_dir.resolve()}")
    print(f"    - Unified Text Output:   {txt_output_path.name}")
    print(f"    - Extracted Images:      images/ ({total_images_extracted} files)")
    print(f"    - Structured JSON Map:   {json_output_path.name}")
