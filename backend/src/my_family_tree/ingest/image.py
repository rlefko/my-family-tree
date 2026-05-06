"""Image OCR via Tesseract. Vision-LLM fallback lives in `vision_fallback.py`
and is gated by per-tree daily spend caps."""

from __future__ import annotations

import io
from dataclasses import dataclass

import pytesseract
from PIL import Image


@dataclass(slots=True)
class OCRResult:
    text: str
    avg_confidence: float
    engine: str = "tesseract"


def ocr_image(data: bytes, *, lang: str = "eng", psm: int = 4) -> OCRResult:
    """Run Tesseract on image bytes. Returns text and a coarse average
    confidence (0..100). The caller decides whether to fall back to a
    vision LLM if confidence is too low."""
    image = Image.open(io.BytesIO(data))
    config = f"--psm {psm}"
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    data_dict = pytesseract.image_to_data(
        image, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )
    confs = [
        int(c) for c in data_dict.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0
    ]
    avg_conf = (sum(confs) / len(confs)) if confs else 0.0
    return OCRResult(text=text, avg_confidence=avg_conf, engine="tesseract")
