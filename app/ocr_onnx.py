"""ONNX OCR 引擎 — DBNet 文本检测 + CRNN 识别 + CTC 解码。

模型来源：LunaTranslator PP-OCRv5_mobile（中日英繁）。
依赖：onnxruntime, numpy, Pillow, shapely, pyclipper（均已安装）。
"""

import os
import numpy as np
from PIL import Image

# ── 模型路径 ────────────────────────────────────────────────

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "cache", "ocrmodel", "jazhchten"
)


class ONNXOCR:
    """PP-OCRv5 ONNX 引擎。recognize(pil) -> list[str]。"""

    def __init__(self, model_dir=_MODEL_DIR, max_side=960):
        import onnxruntime as ort
        self.max_side = max_side
        # Detection
        self._det = ort.InferenceSession(
            os.path.join(model_dir, "det.onnx"),
            providers=["CPUExecutionProvider"],
        )
        # Recognition
        self._rec = ort.InferenceSession(
            os.path.join(model_dir, "rec.onnx"),
            providers=["CPUExecutionProvider"],
        )
        # Character dictionary
        with open(os.path.join(model_dir, "dict.txt"), "r", encoding="utf-8") as f:
            self._chars = [l.strip().split()[0] for l in f if l.strip()]
        self.lang_tag = "onnx:PP-OCRv5_mobile"

    def recognize(self, pil_image) -> list[str]:
        """检测文本行位置 → 逐行识别 → 返回行列表。

        与旧版不同：不再把整张框选图当单行送 CTC（那在多行/多元素
        区域上产乱码），而是先跑 DBNet 检测出每个文本块，排序后
        逐块裁剪送 CRNN 识别。"""
        arr = np.array(pil_image.convert("RGB"), dtype=np.uint8)

        # ── 主路径：检测 → 排序 → 逐行识别 ──
        try:
            boxes = self._detect(arr)
            if boxes:
                boxes = self._sort_boxes(boxes)
                lines = []
                for box in boxes:
                    text = self._recognize_box(arr, box)
                    text = text.strip() if text else ""
                    if text:
                        lines.append(text)
                if lines:
                    return lines
        except Exception:
            # 检测异常（极少见，如 opencv 崩溃）→ 走兜底
            pass

        # ── 兜底：图像极窄（单行文本，检测模型可能漏掉）──
        h, w = arr.shape[:2]
        if h < 60 and h / max(w, 1) < 0.15:
            text = self._ctc_recognize(arr)
            if text and text.strip():
                return [text.strip()]

        return []

    # ── 检测 ───────────────────────────────────────────────

    def _detect(self, img: np.ndarray) -> list:
        h, w = img.shape[:2]
        ratio = min(self.max_side / max(h, w), 1.0)
        nh, nw = int(h * ratio), int(w * ratio)
        # 对齐到 32 倍数（检测模型要求）
        nh = max(32, (nh + 31) // 32 * 32)
        nw = max(32, (nw + 31) // 32 * 32)
        resized = np.array(Image.fromarray(img).resize((nw, nh), Image.BILINEAR))
        # 归一化（均值 0.5，方差 0.5，即 [0,1] → [-1,1]）
        inp = (resized.astype(np.float32) / 255.0 - 0.5) / 0.5
        inp = np.transpose(inp, (2, 0, 1))[None]  # (1,3,H,W)
        # 推理
        output = self._det.run(None, {"x": inp})[0]  # (1,1,H',W')
        prob = 1 / (1 + np.exp(-output[0, 0]))  # sigmoid
        # 二值化（PP-OCRv5 ONNX 输出偏压缩，阈值需 >0.5）
        mask = (prob > 0.55).astype(np.uint8)
        # 用 OpenCV 找连通域和轮廓
        try:
            import cv2
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except ImportError:
            # 纯 Python 回退（基本不会有此情况，opencv 已装）
            return []
        boxes = []
        for cnt in contours:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect).astype(np.int32)
            # 映射回原图坐标
            box = (box.astype(np.float32) / ratio).astype(np.int32)
            x1, y1 = box[:, 0].min(), box[:, 1].min()
            x2, y2 = box[:, 0].max(), box[:, 1].max()
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            boxes.append((x1, y1, x2, y2))
        return boxes

    def _sort_boxes(self, boxes):
        """从上到下行，同行内从左到右排序。"""
        boxes = sorted(boxes, key=lambda b: b[1])  # 按 y 排
        rows = []
        for box in boxes:
            if not rows or box[1] > rows[-1][-1][3]:
                rows.append([])
            rows[-1].append(box)
        for row in rows:
            row.sort(key=lambda b: b[0])
        return [b for row in rows for b in row]

    # ── 识别 ───────────────────────────────────────────────

    def _recognize_box(self, img: np.ndarray, box: tuple) -> str:
        x1, y1, x2, y2 = box
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return ""
        crop = img[y1:y2, x1:x2]
        return self._ctc_recognize(crop)

    def _ctc_recognize(self, crop: np.ndarray) -> str:
        """对裁剪的文字区域做 CRNN + CTC 解码。"""
        h, w = crop.shape[:2]
        if h < 4 or w < 4:
            return ""
        # 保持高宽比，高度缩到 48
        ratio = 48.0 / h
        nw = max(8, int(w * ratio))
        resized = np.array(Image.fromarray(crop).resize((nw, 48), Image.BILINEAR))
        # 归一化（和检测一致）
        inp = (resized.astype(np.float32) / 255.0 - 0.5) / 0.5
        inp = np.transpose(inp, (2, 0, 1))[None]  # (1,3,48,W)
        output = self._rec.run(None, {"x": inp})[0]  # (1,T,18385)
        prob = output[0]  # (T, num_classes)
        # CTC 贪心解码
        # PP-OCRv5 ONNX: idx 0=blank, idx 1=填充, idx i→chars[i-2]
        _CTC_OFFSET = 2
        prev = -1
        chars = []
        for t in range(prob.shape[0]):
            idx = int(np.argmax(prob[t]))
            if idx != prev and idx >= _CTC_OFFSET:
                chars.append(self._chars[idx - _CTC_OFFSET])
            prev = idx
        return "".join(chars)
