class FakeLLM:
    """测试用 LLM 替身，记录调用、返回预设响应。"""
    def __init__(self, response="ok"):
        self.response = response
        self.calls = []

    def chat(self, messages, model, temperature=0.3):
        self.calls.append((messages, model, temperature))
        return self.response
