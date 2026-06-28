# v2: Textractor 通道 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把"喂台词的源头"从 v1 的文件回放注入器换成真实 Textractor：Python WebSocket 客户端连 Textractor 的 `textractor_websocket` 扩展（`ws://localhost:6677`），收实时台词喂进已有 ingest 管线。附 mock WS 服务供无 Textractor 开发测试。

**Architecture:** Textractor（用户安装 + 装 textractor_websocket 扩展 DLL）→ 在 `ws://localhost:6677` 起 WS 服务端，把"用户选中文本线程"的句子作为纯文本帧广播 → 我们的 `TextractorBridge`（后台线程 + 自动重连）作为 WS 客户端接收 → `make_event()` 包成 `LineEvent(source="textractor")` → 复用 v1 的 `ingest()`（去重 → 落盘 transcript → 触发整理）。mock WS 服务（`dev/mock_textractor.py`）模仿 Textractor 在 :6677 广播 sample 台词，用于开发测试。

**Tech Stack:** Python 3.11、`websocket-client`（WS 客户端）、`websockets`（mock WS 服务端，dev only）、复用 v1 的 Flask/SocketIO/ingest/organizer/chat。

**协议事实**（来自 kuroahna/textractor_websocket `lib.rs`）：
- 扩展的 `OnNewSentence` 只在 `current_select == 用户选中文本线程` 且 `text_number == TextThread` 时发送。
- 消息内容是**纯文本字符串**（无 JSON、无说话人名、无线程号）。
- 说话人名不单独给（部分游戏文本里带名字，AI 也能从上下文推断——与设计预期一致）。

---

## Task 1: websocket-client 依赖 + TextractorBridge

**Files:**
- Modify: `pyproject.toml`（加 `websocket-client`）
- Create: `app/textractor.py`
- Create: `tests/test_textractor.py`

**Step 1: 改 pyproject.toml**

在 `dependencies` 里加 `"websocket-client>=1.7",`（保持 `[tool.setuptools] packages = ["app"]` 不动）。然后 `.venv\Scripts\python.exe -m pip install -e ".[dev]"`。

**Step 2: 写失败测试 tests/test_textractor.py**

```python
from app.textractor import make_event

def test_make_event_basic():
    ev = make_event("你好", "g1")
    assert ev.text == "你好"
    assert ev.game_id == "g1"
    assert ev.source == "textractor"
    assert ev.speaker is None
    assert ev.ts is not None  # 默认时间戳已填

def test_make_event_with_explicit_ts():
    ev = make_event("你好", "g1", ts=123.0)
    assert ev.ts == 123.0

def test_make_event_empty_text_still_wraps():
    # 即使空文本也包成事件，去重由 ingest 负责
    ev = make_event("", "g1")
    assert ev.text == ""
    assert ev.source == "textractor"
```

**Step 3: 验证失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_textractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.textractor'`

**Step 4: 写 app/textractor.py**

```python
from threading import Thread, Event
from time import sleep

from app.capture import LineEvent

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None


def make_event(text, game_id, ts=None):
    """把 Textractor 推来的纯文本包成 LineEvent。纯函数，便于测试。"""
    kw = {"game_id": game_id, "source": "textractor", "text": text}
    if ts is not None:
        kw["ts"] = ts
    return LineEvent(**kw)


class TextractorBridge:
    """连 Textractor 的 textractor_websocket 扩展（ws://localhost:6677）。
    收到文本就回调 on_event。Textractor 没开时自动重连。"""

    def __init__(self, url="ws://localhost:6677", game_id="default", on_event=None):
        self.url = url
        self.game_id = game_id
        self.on_event = on_event
        self._stop = Event()
        self._thread = None
        self.connected = False

    def set_game(self, game_id):
        self.game_id = game_id

    def start(self):
        if websocket is None:
            raise RuntimeError("websocket-client 未安装：pip install websocket-client")
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=lambda ws, e: setattr(self, "connected", False),
                    on_close=lambda ws, *a: setattr(self, "connected", False),
                )
                ws.run_forever(ping_interval=10, ping_timeout=10)
            except Exception:
                pass
            self.connected = False
            # 重连间隔 ~5s（Textractor 可能还没开）
            for _ in range(20):
                if self._stop.is_set():
                    return
                sleep(0.25)

    def _on_open(self, ws):
        self.connected = True

    def _on_message(self, ws, msg):
        if not msg or self.on_event is None:
            return
        self.on_event(make_event(msg, self.game_id))
```

