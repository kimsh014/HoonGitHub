# -*- coding: utf-8 -*-
"""POS 화면용 간단 출력 테스트 (터치 친화 GUI).

  홈(우측 상단) / RS232 · USB · BT 큰 버튼 / 설정(우측 하단)

인쇄 엔진(engine/patterns/transports)은 검증용 PrinterTester 와 같은 것을 그대로 쓴다.
설정은 pos_settings.json (exe 옆, 쓸 수 없으면 문서/PrinterTester) 에 저장된다.
"""
import copy
import datetime
import json
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import engine
from transports import TransportError, list_com_ports, list_win_printers, make_transport

SETTINGS_FILE = os.path.join(engine.BASE_DIR, "pos_settings.json")

BAUDS = ("9600", "19200", "38400", "57600", "115200")
FLOWS = ("없음", "RTS/CTS", "DTR/DSR", "XON/XOFF")
KINDS = {"COM": "COM 포트", "WinPrinter": "Windows 프린터"}
CUTS = {"partial": "부분 컷", "full": "전체 컷", "none": "컷 안 함"}

# (이름, 색, 설명)
IFACES = (("RS232", "#2563EB", "시리얼 · RJ45"),
          ("USB", "#059669", "USB B-type"),
          ("BT", "#7C3AED", "블루투스"))

# 인터페이스 화면의 인쇄 버튼: (버튼 이름, 동작 종류, 패턴 이름)
PRINT_ITEMS = (
    ("연결 확인", "pattern", "연결 확인"),
    ("영수증", "pattern", "영수증"),
    ("영수증+이미지", "pattern", "영수증+이미지"),
    ("한글", "pattern", "한글"),
    ("1D 바코드", "pattern", "1D 바코드"),
    ("QR 코드", "pattern", "QR 코드"),
    ("이미지", "pattern", "이미지"),
    ("대용량 이미지", "pattern", "대용량 이미지"),
    ("농도", "pattern", "농도"),
    ("헤드 도트 체크", "pattern", "헤드 도트 체크"),
    ("컷 (부분+전체)", "cut", None),
    ("드로어 열기", "drawer", None),
    ("상태 조회", "status", None),
)

# '텍스트 서식'은 BT 모델에서 인쇄 후 블루투스가 먹통이 되는 현상이 있어 모든 통신에서 제외 (2026-10-01).
# 세 통신 화면은 항상 같은 항목을 보여준다.


def items_for(name):
    return list(PRINT_ITEMS)

DEFAULT_SETTINGS = {
    "printer_name": "프린터1",
    "dots": 576,
    "cut": "partial",
    "fullscreen": False,
    "ifaces": {name: {"kind": "COM", "port": "", "baud": "9600", "flow": "없음", "printer": ""}
               for name, _, _ in IFACES},
}

C_BG = "#F3F5F8"
C_BAR = "#1F2A44"
C_CARD = "#FFFFFF"
C_TEXT = "#1F2937"
C_MUTED = "#6B7280"
C_OK = "#059669"
C_ERR = "#DC2626"
C_BUSY = "#D97706"


# ---------------- 설정 (GUI 와 무관한 부분: 테스트 가능) ----------------

def load_settings(path=SETTINGS_FILE):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return s
    for k in ("printer_name", "dots", "cut", "fullscreen"):
        if k in saved:
            s[k] = saved[k]
    for name in s["ifaces"]:
        s["ifaces"][name].update(saved.get("ifaces", {}).get(name, {}))
    return s


