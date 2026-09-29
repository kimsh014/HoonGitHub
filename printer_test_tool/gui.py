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
        self.agings = {}                       # 프린터 이름 -> AgingRunner
        self.ag_session = engine.Session(log=self.log)   # 에이징 전용 연결
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
        if hasattr(self, "ag_rows"):
            cfg["aging"] = {
                "rows": [{k: v.get() for k, v in r["vars"].items()} for r in self.ag_rows],
                "common": {k: v.get() for k, v in self.ag.items()}}
        self.cfg = cfg
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _on_close(self):
        if self._ag_running_names():
            if not messagebox.askyesno(APP_TITLE, "에이징이 진행 중입니다. 중지하고 종료할까요?"):
                return
            self._ag_stop_all()
        self.cancel.set()
        self._save_settings()
        self.session.close_all()
        self.ag_session.close_all()
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
        self.log("중지 요청 (에이징은 에이징 탭의 중지 버튼 사용)")

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

    # ---- 3. 에이징 (프린터 여러 대 동시) ----
    def _build_aging(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=" 3. 에이징 (다중 프린터) ")
        saved = self.cfg.get("aging", {})

        # -- 프린터 목록 --
        box = ttk.LabelFrame(f, text="프린터 목록 — 대마다 연결을 따로 지정 (최대 9대)", padding=8)
        box.pack(fill="x")
        self.ag_box = box
        heads = ("사용", "프린터 이름(샘플번호)", "인터페이스", "연결 방식", "포트 / 프린터", "속도", "형식", "흐름제어", "")
        for i, h in enumerate(heads):
            ttk.Label(box, text=h).grid(row=0, column=i, padx=3, sticky="w")
        self.ag_rows = []
        rows = saved.get("rows") or [
            {"use": True, "name": "프린터1", "iface": "RS232", "kind": "COM", "baud": "115200", "flow": "RTS/CTS"},
            {"use": True, "name": "프린터2", "iface": "USB", "kind": "COM", "baud": "9600", "flow": "없음"},
            {"use": True, "name": "프린터3", "iface": "BT", "kind": "COM", "baud": "9600", "flow": "없음"},
        ]
        for r in rows:
            self._ag_add_row(r)
        bb = ttk.Frame(f)
        bb.pack(fill="x", pady=4)
        ttk.Button(bb, text="+ 프린터 추가", command=lambda: self._ag_add_row({})).pack(side="left")
        ttk.Button(bb, text="포트 목록 새로고침", command=self._ag_refresh_ports).pack(side="left", padx=6)

        # -- 공통 설정 --
        c = saved.get("common", {})
        cfg = ttk.LabelFrame(f, text="에이징 설정 (모든 프린터 공통)", padding=8)
        cfg.pack(fill="x", pady=4)
        self.ag = {"pattern": tk.StringVar(value=c.get("pattern", "영수증")), "hours": tk.StringVar(value=c.get("hours", "12")),
                   "count": tk.StringVar(value=c.get("count", "0")), "interval": tk.StringVar(value=c.get("interval", "2")),
                   "status": tk.BooleanVar(value=c.get("status", True)), "pause": tk.BooleanVar(value=c.get("pause", True)),
                   "reconnect": tk.BooleanVar(value=c.get("reconnect", True)),
                   "stopfail": tk.BooleanVar(value=c.get("stopfail", False))}
        ttk.Label(cfg, text="패턴").pack(side="left")
        ttk.Combobox(cfg, textvariable=self.ag["pattern"], values=list(patterns.AGING_PATTERNS), width=13,
                     state="readonly").pack(side="left", padx=(2, 10))
        for k, t, w in (("hours", "시간(h)", 5), ("count", "프린터당 장수", 6), ("interval", "간격(초)", 5)):
            ttk.Label(cfg, text=t).pack(side="left")
            ttk.Entry(cfg, textvariable=self.ag[k], width=w).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(cfg, text="상태 조회", variable=self.ag["status"]).pack(side="left")
        ttk.Checkbutton(cfg, text="에러 시 일시정지/재개", variable=self.ag["pause"]).pack(side="left", padx=4)
        ttk.Checkbutton(cfg, text="자동 재연결", variable=self.ag["reconnect"]).pack(side="left")
        ttk.Checkbutton(cfg, text="실패 시 중지", variable=self.ag["stopfail"]).pack(side="left", padx=4)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="▶ 전체 시작", style="Big.TButton", command=self._ag_start_all).pack(side="left")
        ttk.Button(btns, text="■ 전체 중지", style="Big.TButton", command=self._ag_stop_all).pack(side="left", padx=6)
        ttk.Button(btns, text="선택 프린터 중지", command=self._ag_stop_selected).pack(side="left")
        ttk.Button(btns, text="선택 프린터 다시 시작", command=self._ag_restart_selected).pack(side="left", padx=6)
        self.ag_elapsed = tk.StringVar(value="")
        ttk.Label(btns, textvariable=self.ag_elapsed, font=("", 11, "bold")).pack(side="left", padx=12)

        # -- 진행 현황 --
        cols = ("name", "iface", "state", "elapsed", "sent", "ok", "fail", "pause", "reconn", "rate", "last")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=6, selectmode="extended")
        for col, t, w in zip(cols, ("프린터", "인터페이스", "상태", "경과", "전송", "정상", "실패", "일시정지", "재연결",
                                    "평균속도", "최근"),
                             (110, 70, 70, 75, 60, 60, 60, 65, 60, 80, 300)):
            tv.heading(col, text=t)
            tv.column(col, width=w, anchor="w" if col in ("name", "last") else "center")
        tv.tag_configure("fail", background="#FFC7CE")
        tv.tag_configure("run", background="#E2EFDA")
        tv.pack(fill="both", expand=True)
        self.ag_tv = tv
        ttk.Label(f, justify="left", foreground="#404040", text=(
            "■ [전체 시작] 하면 '사용' 체크된 프린터가 각각 독립적으로 동시에 돌아갑니다 (한 대가 실패해도 나머지는 계속)\n"
            "■ 영수증마다 프린터 이름·순번·시각이 찍히고, 로그 CSV 는 프린터별로 따로 생깁니다 (logs 폴더)\n"
            "■ 한 대로 여러 인터페이스를 보려면 같은 이름에 인터페이스만 다르게 여러 줄 등록하세요\n"
            "■ 1. 연결 설정 탭에서 같은 COM 포트를 열어 두었으면 시작 시 자동으로 닫습니다 · PC 절전 모드는 꺼 두세요"
        )).pack(anchor="w", pady=6)
        self.after(1000, self._ag_tick)

    def _ag_add_row(self, d):
        if len(self.ag_rows) >= 9:
            messagebox.showwarning(APP_TITLE, "최대 9대까지 등록할 수 있습니다.")
            return
        n = len(self.ag_rows) + 1
        v = {"use": tk.BooleanVar(value=d.get("use", True)),
             "name": tk.StringVar(value=d.get("name", f"프린터{n}")),
             "iface": tk.StringVar(value=d.get("iface", "RS232")),
             "kind": tk.StringVar(value=d.get("kind", "COM")),
             "target": tk.StringVar(value=d.get("target", "")),
             "baud": tk.StringVar(value=d.get("baud", "9600")),
             "fmt": tk.StringVar(value=d.get("fmt", "8N1")),
             "flow": tk.StringVar(value=d.get("flow", "없음"))}
        r = n
        widgets = [
            ttk.Checkbutton(self.ag_box, variable=v["use"]),
            ttk.Entry(self.ag_box, textvariable=v["name"], width=16),
            ttk.Combobox(self.ag_box, textvariable=v["iface"], values=CHANNELS, width=6, state="readonly"),
            ttk.Combobox(self.ag_box, textvariable=v["kind"], values=("COM", "WinPrinter", "File"), width=10,
                         state="readonly"),
            ttk.Combobox(self.ag_box, textvariable=v["target"], width=40),
            ttk.Combobox(self.ag_box, textvariable=v["baud"], values=BAUDS, width=8),
            ttk.Combobox(self.ag_box, textvariable=v["fmt"], values=FORMATS, width=5),
            ttk.Combobox(self.ag_box, textvariable=v["flow"], values=FLOWS, width=9, state="readonly"),
        ]
        row = {"vars": v, "widgets": widgets}
        widgets.append(ttk.Button(self.ag_box, text="삭제", width=5, command=lambda: self._ag_del_row(row)))
        for i, w in enumerate(widgets):
            w.grid(row=r, column=i, padx=2, pady=1, sticky="w")
        v["kind"].trace_add("write", lambda *a: self._ag_fill_targets(row))
        self.ag_rows.append(row)
        self._ag_fill_targets(row)

    def _ag_del_row(self, row):
        if row["vars"]["name"].get().strip() in self._ag_running_names():
            messagebox.showwarning(APP_TITLE, "진행 중인 프린터는 삭제할 수 없습니다. 먼저 중지하세요.")
            return
        for w in row["widgets"]:
            w.destroy()
        self.ag_rows.remove(row)
        for i, rw in enumerate(self.ag_rows, 1):
            for j, w in enumerate(rw["widgets"]):
                w.grid(row=i, column=j)

    def _ag_fill_targets(self, row):
        kind = row["vars"]["kind"].get()
        if kind == "COM":
            vals = [f"{p} — {d}" for p, d in list_com_ports()]
        elif kind == "WinPrinter":
            vals = list_win_printers()
        else:
            vals = [os.path.join(engine.LOG_DIR, f"dump_{row['vars']['name'].get()}.bin")]
            if not row["vars"]["target"].get().endswith(".bin"):
                row["vars"]["target"].set(vals[0])
        row["widgets"][4]["values"] = vals

    def _ag_refresh_ports(self):
        for row in self.ag_rows:
            self._ag_fill_targets(row)

    def _ag_running_names(self):
        return {name for name, r in self.agings.items() if r.running}

    def _ag_row_cfg(self, row):
        v = {k: x.get() for k, x in row["vars"].items()}
        tgt = v["target"].split(" — ")[0].strip()
        if not tgt:
            raise TransportError(f"{v['name']}: 포트/프린터를 선택하세요")
        fmt = (v["fmt"] or "8N1").upper()
        if v["kind"] == "COM":
            return {"kind": "COM", "port": tgt, "baudrate": int(v["baud"]), "bytesize": int(fmt[0]),
                    "parity": fmt[1], "stopbits": int(fmt[2]), "flow": v["flow"]}
        if v["kind"] == "WinPrinter":
            return {"kind": "WinPrinter", "printer": tgt}
        return {"kind": "File", "path": tgt}

    def _ag_free_port(self, port):
        """1. 연결 설정 탭에서 같은 COM 포트를 열어 두었으면 닫는다(Windows 는 포트 동시 사용 불가)."""
        for label, tr in list(self.session.channels.items()):
            if getattr(tr, "port", None) == port and tr.is_open:
                self._disconnect(label)
                self.log(f"[에이징] {port} 를 사용하던 '{label}' 채널 연결을 해제했습니다")

    def _ag_params(self):
        return (self.ag["pattern"].get(), int(self.ag["count"].get() or 0), float(self.ag["hours"].get() or 0),
                float(self.ag["interval"].get() or 0))

    def _ag_start_rows(self, rows, confirm=True):
        try:
            pattern, count, hours, interval = self._ag_params()
        except ValueError:
            messagebox.showerror(APP_TITLE, "시간/장수/간격을 숫자로 입력하세요")
            return
        if confirm and count == 0 and hours == 0:
            if not messagebox.askyesno(APP_TITLE, "종료 조건이 없습니다(수동 중지까지 계속). 시작할까요?"):
                return
        running = self._ag_running_names()
        names, ports, plan = set(), set(), []
        for row in rows:
            name = row["vars"]["name"].get().strip()
            if not name:
                messagebox.showerror(APP_TITLE, "프린터 이름이 비어 있는 줄이 있습니다.")
                return
            if name in names:
                messagebox.showerror(APP_TITLE, f"프린터 이름 '{name}' 이 중복됩니다. 줄마다 다른 이름을 쓰세요.")
                return
            names.add(name)
            if name in running:
                continue
            try:
                cfg = self._ag_row_cfg(row)
            except (TransportError, ValueError, IndexError) as e:
                messagebox.showerror(APP_TITLE, f"{name}: 설정 오류 — {e}")
                return
            key = cfg.get("port") or cfg.get("printer") or cfg.get("path")
            if key in ports:
                messagebox.showerror(APP_TITLE, f"'{key}' 가 두 줄 이상에 지정되어 있습니다.")
                return
            ports.add(key)
            plan.append((name, row["vars"]["iface"].get(), cfg))
        if not plan:
            messagebox.showinfo(APP_TITLE, "시작할 프린터가 없습니다 (이미 진행 중이거나 '사용' 체크 없음).")
            return

        self.ag_session.opts = dict(self.session.opts)
        errors, ok_names = [], []
        for name, iface, cfg in plan:
            if cfg["kind"] == "COM":
                self._ag_free_port(cfg["port"])
            tr = make_transport(name, cfg)
            try:
                tr.open()
            except TransportError as e:
                errors.append(f"{name}: {e}")
                continue
            self.ag_session.add(tr)
            runner = engine.AgingRunner(self.ag_session, [name], "기본", pattern, count, hours, interval,
                                        self.ag["status"].get(), self.ag["pause"].get(), self.ag["reconnect"].get(),
                                        self.ag["stopfail"].get())
            runner.iface = iface
            self.agings[name] = runner
            vals = (name, iface, "시작", "", 0, 0, 0, 0, 0, "", "")
            if self.ag_tv.exists(name):
                self.ag_tv.item(name, values=vals)      # 선택 상태 유지
            else:
                self.ag_tv.insert("", "end", iid=name, values=vals)
            threading.Thread(target=self._ag_run, args=(name, runner), daemon=True).start()
            ok_names.append(name)
        self.log(f"[에이징] 시작: {', '.join(ok_names) or '없음'}")
        self._save_settings()
        if errors:
            messagebox.showerror(APP_TITLE, "연결 실패로 시작하지 못한 프린터:\n\n" + "\n".join(errors))

    def _ag_run(self, name, runner):
        summary = runner.run()
        self.on_main(lambda: self._ag_finished(name, runner, summary))

    def _ag_start_all(self):
        rows = [r for r in self.ag_rows if r["vars"]["use"].get()]
        if not rows:
            messagebox.showwarning(APP_TITLE, "'사용' 체크된 프린터가 없습니다.")
            return
        self._ag_start_rows(rows)

    def _ag_restart_selected(self):
        sel = set(self.ag_tv.selection())
        rows = [r for r in self.ag_rows if r["vars"]["name"].get().strip() in sel]
        if not rows:
            messagebox.showinfo(APP_TITLE, "아래 진행 현황 표에서 다시 시작할 프린터를 선택하세요.")
            return
        self._ag_start_rows(rows, confirm=False)

    def _ag_stop_selected(self):
        for name in self.ag_tv.selection():
            r = self.agings.get(name)
            if r and r.running:
                r.cancel.set()
                self.log(f"[에이징][{name}] 중지 요청 — 현재 장 전송 후 멈춥니다")

    def _ag_stop_all(self):
        for name, r in self.agings.items():
            if r.running:
                r.cancel.set()
                self.log(f"[에이징][{name}] 중지 요청")

    @staticmethod
    def _hms(sec):
        e = int(sec)
        return f"{e // 3600:02d}:{e % 3600 // 60:02d}:{e % 60:02d}"

    def _ag_tick(self):
        n_run = 0
        for name, r in self.agings.items():
            if not self.ag_tv.exists(name):
                continue
            st = r.stats[name]
            rate = f"{st['bytes'] / st['secs'] / 1024:.1f}KB/s" if st["secs"] else ""
            state = "진행 중" if r.running else "종료"
            n_run += r.running
            self.ag_tv.item(name, values=(name, getattr(r, "iface", ""), state, self._hms(r.elapsed()), st["sent"],
                                          st["ok"], st["fail"], st["pause"], st["reconn"], rate, st["last"]),
                            tags=("fail",) if st["fail"] else (("run",) if r.running else ()))
        if self.agings:
            self.ag_elapsed.set(f"진행 중 {n_run}대 / 전체 {len(self.agings)}대")
        self.after(1000, self._ag_tick)

    def _ag_finished(self, name, runner, summary):
        tr = self.ag_session.channels.get(name)
        if tr:
            tr.close()
        rec = self.results.get("X04")
        note = (rec["note"] + "\n" if rec["note"] else "") + \
            f"[{time.strftime('%m-%d %H:%M')}] 에이징 {name}({getattr(runner, 'iface', '')}) {summary}"
        self.results.set("X04", note=note, tester=self.common["tester"].get(), fw=self.common["fw"].get())
        self._refresh_tv()
        if self._cur() and self._cur()["id"] == "X04":
            self._tc_select()
        if not self._ag_running_names():
            lines = [f"{n}: 전송 {r.stats[n]['sent']} / 정상 {r.stats[n]['ok']} / 실패 {r.stats[n]['fail']}"
                     for n, r in self.agings.items()]
            messagebox.showinfo(APP_TITLE, "모든 프린터 에이징이 종료되었습니다.\n\n" + "\n".join(lines) +
                                "\n\n자세한 내용은 X04 비고와 logs 폴더 CSV 를 확인하세요.")

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