**Step 5: 验证通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_textractor.py -v`
Expected: 3 passed

**Step 6: Commit**

```bash
git add pyproject.toml app/textractor.py tests/test_textractor.py
git commit -m "feat(textractor): WebSocket 客户端 bridge + make_event"
```

---

## Task 2: mock Textractor WS 服务（开发测试用）

**Files:**
- Modify: `pyproject.toml`（dev 依赖加 `websockets`）
- Create: `dev/mock_textractor.py`

**Step 1: 改 pyproject.toml**

`[project.optional-dependencies]` 的 `dev` 改成 `dev = ["pytest>=8.0", "websockets>=12.0"]`。然后 `pip install -e ".[dev]"`。

**Step 2: 写 dev/mock_textractor.py**

```python
"""模仿 Textractor 的 textractor_websocket 扩展：在 ws://localhost:6677 广播台词。
用法: .venv\\Scripts\\python.exe dev\\mock_textractor.py [样本文件] [间隔秒]
不装 Textractor 也能测 TextractorBridge。"""
import asyncio
import sys

import websockets

async def handler(ws):
    path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_lines.txt"
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    for line in lines:
        await ws.send(line)
        await asyncio.sleep(interval)

async def main():
    async with websockets.serve(handler, "localhost", 6677):
        print("mock Textractor WS serving on ws://localhost:6677")
        await asyncio.Future()  # 永久运行

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: 手测 mock 服务**

开两个终端：
- 终端 A: `.venv\Scripts\python.exe dev\mock_textractor.py samples\sample_lines.txt 0.5`
- 终端 B（一次性收一句验证）:
```
.venv\Scripts\python.exe -c "import websocket; ws=websocket.create_connection('ws://localhost:6677'); print(ws.recv()); ws.close()"
```
Expected: 终端 B 打印 sample 第一句（如 `【主角】今天天气不错。`）

**Step 4: Commit**

```bash
git add pyproject.toml dev/mock_textractor.py
git commit -m "dev: mock Textractor WS 服务"
```

---

## Task 3: 把 bridge 接进 server（active game + 状态接口）

**Files:**
- Modify: `app/server.py`

**目标**：服务启动时起 TextractorBridge（自动重连，Textractor 没开也不报错）；维护 `active_game`；加 `/api/game` 设当前游戏、`/api/textractor/status` 查连接状态；连接状态变化时 socketio 推送。

**Step 1: 改 app/server.py**

在 import 区加：
```python
from app.textractor import TextractorBridge
from app.memory import slugify
```

在 `deduper = LineDeduper()` 后面加：
```python
active_game = "default"
bridge = TextractorBridge(game_id=active_game, on_event=ingest)

def set_active_game(name):
    global active_game
    active_game = slugify(name) if name else "default"
    bridge.set_game(active_game)

def emit_status():
    socketio.emit("textractor_status", {
        "connected": bridge.connected,
        "running": bridge._thread is not None and bridge._thread.is_alive(),
        "game_id": active_game,
    })
```

注意 `bridge` 在 `ingest` 之后定义（`ingest` 引用了 `get_store`/`organizers`，`bridge` 的 `on_event=ingest` 需要 ingest 已定义——确认 ingest 在 bridge 之前定义）。

修改 `get_store` 里对 `organizers` 的初始化仍用 `active_game`？不——get_store 接收显式 game_id，不变。但 ingest 里用 `ev.game_id`，bridge 喂的 ev.game_id = active_game，所以落到 active_game 的库。good。

