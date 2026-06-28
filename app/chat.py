CHAT_SYSTEM = """你是一个懂当前 galgame 剧情的伴读。根据提供的【近期台词】【笔记】【人物表】回答用户问题。
如果信息不足，老实说"目前没记录到"，不要编造。
回答后如果得出了值得记录的结论，在末尾另起一行用 `INSIGHT: <结论>` 标注。"""

def build_chat_context(store, question, recent_window=200):
    recent = "\n".join(store.read_recent_lines(recent_window))
    notes = store.read_notes() or "(无笔记)"
    chars = store.read_characters() or "(无人物表)"
    user = (
        f"【近期台词】\n{recent}\n\n"
        f"【笔记】\n{notes}\n\n"
        f"【人物表】\n{chars}\n\n"
        f"【我的问题】\n{question}"
    )
    return [
        {"role": "system", "content": CHAT_SYSTEM},
        {"role": "user", "content": user},
    ]

def extract_insight(answer):
    for line in answer.splitlines():
        s = line.strip()
        if s.startswith("INSIGHT:"):
            return s.split("INSIGHT:", 1)[1].strip()
    return None

class ChatEngine:
    def __init__(self, store, llm, model, recent_window=200):
        self.store = store
        self.llm = llm
        self.model = model
        self.recent_window = recent_window

    def answer(self, question) -> str:
        msgs = build_chat_context(self.store, question, self.recent_window)
        reply = self.llm.chat(msgs, self.model, temperature=0.5)
        insight = extract_insight(reply)
        if insight:
            with open(self.store.notes_path, "a", encoding="utf-8") as f:
                f.write(f"\n- 讨论洞察: {insight}\n")
        return reply
