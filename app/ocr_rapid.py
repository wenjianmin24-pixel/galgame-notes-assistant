"""RapidOCR 引擎封装 — PP-OCRv4 检测 + 识别，ONNX 推理。

比旧版 PP-OCRv5_mobile 显著优势：
  - v4 server 级模型，中日文识别率远超 mobile
  - 内置文本检测+逐行识别+行排序，一条调用搞定
  - 无须手动下载模型，首次自动缓存

依赖：pip install rapidocr-onnxruntime（已依赖 onnxruntime, numpy, opencv, Pillow）
"""

from rapidocr_onnxruntime import RapidOCR


class RapidOCREngine:
    """RapidOCR 薄封装。recognize(pil) -> list[str]。"""

    def __init__(self):
        self._ocr = RapidOCR()
        self.lang_tag = "rapid:PP-OCRv4"

    def recognize(self, pil_image) -> list[str]:
        import numpy as np
        arr = np.array(pil_image.convert("RGB"))
        result, _ = self._ocr(arr)
        if not result:
            return []
        lines = []
        for _box, text, _score in result:
            text = text.strip() if text else ""
            if text:
                lines.append(text)
        return lines
