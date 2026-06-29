"""model_config 各角色回退链测试。"""
from app import config as cfg


def test_defaults_when_empty(tmp_path, monkeypatch):
    # 用空 settings 实例
    s = cfg.RuntimeSettings(str(tmp_path))
    monkeypatch.setattr(cfg, "settings", s)
    base, key, model = cfg.model_config("organize")
    assert base == cfg.CONFIG.llm_base_url
    assert key == cfg.CONFIG.llm_api_key
    assert model == "deepseek-chat"  # .env 默认


def test_legacy_model_alias(tmp_path, monkeypatch):
    s = cfg.RuntimeSettings(str(tmp_path))
    s.update({"llm_model_organize": "legacy-org", "embed_model": "legacy-emb"})
    monkeypatch.setattr(cfg, "settings", s)
    assert cfg.model_config("organize")[2] == "legacy-org"
    assert cfg.model_config("embed")[2] == "legacy-emb"


def test_per_role_overrides_global(tmp_path, monkeypatch):
    s = cfg.RuntimeSettings(str(tmp_path))
    s.update({
        "llm_base_url": "https://global", "llm_api_key": "g-key",
        "llm_chat_base_url": "https://chat-endpoint",
        "llm_chat_model": "chat-m",
    })
    monkeypatch.setattr(cfg, "settings", s)
    # chat 用专属端点+模型，但 key 没配 → 回退全局
    b, k, m = cfg.model_config("chat")
    assert b == "https://chat-endpoint"
    assert k == "g-key"
    assert m == "chat-m"
    # organize 没配专属 → 全用全局
    b2, k2, m2 = cfg.model_config("organize")
    assert b2 == "https://global" and k2 == "g-key"


def test_ocr_vision_default_model(tmp_path, monkeypatch):
    s = cfg.RuntimeSettings(str(tmp_path))
    monkeypatch.setattr(cfg, "settings", s)
    _, _, m = cfg.model_config("ocr_vision")
    assert m == "gpt-4o"