在所有路由之后、`if __name__ == "__main__"` 之前加路由：
```python
@app.post("/api/game")
def post_game():
    global active_game
    d = request.json
    set_active_game(d.get("name", ""))
    emit_status()
    return jsonify(ok=True, game_id=active_game)

@app.get("/api/textractor/status")
def textractor_status():
    return jsonify(connected=bridge.connected,
                   running=bridge._thread is not None and bridge._thread.is_alive(),
                   game_id=active_game)
```

修改 `__main__` 块，启动前 try 起 bridge（websocket-client 没装就跳过）：
```python
if __name__ == "__main__":
    try:
        bridge.start()
        print("Textractor bridge started (ws://localhost:6677)")
    except RuntimeError as e:
        print(f"Textractor bridge 未启动: {e}")
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
```

**Step 2: 验证导入**

Run: `.venv\Scripts\python.exe -c "from app.server import app, bridge; print('ok', bridge.url)"`
Expected: `ok ws://localhost:6677`

**Step 3: Commit**

```bash
git add app/server.py
git commit -m "feat(server): 接入 TextractorBridge + active_game + 状态接口"
```

---

## Task 4: UI 加游戏名输入 + Textractor 状态

**Files:**
- Modify: `web/templates/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`

**Step 1: index.html masthead 加游戏名输入 + 状态点**

把 `<button id="themeToggle" ...>` 那行前面加一个游戏名输入和状态指示：
```html
  <header class="masthead">
    <div class="masthead-title">伴读</div>
    <div class="masthead-sub">一边玩，一边记</div>
    <div class="game-picker">
      <input id="gameName" class="field field-game" placeholder="当前游戏名" value="default">
    </div>
    <div id="txStatus" class="tx-status" title="Textractor 连接状态">
      <span class="dot"></span><span class="tx-label">Textractor</span>
    </div>
    <button id="themeToggle" class="btn btn-ghost btn-sm theme-toggle" type="button">日间</button>
  </header>
```

**Step 2: app.js —— game_id 改成动态 + 状态轮询**

把 `const GAME_ID = "default";` 改成：
```javascript
let GAME_ID = localStorage.getItem("gameName") || "default";
const gameNameEl = document.getElementById("gameName");
gameNameEl.value = GAME_ID;

async function setGame(name) {
  GAME_ID = (name || "default").trim() || "default";
  localStorage.setItem("gameName", GAME_ID);
  await fetch("/api/game", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ name: GAME_ID }) });
}
gameNameEl.addEventListener("change", () => setGame(gameNameEl.value));
gameNameEl.addEventListener("keydown", (e) => { if (e.key === "Enter") gameNameEl.blur(); });
setGame(GAME_ID);  // 启动时同步给服务端
```

把所有 `GAME_ID` 用法（post body 里的 `game_id: GAME_ID`）保持不变——现在是动态变量。

加 Textractor 状态轮询（替换 refreshNotes 之前）：
```javascript
const txStatusEl = document.getElementById("txStatus");
async function pollTxStatus() {
  try {
    const d = await (await fetch("/api/textractor/status")).json();
    txStatusEl.classList.toggle("on", !!d.connected);
    txStatusEl.querySelector(".tx-label").textContent =
      d.connected ? "Textractor 已连" : (d.running ? "Textractor 待连" : "Textractor 未启");
  } catch (e) {}
}
pollTxStatus();
setInterval(pollTxStatus, 3000);
socket.on("textractor_status", () => pollTxStatus());
```

**Step 3: style.css 加样式**

```css
.game-picker { margin-left: auto; align-self: center; }
.field-game { padding: 6px 10px; font-size: 12px; width: 150px; }
.tx-status {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--sans); font-size: 11px; color: var(--muted);
  letter-spacing: 0.06em; align-self: center;
}
.tx-status .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--muted-2); transition: background 200ms ease;
}
.tx-status.on .dot { background: var(--accent); box-shadow: 0 0 6px var(--accent); }
@media (max-width: 960px) {
  .game-picker, .tx-status { margin-left: 0; }
}
```

**Step 4: 验证**

启动服务，浏览器打开，确认：游戏名输入框在、状态点显示"Textractor 未启"（bridge 已起但没连 Textractor）。改游戏名回车，`/api/game` 被调用。

