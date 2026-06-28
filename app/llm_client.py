from openai import OpenAI

class LLMClient:
    """OpenAI 兼容接口的薄封装。"""
    def __init__(self, base_url: str, api_key: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def chat(self, messages, model, temperature=0.3) -> str:
        resp = self.client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content
