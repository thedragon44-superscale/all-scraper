from pathlib import Path
from typing import Any, Dict, List, Tuple
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

    def extract_region_text(
        self, image_path: str | Path, bbox: Tuple[int, int, int, int]
    ) -> Dict[str, Any]:
        """Runs OCR on a specific cropped sub-region (e.g., inside a diagram or figure)
        to extract internal labels and structured text blocks.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        image = Image.open(path)
        x0, y0, x1, y1 = bbox
        width, height = image.size

        # Clamp box to image dimensions
        x0 = max(0, min(x0, width))
        y0 = max(0, min(y0, height))
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))

        if x0 >= x1 or y0 >= y1:
            return {"text_blocks": [], "full_text": ""}

        cropped_image = image.crop((x0, y0, x1, y1))

        ocr_data = pytesseract.image_to_data(
            cropped_image, lang=self.default_lang, output_type=pytesseract.Output.DICT
        )

        text_blocks: List[Dict[str, Any]] = []
        n_boxes = len(ocr_data["text"])

        for i in range(n_boxes):
            text = ocr_data["text"][i].strip()
            conf = int(ocr_data["conf"][i])

            if text and conf > 0:
                bx0 = ocr_data["left"][i] + x0
                by0 = ocr_data["top"][i] + y0
                bw = ocr_data["width"][i]
                bh = ocr_data["height"][i]
                bx1 = bx0 + bw
                by1 = by0 + bh

                block_entry = {
                    "block_type": "sub_text",
                    "text_content": text,
                    "confidence": conf,
                    "spatial_coordinates": [bx0, by0, bx1, by1],
                    "block_id": f"sub_{ocr_data['block_num'][i]}_{ocr_data['par_num'][i]}_{ocr_data['line_num'][i]}_{i}",
                }
                text_blocks.append(block_entry)

        full_text = pytesseract.image_to_string(cropped_image, lang=self.default_lang).strip()

        return {
            "region_box": [x0, y0, x1, y1],
            "text_blocks": text_blocks,
            "full_text": full_text,
        }

    def extract_full_text(self, image_path: str | Path) -> str:
        """Convenience method to retrieve a plain-text transcription of an entire
        scanned page.
        """
        path = Path(image_path)
        image = Image.open(path)
        return pytesseract.image_to_string(image, lang=self.default_lang)
