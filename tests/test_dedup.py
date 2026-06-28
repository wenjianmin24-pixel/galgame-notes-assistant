from app.capture import LineEvent, LineDeduper

def make(text, source="textractor", gid="g1"):
    return LineEvent(game_id=gid, source=source, text=text)

def test_same_text_twice_second_dropped():
    d = LineDeduper()
    assert d.is_new(make("你好")) is True
    assert d.is_new(make("你好")) is False

def test_different_text_passes():
    d = LineDeduper()
    assert d.is_new(make("你好")) is True
    assert d.is_new(make("再见")) is True

def test_empty_text_dropped():
    d = LineDeduper()
    assert d.is_new(make("   ")) is False

def test_different_source_same_text_both_pass():
    d = LineDeduper()
    assert d.is_new(make("你好", source="textractor")) is True
    assert d.is_new(make("你好", source="ocr")) is True

def test_whitespace_only_diff_treated_as_same():
    d = LineDeduper()
    assert d.is_new(make("你好")) is True
    assert d.is_new(make("  你好  ")) is False