**Step 5: Commit**

```bash
git add web/
git commit -m "feat(ui): 游戏名输入 + Textractor 连接状态指示"
```

---

## Task 5: 集成测试（mock Textractor 端到端）

**目标**：不装 Textractor，用 mock WS 服务验证整条真实抓取链路。

**Step 1: 清数据 + 启动 mock + 启动服务**

三个终端 / 后台进程：
- `.venv\Scripts\python.exe dev\mock_textractor.py samples\sample_lines.txt 0.5`（占 :6677）
- `.venv\Scripts\python.exe -m app.server`（:5000，bridge 连 :6677）
- 浏览器开 `http://127.0.0.1:5000`

**Step 2: 验证状态点变"已连"**

UI 状态点应变琥珀色 + "Textractor 已连"（bridge 连上了 mock）。

**Step 3: 验证台词流入 + 笔记生成**

mock 广播 7 句 → 左栏实时出现 VN 对话卡 → 攒够 5 条（ORGANIZE_BATCH_SIZE=5）触发整理 → 右栏笔记由 DeepSeek 生成。

**Step 4: 验证落盘**

`cat data/default/transcript.md` 应含 7 句；`cat data/default/notes.md` 应有结构化笔记。

**Step 5: 跑全量测试**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 全绿（v1 的 18 + Task 1 的 3 = 21 passed）

**Step 6: Commit（如有修复）**

```bash
git add -A
git commit -m "test: mock Textractor 端到端通过"
```

---

## Task 6: Textractor 安装指引 + 文档更新

**Files:**
- Create: `docs/textractor-setup.md`
- Modify: `CLAUDE.md`、`README.md`

**Step 1: 写 docs/textractor-setup.md**

包含：
1. 下载 Textractor：https://github.com/Artikash/Textractor/releases （最新 Release，解压）
2. 装 textractor_websocket 扩展：
   - 从 https://github.com/kuroahna/textractor_websocket/releases/latest 下载 `textractor_websocket_x86.zip` 和 `_x64.zip`
   - x86 DLL 放 `Textractor/x86/`，x64 DLL 放 `Textractor/x64/`
   - 开 Textractor（x86 或 x64 对应你的游戏），Extensions → 右键 → Add extension → 文件类型选 `*.dll` → 选对应 `textractor_websocket_*.dll`
3. 用法：开 Textractor → Attach 到 galgame 进程 → 在文本线程列表里选中目标台词线程 → 扩展自动在 `ws://localhost:6677` 起服务 → 本应用自动连上（状态点变琥珀）
4. 选线程技巧：galgame 通常有多个线程（标题、历史、正文等），选"正文"那个；选错会抓到无关文本。
5. 故障：状态点一直"待连" → 确认 Textractor 开着、扩展加载了、选了线程、:6677 没被占。

**Step 2: 更新 CLAUDE.md**

在"v1 实现状态与运行"后加"v2 Textractor 通道"小节：bridge 在 `app/textractor.py`，mock 服务 `dev/mock_textractor.py`，协议事实（纯文本帧、用户选线程、无说话人），`ws://localhost:6677`，webhook-client 依赖。

**Step 3: 更新 README**

在"运行（v1 MVP）"后加"真实抓取（Textractor）"小节：装 Textractor + 扩展（链接到 docs/textractor-setup.md），启动服务后状态点变琥珀即连上；或用 `dev/mock_textractor.py` 无 Textractor 测试。

**Step 4: Commit & push**

```bash
git add docs/textractor-setup.md CLAUDE.md README.md
git commit -m "docs: Textractor 安装指引 + v2 通道文档"
git push
```

---

## 执行交接

计划保存到 `docs/plans/2026-06-28-v2-textractor-channel.md`。沿用 v1 的子 Agent 驱动：每个 Task 派子 Agent 实现，任务间我 review。Task 5 集成测试我亲自驱动（要起 mock + 服务）。Task 6 的真机测试需要你装好 Textractor + 扩展后做。
