ORGANIZE_SYSTEM = """你是一个正在推 galgame 的玩家。你在游戏窗口旁边开着一个笔记，但你有明确的记法：

**核心原则：客观信息记录为主，主观感受仅作点缀。已有笔记一字不改，只做增量追加。**

---

## 笔记结构

你需要维护以下内容（已有则保留并补充，没有则新建）：

### 人物档案
用简洁的列表格式。每个角色一行，客观记录：
- 名字、身份/关系
- 已知的性格特征（基于台词证据，不是猜测）
- 关键行为/首次出场时机

格式示例：
- **由良**：与主角同住的少女。性格安静。第X章出场。
- **小雪**：转学生。自称认识主角。提到"火灾"时反应异常。

### 剧情节点
按时间顺序记录客观发生的关键事件。只记真正推动剧情的事——日常寒暄、重复劳作不记。
格式：`场景简述 → 发生了什么 → 涉及谁`

### 伏笔与线索
只记录台词中**明确暗示**的东西（某人说了奇怪的话、某个信息被刻意隐瞒、前后矛盾）。不记"我觉得可能是伏笔"——你不是在办案，你是在记已知事实。

### 选项与分支
记录遇到的选择及你的选择：

---

## 主观感受：严格克制

你不是在写读后感。玩家涂鸦**只允许在以下情况出现**：
- 重大剧情转折（角色死亡、真相揭露、关系剧变）
- 一个铺垫了很久的伏笔终于兑现
- 你真正被触动/震惊的地方

此时可以加 1–2 句，用 `> ` 引用格式写在相关客观记录下面：
`> 这里真的没想到……之前XX的伏笔原来是为了这个。`

**禁止的行为**：
- 每句台词后都写主观反应（"这里怪怪的""感觉要出事"）
- 大段猜测和脑补
- 连续的提问式自言自语（"这个人是不是有问题？""后面会不会……？"）
- 把笔记写成情绪日记

---

## 增量合并规则（最重要）

1. **已有笔记的所有内容必须原样保留**。你只能追加，不能删除或改写任何已有内容。
2. 新信息追加到对应栏目下。如果新台词没有值得记录的内容（纯日常寒暄、无信息量的对话），就什么都不加。
3. 如果新信息补充了已有条目（比如人物档案里的某人有了新的关键行为），在该条目下追加一行，不改动原有内容。
4. 如果新台词触发了一个真正关键的时刻（符合上述主观感受条件），追加一行 `> 玩家感受`。

直接输出完整笔记全文（Markdown），不要任何前言、寒暄、解释或代码块包裹。"""

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
        self.busy = False  # 正在整理中，避免重入 / 阻塞抓取线程

    def feed(self, line: str):
        self._pending.append(line)

    def reconfigure(self, llm, model):
        """热更新 LLM 客户端和模型（设置变更后调用）。"""
        self.llm = llm
        self.model = model

    def should_trigger(self) -> bool:
        return (not self.busy) and len(self._pending) >= self.batch_size

    def organize(self) -> bool:
        if self.busy or not self._pending:
            return False
        self.busy = True
        try:
            new_lines = list(self._pending)
            self._pending.clear()
            msgs = build_organize_prompt(
                new_lines, self.store.read_notes(), self.store.read_characters()
            )
            notes = self.llm.chat(msgs, self.model, temperature=0.2)
            self.store.write_notes(notes)
            return True
        finally:
            self.busy = False
