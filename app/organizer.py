import re

ORGANIZE_SYSTEM = """你是一个正在推 galgame 的玩家，边玩边记笔记。你的笔记风格是**叙事整合式**——把分散的台词信息融合成有可读性的故事摘要，而不是信息条目的机械堆砌。

**核心原则：整合优于追加，叙事优于罗列。已有笔记中的信息需要和新台词融合重写，而不是原样保留再加一段。**

---

## 笔记结构

你需要维护以下四个栏目（已有则在新台词基础上重写整合，没有则新建）：

### 主要人物

每个角色**只出现一条**，用一段流畅的文字整合该角色的所有已知信息。
格式：角色名单独一行加粗，下面跟一段整合性描述。不要用多条列表项列同一个角色。

示例（一条整合后的角色）：
```
**由良**
与主角同住的少女。性格安静内向，在第2章首次出场。平时话少，但对主角的关心体现在行动上。后来主动提出陪主角去旧校舍调查，暗示她可能知道些什么。提到"火灾"时反应异常，可能有相关经历。
```

**合并规则**：
- 如果已有笔记中某角色已有描述，**把新台词中的信息融入原有段落**，重写该角色的完整描述，而不是在下面追加一条新的。
- 只有全新角色才新增条目。
- 性格特征要基于台词证据，不凭空猜测。
- 如果新台词没有为该角色带来新信息，保持原描述不变。

### 剧情进展

按时间顺序**叙事**，不是事件列表。把关键事件写成有衔接的故事摘要：
- 只记真正推动剧情的事——日常寒暄、重复信息跳过
- 每个事件 2-4 句，交代场景、发生了什么、涉及谁
- 新事件追加在末尾，保持时间线的连贯感
- 重要的原句对话用缩进引用保留（`> "原句"`），让笔记有原文质感
- 如果新事件和已有笔记末尾的事件是同一场景的连续发展，合并成一段

格式示例：
```
走到大桥上，俯瞰下方城镇的黄昏景色。脑中浮现一段话——"跨越星界，遍历无数的可能性，将汝所欲之一切，悉数赐予"。

到达奥威尔堡，义兄杰拉尔德安排了住所。入睡后又梦到了那个不可名状的原型，它自称"雷克西斯·阿卡曼"，露出慈爱的微笑——只是一场噩梦吗？
```

### 伏笔与线索

只记录台词中**明确暗示**的东西（某人说了奇怪的话、某个信息被刻意隐瞒、前后矛盾）。不记"我觉得可能是伏笔"——你不是在办案，你是在记已知事实。

### 选项与分支

记录遇到的选择及做出的选择。

---

## 主观感受：严格克制

你不是在写读后感。玩家涂鸦**只允许在以下情况出现**：
- 重大剧情转折（角色死亡、真相揭露、关系剧变）
- 一个铺垫了很久的伏笔终于兑现
- 你真正被触动/震惊的地方

此时可以加 1-2 句，用 `> ` 引用格式写在相关记录下面：
`> 这里真的没想到……之前的伏笔原来是为了这个。`

**禁止**：每句台词后都写主观反应、大段猜测和脑补、把笔记写成情绪日记。

---

## 整合重写规则（最重要）

1. **人物必须合并**：同一角色永远只出现一次。新旧信息融合成一段完整的描述。绝对不要出现同一角色名下的多个独立条目。
2. **剧情按时间追加**：新事件追加到「剧情进展」末尾。若新事件和末尾事件是同一场景的连续发展，合并到已有段落中。
3. **信息去重**：新台词如果只是在复述已知信息，不要重复记录。
4. **有则改之，无则加勉**：如果新台词没有值得记录的内容（纯寒暄、无信息量），保持已有笔记不变，不要为了"写点什么"而硬写。
5. **改写时保留重要原句**：如果某句台词是关键信息或金句，保留原文引用。其他叙述性内容用自己的话整合。

直接输出完整笔记全文（Markdown），不要任何前言、寒暄、解释或代码块包裹。"""


def build_organize_prompt(new_lines, existing_notes, characters):
    parts = []
    if existing_notes:
        parts.append(f"【已有笔记——需要和新台词整合重写，不是原样保留】\n{existing_notes}")
    if characters:
        parts.append(f"【已有人物表——仅作参考，已在笔记中的人物无需重复】\n{characters}")
    parts.append(f"【新台词——将其中新信息融入已有笔记，重写后输出完整笔记】\n" + "\n".join(new_lines))
    return [
        {"role": "system", "content": ORGANIZE_SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


# 从 notes 中提取人物段落的正则——兼容新旧标题
_CHAR_HEADING_RE = re.compile(
    r'(?:^|\n)#{1,4}[^\S\n]*(?:主要人物|人物(?:档案|表))[^\S\n]*\n(.*?)(?=\n#{1,4}[^\S\n]|\Z)',
    re.DOTALL,
)


def extract_characters_section(notes_text: str) -> str:
    """从 LLM 整理的 notes 中提取「人物档案」段落，返回纯内容（不含标题行）。"""
    m = _CHAR_HEADING_RE.search(notes_text)
    if not m:
        return ""
    return m.group(1).strip()


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

    def reconfigure(self, llm, model, batch_size=None):
        """热更新 LLM 客户端、模型和批量大小（设置变更后调用）。"""
        self.llm = llm
        self.model = model
        if batch_size is not None:
            self.batch_size = batch_size

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
            chars = extract_characters_section(notes)
            if chars:
                self.store.write_characters(chars)
            return True
        finally:
            self.busy = False
