from dataclasses import dataclass, field
from time import time
import re

@dataclass
class LineEvent:
    game_id: str
    source: str          # "textractor" | "ocr" | "manual" | "replay"
    text: str
    speaker: str | None = None
    thread_id: str | None = None
    ts: float = field(default_factory=time)

class LineDeduper:
    """归一化 + 精确哈希 + Levenshtein 模糊比对，防 OCR 抖动重复。"""
    def __init__(self, history=50):
        self._hist: dict[str, list[str]] = {}
        self._history = history

    def _key(self, ev: LineEvent) -> str:
        return f"{ev.game_id}|{ev.source}|{ev.thread_id or ''}"

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"[\s　]+", "", text)

    def is_new(self, ev: LineEvent, ratio_threshold: float = 0.82) -> bool:
        text = self._norm(ev.text)
        if not text:
            return False
        key = self._key(ev)
        recent = self._hist.setdefault(key, [])
        # 精确匹配
        if text in recent:
            return False
        # 模糊匹配：跟最近几条比对，相似度过高就跳过
        from app.parser import levenshtein_ratio
        check_window = min(len(recent), 8)
        for recent_text in recent[-check_window:]:
            if levenshtein_ratio(text, recent_text) >= ratio_threshold:
                # 选留更长的版本（信息更全）
                if len(text) > len(recent_text):
                    recent.remove(recent_text)
                    break
                return False
        recent.append(text)
        if len(recent) > self._history:
            del recent[: len(recent) - self._history]
        return True


from pathlib import Path
from threading import Thread, Event

class FileInjector:
    """v1 模拟抓取：按行回放文本文件作为 LineEvent。"""
    def __init__(self, path, game_id, source="replay", interval=1.0, on_event=None):
        self.path = Path(path)
        self.game_id = game_id
        self.source = source
        self.interval = interval
        self.on_event = on_event
        self._stop = Event()
        self._thread = None

    def start(self):
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if self._stop.is_set():
                    return
                line = line.rstrip("\n")
                if not line:
                    continue
                if self.on_event:
                    self.on_event(LineEvent(
                        game_id=self.game_id, source=self.source, text=line
                    ))
                self._stop.wait(self.interval)
