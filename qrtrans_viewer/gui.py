from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageTk
from .core import ViewerState, list_images, write_config


def report_error(msg: str) -> None:
    """Windowed 安全的错误上报：优先 Tk 弹窗（windowed 下 stderr=None），退回 print，绝不抛。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("qrtrans-viewer", msg)
        r.destroy()
        return
    except Exception:
        pass
    try:
        if sys.stderr is not None:
            print(f"error: {msg}", file=sys.stderr)
    except Exception:
        pass


def _enable_dpi_awareness():
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass  # 非 Windows 或无 API


def run(target: Path, interval: float, loop: bool, overlay: bool) -> int:
    import tkinter as tk
    from tkinter import Label

    images = list_images(target)
    if not images:
        report_error(f"no images found in {target}")
        return 2

    _enable_dpi_awareness()
    root = tk.Tk()
    root.update_idletasks()
    screen = (root.winfo_screenwidth(), root.winfo_screenheight())
    if screen[0] > 100 and screen[1] > 100:
        write_config(screen)   # best-effort 写 ./qrtrans.json

    state = ViewerState(images=images, index=0, playing=False,
                        interval=interval, loop=loop)
    overlay_on = [overlay]   # 可变，供 O 键翻转

    root.attributes("-fullscreen", True)
    try:
        root.overrideredirect(True)
        root.geometry(f"{screen[0]}x{screen[1]}+0+0")
    except Exception:
        pass
    root.configure(bg="black")

    img_label = Label(root, bg="black")
    img_label.pack(fill="both", expand=True)
    info_label = Label(root, bg="black", fg="white", anchor="sw", justify="left")
    info_label.place(x=8, rely=1.0, y=-8, anchor="sw")

    hint_label = Label(root, bg="black", fg="#ffd24d", anchor="nw", justify="left")
    hint_label.place(x=8, y=8, anchor="nw")
    hint_timer = {"id": None}

    cache = {"cur_index": -1, "cur": None, "next_index": -1, "next": None}

    def _load(idx):
        with Image.open(images[idx]) as im:
            im.load()
            return ImageTk.PhotoImage(im)

    def _ensure_current():
        # 若当前 index 已在 next 缓存里 → 提升为 cur，免重解码
        if state.index == cache["next_index"] and cache["next"] is not None:
            cache["cur"] = cache["next"]; cache["cur_index"] = cache["next_index"]
            cache["next"] = None; cache["next_index"] = -1
        elif state.index != cache["cur_index"] or cache["cur"] is None:
            try:
                cache["cur"] = _load(state.index); cache["cur_index"] = state.index
            except Exception:
                pass  # 坏图保留旧
        # 预加载下一张
        ni = state.index + 1
        if 0 <= ni < len(images) and ni != cache["next_index"]:
            try:
                cache["next"] = _load(ni); cache["next_index"] = ni
            except Exception:
                cache["next"] = None; cache["next_index"] = -1

    def _render():
        _ensure_current()
        img_label.configure(image=cache["cur"])
        if overlay_on[0]:
            mark = "▶" if state.playing else "⏸"
            info_label.configure(text=f"{images[state.index].name} · {state.index+1}/{len(images)} · "
                                      f"{state.interval:.1f}s · {mark}")
            info_label.lift()
        else:
            info_label.configure(text="")

    def _show_hint():
        w, h = screen
        hint_label.configure(text=f"本机分辨率 {w}x{h}\n编码请用 --screen {w}x{h} 匹配以 1:1 铺满")
        hint_label.lift()
        def _clear():
            hint_label.configure(text="")
            hint_timer["id"] = None
        hint_timer["id"] = root.after(3000, _clear)

    timer = {"id": None}

    def _schedule():
        if timer["id"] is not None:
            try:
                root.after_cancel(timer["id"])
            except Exception:
                pass
        if state.playing:
            timer["id"] = root.after(int(state.interval * 1000), _tick)

    def _tick():
        if state.advance() is not None:
            _render(); _schedule()
        else:
            _render()   # 末尾自动暂停

    def _next():
        state.next(); _render(); _schedule()

    def _prev():
        state.prev(); _render(); _schedule()

    def _toggle_play():
        state.playing = not state.playing; _render(); _schedule()

    def _bump(d):
        state.bump_interval(d); _render(); _schedule()

    def _toggle_overlay():
        overlay_on[0] = not overlay_on[0]; _render()

    def _quit():
        if hint_timer["id"] is not None:
            try:
                root.after_cancel(hint_timer["id"])
            except Exception:
                pass
        root.destroy()

    root.bind("<Right>", lambda e: _next())
    root.bind("<space>", lambda e: _next())
    root.bind("<Left>", lambda e: _prev())
    root.bind("p", lambda e: _toggle_play())
    root.bind("P", lambda e: _toggle_play())
    root.bind("<plus>", lambda e: _bump(0.5))
    root.bind("<equal>", lambda e: _bump(0.5))
    root.bind("<minus>", lambda e: _bump(-0.5))
    root.bind("o", lambda e: _toggle_overlay())
    root.bind("O", lambda e: _toggle_overlay())
    root.bind("<Home>", lambda e: (state.first(), _render(), _schedule()))
    root.bind("<End>", lambda e: (state.last(), _render(), _schedule()))
    root.bind("<Escape>", lambda e: _quit())
    root.bind("q", lambda e: _quit())
    root.bind("Q", lambda e: _quit())

    _render()
    _show_hint()
    root.mainloop()
    return 0
