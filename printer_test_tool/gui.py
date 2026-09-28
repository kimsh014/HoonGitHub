"""열전사 프린터 검증 도구 — GUI (tkinter)."""
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

import engine
import patterns
from results import Results
from testcases import BY_ID, TC
from transports import TransportError, list_com_ports, list_win_printers, make_transport

APP_TITLE = "열전사 프린터 검증 도구"
SETTINGS = os.path.join(engine.BASE_DIR, "settings.json")
CHANNELS = ("RS232", "USB", "BT")
KINDS = ("COM", "WinPrinter", "File", "사용 안 함")
BAUDS = ("9600", "19200", "38400", "57600", "115200", "230400")
FORMATS = ("8N1", "7E1", "8E1", "8O1", "7O1", "8N2")
FLOWS = ("없음", "RTS/CTS", "DTR/DSR", "XON/XOFF")
AGING_PRESETS = {
    "기본 에이징 (단일 채널)": ("기본", ["RS232"]),
    "USB + BT 교대 에이징": ("교대", ["USB", "BT"]),
    "3포트 교대 에이징": ("교대", ["RS232", "USB", "BT"]),
    "3포트 동시 에이징": ("동시", ["RS232", "USB", "BT"]),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x800")
        self.minsize(980, 680)
        self.q = queue.Queue()
        self.session = engine.Session(log=self.log)
        self.results = Results()
        self.cancel = threading.Event()
        self.busy = False
        self.aging = None
        self.cfg = self._load_settings()

        self._build()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log(f"로그 폴더: {engine.LOG_DIR}")

    # ------------------------------------------------------------------ 공통
    def log(self, msg):
        self.q.put(("log", f"{time.strftime('%H:%M:%S')} {msg}"))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.logbox.insert("end", payload + "\n")
                    self.logbox.see("end")
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def on_main(self, fn):
        self.q.put(("call", fn))

    def ask_main(self, msg):
        """작업 스레드에서 호출: 메인 스레드에 확인창을 띄우고 답을 기다린다."""
        ev, box = threading.Event(), {}

        def show():
            box["v"] = messagebox.askokcancel(APP_TITLE, msg, parent=self)
            ev.set()
        self.on_main(show)
        ev.wait()
        return box["v"]

    def run_bg(self, name, fn, done=None):
        if self.busy:
            messagebox.showwarning(APP_TITLE, "다른 시험이 진행 중입니다. 끝나거나 [중지] 후 실행하세요.")
            return
        self.busy = True
        self.cancel.clear()
        self.status_var.set(f"실행 중: {name}")

        def work():
            try:
                res = fn()
            except TransportError as e:
                res = {"suggest": "FAIL", "summary": f"통신 오류: {e}"}
                self.log(f"[오류] {e}")
            except Exception as e:  # 예상 못한 오류도 화면에 표시
                res = {"suggest": None, "summary": f"오류: {e!r}"}
                self.log(f"[오류] {e!r}")
            finally:
                self.busy = False
                self.on_main(lambda: self.status_var.set("대기"))
            if done:
                self.on_main(lambda: done(res))
        threading.Thread(target=work, daemon=True).start()

    def _load_settings(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        cfg = {"common": {k: v.get() for k, v in self.common.items()}, "channels": {}}
        for ch, w in self.chw.items():
            cfg["channels"][ch] = {k: v.get() for k, v in w["vars"].items()}
        cfg["plan_path"] = self.cfg.get("plan_path", "")
        self.cfg = cfg
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _on_close(self):
        if self.aging and self.aging.running:
            if not messagebox.askyesno(APP_TITLE, "에이징이 진행 중입니다. 중지하고 종료할까요?"):
                return
            self.aging.cancel.set()
        self.cancel.set()
        self._save_settings()
        self.session.close_all()
        self.destroy()

    # ------------------------------------------------------------------ 화면
    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        style.configure("Big.TButton", padding=6)
        style.configure("Pass.TLabel", foreground="#006100")
        style.configure("Fail.TLabel", foreground="#9C0006")

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=6, pady=6)
        nb = ttk.Notebook(paned)
        self.nb = nb
        paned.add(nb, weight=4)

        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=1)
        bar = ttk.Frame(bottom)
        bar.pack(fill="x")
        self.status_var = tk.StringVar(value="대기")
        ttk.Label(bar, text="상태:").pack(side="left")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left", padx=4)
        ttk.Button(bar, text="■ 중지", command=self._stop).pack(side="right")
        ttk.Button(bar, text="로그 지우기", command=lambda: self.logbox.delete("1.0", "end")).pack(side="right", padx=4)
        ttk.Button(bar, text="로그 폴더 열기", command=lambda: self._open_folder(engine.LOG_DIR)).pack(side="right")
        self.logbox = ScrolledText(bottom, height=9, font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True)

        self._build_conn(nb)
        self._build_tc(nb)
        self._build_aging(nb)
        self._build_manual(nb)

    def _stop(self):
        self.cancel.set()
        if self.aging and self.aging.running:
            self.aging.cancel.set()
        self.log("중지 요청")

    def _open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # noqa
        else:
            messagebox.showinfo(APP_TITLE, path)

    # ---- 1. 연결 설정 ----
    def _build_conn(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=" 1. 연결 설정 ")

        c = self.cfg.get("common", {})
        box = ttk.LabelFrame(f, text="공통 설정", padding=8)
        box.pack(fill="x")
        self.common = {
            "tester": tk.StringVar(value=c.get("tester", "")),
            "fw": tk.StringVar(value=c.get("fw", "")),
            "dots": tk.StringVar(value=c.get("dots", "576")),
            "encoding": tk.StringVar(value=c.get("encoding", "cp949")),
            "korean": tk.BooleanVar(value=c.get("korean", True)),
            "cut": tk.StringVar(value=c.get("cut", "partial")),
        }
        row = [("시험자", ttk.Entry(box, textvariable=self.common["tester"], width=12)),
               ("FW 버전", ttk.Entry(box, textvariable=self.common["fw"], width=12)),
               ("인쇄 폭(도트)", ttk.Combobox(box, textvariable=self.common["dots"], values=("576", "512", "432"), width=6)),
               ("문자 인코딩", ttk.Combobox(box, textvariable=self.common["encoding"], values=("cp949", "utf-8"), width=7)),
               ("컷", ttk.Combobox(box, textvariable=self.common["cut"], values=("partial", "full", "none"), width=7))]
        for i, (lbl, w) in enumerate(row):
            ttk.Label(box, text=lbl).grid(row=0, column=i * 2, sticky="e", padx=(8, 2))
            w.grid(row=0, column=i * 2 + 1, sticky="w")
        ttk.Checkbutton(box, text="한글 모드 명령(FS &) 전송", variable=self.common["korean"]).grid(row=0, column=10, padx=8)
        for v in self.common.values():
            v.trace_add("write", lambda *a: self._apply_common())
        self._apply_common()

        chbox = ttk.LabelFrame(f, text="채널 (프린터 연결)", padding=8)
        chbox.pack(fill="x", pady=8)
        heads = ("채널", "연결 방식", "포트 / 프린터 / 파일", "속도", "형식", "흐름제어", "", "", "", "상태")
        for i, h in enumerate(heads):
            ttk.Label(chbox, text=h).grid(row=0, column=i, padx=3, sticky="w")
        self.chw = {}
        defaults = {"RS232": "COM", "USB": "COM", "BT": "COM"}
        for r, ch in enumerate(CHANNELS, 1):
            cc = self.cfg.get("channels", {}).get(ch, {})
            vars_ = {"kind": tk.StringVar(value=cc.get("kind", defaults[ch])),
                     "target": tk.StringVar(value=cc.get("target", "")),
                     "baud": tk.StringVar(value=cc.get("baud", "115200" if ch == "RS232" else "9600")),
                     "fmt": tk.StringVar(value=cc.get("fmt", "8N1")),
                     "flow": tk.StringVar(value=cc.get("flow", "RTS/CTS" if ch == "RS232" else "없음"))}
            ttk.Label(chbox, text=ch, font=("", 10, "bold")).grid(row=r, column=0, padx=3)
            ttk.Combobox(chbox, textvariable=vars_["kind"], values=KINDS, width=11, state="readonly").grid(row=r, column=1)
            tgt = ttk.Combobox(chbox, textvariable=vars_["target"], width=34)
            tgt.grid(row=r, column=2, padx=3)
            ttk.Combobox(chbox, textvariable=vars_["baud"], values=BAUDS, width=8).grid(row=r, column=3)
            ttk.Combobox(chbox, textvariable=vars_["fmt"], values=FORMATS, width=5).grid(row=r, column=4)
            ttk.Combobox(chbox, textvariable=vars_["flow"], values=FLOWS, width=9, state="readonly").grid(row=r, column=5)
            st = tk.StringVar(value="미연결")
            ttk.Button(chbox, text="연결", width=6, command=lambda c=ch: self._connect(c)).grid(row=r, column=6, padx=2)
            ttk.Button(chbox, text="해제", width=6, command=lambda c=ch: self._disconnect(c)).grid(row=r, column=7, padx=2)
            ttk.Button(chbox, text="상태조회", width=8, command=lambda c=ch: self._quick(c, "status")).grid(row=r, column=8, padx=2)
            ttk.Label(chbox, textvariable=st, width=12).grid(row=r, column=9, padx=3, sticky="w")
            vars_["kind"].trace_add("write", lambda *a, c=ch: self._refresh_targets(c))
            self.chw[ch] = {"vars": vars_, "target": tgt, "state": st}
        ttk.Button(chbox, text="포트 목록 새로고침", command=self._refresh_all_targets).grid(row=4, column=2, sticky="w", pady=6)
        ttk.Button(chbox, text="연결 확인 인쇄(연결된 전체)", command=lambda: self._quick(None, "info")).grid(
            row=4, column=2, sticky="e", pady=6)
        self._refresh_all_targets()

        help_ = (
            "■ RS232(RJ45) : 전용 케이블(RJ45↔DB9) 또는 USB-시리얼 변환기의 COM 포트 선택\n"
            "■ USB : 장치가 가상 COM(CDC)으로 잡히면 'COM', Windows에 프린터로 설치되면 'WinPrinter' 선택\n"
            "        (WinPrinter 는 상태 조회·핫플러그 자동 감지가 불가 → 해당 항목은 육안 판정)\n"
            "■ BT : PC에서 프린터와 페어링하면 'Bluetooth 링크를 통한 표준 직렬(COMx)' 포트가 생깁니다. 그 포트를 선택\n"
            "        (포트가 2개면 보통 '발신(Outgoing)' 포트. BT/USB 가상 COM 은 속도 설정과 무관하게 동작)\n"
            "■ File : 프린터 없이 프로그램 동작만 확인할 때 (전송 바이트를 파일로 저장)\n"
            "■ 설정은 종료 시 자동 저장됩니다."
        )
        ttk.Label(f, text=help_, justify="left", foreground="#404040").pack(anchor="w", pady=6)

    def _apply_common(self):
        try:
            dots = int(self.common["dots"].get())
        except ValueError:
            dots = 576
        self.session.opts = {"dots": dots, "encoding": self.common["encoding"].get() or "cp949",
                             "korean_mode": bool(self.common["korean"].get()), "cut": self.common["cut"].get()}

    def _refresh_targets(self, ch):
        w = self.chw[ch]
        kind = w["vars"]["kind"].get()
        if kind == "COM":
            vals = [f"{p} — {d}" for p, d in list_com_ports()]
        elif kind == "WinPrinter":
            vals = list_win_printers()
        elif kind == "File":
            vals = [os.path.join(engine.LOG_DIR, f"dump_{ch}.bin")]
        else:
            vals = []
        w["target"]["values"] = vals
        if kind == "File" and not w["vars"]["target"].get().endswith(".bin"):
            w["vars"]["target"].set(vals[0])

    def _refresh_all_targets(self):
        for ch in CHANNELS:
            self._refresh_targets(ch)

    def _channel_cfg(self, ch):
        v = {k: x.get() for k, x in self.chw[ch]["vars"].items()}
        kind = v["kind"]
        tgt = v["target"].split(" — ")[0].strip()
        if kind == "사용 안 함":
            return None
        if not tgt:
            raise TransportError(f"{ch}: 포트/프린터를 선택하세요")
        fmt = v["fmt"] or "8N1"
        flow = "없음" if v["flow"] == "없음" else v["flow"]
        if kind == "COM":
            return {"kind": "COM", "port": tgt, "baudrate": int(v["baud"]), "bytesize": int(fmt[0]),
                    "parity": fmt[1], "stopbits": int(fmt[2]), "flow": flow}
        if kind == "WinPrinter":
            return {"kind": "WinPrinter", "printer": tgt}
        return {"kind": "File", "path": tgt}

    def _connect(self, ch):
        try:
            cfg = self._channel_cfg(ch)
            if cfg is None:
                self.chw[ch]["state"].set("사용 안 함")
                return
            tr = make_transport(ch, cfg)
            tr.open()
        except (TransportError, ValueError) as e:
            self.chw[ch]["state"].set("연결 실패")
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.session.add(tr)
        self.chw[ch]["state"].set("● 연결됨")
        self.log(f"[{ch}] 연결: {tr.describe()}")
        self._save_settings()

    def _disconnect(self, ch):
        tr = self.session.channels.pop(ch, None)
        if tr:
            tr.close()
        self.chw[ch]["state"].set("미연결")
        self.log(f"[{ch}] 연결 해제")

    def _quick(self, ch, what):
        if what == "status":
            self.run_bg("상태 조회", lambda: engine.act_status(self.session, ch),
                        lambda r: self.log(f"[{ch}] {r['summary']}"))
        else:
            self.run_bg("연결 확인 인쇄", lambda: engine.act_all_channels(self.session),
                        lambda r: self.log(r["summary"]))

    # ---- 2. 테스트 케이스 ----
    def _build_tc(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=" 2. 테스트 케이스 ")
        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True)
        cols = ("id", "cat", "name", "result")
        tv = ttk.Treeview(left, columns=cols, show="headings", height=20, selectmode="browse")
        for c, t, w in zip(cols, ("ID", "구분", "항목", "결과"), (50, 95, 190, 70)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="center" if c in ("id", "result") else "w")
        tv.tag_configure("Pass", background="#C6EFCE")
        tv.tag_configure("Fail", background="#FFC7CE")
        tv.tag_configure("N/A", background="#EDEDED")
        sb = ttk.Scrollbar(left, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.bind("<<TreeviewSelect>>", lambda e: self._tc_select())
        self.tv = tv
        for t in TC:
            tv.insert("", "end", iid=t["id"], values=(t["id"], t["cat"], t["name"], ""))

        right = ttk.Frame(f, padding=(10, 0))
        right.pack(side="left", fill="both", expand=True)
        self.tc_title = tk.StringVar()
        ttk.Label(right, textvariable=self.tc_title, font=("", 12, "bold")).pack(anchor="w")
        self.tc_info = tk.Text(right, height=9, wrap="word", relief="flat", background="#F7F7F7")
        self.tc_info.pack(fill="x", pady=4)

        run = ttk.LabelFrame(right, text="실행", padding=6)
        run.pack(fill="x")
        ttk.Label(run, text="채널").pack(side="left")
        self.tc_ch = tk.StringVar(value="RS232")
        ttk.Combobox(run, textvariable=self.tc_ch, values=CHANNELS, width=7, state="readonly").pack(side="left", padx=4)
        self.run_btn = ttk.Button(run, text="▶ 실행", style="Big.TButton", command=self._tc_run)
        self.run_btn.pack(side="left", padx=6)
        ttk.Button(run, text="■ 중지", command=self._stop).pack(side="left")
        self.suggest_var = tk.StringVar()
        ttk.Label(run, textvariable=self.suggest_var, foreground="#1F4E78").pack(side="left", padx=8)

        res = ttk.LabelFrame(right, text="판정 (결과 저장 시 계획표 형식으로 기록)", padding=6)
        res.pack(fill="both", expand=True, pady=6)
        self.res_var = tk.StringVar(value="미실시")
        rb = ttk.Frame(res)
        rb.pack(anchor="w")
        for v in ("Pass", "Fail", "N/A", "미실시"):
            ttk.Radiobutton(rb, text=v, value=v, variable=self.res_var).pack(side="left", padx=6)
        ttk.Label(rb, text="  결함 ID").pack(side="left")
        self.defect_var = tk.StringVar()
        ttk.Entry(rb, textvariable=self.defect_var, width=10).pack(side="left", padx=4)
        ttk.Label(res, text="비고 (실행 결과가 자동으로 추가됩니다)").pack(anchor="w", pady=(6, 0))
        self.note = tk.Text(res, height=6, wrap="word")
        self.note.pack(fill="both", expand=True)
        bb = ttk.Frame(res)
        bb.pack(fill="x", pady=4)
        ttk.Button(bb, text="결과 저장", style="Big.TButton", command=self._tc_save).pack(side="left")
        ttk.Button(bb, text="저장 후 다음 ▶", command=lambda: self._tc_save(next_=True)).pack(side="left", padx=4)

        ex = ttk.Frame(right)
        ex.pack(fill="x")
        self.count_var = tk.StringVar()
        ttk.Label(ex, textvariable=self.count_var).pack(side="left")
        ttk.Button(ex, text="계획표 엑셀에 결과 반영", command=self._export_xlsx).pack(side="right")
        ttk.Button(ex, text="CSV 내보내기", command=self._export_csv).pack(side="right", padx=4)
        self._refresh_tv()
        tv.selection_set(TC[0]["id"])

    def _refresh_tv(self):
        for t in TC:
            r = self.results.get(t["id"])["result"]
            self.tv.item(t["id"], values=(t["id"], t["cat"], t["name"], r), tags=(r,))
        c = self.results.counts()
        done = c["Pass"] + c["Fail"]
        rate = f"{c['Pass'] / done * 100:.0f}%" if done else "-"
        self.count_var.set(f"전체 {len(TC)} | Pass {c['Pass']} | Fail {c['Fail']} | N/A {c['N/A']} | "
                           f"미실시 {c['미실시']} | 합격률 {rate}")

    def _cur(self):
        sel = self.tv.selection()
        return BY_ID[sel[0]] if sel else None

    def _tc_select(self):
        t = self._cur()
        if not t:
            return
        self.tc_title.set(f"{t['id']}  {t['name']}  ({t['cat']})")
        self.tc_info.configure(state="normal")
        self.tc_info.delete("1.0", "end")
        auto = "수동 확인 항목 (실행 버튼 없음)" if t["action"] is None else "프로그램 실행 지원"
        self.tc_info.insert("end", f"방법: {t['method']}\n합격 기준: {t['criterion']}\n구분: {auto}\n\n{t['guide']}")
        self.tc_info.configure(state="disabled")
        if t["channel"] in CHANNELS:
            self.tc_ch.set(t["channel"])
        self.run_btn.configure(state="disabled" if t["action"] is None else "normal")
        r = self.results.get(t["id"])
        self.res_var.set(r["result"])
        self.defect_var.set(r["defect"])
        self.note.delete("1.0", "end")
        self.note.insert("end", r["note"])
        self.suggest_var.set("")

    def _tc_save(self, next_=False):
        t = self._cur()
        if not t:
            return
        self.results.set(t["id"], result=self.res_var.get(), tester=self.common["tester"].get(),
                         fw=self.common["fw"].get(), defect=self.defect_var.get(),
                         note=self.note.get("1.0", "end").strip())
        self._refresh_tv()
        self.log(f"[{t['id']}] 결과 저장: {self.res_var.get()}")
        if next_:
            i = [x["id"] for x in TC].index(t["id"])
            if i + 1 < len(TC):
                self.tv.selection_set(TC[i + 1]["id"])
                self.tv.see(TC[i + 1]["id"])

    def _tc_done(self, tid, res):
        self.suggest_var.set(f"자동 판정 제안: {res['suggest']}" if res.get("suggest") else "출력물을 보고 판정하세요")
        self.log(f"[{tid}] {res['summary']}")
        cur = self._cur()
        if cur and cur["id"] == tid:
            self.note.insert("end", ("\n" if self.note.get("1.0", "end").strip() else "") +
                             f"[{time.strftime('%m-%d %H:%M')}] {res['summary']}")
            if res.get("suggest") in ("Pass", "PASS"):
                self.res_var.set("Pass")
            elif res.get("suggest") in ("FAIL", "Fail"):
                self.res_var.set("Fail")
            elif res.get("suggest") == "N/A":
                self.res_var.set("N/A")

    def _tc_run(self):
        t = self._cur()
        if not t or t["action"] is None:
            return
        a = t["action"]
        ch = self.tc_ch.get()
        s = self.session
        tid = t["id"]
        cancel = self.cancel
        done = lambda r: self._tc_done(tid, r)  # noqa: E731
        kind = a[0]

        if kind == "aging":
            self.nb.select(2)
            return
        if kind == "devices":
            self._show_devices()
            return
        if kind == "speed":
            self._speed_test(ch, tid)
            return

        if kind not in ("x01", "x02", "x03") and not self._ensure(ch):
            return
        if kind == "print":
            fn = lambda: engine.act_print(s, ch, a[1], cancel)  # noqa: E731
        elif kind == "burst":
            tag = ""
            if tid == "T03":
                d = simpledialog.askstring(APP_TITLE, "현재 거리(예: 1m, 5m, 10m)", parent=self)
                if d is None:
                    return
                tag = f"@{d}"
            n = simpledialog.askinteger(APP_TITLE, "인쇄 장수", initialvalue=a[2], minvalue=1, parent=self)
            if not n:
                return
            fn = lambda: engine.act_burst(s, ch, a[1], n, cancel, tag)  # noqa: E731
        elif kind == "reconnect":
            n = simpledialog.askinteger(APP_TITLE, "목표 재연결 횟수", initialvalue=a[1], minvalue=1, parent=self)
            if not n:
                return
            fn = lambda: engine.act_reconnect(s, ch, n, cancel, a[2])  # noqa: E731
        elif kind == "status":
            fn = lambda: engine.act_status(s, ch)  # noqa: E731
        elif kind == "monitor":
            fn = lambda: engine.act_status_monitor(s, ch, a[1], cancel, a[2])  # noqa: E731
        elif kind == "cut":
            fn = lambda: engine.act_cut(s, ch, a[1], cancel)  # noqa: E731
        elif kind == "drawer":
            fn = lambda: engine.act_drawer(s, ch)  # noqa: E731
        elif kind == "comm":
            if tid == "R01":
                bauds = simpledialog.askstring(APP_TITLE, "시험할 속도(쉼표 구분)", initialvalue="9600,19200,38400,57600,115200",
                                               parent=self)
                fmts = "8N1"
            else:
                bauds = self.chw[ch]["vars"]["baud"].get()
                fmts = simpledialog.askstring(APP_TITLE, "시험할 형식(쉼표 구분)", initialvalue="8N1,7E1,8E1,8O1", parent=self)
            if not bauds or not fmts:
                return
            try:
                cfgs = [(int(b), f.strip().upper()) for b in bauds.split(",") for f in fmts.split(",")]
            except ValueError:
                messagebox.showerror(APP_TITLE, "입력 형식 오류")
                return
            fn = lambda: engine.act_comm_configs(s, ch, cfgs, self.ask_main, cancel)  # noqa: E731
        elif kind == "mismatch":
            wb = simpledialog.askinteger(APP_TITLE, "일부러 틀리게 보낼 속도", initialvalue=9600, parent=self)
            if not wb:
                return
            fn = lambda: engine.act_mismatch(s, ch, wb)  # noqa: E731
        elif kind == "x01":
            fn = lambda: engine.act_all_channels(s)  # noqa: E731
        elif kind == "x02":
            fn = lambda: engine.act_concurrent(s)  # noqa: E731
        elif kind == "x03":
            open_ = [c.label for c in s.open_channels()]
            if len(open_) < 2:
                messagebox.showwarning(APP_TITLE, "2개 이상 채널을 연결하세요")
                return
            main = "USB" if "USB" in open_ else open_[0]
            other = "BT" if "BT" in open_ and main != "BT" else [x for x in open_ if x != main][0]
            fn = lambda: engine.act_interleave(s, main, other)  # noqa: E731
        else:
            return
        self.log(f"[{tid}] 실행 ({ch})")
        self.run_bg(tid, fn, done)

    def _ensure(self, ch):
        if ch in self.session.channels and self.session.channels[ch].is_open:
            return True
        self._connect(ch)
        return ch in self.session.channels

    def _show_devices(self):
        ports = list_com_ports()
        prs = list_win_printers()
        lines = ["[COM 포트]"] + [f"  {p}  {d}" for p, d in ports] + ["", "[Windows 프린터]"] + [f"  {p}" for p in prs]
        text = "\n".join(lines)
        self.log(text)
        messagebox.showinfo(APP_TITLE, text or "장치 없음")

    def _speed_test(self, ch, tid):
        if not self._ensure(ch):
            return
        length = simpledialog.askinteger(APP_TITLE, "인쇄 길이(mm)", initialvalue=1000, minvalue=100, parent=self)
        if not length:
            return
        data = patterns.pattern_speed(self.session.opts, ch, length)
        t0 = time.perf_counter()
        threading.Thread(target=lambda: engine._safe_write(self.session, ch, data), daemon=True).start()
        messagebox.showinfo(APP_TITLE, "인쇄가 끝나는 순간(컷) [확인]을 누르세요.", parent=self)
        secs = time.perf_counter() - t0
        res = {"suggest": None, "summary": f"{length}mm / {secs:.1f}s = {length / secs:.1f} mm/s (전송 시작~확인 클릭 기준)"}
        self._tc_done(tid, res)

    def _export_csv(self):
        p = self.results.export_csv()
        self.log(f"CSV 저장: {p}")
        messagebox.showinfo(APP_TITLE, f"저장했습니다.\n{p}")

    def _export_xlsx(self):
        p = filedialog.askopenfilename(title="검증 계획표 엑셀 선택", filetypes=[("Excel", "*.xlsx")],
                                       initialfile=os.path.basename(self.cfg.get("plan_path", "")))
        if not p:
            return
        try:
            out, n = self.results.export_xlsx(p)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"반영 실패: {e}")
            return
        self.cfg["plan_path"] = p
        self.log(f"엑셀 반영 {n}건: {out}")
        messagebox.showinfo(APP_TITLE, f"{n}개 항목을 반영해 새 파일로 저장했습니다.\n{out}")

    # ---- 3. 에이징 ----
    def _build_aging(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=" 3. 에이징 ")
        cfg = ttk.LabelFrame(f, text="설정", padding=8)
        cfg.pack(fill="x")
        self.ag = {"preset": tk.StringVar(value=list(AGING_PRESETS)[0]), "mode": tk.StringVar(value="기본"),
                   "pattern": tk.StringVar(value="영수증"), "count": tk.StringVar(value="0"),
                   "hours": tk.StringVar(value="12"), "interval": tk.StringVar(value="2"),
                   "status": tk.BooleanVar(value=True), "pause": tk.BooleanVar(value=True),
                   "reconnect": tk.BooleanVar(value=True), "stopfail": tk.BooleanVar(value=False)}
        self.ag_ch = {c: tk.BooleanVar(value=(c == "RS232")) for c in CHANNELS}

        ttk.Label(cfg, text="프리셋").grid(row=0, column=0, sticky="e")
        pc = ttk.Combobox(cfg, textvariable=self.ag["preset"], values=list(AGING_PRESETS), width=26, state="readonly")
        pc.grid(row=0, column=1, sticky="w", columnspan=2)
        pc.bind("<<ComboboxSelected>>", lambda e: self._ag_preset())
        ttk.Label(cfg, text="모드").grid(row=0, column=3, sticky="e", padx=(12, 2))
        ttk.Combobox(cfg, textvariable=self.ag["mode"], values=("기본", "교대", "동시"), width=6, state="readonly").grid(
            row=0, column=4, sticky="w")
        ttk.Label(cfg, text="채널").grid(row=0, column=5, sticky="e", padx=(12, 2))
        chf = ttk.Frame(cfg)
        chf.grid(row=0, column=6, sticky="w")
        for c in CHANNELS:
            ttk.Checkbutton(chf, text=c, variable=self.ag_ch[c]).pack(side="left")

        ttk.Label(cfg, text="패턴").grid(row=1, column=0, sticky="e", pady=6)
        ttk.Combobox(cfg, textvariable=self.ag["pattern"], values=list(patterns.AGING_PATTERNS), width=14,
                     state="readonly").grid(row=1, column=1, sticky="w")
        ttk.Label(cfg, text="시간(h, 0=무제한)").grid(row=1, column=2, sticky="e")
        ttk.Entry(cfg, textvariable=self.ag["hours"], width=6).grid(row=1, column=3, sticky="w")
        ttk.Label(cfg, text="장수(0=무제한)").grid(row=1, column=4, sticky="e")
        ttk.Entry(cfg, textvariable=self.ag["count"], width=7).grid(row=1, column=5, sticky="w")
        ttk.Label(cfg, text="간격(초)").grid(row=1, column=6, sticky="w")
        ttk.Entry(cfg, textvariable=self.ag["interval"], width=5).grid(row=1, column=6, sticky="e")

        opt = ttk.Frame(cfg)
        opt.grid(row=2, column=0, columnspan=8, sticky="w")
        ttk.Checkbutton(opt, text="매 장 상태 조회(COM)", variable=self.ag["status"]).pack(side="left")
        ttk.Checkbutton(opt, text="에러 시 일시정지 후 자동 재개(용지 보충 등)", variable=self.ag["pause"]).pack(side="left", padx=8)
        ttk.Checkbutton(opt, text="전송 실패 시 자동 재연결", variable=self.ag["reconnect"]).pack(side="left")
        ttk.Checkbutton(opt, text="첫 실패 시 중지", variable=self.ag["stopfail"]).pack(side="left", padx=8)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="▶ 에이징 시작", style="Big.TButton", command=self._ag_start).pack(side="left")
        ttk.Button(btns, text="■ 에이징 중지", style="Big.TButton", command=self._ag_stop).pack(side="left", padx=6)
        self.ag_elapsed = tk.StringVar(value="")
        ttk.Label(btns, textvariable=self.ag_elapsed, font=("", 11, "bold")).pack(side="left", padx=12)

        cols = ("ch", "sent", "ok", "fail", "pause", "reconn", "rate", "last")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=4)
        for c, t, w in zip(cols, ("채널", "전송", "정상", "실패", "일시정지", "재연결", "평균속도", "최근"),
                           (70, 70, 70, 70, 70, 70, 90, 380)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="center" if c != "last" else "w")
        tv.pack(fill="x")
        self.ag_tv = tv
        ttk.Label(f, justify="left", foreground="#404040", text=(
            "■ 기본 에이징 : 채널 1개로 연속 인쇄 (계획표 야간 에이징 #1 — RS232)\n"
            "■ USB + BT 교대 : 두 채널을 번갈아 인쇄 (야간 에이징 #2). '동시'는 채널마다 동시에 계속 인쇄\n"
            "■ 영수증마다 채널·순번·시각이 찍힙니다. 아침에 순번이 빠진 곳이 없는지, 로그 CSV 의 FAIL/ERROR 행을 확인하세요\n"
            "■ 용지 롤이 다 떨어지면 '에러 시 일시정지'가 켜져 있을 때 보충 후 자동 재개됩니다\n"
            "■ PC 절전 모드를 꺼 두세요 (절전 시 USB/BT 연결이 끊겨 실패로 기록됩니다)"
        )).pack(anchor="w", pady=8)

    def _ag_preset(self):
        mode, chans = AGING_PRESETS[self.ag["preset"].get()]
        self.ag["mode"].set(mode)
        for c in CHANNELS:
            self.ag_ch[c].set(c in chans)

    def _ag_start(self):
        if self.aging and self.aging.running:
            messagebox.showwarning(APP_TITLE, "에이징이 이미 진행 중입니다.")
            return
        labels = [c for c in CHANNELS if self.ag_ch[c].get()]
        if not labels:
            messagebox.showwarning(APP_TITLE, "채널을 선택하세요")
            return
        for c in labels:
            if not self._ensure(c):
                return
        try:
            runner = engine.AgingRunner(
                self.session, labels, self.ag["mode"].get(), self.ag["pattern"].get(),
                int(self.ag["count"].get() or 0), float(self.ag["hours"].get() or 0), float(self.ag["interval"].get() or 0),
                self.ag["status"].get(), self.ag["pause"].get(), self.ag["reconnect"].get(), self.ag["stopfail"].get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "시간/장수/간격을 숫자로 입력하세요")
            return
        if runner.count == 0 and runner.hours == 0:
            if not messagebox.askyesno(APP_TITLE, "종료 조건이 없습니다(수동 중지까지 계속). 시작할까요?"):
                return
        self.aging = runner
        self.ag_tv.delete(*self.ag_tv.get_children())
        for c in labels:
            self.ag_tv.insert("", "end", iid=c, values=(c, 0, 0, 0, 0, 0, "", ""))

        def work():
            summary = runner.run()
            self.on_main(lambda: self._ag_finished(summary))
        threading.Thread(target=work, daemon=True).start()
        self.after(1000, self._ag_tick)

    def _ag_tick(self):
        r = self.aging
        if not r:
            return
        for c, st in r.stats.items():
            rate = f"{st['bytes'] / st['secs'] / 1024:.1f}KB/s" if st["secs"] else ""
            if self.ag_tv.exists(c):
                self.ag_tv.item(c, values=(c, st["sent"], st["ok"], st["fail"], st["pause"], st["reconn"], rate, st["last"]))
        e = int(r.elapsed())
        self.ag_elapsed.set(f"{'진행 중' if r.running else '종료'}  {e // 3600:02d}:{e % 3600 // 60:02d}:{e % 60:02d}  "
                            f"총 {r.total}장")
        if r.running:
            self.after(1000, self._ag_tick)

    def _ag_stop(self):
        if self.aging and self.aging.running:
            self.aging.cancel.set()
            self.log("[에이징] 중지 요청 — 현재 장 전송 후 멈춥니다")

    def _ag_finished(self, summary):
        self._ag_tick()
        r = self.results.get("X04")
        note = (r["note"] + "\n" if r["note"] else "") + f"[{time.strftime('%m-%d %H:%M')}] 에이징({self.aging.mode} " \
            f"{'+'.join(self.aging.labels)}) {summary}"
        self.results.set("X04", note=note, tester=self.common["tester"].get(), fw=self.common["fw"].get())
        self._refresh_tv()
        if self._cur() and self._cur()["id"] == "X04":
            self._tc_select()
        messagebox.showinfo(APP_TITLE, "에이징 종료\n\n" + summary)

    # ---- 4. 수동 인쇄 ----
    def _build_manual(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=" 4. 패턴 인쇄 / 명령 전송 ")
        a = ttk.LabelFrame(f, text="패턴 인쇄", padding=8)
        a.pack(fill="x")
        self.m_ch = tk.StringVar(value="RS232")
        self.m_pat = tk.StringVar(value="연결 확인")
        self.m_rep = tk.StringVar(value="1")
        ttk.Label(a, text="채널").pack(side="left")
        ttk.Combobox(a, textvariable=self.m_ch, values=CHANNELS, width=7, state="readonly").pack(side="left", padx=4)
        ttk.Label(a, text="패턴").pack(side="left", padx=(10, 0))
        ttk.Combobox(a, textvariable=self.m_pat, values=list(patterns.PATTERNS), width=16, state="readonly").pack(
            side="left", padx=4)
        ttk.Label(a, text="반복").pack(side="left", padx=(10, 0))
        ttk.Entry(a, textvariable=self.m_rep, width=5).pack(side="left", padx=4)
        ttk.Button(a, text="인쇄", command=self._m_print).pack(side="left", padx=8)
        ttk.Button(a, text="상태 조회", command=lambda: self._quick(self.m_ch.get(), "status")).pack(side="left")
        ttk.Button(a, text="상태 감시 60초", command=self._m_monitor).pack(side="left", padx=4)

        b = ttk.LabelFrame(f, text="명령 직접 전송 (HEX 또는 텍스트)", padding=8)
        b.pack(fill="x", pady=8)
        self.m_hex = tk.StringVar(value="1B 40 1B 61 01 48 45 4C 4C 4F 0A 1D 56 42 00")
        self.m_mode = tk.StringVar(value="HEX")
        ttk.Combobox(b, textvariable=self.m_mode, values=("HEX", "텍스트"), width=6, state="readonly").pack(side="left")
        ttk.Entry(b, textvariable=self.m_hex, width=70).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(b, text="전송", command=self._m_send).pack(side="left")
        self.m_wait = tk.BooleanVar(value=False)
        ttk.Checkbutton(b, text="응답 읽기", variable=self.m_wait).pack(side="left", padx=4)

        ttk.Label(f, justify="left", foreground="#404040", text=(
            "자주 쓰는 명령 (HEX)\n"
            "  초기화 1B 40   |  컷(부분) 1D 56 42 00   |  컷(전체) 1D 56 41 00   |  급지 3줄 1B 64 03\n"
            "  상태 조회 10 04 01~04   |  드로어 1B 70 00 19 FA   |  셀프테스트(일부 모델) 1D 28 41 02 00 00 02"
        )).pack(anchor="w", pady=6)

    def _m_print(self):
        ch = self.m_ch.get()
        if not self._ensure(ch):
            return
        try:
            n = max(1, int(self.m_rep.get()))
        except ValueError:
            n = 1
        pat = self.m_pat.get()

        def fn():
            r = None
            for i in range(n):
                if self.cancel.is_set():
                    break
                r = engine.act_print(self.session, ch, pat, self.cancel)
            return r or {"summary": "중지됨"}
        self.run_bg("패턴 인쇄", fn, lambda r: self.log(r["summary"]))

    def _m_monitor(self):
        ch = self.m_ch.get()
        if not self._ensure(ch):
            return
        self.run_bg("상태 감시", lambda: engine.act_status_monitor(self.session, ch, 60, self.cancel),
                    lambda r: self.log(r["summary"]))

    def _m_send(self):
        ch = self.m_ch.get()
        if not self._ensure(ch):
            return
        txt = self.m_hex.get()
        try:
            data = bytes.fromhex(txt.replace(",", " ")) if self.m_mode.get() == "HEX" else \
                txt.encode(self.session.opts["encoding"]) + b"\n"
        except ValueError:
            messagebox.showerror(APP_TITLE, "HEX 형식 오류 (예: 1B 40 0A)")
            return
        want = self.m_wait.get()

        def fn():
            tr = self.session.get(ch)
            if want:
                resp = tr.query(data, 64, 1.0)
                return {"summary": f"[{ch}] 전송 {len(data)}B, 응답: " + (resp.hex(" ").upper() if resp else "없음")}
            tr.write(data)
            return {"summary": f"[{ch}] 전송 {len(data)}B"}
        self.run_bg("명령 전송", fn, lambda r: self.log(r["summary"]))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
