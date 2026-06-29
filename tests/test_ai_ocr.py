"""AIVisionOCR 按行切分测试。直接 patch model_config 避免 .env 依赖。"""
from app import ocr_ai


class FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def vision_chat(self, model, prompt, pil_image, temperature=0.1):
        self.calls.append((model, prompt))
        return self._resp


def test_recognize_splits_lines(monkeypatch):
    fake = FakeClient("第一行\n第二行\n\n第三行")
    monkeypatch.setattr(ocr_ai, "model_config", lambda r: ("https://x", "k2", "vision-m"))
    monkeypatch.setattr(ocr_ai, "LLMClient", lambda b, k: fake)
    eng = ocr_ai.AIVisionOCR()
    lines = eng.recognize(None)
    assert lines == ["第一行", "第二行", "第三行"]
    assert eng.lang_tag == "ai:vision-m"
    assert fake.calls[0][0] == "vision-m"


def test_recognize_no_text(monkeypatch):
    fake = FakeClient("")
    monkeypatch.setattr(ocr_ai, "model_config", lambda r: ("https://x", "k2", "m"))
    monkeypatch.setattr(ocr_ai, "LLMClient", lambda b, k: fake)
    eng = ocr_ai.AIVisionOCR()
    assert eng.recognize(None) == []


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(ocr_ai, "model_config", lambda r: ("https://x", "", "m"))
    import pytest
    with pytest.raises(RuntimeError):
        ocr_ai.AIVisionOCR()
