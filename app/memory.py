import json
import re
from pathlib import Path

MARKER_PREFIX = "═══"

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9一-龥]+", "_", name).strip("_")
    return s or "game"

class GameStore:
    def __init__(self, root: str, game_id: str):
        self.root = Path(root)
        self.dir = self.root / game_id
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def transcript_path(self): return self.dir / "transcript.md"
    @property
    def notes_path(self): return self.dir / "notes.md"
    @property
    def characters_path(self): return self.dir / "characters.md"
    @property
    def meta_path(self): return self.dir / "meta.json"

    def append_line(self, text, speaker=None, source=None, ts=None):
        prefix = f"【{speaker}】" if speaker else ""
        with open(self.transcript_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{text}\n")

    def add_marker(self, label):
        with open(self.transcript_path, "a", encoding="utf-8") as f:
            f.write(f"\n{MARKER_PREFIX} {label} {MARKER_PREFIX}\n\n")

    def read_transcript(self):
        if not self.transcript_path.exists(): return ""
        return self.transcript_path.read_text(encoding="utf-8")

    def read_recent_lines(self, n):
        lines = [l for l in self.read_transcript().splitlines() if l.strip()]
        return lines[-n:]

    def read_notes(self):
        if not self.notes_path.exists(): return ""
        return self.notes_path.read_text(encoding="utf-8")

    def write_notes(self, content):
        self.notes_path.write_text(content, encoding="utf-8")

    def read_characters(self):
        if not self.characters_path.exists(): return ""
        return self.characters_path.read_text(encoding="utf-8")

    def write_characters(self, content):
        self.characters_path.write_text(content, encoding="utf-8")

    def meta(self):
        if not self.meta_path.exists(): return {}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def set_meta(self, **kw):
        m = self.meta(); m.update(kw)
        self.meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