def save_settings(s, path=SETTINGS_FILE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def transport_cfg(ic):
    """인터페이스 설정 → make_transport 설정. 포트가 비어 있으면 ValueError."""
    if ic.get("kind") == "WinPrinter":
        if not ic.get("printer"):
            raise ValueError("설정에서 Windows 프린터를 선택하세요")
        return {"kind": "WinPrinter", "printer": ic["printer"]}
    if not ic.get("port"):
        raise ValueError("설정에서 COM 포트를 선택하세요")
    return {"kind": "COM", "port": ic["port"], "baudrate": int(ic.get("baud") or 9600),
            "flow": ic.get("flow") or "없음"}


def describe(ic):
    if ic.get("kind") == "WinPrinter":
        return f"Windows 프린터 · {ic['printer']}" if ic.get("printer") else "설정 필요"
    if not ic.get("port"):
        return "설정 필요"
    flow = "" if (ic.get("flow") or "없음") == "없음" else f" · {ic['flow']}"
    return f"{ic['port']} · {ic.get('baud') or 9600}bps{flow}"


# ---------------- 화면 ----------------

class PosApp:
    def __init__(self, root):
        self.root = root
        self.s = load_settings()
        self.session = engine.Session(log=self._log)
        self._apply_opts()
        self.dirty = {name: True for name, _, _ in IFACES}   # 설정이 바뀌어 다시 연결해야 하는 채널
        self.state = {name: ("", C_MUTED) for name, _, _ in IFACES}  # 홈 타일에 보일 마지막 결과
        self.q = queue.Queue()
        self.busy = None            # 실행 중인 작업 이름
        self.cancel = threading.Event()
        self.page = None

        root.title("프린터 출력 테스트")
        root.configure(bg=C_BG)
        root.minsize(800, 560)
        self._fonts()
        self._chrome()
        root.bind("<F11>", lambda e: self._set_fullscreen(not root.attributes("-fullscreen")))
        root.bind("<Escape>", lambda e: self._set_fullscreen(False))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.s["fullscreen"]:
            self._set_fullscreen(True)
        else:
            try:
                root.state("zoomed")
            except tk.TclError:
                root.geometry("1024x700")
        self.show_home()
        root.after(100, self._poll)

    # ---- 공통 ----
    def _fonts(self):
        fams = set(tkfont.families(self.root))
        fam = next((f for f in ("Malgun Gothic", "맑은 고딕", "NanumGothic", "Noto Sans CJK KR") if f in fams),
                   "TkDefaultFont")
        self.f_title = (fam, 18, "bold")
        self.f_tile = (fam, 30, "bold")
        self.f_big = (fam, 16, "bold")
        self.f_mid = (fam, 13)
        self.f_small = (fam, 11)
        self.root.option_add("*TCombobox*Listbox.font", self.f_mid)
        st = ttk.Style(self.root)
        st.configure("TCombobox", padding=6)
        st.configure("Pos.TRadiobutton", font=self.f_mid, background=C_CARD)
        st.configure("Pos.TCheckbutton", font=self.f_mid, background=C_CARD)

    def _btn(self, parent, text, cmd, bg=C_CARD, fg=C_TEXT, font=None, **kw):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                      font=font or self.f_big, relief="flat", bd=0, cursor="hand2",
                      highlightthickness=1, highlightbackground="#D1D5DB", **kw)
        return b

    def _chrome(self):
        top = tk.Frame(self.root, bg=C_BAR, height=64)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)
        self.title_lbl = tk.Label(top, text="", bg=C_BAR, fg="white", font=self.f_title, anchor="w")
        self.title_lbl.pack(side="left", padx=20)
        self._btn(top, "홈", self.show_home, bg="#334155", fg="white", padx=22).pack(
            side="right", padx=12, pady=10, fill="y")

        bottom = tk.Frame(self.root, bg=C_CARD, height=64, highlightthickness=1, highlightbackground="#E5E7EB")
        bottom.pack(side="bottom", fill="x")
        bottom.pack_propagate(False)
        self.msg_lbl = tk.Label(bottom, text="", bg=C_CARD, fg=C_MUTED, font=self.f_mid, anchor="w")
        self.msg_lbl.pack(side="left", padx=20, fill="x", expand=True)
        self._btn(bottom, "설정", self.show_settings, bg="#E5E7EB", padx=22).pack(
            side="right", padx=12, pady=10, fill="y")
        self.stop_btn = self._btn(bottom, "■  중지", self._stop, bg=C_ERR, fg="white", padx=18)

        self.body = tk.Frame(self.root, bg=C_BG)
        self.body.pack(side="top", fill="both", expand=True, padx=24, pady=20)

    def _clear(self, title):
        for w in self.body.winfo_children():
            w.destroy()
        self.title_lbl.config(text=f"{title}   ·   {self.s['printer_name']}")

    def message(self, text, color=C_MUTED):
        self.msg_lbl.config(text=text, fg=color)

    def _log(self, line):
        try:
            os.makedirs(engine.LOG_DIR, exist_ok=True)
            path = os.path.join(engine.LOG_DIR, f"pos_{datetime.date.today():%Y%m%d}.txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%H:%M:%S} {line}\n")
        except OSError:
            pass

    def _set_fullscreen(self, on):
        self.root.attributes("-fullscreen", bool(on))

    def _apply_opts(self):
        self.session.opts["dots"] = int(self.s["dots"])
        self.session.opts["cut"] = self.s["cut"]

    # ---- 홈 ----
    def show_home(self):
        self.page = "home"
        self._clear("프린터 출력 테스트")
        grid = tk.Frame(self.body, bg=C_BG)
        grid.pack(fill="both", expand=True)
        for i, (name, color, sub) in enumerate(IFACES):
            grid.columnconfigure(i, weight=1, uniform="tile")
            grid.rowconfigure(0, weight=1)
            tile = tk.Frame(grid, bg=color, cursor="hand2")
            tile.grid(row=0, column=i, sticky="nsew", padx=10, pady=10)
            inner = tk.Frame(tile, bg=color)
            inner.place(relx=0.5, rely=0.5, anchor="center")
            ic = self.s["ifaces"][name]
            text, col = self.state[name]
            widgets = [tile, inner,
                       tk.Label(inner, text=name, bg=color, fg="white", font=self.f_tile),
                       tk.Label(inner, text=sub, bg=color, fg="#E5E7EB", font=self.f_mid),
                       tk.Label(inner, text=describe(ic), bg=color, fg="white", font=self.f_small, pady=12)]
            if text:
                widgets.append(tk.Label(inner, text=text, bg="white", fg=col, font=self.f_small, padx=10, pady=2))
            for w in widgets[2:]:
                w.pack()
            for w in widgets:
                w.bind("<Button-1>", lambda e, n=name: self.show_iface(n))
        if not self.busy:
            self.message("출력할 통신 방식을 누르세요.  (F11: 전체 화면)")

    # ---- 인터페이스 화면 ----
    def show_iface(self, name):
        self.page = name
        color = dict((n, c) for n, c, _ in IFACES)[name]
        self._clear(f"{name} 출력")
        ic = self.s["ifaces"][name]
        head = tk.Frame(self.body, bg=C_BG)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text=f"  {name}  ", bg=color, fg="white", font=self.f_big).pack(side="left")
        tk.Label(head, text=describe(ic), bg=C_BG, fg=C_TEXT, font=self.f_mid).pack(side="left", padx=12)

        grid = tk.Frame(self.body, bg=C_BG)
        grid.pack(fill="both", expand=True)
        cols = 4
        self.item_btns = []
        for i, (label, kind, pat) in enumerate(items_for(name)):
            r, c = divmod(i, cols)
            grid.columnconfigure(c, weight=1, uniform="b")
            grid.rowconfigure(r, weight=1, uniform="r")
            b = self._btn(grid, label, lambda l=label, k=kind, p=pat: self.run(name, l, k, p))
            b.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            self.item_btns.append(b)
        if describe(ic) == "설정 필요":
            self.message(f"{name} 포트가 설정되지 않았습니다. 우측 하단 [설정]에서 선택하세요.", C_ERR)
        elif not self.busy:
            self.message("인쇄할 항목을 누르세요.")

    # ---- 작업 실행 ----
    def run(self, name, label, kind, pat):
        if self.busy:
            self.message(f"'{self.busy}' 인쇄 중입니다. 끝난 뒤 다시 누르거나 [중지]를 누르세요.", C_BUSY)
            return
        self.busy = f"{name} {label}"
        self.cancel.clear()
        self.stop_btn.pack(side="right", padx=4, pady=10, fill="y")
        self.message(f"{name} · {label} 인쇄 중…", C_BUSY)
        threading.Thread(target=self._work, args=(name, label, kind, pat), daemon=True).start()

    def _work(self, name, label, kind, pat):
        try:
            if self.dirty[name] or name not in self.session.channels:
                self.session.add(make_transport(name, transport_cfg(self.s["ifaces"][name])))
                self.dirty[name] = False
            if kind == "pattern":
                r = engine.act_print(self.session, name, pat, self.cancel)
            elif kind == "cut":
                r = engine.act_cut(self.session, name, 1, self.cancel)
            elif kind == "drawer":
                r = engine.act_drawer(self.session, name, self.cancel)
            else:
                r = engine.act_status(self.session, name, self.cancel)
            ok = r.get("suggest") != "FAIL"
            self.q.put((name, label, ok, r.get("summary", "")))
        except (TransportError, ValueError, OSError) as e:
            tr = self.session.channels.get(name)
            if tr:
                tr.close()
            self.q.put((name, label, False, str(e)))
        except Exception as e:  # 예기치 못한 오류도 화면에 표시하고 계속 사용 가능하게
            self.q.put((name, label, False, f"오류: {e}"))

    def _poll(self):
        try:
            while True:
                name, label, ok, summary = self.q.get_nowait()
                self.busy = None
                self.stop_btn.pack_forget()
                now = datetime.datetime.now().strftime("%H:%M")
                self.state[name] = (f"{now} {label} {'완료' if ok else '실패'}", C_OK if ok else C_ERR)
                self._log(f"[{name}] {label}: {'OK' if ok else 'FAIL'} {summary}")
                self.message(f"{name} · {label}: {summary}", C_OK if ok else C_ERR)
                if self.page == "home":
                    self.show_home()
                    self.message(f"{name} · {label}: {summary}", C_OK if ok else C_ERR)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _stop(self):
        self.cancel.set()
        self.message("중지 요청 — 프린터 버퍼에 남은 내용은 계속 인쇄될 수 있습니다.", C_BUSY)

    # ---- 설정 ----
    def show_settings(self):
        self.page = "settings"
        self._clear("설정")
        card = tk.Frame(self.body, bg=C_CARD, highlightthickness=1, highlightbackground="#E5E7EB")
        card.pack(fill="both", expand=True)
        card.columnconfigure(3, weight=1)
        v = self.svars = {}
        pad = {"padx": 10, "pady": 8}

        tk.Label(card, text="프린터 이름", bg=C_CARD, font=self.f_mid).grid(row=0, column=0, sticky="w", **pad)
        v["printer_name"] = tk.StringVar(value=self.s["printer_name"])
        tk.Entry(card, textvariable=v["printer_name"], font=self.f_mid, width=16).grid(
            row=0, column=1, columnspan=2, sticky="w", **pad)
        v["dots"] = tk.StringVar(value=str(self.s["dots"]))
        tk.Label(card, text="인쇄 폭(도트)", bg=C_CARD, font=self.f_mid).grid(row=0, column=3, sticky="e", **pad)
        ttk.Combobox(card, textvariable=v["dots"], values=("576", "512"), width=6, font=self.f_mid,
                     state="readonly").grid(row=0, column=4, sticky="w", **pad)
        v["cut"] = tk.StringVar(value=CUTS.get(self.s["cut"], CUTS["partial"]))
        tk.Label(card, text="자동 컷", bg=C_CARD, font=self.f_mid).grid(row=0, column=5, sticky="e", **pad)
        ttk.Combobox(card, textvariable=v["cut"], values=tuple(CUTS.values()), width=8, font=self.f_mid,
                     state="readonly").grid(row=0, column=6, sticky="w", **pad)

        hdr = ("통신", "연결 방식", "", "포트 / 프린터", "속도", "흐름제어", "")
        for c, t in enumerate(hdr):
            tk.Label(card, text=t, bg=C_CARD, fg=C_MUTED, font=self.f_small).grid(row=1, column=c, sticky="w", **pad)
        com_ports = [p for p, _ in list_com_ports()]
        win_printers = list_win_printers()
        for r, (name, color, _) in enumerate(IFACES, start=2):
            ic = self.s["ifaces"][name]
            iv = v[name] = {k: tk.StringVar(value=str(ic.get(k, ""))) for k in ("kind", "port", "baud", "flow", "printer")}
            tk.Label(card, text=f" {name} ", bg=color, fg="white", font=self.f_big, width=6).grid(
                row=r, column=0, sticky="w", **pad)
            kinds = tk.Frame(card, bg=C_CARD)
            kinds.grid(row=r, column=1, columnspan=2, sticky="w", **pad)
            target = ttk.Combobox(card, font=self.f_mid, width=22)
            target.grid(row=r, column=3, sticky="we", **pad)
            baud = ttk.Combobox(card, textvariable=iv["baud"], values=BAUDS, width=7, font=self.f_mid)
            baud.grid(row=r, column=4, sticky="w", **pad)
            flow = ttk.Combobox(card, textvariable=iv["flow"], values=FLOWS, width=8, font=self.f_mid, state="readonly")
            flow.grid(row=r, column=5, sticky="w", **pad)
            self._btn(card, "시험 인쇄", lambda n=name: self._test_print(n), font=self.f_mid, padx=10).grid(
                row=r, column=6, sticky="we", **pad)

            def refresh(iv=iv, target=target, baud=baud, flow=flow):
                if iv["kind"].get() == "WinPrinter":
                    target.config(textvariable=iv["printer"], values=win_printers, state="readonly")
                    baud.config(state="disabled")
                    flow.config(state="disabled")
                else:
                    target.config(textvariable=iv["port"], values=com_ports, state="normal")
                    baud.config(state="normal")
                    flow.config(state="readonly")
            for k, t in KINDS.items():
                ttk.Radiobutton(kinds, text=t, value=k, variable=iv["kind"], command=refresh,
                                style="Pos.TRadiobutton").pack(side="left", padx=4)
            refresh()

        v["fullscreen"] = tk.BooleanVar(value=bool(self.s["fullscreen"]))
        ttk.Checkbutton(card, text="프로그램을 전체 화면으로 시작 (F11 전환, Esc 해제)", variable=v["fullscreen"],
                        style="Pos.TCheckbutton").grid(row=6, column=0, columnspan=5, sticky="w", padx=10, pady=16)
        tk.Label(card, text="RS232 기본값: 9600bps · 흐름제어 없음   |   USB/BT 가상 COM 은 속도와 무관",
                 bg=C_CARD, fg=C_MUTED, font=self.f_small).grid(row=7, column=0, columnspan=7, sticky="w", padx=10)

        btns = tk.Frame(card, bg=C_CARD)
        btns.grid(row=8, column=0, columnspan=7, sticky="e", padx=10, pady=16)
        self._btn(btns, "포트 새로고침", self.show_settings, font=self.f_mid, padx=16, pady=8).pack(side="left", padx=6)
        self._btn(btns, "저장", self._save, bg=C_OK, fg="white", padx=40, pady=8).pack(side="left", padx=6)
        self.message("통신별 포트를 선택하고 [저장]을 누르세요.")

    def _collect(self):
        v = self.svars
        s = copy.deepcopy(self.s)
        s["printer_name"] = v["printer_name"].get().strip() or "프린터1"
        s["dots"] = int(v["dots"].get() or 576)
        s["cut"] = {t: k for k, t in CUTS.items()}.get(v["cut"].get(), "partial")
        s["fullscreen"] = bool(v["fullscreen"].get())
        for name, _, _ in IFACES:
            s["ifaces"][name] = {k: var.get().strip() for k, var in v[name].items()}
        return s

    def _save(self, quiet=False):
        if self.busy:
            self.message("인쇄가 끝난 뒤 저장하세요.", C_BUSY)
            return False
        self.s = self._collect()
        try:
            save_settings(self.s)
        except OSError as e:
            self.message(f"저장 실패: {e}", C_ERR)
            return False
        self._apply_opts()
        for name in self.dirty:
            self.dirty[name] = True
        self.session.close_all()
        self.title_lbl.config(text=f"설정   ·   {self.s['printer_name']}")
        if not quiet:
            self.message("저장했습니다. 우측 상단 [홈]에서 통신 방식을 선택하세요.", C_OK)
        return True

    def _test_print(self, name):
        if self._save(quiet=True):
            self.run(name, "연결 확인", "pattern", "연결 확인")

    def _on_close(self):
        self.cancel.set()
        try:
            self.session.close_all()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    PosApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
