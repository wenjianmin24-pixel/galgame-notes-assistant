import base64
import io

from openai import OpenAI

# 按 (base_url, api_key) 缓存 OpenAI 客户端，避免重复构造
_CLIENTS: dict[tuple[str, str], OpenAI] = {}


def _get_client(base_url: str, api_key: str) -> OpenAI:
    k = (base_url, api_key)
    c = _CLIENTS.get(k)
    if c is None:
        c = OpenAI(base_url=base_url, api_key=api_key)
        _CLIENTS[k] = c
    return c


class LLMClient:
    """OpenAI 兼容接口的薄封装。"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.client = _get_client(base_url, api_key)

    def chat(self, messages, model, temperature=0.3) -> str:
        resp = self.client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content

    def embed(self, text: str, model: str) -> list[float]:
        """单文本 embedding。返回浮点向量。"""
        resp = self.client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str], model: str) -> list[list[float]]:
        """批量 embedding。"""
        resp = self.client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    # ── 配置类辅助 ────────────────────────────────────────

    def list_models(self) -> list[str]:
        """GET /models，返回模型 id 列表。兼容 base_url 带/不带 /v1。"""
        try:
            resp = self.client.models.list()
            return sorted(m.id for m in resp.data)
        except Exception as e:
            raise RuntimeError(f"{type(e).__name__}: {e}")

    def test_chat(self, model: str) -> tuple[bool, str]:
        """发一条 ping 消息验证端点+key+模型可用。返回 (ok, msg)。"""
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4,
                temperature=0,
            )
            reply = resp.choices[0].message.content or ""
            return True, f"OK · {reply[:40]}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def vision_chat(self, model: str, prompt: str, pil_image,
                    temperature: float = 0.1) -> str:
        """发一帧图像 + 文字提示，返回模型文本。用于 AI 视觉 OCR。"""
        buf = io.BytesIO()
        pil_image.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        data_url = f"data:image/png;base64,{b64}"
        resp = self.client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        )
        return resp.choices[0].message.content or ""
