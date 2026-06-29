"""AI 视觉 OCR 后端 — 把截图发给视觉大模型提取文字。

依赖：与 LLMClient 相同（openai）。需要一个支持图像输入的视觉模型
（如 GPT-4o / Qwen-VL / Gemini）。
"""

from app.config import model_config
from app.llm_client import LLMClient

_PROMPT = (
    "提取图中所有文字，按阅读顺序原样输出，每行一条。"
    "只输出识别到的文字内容，不要解释、不要加引号、不要标注坐标。"
    "如果图中没有文字，输出一个空行。"
)


class AIVisionOCR:
    """调视觉 LLM 做 OCR。recognize(pil) -> list[str]。"""

    def __init__(self):
        base, key, model = model_config("ocr_vision")
        if not key:
            raise RuntimeError(
                "AI 视觉 OCR 未配置 API Key（在 OCR 设置里填第 4 个模型块）"
            )
        self._client = LLMClient(base, key)
        self._model = model
        self.lang_tag = f"ai:{model}"

    def recognize(self, pil_image) -> list[str]:
        text = self._client.vision_chat(self._model, _PROMPT, pil_image)
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
