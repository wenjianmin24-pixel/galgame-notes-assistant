from app.llm_client import LLMClient

def test_client_calls_openai_and_returns_content(monkeypatch):
    captured = {}
    class FakeChoice:
        class message: content = "你好"
    class FakeResp:
        choices = [FakeChoice()]
    class FakeCompletions:
        def create(self, **kw):
            captured["kw"] = kw
            return FakeResp()
    class FakeChat:
        completions = FakeCompletions()
    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            self.chat = FakeChat()
    monkeypatch.setattr("app.llm_client.OpenAI", FakeOpenAI)

    c = LLMClient("https://example.com", "sk-test")
    out = c.chat([{"role":"user","content":"hi"}], model="m1", temperature=0.7)
    assert out == "你好"
    assert captured["base_url"] == "https://example.com"
    assert captured["kw"]["model"] == "m1"
    assert captured["kw"]["temperature"] == 0.7
