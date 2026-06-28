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
