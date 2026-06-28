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

## 技术栈（拟定）

- Python 3.11 核心服务（常驻进程）
- Textractor + 自写 WebSocket 扩展
- PaddleOCR（本地）
- 云端 LLM（OpenAI 兼容接口）
- Tauri 或 Flask + 浏览器作为界面

## 仓库与本地

- 远程：`https://github.com/wenjianmin24-pixel/galgame-notes-assistant`（私有）
- 本地：`C:\Users\温建民\projects\galgame-notes-assistant`
- git 凭据已存进用户主目录的 git credential store，`git push`/`git fetch` 无需再输 token。
- **不要**把 token 写进项目文件或 .git/config。凭据从 mcp.json 或 credential store 取。

## 还没定的（待迭代）

见 `docs/design.md` 第 8 节"待定问题"：分支/路线标记、OCR 文本框区域检测方式、对话上下文检索（近期窗口 vs 向量检索）、界面技术选型、自动整理的"重要性"判定。
