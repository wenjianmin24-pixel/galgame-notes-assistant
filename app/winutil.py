"""Win32 窗口工具 — 用 ctypes 枚举/查找窗口，无额外依赖。

用于 OCR 窗口绑定：把截取区域锚定到某个游戏窗口的客户区，
窗口移动后仍能跟着抓，不再抓到挡在前面的网页。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

# EnumWindows 回调签名
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _get_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def list_visible_windows() -> list[dict]:
    """返回可见、有标题的顶层窗口：[{"title": str}]。"""
    out = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _get_title(hwnd).strip()
        if title:
            out.append({"title": title})
        return True

    user32.EnumWindows(_WNDENUMPROC(cb), 0)
    return out


def find_window_by_title(substr: str):
    """模糊匹配窗口标题（大小写不敏感），返回 hwnd 或 None。取第一个匹配。"""
    needle = (substr or "").strip().lower()
    if not needle:
        return None
    found = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _get_title(hwnd)
        if needle in title.lower():
            found.append(hwnd)
            return False  # 命中即停
        return True

    user32.EnumWindows(_WNDENUMPROC(cb), 0)
    return found[0] if found else None


def get_client_screen_rect(hwnd) -> tuple[int, int, int, int] | None:
    """返回窗口客户区在屏幕上的 (x0, y0, x1, y1)；窗口无效返回 None。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.right == 0 or rect.bottom == 0:
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    return pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom


# ── 窗口截图（PrintWindow，即使被遮挡也能抓）──────────────────────

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def _setup_signatures():
    gdi = ctypes.windll.gdi32
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    gdi.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), ctypes.c_uint,
    ]
    gdi.GetDIBits.restype = ctypes.c_int
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]


_setup_signatures()


def capture_window_client(hwnd):
    """用 PrintWindow 抓窗口客户区，返回 PIL.Image（RGBA）；失败返回 None。
    即使窗口被其他窗口遮挡也能抓到（对 GDI/KiriKiri/RPGMaker 类有效；
    DirectX/Unity 全屏游戏可能返回黑图，那时调用方应回退到屏幕截取）。
    """
    from PIL import Image
    gdi = ctypes.windll.gdi32
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        return None

    hdc_screen = user32.GetDC(0)
    mdc = gdi.CreateCompatibleDC(hdc_screen)
    bmp = gdi.CreateCompatibleBitmap(hdc_screen, w, h)
    old = gdi.SelectObject(mdc, bmp)

    # 3 = PW_CLIENTONLY(1) | PW_RENDERFULLCONTENT(2)：只抓客户区，含新内容
    ok = user32.PrintWindow(hwnd, mdc, 3)
    img = None
    if ok:
        bi = _BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h  # 负值=自上而下
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        got = gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        if got:
            img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)

    gdi.SelectObject(mdc, old)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc_screen)
    return img

