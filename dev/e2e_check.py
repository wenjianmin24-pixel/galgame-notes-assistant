"""端到端检查：轮询服务状态 + transcript + notes。dev/e2e_check.py"""
import urllib.request, json, time, sys

def get(path):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:5000" + path, timeout=3).read())

for i in range(1, 26):
    try:
        st = get("/api/textractor/status")
        n = get("/api/notes?game_id=default")
        notes_len = len(n.get("notes", "") or "")
        tcount = len([l for l in (n.get("transcript") or "").splitlines() if l.strip()])
        print(f"t={i} connected={st.get('connected')} running={st.get('running')} transcript={tcount} notes={notes_len}", flush=True)
        if notes_len > 5:
            print("NOTES READY — e2e pass", flush=True)
            sys.exit(0)
    except Exception as e:
        print(f"t={i} not ready: {type(e).__name__}", flush=True)
    time.sleep(1)
print("TIMEOUT — notes never generated", flush=True)
sys.exit(1)
