"""Windows.Media.Ocr 后端 — 调 Windows 10/11 内置 OCR API。

为什么用它：
  - 无须下载模型（PaddleOCR/EasyOCR 都要几百 MB）
  - 中文/日文/英文等识别质量足够日常 galgame 抓字幕
  - 单进程，无 GPU 依赖

前置：系统里要装对应语言包（设置 → 时间和语言 → 语言 → 添加首选语言 → 选"日语"/"中文"，并勾选"包括手写、语音、OCR"等可选功能）。

依赖（二选一，winrt 支持 Python 3.13，推荐）：
  pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization \\
              winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams
  # 或老版 winsdk（仅支持到 3.12）：pip install winsdk
"""

import asyncio
import io
from typing import Optional

# 优先 winrt v3（支持 Python 3.13），回退 winsdk（仅 ≤3.12）
try:
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import (
        InMemoryRandomAccessStream, DataWriter,
    )
    _OCR_ROOT = "winrt"
    _OK = True
    _ERR = None
except Exception:
    try:
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.storage.streams import (
            InMemoryRandomAccessStream, DataWriter,
        )
        _OCR_ROOT = "winsdk"
        _OK = True
        _ERR = None
    except Exception as e:  # pragma: no cover
        _OCR_ROOT = None
        _OK = False
        _ERR = e


# 用户 lang 设置 → Windows BCP-47 候选标签的映射
LANG_ALIASES = {
    "ja": ["ja", "ja-JP"],
    "jp": ["ja", "ja-JP"],
    "ch": ["zh-Hans-CN", "zh-Hans", "zh-CN", "zh"],
    "zh": ["zh-Hans-CN", "zh-Hans", "zh-CN", "zh"],
    "chinese": ["zh-Hans-CN", "zh-Hans", "zh-CN", "zh"],
    "japanese": ["ja", "ja-JP"],
    "en": ["en-US", "en"],
}

# 中文 Windows 默认就有简体识别；汉化 galgame 优先中文，日文英文兜底
DEFAULT_FALLBACK = ["zh-Hans-CN", "zh-Hans", "zh-CN", "zh", "ja", "ja-JP", "en-US"]


class WindowsOCR:
    """轻量包装 Windows.Media.Ocr.OcrEngine。"""

    def __init__(self, lang: str = "ch"):
        if not _OK:
            raise RuntimeError(
                f"winrt/winsdk 未安装或加载失败：{_ERR}。"
                f"Python 3.13 请装 winrt 系列：\n"
                f"  pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization "
                f"winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams"
            )
        candidates = LANG_ALIASES.get(lang.lower(), [lang]) + DEFAULT_FALLBACK
        # 去重保序
        seen = set()
        prefs = []
        for t in candidates:
            if t not in seen:
                seen.add(t)
                prefs.append(t)

        self.engine = None
        self.lang_tag: Optional[str] = None
        for tag in prefs:
            try:
                language = Language(tag)
                if not OcrEngine.is_language_supported(language):
                    continue
                eng = OcrEngine.try_create_from_language(language)
                if eng is not None:
                    self.engine = eng
                    self.lang_tag = tag
                    break
            except Exception:
                continue

        if self.engine is None:
            avail = self.list_installed_languages()
            raise RuntimeError(
                f"Windows OCR 没找到合适的识别语言。"
                f"已安装: {avail or '无'}。"
                f"请到「设置 → 时间和语言 → 语言」添加日语或中文语言包，"
                f"并在该语言的「选项」里勾选 OCR 等可选功能。"
            )

    @staticmethod
    def list_installed_languages() -> list[str]:
        if not _OK:
            return []
        try:
            langs = OcrEngine.available_recognizer_languages
            return [l.language_tag for l in langs]
        except Exception:
            return []

    def recognize(self, pil_image) -> list[str]:
        return asyncio.run(self._recognize_async(pil_image))

    async def _recognize_async(self, pil_image) -> list[str]:
        bmp = await _pil_to_software_bitmap(pil_image)
        result = await self.engine.recognize_async(bmp)
        lines = []
        for line in result.lines:
            text = line.text
            if text and text.strip():
                lines.append(text.strip())
        return lines


async def _pil_to_software_bitmap(pil_image):
    """PIL.Image → Windows SoftwareBitmap，经 PNG 内存流中转。"""
    buf = io.BytesIO()
    pil_image.convert("RGBA").save(buf, format="PNG")
    png_bytes = buf.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bmp = await decoder.get_software_bitmap_async()
    return bmp
