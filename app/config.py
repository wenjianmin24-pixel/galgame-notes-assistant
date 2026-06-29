import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    data_dir: str = os.getenv("DATA_DIR", "data")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.proma.cool")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model_organize: str = os.getenv("LLM_MODEL_ORGANIZE", "deepseek-chat")
    llm_model_chat: str = os.getenv("LLM_MODEL_CHAT", "deepseek-chat")
    organize_batch_size: int = int(os.getenv("ORGANIZE_BATCH_SIZE", "20"))
    organize_interval_sec: int = int(os.getenv("ORGANIZE_INTERVAL_SEC", "180"))
    chat_recent_window: int = int(os.getenv("CHAT_RECENT_WINDOW", "200"))
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    vector_top_k: int = int(os.getenv("VECTOR_TOP_K", "5"))

CONFIG = Config()

# ── 运行时设置（可通过 API 读写，覆盖 .env 默认值）────────────

_RUNTIME_FIELDS = [
    # 全局默认（角色未单独配时回退到这里）
    "llm_base_url", "llm_api_key", "llm_model_organize", "llm_model_chat",
    "embed_model",
    # 三角色独立配置（任一未填则回退到全局）
    "llm_organize_base_url", "llm_organize_api_key", "llm_organize_model",
    "llm_chat_base_url", "llm_chat_api_key", "llm_chat_model",
    "llm_embed_base_url", "llm_embed_api_key", "llm_embed_model",
    # 抓取 / OCR
    "capture_mode", "ocr_region", "ocr_interval", "ocr_lang", "ocr_window",
    "ocr_mode", "ocr_vision_base_url", "ocr_vision_api_key", "ocr_vision_model",
]

# 角色专属字段名 → legacy 别名（旧 settings.json 兼容）
_ROLE_LEGACY = {
    "organize": "llm_model_organize",
    "chat": "llm_model_chat",
    "embed": "embed_model",
}

# 角色默认模型（.env 没配时的兜底）
_ROLE_DEFAULT_MODEL = {
    "organize": "deepseek-chat",
    "chat": "deepseek-chat",
    "embed": "text-embedding-3-small",
    "ocr_vision": "gpt-4o",
}


class RuntimeSettings:
    """可运行时修改的设置，存于 data/settings.json。"""

    def __init__(self, data_dir: str):
        self._path = Path(data_dir) / "settings.json"
        self._data: dict = {}

    def _ensure_loaded(self):
        if self._data:
            return
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, key: str, default=None):
        self._ensure_loaded()
        return self._data.get(key, default)

    def get_all(self) -> dict:
        self._ensure_loaded()
        return dict(self._data)

    def update(self, updates: dict):
        self._ensure_loaded()
        for k, v in updates.items():
            if k in _RUNTIME_FIELDS or k.startswith("ocr_"):
                self._data[k] = v
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# 全局单例
settings = RuntimeSettings(CONFIG.data_dir)


def effective(key: str) -> str | int | None:
    """取运行时覆盖值，没有则回退到 .env 默认。"""
    val = settings.get(key)
    if val is not None:
        return val
    return getattr(CONFIG, key, None)


def model_config(role: str) -> tuple[str, str, str]:
    """解析某角色的 (base_url, api_key, model)。
    回退链：角色专属字段 → 全局 llm_base_url/llm_api_key → .env → legacy 别名 → 默认。
    role ∈ {organize, chat, embed, ocr_vision}。
    """
    g_base = settings.get("llm_base_url") or CONFIG.llm_base_url
    g_key = settings.get("llm_api_key") or CONFIG.llm_api_key
    base = settings.get(f"llm_{role}_base_url") or g_base
    key = settings.get(f"llm_{role}_api_key") or g_key
    model = (
        settings.get(f"llm_{role}_model")
        or settings.get(_ROLE_LEGACY.get(role, ""))
        or _ROLE_DEFAULT_MODEL.get(role, "")
    )
    return base, key, model
