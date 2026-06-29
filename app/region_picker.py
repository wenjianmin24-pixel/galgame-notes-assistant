"""屏幕区域框选工具 — tkinter 全屏半透明窗口，鼠标拖拽画框。

独立脚本：python -m app.region_picker
stdout 输出选中区域的 JSON：{"x":..,"y":..,"w":..,"h":..}
取消 / ESC 则输出 null。
"""
import json
import sys
import tkinter as tk


def pick_region() -> dict | None:
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.30)  # 半透明遮罩
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.config(cursor="cross")

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    canvas = tk.Canvas(root, bg="black", width=sw, height=sh, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # 顶部提示文字
    canvas.create_text(
        sw // 2, 40,
        text="拖动鼠标框选游戏台词区域 · ESC 取消 · 松开鼠标确认",
        fill="white", font=("Microsoft YaHei", 16, "bold"),
    )

    state = {"start": None, "rect": None, "result": None}

    def on_press(e):
        state["start"] = (e.x, e.y)
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#C9842C", width=2, fill="",
        )

    def on_drag(e):
        if state["start"] and state["rect"]:
            x0, y0 = state["start"]
            canvas.coords(state["rect"], x0, y0, e.x, e.y)

    def on_release(e):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = e.x, e.y
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < 10 or h < 10:  # 太小忽略
            state["start"] = None
            return
        state["result"] = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        root.destroy()

    def on_escape(e):
        state["result"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.mainloop()
    return state["result"]


if __name__ == "__main__":
    result = pick_region()
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
