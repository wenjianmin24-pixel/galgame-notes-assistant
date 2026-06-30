"""Tauri sidecar 入口 — 重定向输出到日志文件。

windows_subsystem="windows" 的进程无控制台，stdout/stderr
不可见。本入口把所有输出写入 data/tauri-server.log 方便排查。
"""

import sys
import os
import io
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "tauri-server.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# 重定向 stdout/stderr 到文件（带行缓冲，实时可读）
log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)  # line-buffered
sys.stdout = log_fh
sys.stderr = log_fh

os.environ["GNA_TAURI"] = "1"

print(f"--- Tauri server starting at {__import__('datetime').datetime.now()} ---", flush=True)
print(f"Python: {sys.executable}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)

# Import server module (loads Flask app, route handlers, etc.)
import app.server

# Run startup logic (normally in __main__ guard of server.py)
mode = app.server.settings.get("capture_mode", "textractor")
print(f"Capture mode: {mode}", flush=True)
if mode == "ocr":
    app.server.ensure_capture_mode(app.server.DEFAULT_GAME)
else:
    try:
        app.server.bridge.start()
        print("Textractor bridge started (ws://localhost:6677)", flush=True)
    except RuntimeError as e:
        print(f"Textractor bridge 未启动: {e}", flush=True)

# Start serving
print("Starting Flask server on :5000 ...", flush=True)
try:
    app.server.socketio.run(
        app.server.app,
        debug=False,
        port=5000,
        allow_unsafe_werkzeug=True,
    )
except KeyboardInterrupt:
    print("Server stopped.", flush=True)
