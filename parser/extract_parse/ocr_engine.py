from pathlib import Path
from typing import Any, Dict, List
from PIL import Image
import pytesseract


class OCREngine:

    def __init__(self, tesseract_cmd: str = None, default_lang: str = "eng"):
        """Initializes the OCR engine.

        Args:
            tesseract_cmd: Optional path to the tesseract executable if not in
              system PATH.
            default_lang: Language code for OCR transcription (default: 'eng').
        """
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self.default_lang = default_lang

    def extract_page_data(self, image_path: str | Path) -> Dict[str, Any]:
        """Processes a single scanned page image to extract text blocks,

        bounding boxes, and confidence scores using Tesseract data output.

        Args:
            image_path: Path to the scanned page image file.

        Returns:
            A dictionary containing page dimensions and a list of detected text
            blocks.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        image = Image.open(path)
        width, height = image.size

        # Extract detailed data including boxes, text, and confidence levels
        # image_to_data returns a dictionary of lists containing layout and text info
        ocr_data = pytesseract.image_to_data(
            image, lang=self.default_lang, output_type=pytesseract.Output.DICT
        )

        text_blocks: List[Dict[str, Any]] = []
        n_boxes = len(ocr_data["text"])

        for i in range(n_boxes):
            text = ocr_data["text"][i].strip()
            conf = int(ocr_data["conf"][i])

            # Filter out empty strings or low-confidence noise blocks (-1 means no text)
            if text and conf > 0:
                x0 = ocr_data["left"][i]
                y0 = ocr_data["top"][i]
                w = ocr_data["width"][i]
                h = ocr_data["height"][i]
                x1 = x0 + w
                y1 = y0 + h

                block_entry = {
                    "block_type": "text",
                    "text_content": text,
                    "confidence": conf,
                    "spatial_coordinates": [x0, y0, x1, y1],
                    "block_id": f"block_{ocr_data['block_num'][i]}_{ocr_data['par_num'][i]}_{ocr_data['line_num'][i]}_{i}",
                }
                text_blocks.append(block_entry)

        return {
            "image_path": str(path.resolve()),
            "page_dimensions": {"width": width, "height": height},
            "text_blocks": text_blocks,
        }

    def extract_full_text(self, image_path: str | Path) -> str:
        """Convenience method to retrieve a plain-text transcription of an entire

        scanned page.
        """
        path = Path(image_path)
        image = Image.open(path)
        return pytesseract.image_to_string(image, lang=self.default_lang)
