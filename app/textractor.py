from threading import Thread, Event
from time import sleep

from app.capture import LineEvent

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None


def make_event(text, game_id, ts=None):
    """把 Textractor 推来的纯文本包成 LineEvent。纯函数，便于测试。"""
    kw = {"game_id": game_id, "source": "textractor", "text": text}
    if ts is not None:
        kw["ts"] = ts
    return LineEvent(**kw)


class TextractorBridge:
    """连 Textractor 的 textractor_websocket 扩展（ws://localhost:6677）。
    收到文本就回调 on_event。Textractor 没开时自动重连。"""

    def __init__(self, url="ws://localhost:6677", game_id="default", on_event=None):
        self.url = url
        self.game_id = game_id
        self.on_event = on_event
        self._stop = Event()
        self._thread = None
        self.connected = False

    def set_game(self, game_id):
        self.game_id = game_id

    def start(self):
        if websocket is None:
            raise RuntimeError("websocket-client 未安装：pip install websocket-client")
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=lambda ws, e: setattr(self, "connected", False),
                    on_close=lambda ws, *a: setattr(self, "connected", False),
                )
                ws.run_forever(ping_interval=30, ping_timeout=8)
            except Exception as e:
                # 打印异常避免静默吞掉（便于排查连接问题）
                print(f"[textractor] run_forever exited: {type(e).__name__}: {e}", flush=True)
            self.connected = False
            # 重连间隔 ~5s（Textractor 可能还没开）
            for _ in range(20):
                if self._stop.is_set():
                    return
                sleep(0.25)

    def _on_open(self, ws):
        self.connected = True

    def _on_message(self, ws, msg):
        if not msg or self.on_event is None:
            return
        self.on_event(make_event(msg, self.game_id))
