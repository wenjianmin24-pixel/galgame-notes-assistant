from app.organizer import build_organize_prompt, Organizer
from tests.conftest import FakeLLM

def test_prompt_contains_new_lines_and_existing_notes():
    msgs = build_organize_prompt(["【主角】你好", "【小雪】再见"], existing_notes="# 旧笔记", characters="小雪")
    user_text = msgs[-1]["content"]
    assert "【主角】你好" in user_text
    assert "# 旧笔记" in user_text
    assert "小雪" in user_text
    assert msgs[0]["role"] == "system"

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

def test_organize_no_pending_returns_false(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    org = Organizer(store, FakeLLM(), "m")
    assert org.organize() is False
