from pathlib import Path
import sys
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

from app.config import CONFIG, settings, model_config
from app.capture import LineDeduper, LineEvent, FileInjector
from app.memory import GameStore
from app.llm_client import LLMClient
from app.organizer import Organizer
from app.chat import ChatEngine
from app.textractor import TextractorBridge
from app.memory import slugify
from app.parser import parse_speaker, recover_encoding
from app.indexer import TranscriptIndex
from app.ocr import OCRCapture

app = Flask(__name__, template_folder="../web/templates", static_folder="../web/static")
socketio = SocketIO(app, cors_allowed_origins="*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

stores: dict[str, GameStore] = {}
organizers: dict[str, Organizer] = {}
indexes: dict[str, TranscriptIndex] = {}
ocr_captures: dict[str, OCRCapture] = {}
deduper = LineDeduper()
DEFAULT_GAME = "default"


def get_llm(role: str) -> LLMClient:
    """按角色解析 (base,key) 并取/建缓存的 LLMClient。"""
    base, key, _ = model_config(role)
    return LLMClient(base, key)


def get_store(game_id: str) -> GameStore:
    if game_id not in stores:
        stores[game_id] = GameStore(CONFIG.data_dir, game_id)
        organizers[game_id] = Organizer(
            stores[game_id], get_llm("organize"), model_config("organize")[2],
            CONFIG.organize_batch_size, CONFIG.organize_interval_sec,
        )
        indexes[game_id] = TranscriptIndex(get_llm("embed"), model_config("embed")[2])
    return stores[game_id]

def get_index(game_id: str) -> TranscriptIndex:
    get_store(game_id)  # ensure store + index exist
    return indexes[game_id]

def _reconfigure_llm():
    """设置变更后热更新所有 game 的 Organizer / Indexer。"""
    for gid, org in organizers.items():
        try:
            org.reconfigure(get_llm("organize"), model_config("organize")[2])
        except Exception as e:
            print(f"[reconfigure] organizer {gid}: {e}", flush=True)
    for gid, idx in indexes.items():
        try:
            idx.reconfigure(get_llm("embed"), model_config("embed")[2])
        except Exception as e:
            print(f"[reconfigure] index {gid}: {e}", flush=True)

def ensure_capture_mode(game_id: str):
    """根据运行时设置启动对应抓取通道。"""
    mode = settings.get("capture_mode", "textractor")
    if mode == "ocr":
        _start_ocr(game_id)
    else:
        _stop_ocr(game_id)

def _ocr_settings_for(game_id: str) -> dict:
    """读取某游戏的 OCR 配置：优先 meta.json 里的游戏专属值，否则回退全局 settings。"""
    _DEFAULTS = {
        "ocr_region": {"x": 0, "y": 0, "w": 800, "h": 200},
        "ocr_window": None, "ocr_mode": "onnx", "ocr_lang": "ch", "ocr_interval": 1.0,
    }
    gs = {}
    if game_id in stores or Path(CONFIG.data_dir, game_id, "meta.json").exists():
        store = get_store(game_id)
        gs = store.meta()
    out = {}
    for key in _DEFAULTS:
        v = gs.get(key)
        if v is None:
            v = settings.get(key)
        if v is None:
            v = _DEFAULTS[key]
        out[key] = v
    return out


def _start_ocr(game_id: str):
    if game_id in ocr_captures and ocr_captures[game_id].running:
        return
    s = _ocr_settings_for(game_id)
    cap = OCRCapture(
        region=s["ocr_region"], game_id=game_id, interval=s["ocr_interval"],
        lang=s["ocr_lang"], window_title=s.get("ocr_window"),
        ocr_mode=s["ocr_mode"], on_event=ingest,
    )
    try:
        cap.start()
        ocr_captures[game_id] = cap
        bound = f" window={s.get('ocr_window')!r}" if s.get("ocr_window") else ""
        print(f"[ocr] started mode={s['ocr_mode']} region={s['ocr_region']} interval={s['ocr_interval']}s{bound}", flush=True)
    except Exception as e:
        print(f"[ocr] start failed: {e}", flush=True)

def _stop_ocr(game_id: str):
    if game_id in ocr_captures:
        ocr_captures[game_id].stop()
        del ocr_captures[game_id]

def _run_organize(game_id: str):
    """后台整理笔记，避免阻塞抓取线程（OCR/Textractor）。"""
    org = organizers.get(game_id)
    store = stores.get(game_id)
    if not org or not store:
        return
    try:
        if org.organize():
            socketio.emit("notes", {"notes": store.read_notes()})
            socketio.emit("characters", {"characters": store.read_characters()})
    except Exception as e:
        print(f"[organize] {game_id} failed: {e}", flush=True)


def ingest(ev: LineEvent):
    # 上游没修复编码的话，这里兜底修复
    ev.text = recover_encoding(ev.text)
    # 如果上游没提取说话人，这里兜底解析
    if ev.speaker is None:
        speaker, body = parse_speaker(ev.text)
        ev = LineEvent(
            game_id=ev.game_id, source=ev.source,
            text=body, speaker=speaker, thread_id=ev.thread_id, ts=ev.ts,
        )
    if not deduper.is_new(ev):
        return
    store = get_store(ev.game_id)
    store.append_line(ev.text, speaker=ev.speaker, source=ev.source, ts=ev.ts)
    socketio.emit("line", {"text": ev.text, "speaker": ev.speaker, "source": ev.source})
    org = organizers[ev.game_id]
    org.feed(ev.text)
    if org.should_trigger():
        # 丢后台线程，绝不阻塞抓取线程
        from threading import Thread
        Thread(target=_run_organize, args=(ev.game_id,), daemon=True).start()

active_game = "default"
bridge = TextractorBridge(game_id=active_game, on_event=ingest)

def set_active_game(name):
    global active_game
    new_id = slugify(name) if name else "default"
    if new_id == active_game:
        return
    # OCR 通道：停旧起新，加载新游戏的专属设置
    prev = active_game
    active_game = new_id
    bridge.set_game(active_game)
    if prev in ocr_captures:
        _stop_ocr(prev)
    mode = settings.get("capture_mode", "textractor")
    if mode == "ocr":
        _start_ocr(active_game)

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
    game_id = d.get("game_id", DEFAULT_GAME)
    store = get_store(game_id)
    idx = get_index(game_id)
    engine = ChatEngine(
        store, get_llm("chat"), model_config("chat")[2],
        recent_window=CONFIG.chat_recent_window,
        index=idx, top_k=CONFIG.vector_top_k,
    )
    reply = engine.answer(d["question"])
    return jsonify(reply=reply, notes=store.read_notes(), characters=store.read_characters())

@app.get("/api/notes")
def get_notes():
    store = get_store(request.args.get("game_id", DEFAULT_GAME))
    return jsonify(
        notes=store.read_notes(),
        characters=store.read_characters(),
        transcript=store.read_transcript(),
    )

@app.put("/api/notes")
def put_notes():
    d = request.json
    store = get_store(d.get("game_id", DEFAULT_GAME))
    store.write_notes(d.get("notes", ""))
    socketio.emit("notes", {"notes": store.read_notes()})
    return jsonify(ok=True)

@app.get("/api/games")
def list_games():
    """列出所有已有游戏（data/ 下有 transcript.md 的目录），附带基本统计。"""
    result = []
    root = Path(CONFIG.data_dir)
    if root.exists():
        for d in sorted(root.iterdir()):
            if not d.is_dir() or (not (d / "meta.json").exists() and not (d / "transcript.md").exists()):
                continue
            gid = d.name
            store = get_store(gid)
            notes = store.read_notes()
            transcript = store.read_transcript()
            line_count = sum(1 for _ in transcript.splitlines()) if transcript else 0
            meta = store.meta()
            result.append({
                "game_id": gid,
                "title": meta.get("title", gid),
                "transcript_lines": line_count,
                "notes_size": len(notes),
                "has_ocr_region": bool(meta.get("ocr_region")),
                "created_at": meta.get("created_at", ""),
                "is_active": gid == active_game,
            })
    return jsonify(games=result, active=active_game)


@app.post("/api/game")
def post_game():
    global active_game
    d = request.json
    set_active_game(d.get("name", ""))
    emit_status()
    # 标注最后的游玩时间
    store = get_store(active_game)
    store.set_meta(**store.meta(), last_access=__import__("time").strftime("%Y-%m-%dT%H:%M:%S"))
    return jsonify(ok=True, game_id=active_game)

@app.get("/api/textractor/status")
def textractor_status():
    return jsonify(connected=bridge.connected,
                   running=bridge._thread is not None and bridge._thread.is_alive(),
                   game_id=active_game)

@app.get("/api/settings")
def get_settings():
    """全局设置 + 当前游戏的 OCR 专属覆盖合并后返回。"""
    base = settings.get_all()
    gs = get_store(active_game).meta()
    for k in ("ocr_region", "ocr_window", "ocr_mode", "ocr_lang", "ocr_interval"):
        if k in gs:
            base[k] = gs[k]
    return jsonify(base)

@app.put("/api/settings")
def put_settings():
    body = request.json or {}
    # 游戏专属 OCR 字段存到游戏的 meta.json，其他存全局 settings
    game_ocr_keys = {"ocr_region", "ocr_window", "ocr_mode", "ocr_lang", "ocr_interval"}
    game_body = {k: body[k] for k in game_ocr_keys if k in body}
    global_body = {k: v for k, v in body.items() if k not in game_ocr_keys}
    prev_mode = settings.get("capture_mode", "textractor")
    prev_ocr_mode = game_body.get("ocr_mode") or _ocr_settings_for(active_game).get("ocr_mode", "local")
    if global_body:
        settings.update(global_body)
    if game_body:
        store = get_store(active_game)
        m = store.meta()
        m.update(game_body)
        store.set_meta(**m)
    new_mode = settings.get("capture_mode", "textractor")
    new_ocr_mode = settings.get("ocr_mode") or _ocr_settings_for(active_game).get("ocr_mode", "local")
    # LLM 配置变更 → 热更新 Organizer/Indexer（ChatEngine 每次现建，天然最新）
    if any(k.startswith("llm_") or k == "embed_model" for k in body):
        _reconfigure_llm()
    # 抓取模式切换
    if new_mode != prev_mode:
        if new_mode == "ocr":
            try:
                bridge.stop()
            except Exception:
                pass
            _start_ocr(active_game)
        else:
            _stop_ocr(active_game)
            try:
                bridge.start()
            except Exception as e:
                print(f"[textractor] restart failed: {e}", flush=True)
    elif new_mode == "ocr" and (
        "ocr_interval" in body or "ocr_window" in body or "ocr_lang" in body
        or "ocr_mode" in body or "ocr_vision_base_url" in body
        or "ocr_vision_api_key" in body or "ocr_vision_model" in body
        or prev_ocr_mode != new_ocr_mode
    ):
        # OCR 相关参数或模式改了的话重启 OCR
        _stop_ocr(active_game)
        _start_ocr(active_game)
    return jsonify(ok=True)

@app.get("/api/models")
def list_models():
    """拉取模型列表。?role=organize 用已存配置；也可带 base_url/api_key 测未保存配置。"""
    role = request.args.get("role", "organize")
    base = request.args.get("base_url")
    key = request.args.get("api_key")
    if not base or not key:
        b, k, _ = model_config(role)
        base, key = base or b, key or k
    try:
        client = LLMClient(base, key)
        return jsonify(models=client.list_models())
    except Exception as e:
        return jsonify(error=str(e)), 200

@app.post("/api/models/test")
def test_model():
    """测试连接。{role, base_url?, api_key?, model?} → {ok, reply} 或 {error}。"""
    d = request.json or {}
    role = d.get("role", "organize")
    b, k, m = model_config(role)
    base = d.get("base_url") or b
    key = d.get("api_key") or k
    model = d.get("model") or m
    if not key:
        return jsonify(ok=False, error="未配置 API Key"), 200
    try:
        client = LLMClient(base, key)
        ok, msg = client.test_chat(model)
        return jsonify(ok=ok, reply=msg)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 200

@app.get("/api/ocr/windows")
def list_ocr_windows():
    """列出当前可见的顶层窗口，供用户选目标窗口绑定。"""
    from app import winutil
    wins = winutil.list_visible_windows()
    # 按标题排序，去重
    seen = set()
    out = []
    for w in wins:
        t = w["title"]
        if t not in seen:
            seen.add(t)
            out.append(t)
    out.sort()
    return jsonify(windows=out)

@app.post("/api/ocr/region")
def set_ocr_region():
    """直接设置 OCR 区域（前端在截图上框选后调用）。region 已是相对窗口的偏移。存到游戏 meta。"""
    d = request.json or {}
    region = d.get("region")
    if not region or not region.get("w") or not region.get("h"):
        return jsonify(error="region 无效"), 400
    store = get_store(active_game)
    m = store.meta()
    m["ocr_region"] = region
    store.set_meta(**m)
    cap = ocr_captures.get(active_game)
    if cap and cap.running:
        cap.set_region(region)
        print(f"[ocr] region hot-updated to {region}", flush=True)
    return jsonify(ok=True, region=region)

@app.get("/api/ocr/window-snapshot")
def ocr_window_snapshot():
    """返回目标窗口客户区的 PNG 截图（PrintWindow，被遮挡也能抓），
    供前端在图上框选区域。未绑定窗口时返回主屏全屏截图。
    """
    from flask import Response
    from app import winutil
    import mss
    from PIL import Image
    import io
    window = settings.get("ocr_window")
    img = None
    if window:
        hwnd = winutil.find_window_by_title(window)
        if not hwnd:
            return jsonify(error=f"找不到窗口：{window}"), 400
        img = winutil.capture_window_client(hwnd)
    if img is None:
        # 回退：主屏截图
        with mss.mss() as s:
            mon = s.monitors[1] if len(s.monitors) > 1 else s.monitors[0]
            shot = s.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png")

@app.post("/api/ocr/pick-region")
def pick_ocr_region():
    """启动 tkinter picker 让用户框选屏幕区域。阻塞直到用户选完或取消。
    若已绑定目标窗口，框选的绝对坐标会自动转成相对该窗口客户区的偏移，
    之后窗口移动仍能跟着抓。
    """
    import subprocess
    import json as _json
    from app import winutil
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "app.region_picker"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            encoding="utf-8", timeout=120,
        )
        result = _json.loads(proc.stdout.strip() or "null")
        if result:
            window = settings.get("ocr_window")
            if window:
                # 转成相对窗口客户区的偏移
                hwnd = winutil.find_window_by_title(window)
                rect = winutil.get_client_screen_rect(hwnd) if hwnd else None
                if rect:
                    ox, oy, _x1, _y1 = rect
                    result = {
                        "x": result["x"] - ox,
                        "y": result["y"] - oy,
                        "w": result["w"],
                        "h": result["h"],
                    }
                else:
                    return jsonify(error=f"找不到绑定窗口：{window}（请先刷新窗口列表或重新选取）"), 400
            # 存到游戏专属 meta，不存全局 settings
            store = get_store(active_game)
            m = store.meta()
            m["ocr_region"] = result
            store.set_meta(**m)
            mode = settings.get("capture_mode", "textractor")
            if mode == "ocr":
                cap = ocr_captures.get(active_game)
                if cap and cap.running:
                    cap.set_region(result)
                    print(f"[ocr] region hot-updated to {result}", flush=True)
                else:
                    _start_ocr(active_game)
        return jsonify(region=result)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.post("/api/ocr/restart")
