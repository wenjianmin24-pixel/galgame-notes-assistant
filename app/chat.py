CHAT_SYSTEM = """你是一个懂当前 galgame 剧情的伴读。根据提供的上下文回答用户问题：

上下文中包含：
- 【相关历史台词】（通过语义搜索从全量台本中召回，可能与问题相关）
- 【近期台词】（最近发生的对话）
- 【笔记】（AI 整理的结构化剧情笔记）
- 【人物表】（已知角色信息）

优先信任【相关历史台词】和【笔记】中的信息，它们来自游戏原文。
如果信息不足，老实说"目前没记录到这段"，不要编造。
回答后如果得出了值得记录的结论，在末尾另起一行用 `INSIGHT: <结论>` 标注。"""


def build_chat_context(store, question, recent_window=200, index=None, top_k=5):
    parts = []

    # 向量检索：从全量台本中找回相关历史台词
    if index is not None and not index.is_empty():
        transcript = store.read_transcript()
        index.ensure_synced(transcript)
        hits = index.search(question, top_k=top_k)
        if hits:
            parts.append("【相关历史台词】（以下为全量台本中与你问题最相关的片段）\n"
                         + "\n---\n".join(hits))

    recent = "\n".join(store.read_recent_lines(recent_window))
    parts.append(f"【近期台词】\n{recent}")

    notes = store.read_notes() or "(无笔记)"
    parts.append(f"【笔记】\n{notes}")

    chars = store.read_characters() or "(无人物表)"
    parts.append(f"【人物表】\n{chars}")

    parts.append(f"【我的问题】\n{question}")

    user = "\n\n".join(parts)
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
    def __init__(self, store, llm, model, recent_window=200,
                 index=None, top_k=5):
        self.store = store
        self.llm = llm
        self.model = model
        self.recent_window = recent_window
        self.index = index
        self.top_k = top_k

    def reconfigure(self, llm, model):
        """热更新 LLM 客户端和模型。"""
        self.llm = llm
        self.model = model

    def answer(self, question) -> str:
        msgs = build_chat_context(
            self.store, question, self.recent_window,
            index=self.index, top_k=self.top_k,
        )
        reply = self.llm.chat(msgs, self.model, temperature=0.5)
        insight = extract_insight(reply)
        if insight:
            with open(self.store.notes_path, "a", encoding="utf-8") as f:
                f.write(f"\n- 讨论洞察: {insight}\n")
        return reply
