# galgame-notes-assistant

AI 笔记助手 for galgame / 视觉小说：游玩时实时抓取屏幕上的文本，自动整理成结构化笔记（人物、场景、事件、伏笔、选项分支），还能和一个"懂你正在玩什么游戏"的 AI 讨论剧情。

## 解决什么痛点

玩 galgame / 视觉小说时内容量大，边玩边手动记笔记会频繁打断沉浸感。本项目的目标是让 AI 在后台实时记录重要文本，玩完一段就有现成笔记可看，并随时能就剧情提问、讨论，讨论中的发现回填进笔记。

## 抓取方式（双通道）

- **主通道 — Textractor（内存文本钩子）**：用于 PC 原生引擎的 galgame。准确、零延迟、能拿到说话人名字，中文日文都吃。
- **兜底通道 — 截屏 + OCR**：用于 Textractor 抓不到的场景（模拟器、非传统引擎视觉小说）。本地 PaddleOCR，按窗口/区域定时截屏并去重，仅在文本变化时推送新台词。

两条通道汇成统一台词流，下游 AI 层不关心文本来自哪条。

## 规划特性

- 实时台词抓取（双通道，自动切换）
- 自动整理结构化笔记：人物表、场景/章节、关键事件、伏笔、选项分支
- 按游戏分库的本地记忆（Markdown，人可读可改）
- 剧情感知的对话陪读（检索近期台词 + 笔记 + 人物表作上下文）
- 与游戏并排显示的轻量界面（实时台词流 / 笔记视图 / 聊天框）

## 状态

设计阶段。完整设计见 [docs/design.md](docs/design.md)。

## 技术栈（拟定）

- Python 3.11 核心服务（常驻进程）
- Textractor（已有工具）+ WebSocket 扩展
- PaddleOCR（本地，中日文）
- 云端 LLM（OpenAI 兼容接口：Proma Cloud / DeepSeek / Qwen / Gemini）
- Tauri 或 Flask + 浏览器作为界面
- 本地 Markdown 文件作为记忆库

## 运行（v1 MVP）

v1 用文件回放注入器模拟抓取，已跑通"台词入库 → AI 自动整理笔记 → 剧情对话"核心管线。

```bash
# 1. 装依赖（项目专用 venv，别用系统 python）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. 配置 .env（从 .env.example 复制，填你的 LLM key；默认 DeepSeek 官方）
copy .env.example .env

# 3. 启动服务
.venv\Scripts\python.exe -m app.server

# 4. 浏览器打开 http://127.0.0.1:5000
#    点"回放 sample_lines.txt"喂台词 → 攒够 N 条自动整理笔记 → 在聊天框问剧情
```

记忆库落在 `data/<game_id>/`（`transcript.md` 原始台词、`notes.md` AI 笔记、`characters.md`、`meta.json`）。`data/` 和 `.env` 不入库。

## 真实抓取（Textractor，v2）

接上真实 galgame：装 [Textractor](https://github.com/Artikash/Textractor) + [textractor_websocket](https://github.com/kuroahna/textractor_websocket) 扩展，启动本应用后状态点变琥珀即连上。游戏里每出一句新台词，左栏实时出现对话卡，攒够 N 条自动整理成笔记。完整安装与选线程指引见 [docs/textractor-setup.md](docs/textractor-setup.md)。

无 Textractor 时可用 mock 服务测：`.venv\Scripts\python.exe dev\mock_textractor.py samples\sample_lines.txt 0.5`（在 :6677 模仿 Textractor）。

测试：`.venv\Scripts\python.exe -m pytest`

设计文档见 [docs/design.md](docs/design.md)，实现计划见 [docs/plans/](docs/plans/)。

