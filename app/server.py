from pathlib import Path
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

from app.config import CONFIG
from app.capture import LineDeduper, LineEvent, FileInjector
from app.memory import GameStore
from app.llm_client import LLMClient
from app.organizer import Organizer
from app.chat import ChatEngine
from app.textractor import TextractorBridge
from app.memory import slugify

app = Flask(__name__, template_folder="../web/templates", static_folder="../web/static")
socketio = SocketIO(app, cors_allowed_origins="*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

llm = LLMClient(CONFIG.llm_base_url, CONFIG.llm_api_key)
stores: dict[str, GameStore] = {}
organizers: dict[str, Organizer] = {}
deduper = LineDeduper()
DEFAULT_GAME = "default"

def get_store(game_id: str) -> GameStore:
    if game_id not in stores:
        stores[game_id] = GameStore(CONFIG.data_dir, game_id)
        organizers[game_id] = Organizer(
            stores[game_id], llm, CONFIG.llm_model_organize,
            CONFIG.organize_batch_size, CONFIG.organize_interval_sec,
        )
    return stores[game_id]

def ingest(ev: LineEvent):
    if not deduper.is_new(ev):
        return
    store = get_store(ev.game_id)
    store.append_line(ev.text, speaker=ev.speaker, source=ev.source, ts=ev.ts)
    socketio.emit("line", {"text": ev.text, "speaker": ev.speaker, "source": ev.source})
    org = organizers[ev.game_id]
    org.feed(ev.text)
    if org.should_trigger():
        org.organize()
        socketio.emit("notes", {"notes": store.read_notes()})

active_game = "default"
bridge = TextractorBridge(game_id=active_game, on_event=ingest)

def set_active_game(name):
    global active_game
    active_game = slugify(name) if name else "default"
    bridge.set_game(active_game)

def emit_status():
    socketio.emit("textractor_status", {
        "connected": bridge.connected,
        "running": bridge._thread is not None and bridge._thread.is_alive(),
        "game_id": active_game,
    })

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/line")
def post_line():
    d = request.json
    ingest(LineEvent(
        game_id=d.get("game_id", DEFAULT_GAME),
        source=d.get("source", "manual"),
        text=d["text"],
        speaker=d.get("speaker"),
    ))
    return jsonify(ok=True)

@app.post("/api/marker")
def post_marker():
    d = request.json
    store = get_store(d.get("game_id", DEFAULT_GAME))
    store.add_marker(d["label"])
    socketio.emit("line", {"text": f"═══ {d['label']} ═══", "marker": True})
    return jsonify(ok=True)

@app.post("/api/replay")
def post_replay():
    d = request.json
    p = Path(d["path"])
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    inj = FileInjector(
        str(p), d.get("game_id", DEFAULT_GAME),
        source="replay", interval=float(d.get("interval", 1.0)),
        on_event=ingest,
    )
    inj.start()
    return jsonify(ok=True)

@app.post("/api/chat")
def post_chat():
    d = request.json
    store = get_store(d.get("game_id", DEFAULT_GAME))
    engine = ChatEngine(store, llm, CONFIG.llm_model_chat, CONFIG.chat_recent_window)
    reply = engine.answer(d["question"])
    return jsonify(reply=reply, notes=store.read_notes())

@app.get("/api/notes")
def get_notes():
    store = get_store(request.args.get("game_id", DEFAULT_GAME))
    return jsonify(
        notes=store.read_notes(),
        characters=store.read_characters(),
        transcript=store.read_transcript(),
    )

@app.post("/api/game")
def post_game():
    global active_game
    d = request.json
    set_active_game(d.get("name", ""))
    emit_status()
    return jsonify(ok=True, game_id=active_game)

@app.get("/api/textractor/status")
def textractor_status():
    return jsonify(connected=bridge.connected,
                   running=bridge._thread is not None and bridge._thread.is_alive(),
                   game_id=active_game)

if __name__ == "__main__":
    try:
        bridge.start()
        print("Textractor bridge started (ws://localhost:6677)")
    except RuntimeError as e:
        print(f"Textractor bridge 未启动: {e}")
    # allow_unsafe_werkzeug: 新版 flask-socketio 默认禁止 Werkzeug dev server，开发环境显式开启
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
