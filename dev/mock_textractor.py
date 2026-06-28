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
