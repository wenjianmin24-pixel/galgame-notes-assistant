# galgame-notes-assistant

AI 笔记助手 for galgame / 视觉小说——游玩时实时抓取屏幕上的文本（Textractor 钩子 + OCR 截屏双通道），云端 LLM 自动整理结构化笔记（人物表、剧情节点、伏笔、选项分支），支持按游戏分库管理和剧情感知的对话陪读。

## 当前状态

**v3/v4 已实现**，44 个单元测试全绿。核心管线全通：抓取 → 去重 → 转录落盘 → AI 自动整理笔记 → 向量增强对话陪读 → 游戏管理 → Tauri 桌面窗口。

## 抓取方式

| 通道 | 引擎 | 速度 | 精度 | 适用 |
|------|------|------|------|------|
| **Textractor**（主） | 内存文本钩子 | 即时 | ~100% | PC 原生引擎（KiriKiri / RPGMaker 等） |
| **RapidOCR**（推荐） | PP-OCRv4 + ONNX | ~150ms | 高 | 大部分 VN 字幕 |
| **Windows.Media.Ocr**（备用） | winrt 系统内置 | ~100ms | 中 | 桌面应用 |
| **AI 视觉 OCR**（高端） | GPT-4o / Qwen-VL | ~1-3s | 最高 | 特殊字体、低对比度 |

截图支持 PrintWindow（被遮挡也能抓）+ 回退 mss 屏幕截取。可在**截图上框选**台词区域，区域锚定游戏窗口客户区（窗口移动跟得住）。

## 核心功能

- **实时台词抓取**：双通道自动切换，稳定性门控（等 2 帧不动 + 4 秒兜底防打字机黑墙），像素差跳过无效帧
- **自动整理笔记**：LLM 根据新台词增量更新结构化 Markdown 笔记（人物档案 / 剧情节点 / 伏笔 / 选项分支），保留已有内容
- **向量增强对话**：transcript 全量 embedding + 余弦检索，对话时自动注入相关历史台词上下文
- **多游戏管理**：按 `data/{game_id}/` 独立分库，前端下拉切换，OCR 设置按游戏独立存储
- **多模型配置**：整理 / 对话 / embedding / 视觉 OCR 四角色各自独立端点 + API Key + 模型，留空回退全局，支持拉取模型列表 + 测试连接
- **说话人自动解析**：支持 `@name@「text」`、`【name】text`、`name「text」`、`name：text` 等六种格式
- **编码修复**：Textractor codepage 不匹配时自动多对编码评估修复
- **笔记编辑**：前端笔记面板支持随时编辑，取消即可还原

## 快速开始

```bash
# 1. 创建 venv
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ocr]"

# 2. 配置 .env
copy .env.example .env   # 填 LLM_API_KEY（默认 DeepSeek）

# 3. 启动服务
.venv\Scripts\python.exe -m app.server   # → http://127.0.0.1:5000

# 或启动 Tauri 桌面窗口
start-tauri.bat                           # → 原生窗口，无浏览器依赖
```

测试：`.venv\Scripts\python.exe -m pytest`

## 技术栈

- Python 3.11+（Flask + SocketIO）
- [Textractor](https://github.com/Artikash/Textractor) + [textractor_websocket](https://github.com/kuroahna/textractor_websocket)（内存钩子）
- RapidOCR PP-OCRv4（ONNX Runtime）+ Windows.Media.Ocr（winrt）+ AI 视觉大模型
- 云端 LLM，OpenAI 兼容接口（DeepSeek / GPT / Qwen / Gemini）
- 向量检索：纯 Python 余弦相似度（无外部依赖）
- 前端：原生 HTML/CSS/JS（Flask 模板 + SocketIO），可选 Tauri 2.x 桌面窗口
- 记忆：本地 Markdown（`data/{game_id}/transcript.md` / `notes.md` / `characters.md` / `meta.json`）

## 记忆库结构

```
data/
  default/             ← 游戏数据根（game_id）
    transcript.md      ← 原始台词流
    notes.md           ← AI 整理的结构化笔记（Markdown，可手动编辑）
    characters.md      ← 人物表
    meta.json          ← 游戏元数据 + OCR 区域等专属设置
  settings.json        ← 全局设置（LLM 端点/Key/模型等）
```

## 致谢

OCR 模型来自 [LunaTranslator](https://github.com/HIllya51/LunaTranslator)（PP-OCRv5 ONNX），后升级为 RapidOCR PP-OCRv4。OCR 稳定性门控策略、文本后处理管道、多 OCR 引擎设计参考自 Luna。

## License

MIT
