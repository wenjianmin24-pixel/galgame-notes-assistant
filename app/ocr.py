"""OCR 抓取通道 — 屏幕区域截取 + 文本识别 + 去重。

后端：Windows.Media.Ocr（无须下载模型，系统装了对应语言包即可）。
依赖：pip install mss winsdk Pillow
"""

import hashlib
import traceback
from threading import Thread, Event, Lock
from time import time, sleep

from app.capture import LineEvent


def _text_hash(text: str) -> str:
    return hashlib.md5(text.strip().encode()).hexdigest()


class OCRCapture:
    """对屏幕区域定期截取并 OCR 识别，文本变化时回调 on_event。

    支持运行时热更新 region（框选完毕立即生效，不必重启进程）。
    """

    def __init__(self, region: dict, game_id="default", interval=1.0,
                 on_event=None, lang="ch", window_title: str | None = None,
                 ocr_mode: str = "local"):
        self._region_lock = Lock()
        self._region = dict(region)
        self.game_id = game_id
        self.interval = max(interval, 0.3)
        self.on_event = on_event
        self.lang = lang
        self.window_title = (window_title or "").strip() or None
        self.ocr_mode = ocr_mode or "local"
        self._stop = Event()
        self._thread = None
        self._engine = None
        self._mss = None
        self._last_hash: str | None = None
        self.running = False
        self.last_text: str | None = None
        self.frame_count: int = 0
        self.last_error: str | None = None
        self.init_error: str | None = None
        self.lang_tag: str | None = None  # 实际选中的语言/模型

    def set_region(self, region: dict):
        with self._region_lock:
            self._region = dict(region)
        self._last_hash = None
        self._last_pixels = None

    def set_window(self, window_title: str | None):
        self.window_title = (window_title or "").strip() or None
        self._last_hash = None
        self._last_pixels = None

    def get_region(self) -> dict:
        with self._region_lock:
            return dict(self._region)

    def _resolve_monitor(self) -> dict | None:
        """未绑定窗口时，返回屏幕绝对坐标的 mss monitor。"""
        with self._region_lock:
            r = dict(self._region)
        return {
            "top": r.get("y", 0), "left": r.get("x", 0),
            "width": max(r.get("w", 800), 1),
            "height": max(r.get("h", 200), 1),
        }

    def _capture_frame(self):
        """抓一帧台词区域，返回 PIL.Image。
        绑定窗口时优先 PrintWindow（被遮挡也能抓），失败回退屏幕截取；
        未绑定时直接屏幕截取。
        """
        from PIL import Image
        with self._region_lock:
            r = dict(self._region)
        rx = r.get("x", 0); ry = r.get("y", 0)
        rw = max(r.get("w", 800), 1); rh = max(r.get("h", 200), 1)

        if self.window_title:
            from app import winutil
            hwnd = winutil.find_window_by_title(self.window_title)
            if not hwnd:
                raise RuntimeError(f"找不到窗口：{self.window_title}")
            img = winutil.capture_window_client(hwnd)
            if img is not None:
                # region 是相对客户区左上角的偏移
                cw, ch = img.size
                box = (max(rx, 0), max(ry, 0),
                       min(rx + rw, cw), min(ry + rh, ch))
                if box[2] > box[0] and box[3] > box[1]:
                    return img.crop(box).convert("RGB")
                return img.convert("RGB")
            # PrintWindow 失败（DirectX/全屏游戏），回退屏幕截取
            rect = winutil.get_client_screen_rect(hwnd)
            if not rect:
                raise RuntimeError(f"窗口已关闭：{self.window_title}")
            ox, oy, _x1, _y1 = rect
            monitor = {"left": ox + rx, "top": oy + ry,
                       "width": rw, "height": rh}
            shot = self._mss.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # 未绑定窗口：屏幕绝对坐标
        monitor = {"left": rx, "top": ry, "width": rw, "height": rh}
        shot = self._mss.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def _lazy_init(self):
        if self._engine is not None:
            return
        import mss
        if self.ocr_mode == "ai_vision":
            from app.ocr_ai import AIVisionOCR
            self._engine = AIVisionOCR()
        elif self.ocr_mode == "rapid":
            from app.ocr_rapid import RapidOCREngine
            self._engine = RapidOCREngine()
        else:
            from app.ocr_winsdk import WindowsOCR
            self._engine = WindowsOCR(lang=self.lang)
        self.lang_tag = self._engine.lang_tag
        self._mss = mss.mss()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._last_pixels = None
        self._pending_frame = None   # 画面变化后等稳定再 OCR 的待处理帧
        self._stable_count = 0        # 连续稳定帧计数
        self._last_ocr_time = 0.0     # 上次 OCR 完成时间（用于 max-wait）
        self._pending_since = 0.0     # pending_frame 首次设定的时间
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        self.running = True

    def stop(self):
        self._stop.set()
        self.running = False

    def _frame_changed(self, pil) -> bool:
        """缩略图像素比对：>2% 像素显著变化才认为画面变了。"""
        from PIL import Image
        w = min(150, pil.width)
        h = max(1, int(pil.height * w / pil.width))
        thumb = pil.resize((w, h), Image.NEAREST)
        px = thumb.tobytes()
        if self._last_pixels is None or len(self._last_pixels) != len(px):
            self._last_pixels = px
            return True
        prev = self._last_pixels
        self._last_pixels = px
        diff = 0
        threshold = 40
        for i in range(0, len(px) - 2, 3):
            if (abs(px[i] - prev[i]) + abs(px[i + 1] - prev[i + 1]) +
                    abs(px[i + 2] - prev[i + 2])) > threshold:
                diff += 1
        return diff / max(len(px) // 3, 1) > 0.02

    def _run(self):
        try:
            self._lazy_init()
        except Exception as e:
            tb = traceback.format_exc()
            self.init_error = f"{e}"
            self.last_error = f"init failed: {e}"
            print(f"[ocr] init failed: {e}\n{tb}", flush=True)
            self.running = False
            return

        self._last_pixels: bytes | None = None  # 上一帧的缩略图像素（RGB bytes）

        print(f"[ocr] engine ready, using language {self.lang_tag}", flush=True)

        while not self._stop.is_set():
            try:
                pil = self._capture_frame()

                now = time()

                # 稳定性门控：画面变了就存起来，连续稳定 2 帧才跑 OCR
                # 防止类型机逐字推进时抓到半成品句子
                changed = self._frame_changed(pil)
                if changed:
                    self._stable_count = 0
                    if self._pending_frame is None:
                        self._pending_since = now
                    self._pending_frame = pil
                    self.last_error = None
                    sleep(self.interval)
                    continue

                # 画面没变：累积稳定计数
                self._stable_count += 1
                # 触发条件：
                #   a) 连续 2 帧稳定（正常结束）
                #   b) 自首次变化起超过 4 秒（打字机兜底——等太久了，强跑）
                stable_enough = self._stable_count >= 2
                waited_too_long = (
                    self._pending_since > 0
                    and now - self._pending_since > 4.0
                    and now - self._last_ocr_time > 4.0
                )
                if (not stable_enough and not waited_too_long) or self._pending_frame is None:
                    sleep(self.interval)
                    continue

                # 对之前留存的稳定帧跑 OCR
                ocr_pil = self._pending_frame
                self._pending_frame = None
                self._stable_count = 0
                self._pending_since = 0.0

                lines = self._engine.recognize(ocr_pil)
                # 清洗 OCR 输出（去控制字符、ruby、空白折叠）
                from app.parser import clean_ocr_text
                lines = [clean_ocr_text(l) for l in lines]
                lines = [l for l in lines if l]
                if not lines:
                    self.last_error = None
                    sleep(self.interval)
                    continue

                combined = "\n".join(lines)
                h = _text_hash(combined)
                if h == self._last_hash:
                    sleep(self.interval)
                    continue

                self._last_hash = h
                self.last_text = combined
                self.frame_count += 1
                self._last_ocr_time = time()
                self.last_error = None
                if self.on_event:
                    for line in lines:
                        self.on_event(LineEvent(
                            game_id=self.game_id, source="ocr", text=line, ts=time(),
                        ))
            except Exception as e:
                tb = traceback.format_exc()
                self.last_error = f"{type(e).__name__}: {e}"
                print(f"[ocr] frame error: {e}\n{tb}", flush=True)

            for _ in range(int(self.interval * 10)):
                if self._stop.is_set():
                    return
                sleep(0.1)
