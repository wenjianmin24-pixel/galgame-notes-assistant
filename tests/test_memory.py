import os
from app.memory import GameStore, slugify, MARKER_PREFIX

def test_slugify():
    assert slugify("Clannad") == "Clannad"
    assert slugify("Steins;Gate") == "Steins_Gate"
    assert slugify("   ") == "game"

def test_append_and_read_recent(tmp_path):
    s = GameStore(str(tmp_path), "g1")
    s.append_line("第一句")
    s.append_line("第二句")
    s.append_line("第三句")
    assert s.read_recent_lines(2) == ["第二句", "第三句"]

def test_marker_inserted(tmp_path):
    s = GameStore(str(tmp_path), "g1")
    s.append_line("a")
    s.add_marker("B 线开始")
    text = s.read_transcript()
    assert MARKER_PREFIX in text
    assert "B 线开始" in text

def test_notes_roundtrip(tmp_path):
    s = GameStore(str(tmp_path), "g1")
    assert s.read_notes() == ""
    s.write_notes("# 笔记\n内容")
    assert s.read_notes() == "# 笔记\n内容"

def test_meta_roundtrip(tmp_path):
    s = GameStore(str(tmp_path), "g1")
    assert s.meta() == {}
    s.set_meta(title="测试游戏", capture="ocr")
    assert s.meta()["title"] == "测试游戏"
