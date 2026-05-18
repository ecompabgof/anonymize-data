"""Image handler: pytesseract OCR + Presidio anonymization.

Supports JPG/PNG/WEBP/BMP/TIFF/GIF natively via Pillow.
HEIC/AVIF require pillow-heif registered.
"""
import os
import sys
from pathlib import Path
import pytesseract
from PIL import Image

# Register HEIC/AVIF if pillow-heif available
try:
    from pillow_heif import register_heif_opener, register_avif_opener
    register_heif_opener()
    try:
        register_avif_opener()
    except Exception:
        pass
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from presidio_helper import anonymize_text


def anonymize(path, output=None, template=None):
    img = Image.open(path)
    # Tesseract works best with RGB
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    text = pytesseract.image_to_string(img, lang='fra+eng')
    anon = anonymize_text(text)

    if output:
        out_path = output if output.endswith(('.txt', '.md')) else output + '.txt'
        Path(out_path).write_text(anon, encoding='utf-8')
        return out_path
    return anon
