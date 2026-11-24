# -*- coding: utf-8 -*-
"""이미지 파일 인쇄 창 (PrinterTester · PrinterTestPOS 공용).

파일 선택 → 미리보기(실제 찍힐 흑백 그대로) → 너비·방식·정렬·밝기·대비 조정 → [인쇄].
ask_image(...) 는 인쇄할 ESC/POS 바이트와 이름을 돌려주고, 취소하면 None.
"""
import os
import tkinter as tk
from tkinter import filedialog, ttk

from PIL import ImageTk

import imageprint

PREVIEW_W, PREVIEW_H = 288, 420
WIDTHS = ("100", "75", "50", "25")


class ImageDialog:
    def __init__(self, parent, dots=576, cut="partial", font=None, path=None):
        self.dots, self.cut = int(dots), cut
        self.result = None
        self.src = self.bw = self.photo = None
        self.path = None
        self._job = None
        t = self.top = tk.Toplevel(parent)
        t.title("이미지 파일 인쇄")
        t.transient(parent)
        t.resizable(False, False)
        f = font
        kw = {"font": f} if f else {}

        left = ttk.Frame(t, padding=10)
        left.pack(side="left", fill="y")
        self.canvas = tk.Canvas(left, width=PREVIEW_W, height=PREVIEW_H, bg="#9CA3AF", highlightthickness=0)
        self.canvas.pack()
        self.info = tk.Label(left, text="", fg="#4B5563", wraplength=PREVIEW_W, justify="left", **kw)
        self.info.pack(anchor="w", pady=(6, 0))

        right = ttk.Frame(t, padding=10)
        right.pack(side="left", fill="both")
        tk.Button(right, text="파일 선택…", command=self.pick, padx=12, pady=6, **kw).grid(
            row=0, column=0, columnspan=2, sticky="we")
        self.name = tk.Label(right, text="(파일을 선택하세요)", fg="#6B7280", wraplength=260, **kw)
        self.name.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        self.v_width = tk.StringVar(value="100")
        self.v_mode = tk.StringVar(value="photo")
        self.v_align = tk.StringVar(value=imageprint.ALIGNS["center"])
        self.v_bright = tk.IntVar(value=0)
        self.v_contrast = tk.IntVar(value=0)
        row = 2
        tk.Label(right, text="너비 (%)", **kw).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(right, textvariable=self.v_width, values=WIDTHS, width=6, state="readonly").grid(
            row=row, column=1, sticky="w")
        row += 1
        tk.Label(right, text="방식", **kw).grid(row=row, column=0, sticky="nw", pady=4)
        mf = ttk.Frame(right)
        mf.grid(row=row, column=1, sticky="w")
        for k, txt in imageprint.MODES.items():
            tk.Radiobutton(mf, text=txt, value=k, variable=self.v_mode, command=self.refresh, **kw).pack(anchor="w")
        row += 1
        tk.Label(right, text="정렬", **kw).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(right, textvariable=self.v_align, values=tuple(imageprint.ALIGNS.values()), width=8,
                     state="readonly").grid(row=row, column=1, sticky="w")
        for label, var in (("밝기", self.v_bright), ("대비", self.v_contrast)):
            row += 1
            tk.Label(right, text=label, **kw).grid(row=row, column=0, sticky="w", pady=4)
            tk.Scale(right, from_=-50, to=50, orient="horizontal", variable=var, length=180, resolution=5,
                     command=lambda _v: self.refresh()).grid(row=row, column=1, sticky="w")
        row += 1
        tk.Label(right, justify="left", fg="#6B7280", **kw, text=(
            "· 사진: 회색을 점 밀도로 표현\n· 로고·글자: 검정/흰색만, 선명하게\n"
            "· 어두우면 밝기를 올리세요")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row += 1
        bf = ttk.Frame(right)
        bf.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))
        self.print_btn = tk.Button(bf, text="인쇄", command=self.ok, bg="#059669", fg="white", padx=24, pady=6,
                                   state="disabled", **kw)
        self.print_btn.pack(side="left", padx=4)
        tk.Button(bf, text="취소", command=t.destroy, padx=16, pady=6, **kw).pack(side="left")
        for v in (self.v_width, self.v_align):
            v.trace_add("write", lambda *_: self.refresh())

        t.protocol("WM_DELETE_WINDOW", t.destroy)
        t.grab_set()
        if path:
            self.open(path)
        else:
            t.after(50, self.pick)

    def pick(self):
        path = filedialog.askopenfilename(parent=self.top, title="인쇄할 이미지 선택", filetypes=imageprint.FILETYPES)
        if path:
            self.open(path)

    def open(self, path):
        try:
            self.src = imageprint.load(path)
        except (OSError, ValueError) as e:
            self.src = None
            self.name.config(text=f"열 수 없는 파일입니다: {e}", fg="#DC2626")
            self.print_btn.config(state="disabled")
            return
        self.path = path
        self.name.config(text=os.path.basename(path), fg="#1F2937")
        self.refresh()

    def params(self):
        align = {t: k for k, t in imageprint.ALIGNS.items()}.get(self.v_align.get(), "center")
        return dict(dots=self.dots, width_pct=int(self.v_width.get() or 100), mode=self.v_mode.get(),
                    brightness=self.v_bright.get(), contrast=self.v_contrast.get(), align=align)

    def refresh(self):
        # 슬라이더를 끄는 동안 매번 변환하지 않도록 잠깐 모아서 한 번에
        if self._job:
            self.top.after_cancel(self._job)
        self._job = self.top.after(120, self._render)

    def _render(self):
        self._job = None
        if self.src is None:
            return
        self.bw = imageprint.convert(self.src, **self.params())
        scale = min(PREVIEW_W / self.bw.width, PREVIEW_H / self.bw.height)
        pv = self.bw.convert("L").resize((max(1, int(self.bw.width * scale)), max(1, int(self.bw.height * scale))))
        self.photo = ImageTk.PhotoImage(pv)
        self.canvas.delete("all")
        self.canvas.create_image(PREVIEW_W // 2, 0, image=self.photo, anchor="n")
        self.info.config(text=imageprint.info(self.src, self.bw))
        self.print_btn.config(state="normal")

    def ok(self):
        if self._job:                       # 마지막 조정이 아직 반영되지 않았으면 먼저 반영
            self.top.after_cancel(self._job)
            self._render()
        if self.bw is None:
            return
        self.result = (imageprint.to_escpos(self.bw, cut=self.cut), os.path.basename(self.path))
        self.top.destroy()


def ask_image(parent, dots=576, cut="partial", font=None):
    """창을 띄워 기다린 뒤 (ESC/POS 바이트, 파일 이름) 또는 None."""
    d = ImageDialog(parent, dots, cut, font)
    parent.wait_window(d.top)
    return d.result
