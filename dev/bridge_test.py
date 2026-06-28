"""独立测试 TextractorBridge 对 mock 的连接。dev/bridge_test.py"""
import time
from app.textractor import TextractorBridge

received = []
def on_event(ev):
    received.append(ev.text)
    print(f"GOT: {ev.text!r}", flush=True)

b = TextractorBridge(url="ws://localhost:6677", game_id="test", on_event=on_event)
b.start()
print("bridge started, watching 12s...", flush=True)
for i in range(12):
    time.sleep(1)
    print(f"t={i+1} connected={b.connected} received_n={len(received)}", flush=True)
    if len(received) >= 5:
        print("got enough, stop early", flush=True)
        break
b.stop()
print(f"TOTAL received: {len(received)}", flush=True)
