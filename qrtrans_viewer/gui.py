from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageTk
from .core import ViewerState, list_images, write_config


def run(target: Path, interval: float, loop: bool, overlay: bool) -> int:
    import tkinter as tk
    from tkinter import Label

    images = list_images(target)
    if not images:
        print("error: no images found", file=sys.stderr)
        return 2

    root = tk.Tk()
    root.update_idletasks()
    screen = (root.winfo_screenwidth(), root.winfo_screenheight())
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

    cache = {"cur": None, "next": None}   # 防 GC + 预加载

    def _render():
        cur = images[state.index]
        im = Image.open(cur); im.load()
        cache["cur"] = ImageTk.PhotoImage(im)
        img_label.configure(image=cache["cur"])
        if state.index + 1 < len(images):
            try:
                cache["next"] = ImageTk.PhotoImage(Image.open(images[state.index + 1]))
            except Exception:
                cache["next"] = None
        if overlay_on[0]:
            mark = "▶" if state.playing else "⏸"
            info_label.configure(text=f"{cur.name} · {state.index+1}/{len(images)} · "
                                      f"{state.interval:.1f}s · {mark}")
            info_label.lift()
        else:
            info_label.configure(text="")

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
    root.mainloop()
    return 0
