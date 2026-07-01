from app.organizer import build_organize_prompt, Organizer, extract_characters_section
from tests.conftest import FakeLLM

def test_extract_characters_section_basic():
    notes = """### 剧情节点
- 小明出场

### 人物档案
- **小明**：主角的同学。性格开朗。
- **小红**：隔壁班的女生。第3章出场。

### 伏笔与线索
- 小红提到"那个夜晚"时神色异常"""
    chars = extract_characters_section(notes)
    assert "**小明**" in chars
    assert "**小红**" in chars
    assert "剧情节点" not in chars
    assert "伏笔与线索" not in chars

def test_extract_characters_section_no_heading():
    notes = """### 剧情节点
- 主角到了学校。

### 伏笔与线索
- 老师的眼神有点奇怪。"""
    assert extract_characters_section(notes) == ""

def test_extract_characters_section_empty_section():
    notes = """### 人物档案

### 剧情节点
- 下一段。"""
    assert extract_characters_section(notes) == ""

def test_extract_characters_section_with_hashes():
    notes = """## 人物表
- **张三**：路人甲。
- **李四**：路人乙。

## 其他"""
    chars = extract_characters_section(notes)
    assert "张三" in chars
    assert "李四" in chars
    assert "其他" not in chars

def test_prompt_contains_new_lines_and_existing_notes():
    msgs = build_organize_prompt(["【主角】你好", "【小雪】再见"], existing_notes="# 旧笔记", characters="小雪")
    user_text = msgs[-1]["content"]
    assert "【主角】你好" in user_text
    assert "# 旧笔记" in user_text
    assert "小雪" in user_text
    assert "整合" in user_text  # 新 prompt 强调整合而非追加
    assert msgs[0]["role"] == "system"

def test_extract_characters_section_new_heading():
    """新标题「主要人物」也能正确提取。"""
    notes = """## 主要人物
**小明**：主角的同学。性格开朗。

## 剧情进展
小明出场了。"""
    chars = extract_characters_section(notes)
    assert "**小明**" in chars
    assert "剧情进展" not in chars

def test_should_trigger_at_batch_size(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    org = Organizer(store, FakeLLM(), "m", batch_size=3)
    org.feed("a"); org.feed("b")
    assert org.should_trigger() is False
    org.feed("c")
    assert org.should_trigger() is True

def test_organize_writes_llm_output_to_notes(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    llm = FakeLLM(response="# 整理后的笔记\n- 小雪出场")
    org = Organizer(store, llm, "m", batch_size=2)
    org.feed("a"); org.feed("b")
    assert org.organize() is True
    assert store.read_notes() == "# 整理后的笔记\n- 小雪出场"
    assert len(llm.calls) == 1
    assert org.should_trigger() is False

def test_organize_writes_characters_when_present(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    llm = FakeLLM(response="""### 人物档案
- **小雪**：转学生。自称认识主角。

### 剧情节点
- 小雪第一次出现。""")
    org = Organizer(store, llm, "m", batch_size=2)
    org.feed("a"); org.feed("b")
    assert org.organize() is True
    assert "**小雪**" in store.read_characters()
    assert "剧情节点" not in store.read_characters()
    # notes 仍包含完整内容
    assert "人物档案" in store.read_notes()

def test_organize_no_characters_section_skips_write(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    # 预先写入一些旧人物（模拟手动编辑）
    store.write_characters("- **旧角色**：已删除的人物。")
    llm = FakeLLM(response="""### 剧情节点
- 今天什么都没发生。""")
    org = Organizer(store, llm, "m", batch_size=2)
    org.feed("a"); org.feed("b")
    assert org.organize() is True
    # 没有人物档案段落 → 保留旧 characters.md 不动
    assert "旧角色" in store.read_characters()

def test_organize_no_pending_returns_false(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    org = Organizer(store, FakeLLM(), "m")
    assert org.organize() is False
