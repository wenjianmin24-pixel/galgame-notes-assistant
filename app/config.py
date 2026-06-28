import os
from dataclasses import dataclass
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

CONFIG = Config()
