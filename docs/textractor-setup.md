# Textractor 接入指引

本应用通过 [Textractor](https://github.com/Artikash/Textractor) + [textractor_websocket](https://github.com/kuroahna/textractor_websocket) 扩展实时抓取 galgame 台词。Textractor 抓到文本 → 扩展在 `ws://localhost:6677` 起 WebSocket 服务端 → 本应用自动连上收台词。

## 一次配置

### 1. 装 Textractor

- 去 https://github.com/Artikash/Textractor/releases 下载最新 Release（`Textractor-...zip`），解压到任意目录。
- 目录结构里有 `x86/Textractor.exe` 和 `x64/Textractor.exe` 两个版本——用哪个取决于你的游戏（多数现代游戏用 x64，老游戏/部分日文游戏用 x86）。两个都装扩展即可，按需启动对应版本。

### 2. 装 textractor_websocket 扩展

- 去 https://github.com/kuroahna/textractor_websocket/releases/latest 下载两个 zip：
  - `textractor_websocket_x86.zip`
  - `textractor_websocket_x64.zip`
- 解压：
  - x86 的 `textractor_websocket_x86.dll` 放进 `Textractor/x86/`
  - x64 的 `textractor_websocket_x64.dll` 放进 `Textractor/x64/`
- 启动 `Textractor/x64/Textractor.exe`（或 x86），点 **Extensions** → 在扩展对话框里**右键** → **Add extension** → 文件类型下拉从 `*.xdll` 改成 `*.dll` → 选刚才放的 `textractor_websocket_x64.dll`。x86 版同理。
- 扩展出现在扩展列表里即加载成功。

### 3. 验证本应用连上

- 启动本应用：`.venv\Scripts\python.exe -m app.server`
- 浏览器打开 `http://127.0.0.1:5000`，masthead 右侧的 Textractor 状态点应变琥珀色 + "Textractor 已连"。没变就见下面故障排查。

## 用法

1. 启动 Textractor（选对应你游戏的 x86/x64 版本）
2. 启动你的 galgame
3. 在 Textractor 里 **Attach** 到游戏进程（Ctrl+A 或菜单）
4. Textractor 会扫出一堆"文本线程"（thread）——在 Textractor 主窗口的线程列表里找到**正文台词**那个线程并**选中**它
5. 选中后，扩展只在"用户选中的线程"有新句子时才广播——所以游戏里每出一句新台词，本应用左栏就实时出现一张 VN 对话卡，攒够 N 条（`ORGANIZE_BATCH_SIZE`，默认 20）自动整理成笔记

## 选线程技巧

- galgame 通常有多个线程：窗口标题、系统提示、历史记录、回溯、正文等。**选正文那个**（一般文本最长、最像对话）。
- 选错会抓到无关文本（系统日志、菜单字），笔记就乱了。换选其他线程即可，无需重启。
- 部分游戏正文线程要等游戏推进到第一句台词后才出现。

## 故障排查

- **状态点一直"待连"**：① 确认 Textractor 开着；② 确认扩展加载了（Extensions 列表里有）；③ 确认在 Textractor 里**选中了一个文本线程**（扩展只在有选中线程时才发）；④ 确认 `:6677` 没被别的程序占用（`netstat -ano | findstr :6677`）；⑤ 本应用和 Textractor 在同一台机器。
- **连上了但没有台词进来**：游戏没推进到新台词，或选错了线程（选的是不更新的线程）。换线程。
- **台词乱码**：Textractor 的文本编码钩子问题，换 H-code 或在 Textractor 里调编码；本应用原样存储，乱码会进笔记。
- **没有说话人名**：正常。扩展只发纯文本，不带说话人。部分游戏文本里自带名字（会被识别），否则 AI 会从上下文推断。

## 无 Textractor 也能测试

开发/演示时可用 mock 服务代替真 Textractor：

```bash
# 终端 A：起 mock（在 :6677 广播 sample 台词）
.venv\Scripts\python.exe dev\mock_textractor.py samples\sample_lines.txt 0.5
# 终端 B：起本应用
.venv\Scripts\python.exe -m app.server
```

mock 会模仿 Textractor 连续推台词，本应用状态点变琥珀、台词流入、笔记生成。注意 mock 每次连上会重发全部 sample 行（真 Textractor 不会重复）。
