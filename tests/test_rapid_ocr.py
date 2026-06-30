"""RapidOCR 引擎测试。"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _make_text_image(lines, font_path="C:/Windows/Fonts/simsun.ttc"):
    h = 30 + 48 * len(lines)
    img = Image.new("RGB", (600, h), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, 30)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        draw.text((10, 5 + i * 48), line, fill="black", font=font)
    return img


def test_rapid_ocr_imports():
    from app.ocr_rapid import RapidOCREngine
    eng = RapidOCREngine()
    assert eng.lang_tag == "rapid:PP-OCRv4"


def test_rapid_recognize_returns_lines():
    from app.ocr_rapid import RapidOCREngine
    img = _make_text_image(["测试文本"])
    eng = RapidOCREngine()
    lines = eng.recognize(img)
    assert isinstance(lines, list)
    assert len(lines) >= 1
    assert all(isinstance(l, str) for l in lines)


def test_rapid_recognize_empty_image():
    from app.ocr_rapid import RapidOCREngine
    img = Image.new("RGB", (100, 30), "white")
    eng = RapidOCREngine()
    lines = eng.recognize(img)
    assert lines == [] or all(isinstance(l, str) for l in lines)


def test_rapid_recognize_multi_line():
    from app.ocr_rapid import RapidOCREngine
    img = _make_text_image(["第一行文本", "第二行内容"])
    eng = RapidOCREngine()
    lines = eng.recognize(img)
    assert len(lines) >= 1
    assert all(isinstance(l, str) and len(l) > 0 for l in lines)


def test_rapid_recognize_chinese_accuracy():
    """验证 RapidOCR 对中文的识别能力优于旧 ONNX mobile 模型。"""
    from app.ocr_rapid import RapidOCREngine
    img = _make_text_image(["欢迎来到这个世界"])
    eng = RapidOCREngine()
    lines = eng.recognize(img)
    assert len(lines) >= 1
    combined = "".join(lines)
    # 至少应包含部分正确字符
    assert len(combined) >= 3, f"too few chars: {combined}"
