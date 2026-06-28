from app.textractor import make_event

def test_make_event_basic():
    ev = make_event("你好", "g1")
    assert ev.text == "你好"
    assert ev.game_id == "g1"
    assert ev.source == "textractor"
    assert ev.speaker is None
    assert ev.ts is not None  # 默认时间戳已填

def test_make_event_with_explicit_ts():
    ev = make_event("你好", "g1", ts=123.0)
    assert ev.ts == 123.0

def test_make_event_empty_text_still_wraps():
    # 即使空文本也包成事件，去重由 ingest 负责
    ev = make_event("", "g1")
    assert ev.text == ""
    assert ev.source == "textractor"
