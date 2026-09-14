# OCR와 perceptual hash 기반 이미지 재유포 탐지

from io import BytesIO
from PIL import Image

def analyze_image(payload: bytes) -> dict:
    image = Image.open(BytesIO(payload)).convert("L")
    tiny = image.resize((8, 8)); pixels = list(tiny.getdata()); mean = sum(pixels) / len(pixels)
    perceptual_hash = f"{sum((1 << index) for index, value in enumerate(pixels) if value >= mean):016x}"
    text, ocr_available = "", False
    try:
        import pytesseract
        from pathlib import Path
        executable = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if executable.exists(): pytesseract.pytesseract.tesseract_cmd = str(executable)
        text = pytesseract.image_to_string(image, lang="kor+eng").strip(); ocr_available = True
    except Exception: pass
    return {"width": image.width, "height": image.height, "ocr_text": text, "ocr_available": ocr_available, "perceptual_hash": perceptual_hash}
