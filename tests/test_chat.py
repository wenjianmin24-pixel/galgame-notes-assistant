from app.chat import build_chat_context, extract_insight, ChatEngine
from tests.conftest import FakeLLM

def test_context_contains_recent_notes_and_question(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    store.append_line("【主角】你好")
    store.write_notes("# 笔记\n小雪是女主")
    store.write_characters("小雪：女主")
    msgs = build_chat_context(store, "小雪是谁？", recent_window=10)
    text = msgs[-1]["content"]
    assert "【主角】你好" in text
    assert "小雪是女主" in text
    assert "小雪：女主" in text
    assert "小雪是谁？" in text

def test_extract_insight():
    assert extract_insight("回答\nINSIGHT: 伏笔X") == "伏笔X"
    assert extract_insight("回答") is None

def test_chat_engine_writes_insight_back(tmp_path):
    from app.memory import GameStore
    store = GameStore(str(tmp_path), "g1")
    store.write_notes("# 笔记\n")
    llm = FakeLLM(response="根据剧情……\nINSIGHT: 小雪认识主角")
    engine = ChatEngine(store, llm, "m", recent_window=10)
    reply = engine.answer("小雪怎么认识主角的？")
    assert "小雪认识主角" in reply
    assert "小雪认识主角" in store.read_notes()
