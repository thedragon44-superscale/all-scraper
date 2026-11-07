import os
from pathlib import Path
from PIL import Image

def stitch_images_to_pdf():
    data_dir = Path("data")
    if not data_dir.exists():
        print("[!] The 'data/' directory does not exist yet.")
        return

    # Scan for subdirectories inside data/
    subdirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name != "pdf"]
    
    if not subdirs:
        print("[!] No document subdirectories found inside 'data/'.")
        return

    print("\n========================================")
    print("         SELECT SOURCE DIRECTORY        ")
    print("========================================")
    for idx, subdir in enumerate(subdirs, 1):
        # Count potential page images inside
        image_count = len(list(subdir.glob("page_*.png"))) + len(list(subdir.glob("*.jpg")))
        print(f"  [{idx}] {subdir.name}/ ({image_count} images found)")
    print("----------------------------------------")

    try:
        choice = input("Select directory number: ").strip()
        if not choice.isdigit():
            print("[!] Invalid input. Aborting.")
            return
        
        selected_idx = int(choice) - 1
        if not (0 <= selected_idx < len(subdirs)):
            print("[!] Selection out of range. Aborting.")
            return
            
        source_dir = subdirs[selected_idx]
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation cancelled.")
        return

    # Gather and sort image files numerically/alphabetically
    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    image_files = sorted(
        [f for f in source_dir.iterdir() if f.suffix.lower() in image_extensions],
        key=lambda x: x.name
    )

    if not image_files:
        print(f"[!] No valid image files found in '{source_dir.name}/'.")
        return

    # Prompt for custom PDF name
    try:
        pdf_name = input("Enter name for the output PDF (e.g., EMV_Book_1): ").strip()
        if not pdf_name:
            pdf_name = "document"
        if not pdf_name.endswith(".pdf"):
            pdf_name += ".pdf"
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Operation cancelled.")
        return

    output_pdf_dir = data_dir / "pdf"
    output_pdf_dir.mkdir(parents=True, exist_ok=True)
    output_pdf_path = output_pdf_dir / pdf_name

    print(f"[*] Compiling {len(image_files)} pages into PDF...")

    try:
        images = []
        for img_path in image_files:
            img = Image.open(img_path)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)

        if images:
            images[0].save(
                output_pdf_path,
                "PDF",
                save_all=True,
                append_images=images[1:]
            )
            print(f"[+] Successfully generated PDF: {output_pdf_path.resolve()}")
        else:
            print("[!] No images could be loaded for stitching.")
            
    except Exception as e:
        print(f"[!] Error during PDF compilation: {e}")

if __name__ == "__main__":
    stitch_images_to_pdf()