def restart_ocr():
    """手动重启 OCR — 切换模式或换模型后用。"""
    _stop_ocr(active_game)
    settings.update({"capture_mode": "ocr"})
    _start_ocr(active_game)
    cap = ocr_captures.get(active_game)
    return jsonify(ok=True, running=bool(cap and cap.running))

@app.get("/api/ocr/status")
def ocr_status():
    game_id = active_game
    cap = ocr_captures.get(game_id)
    window = settings.get("ocr_window")
    return jsonify(
        mode=settings.get("capture_mode", "textractor"),
        running=bool(cap and cap.running),
        last_text=cap.last_text if cap else None,
        frame_count=cap.frame_count if cap else 0,
        last_error=cap.last_error if cap else None,
        init_error=cap.init_error if cap else None,
        region=cap.get_region() if cap else settings.get("ocr_region"),
        lang_tag=cap.lang_tag if cap else None,
        window=window,
        window_bound=bool(getattr(cap, "window_title", None)) if cap else bool(window),
        ocr_mode=settings.get("ocr_mode", "local"),
    )

if __name__ == "__main__":
    import os
    DEBUG = True
    if (not DEBUG) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        mode = settings.get("capture_mode", "textractor")
        if mode == "ocr":
            ensure_capture_mode(DEFAULT_GAME)
        else:
            try:
                bridge.start()
                print("Textractor bridge started (ws://localhost:6677)", flush=True)
            except RuntimeError as e:
                print(f"Textractor bridge 未启动: {e}", flush=True)
    socketio.run(app, debug=DEBUG, port=5000, allow_unsafe_werkzeug=True)
