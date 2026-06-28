# CLAUDE.md — galgame-notes-assistant

> 给未来接手本项目的 Agent 看的项目知识库。只记"删掉就会犯错"的内容。

## 项目一句话

galgame / 视觉小说的 AI 笔记助手：游玩时实时抓取屏幕文本 → 云端 LLM 自动整理结构化笔记 + 可讨论剧情，按游戏分库。设计文档见 `docs/design.md`。

## 已定的关键决策（不要推翻，除非和用户重新讨论）

- **抓取双通道**：Textractor（内存钩子，主）+ 本地 PaddleOCR（截屏，兜底）。不自研钩子引擎。
- **语言**：中文，无翻译层（用户主要玩中文版）。
- **AI 角色**：自动整理结构化笔记 + 剧情对话陪读，共用同一份按游戏分库的记忆。
- **LLM 后端**：云端 API（OpenAI 兼容：Proma Cloud / DeepSeek / Qwen / Gemini）。自动整理用便宜档、批量触发控制成本；对话用强档。
- **记忆**：本地 Markdown 文件，按游戏分文件夹（transcript.md / notes.md / characters.md / meta.json）。

## 技术栈

- Python 3.11+ 核心服务（Flask + SocketIO，常驻进程）
- Textractor + 自写 WebSocket 扩展（v2，未实现）
- PaddleOCR（本地，v2，未实现）
- 云端 LLM，OpenAI 兼容接口（当前用 DeepSeek 官方：`deepseek-chat`）
- Flask + 浏览器作为界面（v1；后续可迁 Tauri）
- 本地 Markdown 文件作为记忆库

## v1 实现状态与运行

v1 MVP 已跑通核心管线：文件回放注入器（模拟抓取）→ 去重 → transcript 落盘 → DeepSeek 自动整理结构化笔记 → 剧情对话 + 洞察回填 → 路标。v2 已接 Textractor 真实抓取通道（见下）。OCR、向量检索、Tauri 未实现。21 个单元测试全绿。

**运行**：
```bash
cd C:\Users\温建民\projects\galgame-notes-assistant
.venv\Scripts\python.exe -m app.server   # 起 http://127.0.0.1:5000
.venv\Scripts\python.exe -m pytest        # 测试
```

**关键约定（改了会出错）**：
- 所有 python/pip 命令必须用 `.venv\Scripts\python.exe`。系统 `python` 指向 Proma 自带的 hermes-agent venv，**绝不能**把项目依赖装进去。
- `app/server.py` 的 `socketio.run(...)` 必须带 `allow_unsafe_werkzeug=True`（新版 flask-socketio 强制要求）。
- `pyproject.toml` 有 `[tool.setuptools] packages = ["app"]`，flat-layout 必需，删了 `pip install -e` 会失败。
- `.env` 不入库（.gitignore），含真实 LLM key；`.env.example` 是占位模板。LLM 配置：`LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL_ORGANIZE` + `LLM_MODEL_CHAT`。
- 记忆库根目录 `data/`（.gitignore 忽略），按 game_id 分库。冒烟测试时 `ORGANIZE_BATCH_SIZE` 临时设 5（sample 7 行才触发整理），正式用可调回 20。
- DeepSeek 端点：`https://api.deepseek.com`（不要加 /v1，openai SDK 会自动拼）。模型：`deepseek-chat` / `deepseek-reasoner`。Proma Cloud 的 key 能列模型但不能调 chat（401），故改用 DeepSeek。

## v2 Textractor 通道（已实现）

真实抓取：Textractor + textractor_websocket 扩展在 `ws://localhost:6677` 起 WS 服务端，本应用的 `app/textractor.py` `TextractorBridge` 作为 WS 客户端后台线程连接，收到纯文本帧 → `make_event` 包成 `LineEvent(source="textractor")` → 复用 `ingest`。安装见 `docs/textractor-setup.md`。

**关键约定（改了会出错）**：
- `TextractorBridge._run` 的 `ws.run_forever(ping_interval=30, ping_timeout=8)`：**ping_interval 必须 > ping_timeout**，否则 websocket-client 抛 `WebSocketException("Ensure ping_interval > ping_timeout")` 且被 except 静默吞掉，bridge 永远连不上（v2 调试踩过的坑）。
- bridge 的 except **要打印异常**，不能 `except: pass`，否则连接问题静默无从排查。
- `app/server.py` 的 `__main__` 用 `WERKZEUG_RUN_MAIN` 守卫：debug reloader 下父进程重跑 `__main__`，只在子进程（`WERKZEUG_RUN_MAIN=true`）起 bridge，避免双进程重复连 Textractor / 重复落盘 / 重复调 LLM。
- 协议事实（kuroahna/textractor_websocket `lib.rs`）：扩展只在"用户选中文本线程"时发，消息是**纯文本字符串**，无 JSON、无说话人名、无线程号。
- mock 服务 `dev/mock_textractor.py` 在 :6677 模仿 Textractor 广播 sample，无 Textractor 时用它测（注意 mock 每次连上重发全部行，真 Textractor 不重复）。`dev/bridge_test.py`、`dev/e2e_check.py` 是开发测试工具。
- 依赖：`websocket-client`（WS 客户端，运行时）、`websockets`（mock 服务端，dev）。

## 仓库与本地

- 远程：`https://github.com/wenjianmin24-pixel/galgame-notes-assistant`（私有）
- 本地：`C:\Users\温建民\projects\galgame-notes-assistant`
- git 凭据已存进用户主目录的 git credential store，`git push`/`git fetch` 无需再输 token。
- **不要**把 token 写进项目文件或 .git/config。凭据从 mcp.json 或 credential store 取。

## 待迭代（v3）

- ~~Textractor WebSocket 通道~~ ✅ 已实现（v2）
- PaddleOCR 通道（截屏去重 + 手动框选区域存 meta.json）
- 向量检索（跨全本台词精准捞取，替代"近期窗口"）
- Tauri 迁移（前端代码可复用）
- 自动线路推断（v1 用手动路标）
- characters.md 当前未被整理器单独维护（笔记里含人物表，但 characters.md 还是空）——后续可让整理器同步产出。
