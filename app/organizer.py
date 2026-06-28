ORGANIZE_SYSTEM = """你是一个 galgame/视觉小说的笔记整理助手。
把新台词增量合并进现有笔记。笔记结构：人物、场景/章节、关键事件、伏笔、选项分支、讨论洞察。
重要性标准：新人物首次出场 / 伏笔暗示 / 剧情转折 / 关键选项 → 记；日常寒暄 / 重复 / 纯环境描写 → 不记。
不要删除用户已写的内容。输出完整的合并后笔记全文（Markdown）。"""

def build_organize_prompt(new_lines, existing_notes, characters):
    user = (
        f"【现有笔记】\n{existing_notes or '(空)'}\n\n"
        f"【现有人物表】\n{characters or '(空)'}\n\n"
        f"【新台词】\n" + "\n".join(new_lines)
    )
    return [
        {"role": "system", "content": ORGANIZE_SYSTEM},
        {"role": "user", "content": user},
    ]

class Organizer:
    def __init__(self, store, llm, model, batch_size=20, interval_sec=180):
        self.store = store
        self.llm = llm
        self.model = model
        self.batch_size = batch_size
        self.interval_sec = interval_sec
        self._pending: list[str] = []

    def feed(self, line: str):
        self._pending.append(line)

    def should_trigger(self) -> bool:
        return len(self._pending) >= self.batch_size

    def organize(self) -> bool:
        if not self._pending:
            return False
        new_lines = list(self._pending)
        self._pending.clear()
        msgs = build_organize_prompt(
            new_lines, self.store.read_notes(), self.store.read_characters()
        )
        notes = self.llm.chat(msgs, self.model, temperature=0.2)
        self.store.write_notes(notes)
        return True
