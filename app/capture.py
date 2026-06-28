from dataclasses import dataclass, field
from time import time

@dataclass
class LineEvent:
    game_id: str
    source: str          # "textractor" | "ocr" | "manual" | "replay"
    text: str
    speaker: str | None = None
    thread_id: str | None = None
    ts: float = field(default_factory=time)

class LineDeduper:
    """同一通道同一文本只推一次。"""
    def __init__(self):
        self._last: dict[str, str] = {}

    def _key(self, ev: LineEvent) -> str:
        return f"{ev.game_id}|{ev.source}|{ev.thread_id or ''}"

    def is_new(self, ev: LineEvent) -> bool:
        text = ev.text.strip()
        if not text:
            return False
        key = self._key(ev)
        if self._last.get(key) == text:
            return False
        self._last[key] = text
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
