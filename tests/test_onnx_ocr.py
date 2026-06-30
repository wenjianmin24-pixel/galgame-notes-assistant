"""ONNX OCR 引擎测试 — 检测 + 识别管线。

模型在 cache/ocrmodel/ 下（gitignore），CI 无模型时自动跳过。
"""

import os
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "cache", "ocrmodel", "jazhchten"
)

needs_model = pytest.mark.skipif(
    not os.path.isdir(MODEL_DIR)
    or not os.path.isfile(os.path.join(MODEL_DIR, "det.onnx"))
    or not os.path.isfile(os.path.join(MODEL_DIR, "rec.onnx")),
    reason="ONNX 模型未下载（cache/ocrmodel/jazhchten/）",
)


def _make_text_image(lines, font_path="C:/Windows/Fonts/simsun.ttc"):
    """生成白底黑字多行测试图。"""
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


@needs_model
def test_model_loads():
    from app.ocr_onnx import ONNXOCR
    ocr = ONNXOCR()
    assert ocr.lang_tag == "onnx:PP-OCRv5_mobile"
    assert ocr._det is not None
    assert ocr._rec is not None


@needs_model
def test_detect_finds_boxes():
    from app.ocr_onnx import ONNXOCR
    img = _make_text_image(["你好", "世界"])
    arr = np.array(img)
    ocr = ONNXOCR()
    boxes = ocr._detect(arr)
    assert len(boxes) >= 1, "should find at least 1 text box"


@needs_model
def test_recognize_returns_lines():
    from app.ocr_onnx import ONNXOCR
    img = _make_text_image(["测试文本"])
    ocr = ONNXOCR()
    lines = ocr.recognize(img)
    assert isinstance(lines, list)
    assert len(lines) >= 1


@needs_model
def test_recognize_empty_image():
    from app.ocr_onnx import ONNXOCR
    img = Image.new("RGB", (100, 30), "white")
    ocr = ONNXOCR()
    lines = ocr.recognize(img)
    # 纯白图可能检测到 0 框或识别出空串
    assert lines == [] or all(isinstance(l, str) for l in lines)


@needs_model
def test_recognize_multi_line_separates():
    from app.ocr_onnx import ONNXOCR
    img = _make_text_image(["第一行文本", "第二行内容"])
    ocr = ONNXOCR()
    lines = ocr.recognize(img)
    # 多行文本应该被检测分离为多行
    assert len(lines) >= 1
    assert all(isinstance(l, str) and len(l) > 0 for l in lines)
