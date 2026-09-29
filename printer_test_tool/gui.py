"""열전사 프린터 검증 도구 — GUI (tkinter).

화면 구성
  1. 프린터 연결   : 프린터(이름)마다 RS232 / USB / BT 연결을 따로 설정·연결
  2. 테스트 케이스 : 프린터와 인터페이스를 골라 시험 실행 (인터페이스마다 따로 출력)
  3. 에이징        : 프린터·인터페이스를 체크해 동시에 에이징
  4. 패턴 인쇄     : 패턴 인쇄, 정보·상태 조회, 명령 직접 전송
  아래 [작업 현황] : 지금 무엇이 어디서 얼마나 진행 중인지 항상 표시 + 중지
"""
import json
import os
import pathlib
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

import engine
import patterns
from results import Results
from testcases import BY_ID, TC
from transports import TransportError, list_com_ports, list_win_printers, make_transport

APP_TITLE = "열전사 프린터 검증 도구"
SETTINGS = os.path.join(engine.BASE_DIR, "settings.json")
IFACES = ("RS232", "USB", "BT")
KINDS = ("COM", "WinPrinter", "File")
BAUDS = ("9600", "19200", "38400", "57600", "115200", "230400")
FORMATS = ("8N1", "7E1", "8E1", "8O1", "7O1", "8N2")
FLOWS = ("없음", "RTS/CTS", "DTR/DSR", "XON/XOFF")
IFACE_DEFAULTS = {"RS232": {"baud": "115200", "flow": "RTS/CTS"}, "USB": {"baud": "9600", "flow": "없음"},
                  "BT": {"baud": "9600", "flow": "없음"}}
MAX_PRINTERS = 9


def resource_path(name):
    """exe 로 묶였을 때는 임시 해제 폴더(_MEIPASS), 아니면 소스 폴더."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def cid(printer, iface):
    return f"{printer}/{iface}"


# ======================================================================== 작업
class Task:
    """화면 아래 [작업 현황]에 보이는 작업 하나. engine 함수에는 cancel 자리로 넘긴다."""
    _seq = 0

    def __init__(self, name, targets, cancel=None):
        Task._seq += 1
        self.id = f"T{Task._seq}"
        self.name = name
        self.targets = list(targets)
        self.cancel = cancel or threading.Event()
        self.state = "진행 중"
        self.msg = ""
        self.done = None
        self.total = None
        self.started = time.time()
        self.ended = None
        self.runner = None          # 에이징이면 AgingRunner

    # engine 은 cancel.is_set() 과 report() 를 쓴다
    def is_set(self):
        return self.cancel.is_set()

    def set(self):
        self.cancel.set()

    def report(self, msg=None, done=None, total=None):
        if msg is not None:
            self.msg = msg
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total

    @property
    def running(self):
        return self.ended is None

    def progress_text(self):
        if self.runner is not None:
            st = self.runner.stats[self.targets[0]]
            p = f"전송 {st['sent']} / 정상 {st['ok']} / 실패 {st['fail']}"
            if self.runner.count:
                p += f" (목표 {self.runner.count}장)"
            return p
        if self.total:
            return f"{self.done or 0}/{self.total} ({int(100 * (self.done or 0) / self.total)}%)"
        return ""

    def elapsed(self):
        return (self.ended or time.time()) - self.started


# ======================================================================== 앱
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x900")
        self.minsize(1050, 720)
        self.q = queue.Queue()
        self.session = engine.Session(log=self.log)
        self.results = Results()
        self.tasks = {}              # id -> Task (표시 순서 유지)
        self.busy = {}               # 채널 id -> Task
        self.printers = []           # 프린터 패널 목록
        self.cfg = self._load_settings()
        self._closing = False

        self._build()
        self.after(100, self._poll)
        self.after(500, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log(f"로그 폴더: {engine.LOG_DIR}")

    # ------------------------------------------------------------------ 공통
    def log(self, msg):
        self.q.put(("log", f"{time.strftime('%H:%M:%S')} {msg}"))

    def _poll(self):
        try:
            while True:
                try:
                    kind, payload = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    if kind == "log":
                        self.logbox.insert("end", payload + "\n")
                        self.logbox.see("end")
                    elif kind == "call":
                        payload()
                except Exception as e:  # 콜백 하나의 오류로 화면 갱신이 멈추지 않도록
                    self.logbox.insert("end", f"{time.strftime('%H:%M:%S')} [내부 오류] {e!r}\n")
                    self.logbox.see("end")
        finally:
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

    def _load_settings(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        cfg = {"common": {k: v.get() for k, v in self.common.items()},
               "printers": [p.to_dict() for p in self.printers],
               "aging": dict({k: v.get() for k, v in self.ag.items()}, checked=sorted(self.ag_checked)),
               "plan_path": self.cfg.get("plan_path", "")}
        self.cfg = cfg
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _on_close(self):
        running = self.running_tasks()
        if running:
            if not messagebox.askyesno(APP_TITLE, f"진행 중인 작업이 {len(running)}개 있습니다.\n모두 중지하고 종료할까요?"):
                return
            self._closing = True
            for t in running:
                t.set()
            end = time.time() + 10       # 현재 장 전송을 마치고 결과가 기록될 때까지 최대 10초
            while (self.running_tasks() or not self.q.empty()) and time.time() < end:
                self.update()
                time.sleep(0.05)
        self._save_settings()
        self.session.close_all()
        self.destroy()

    def open_manual(self):
        path = resource_path("manual.html")
        if not os.path.exists(path):
            messagebox.showerror(APP_TITLE, f"설명서 파일이 없습니다: {path}")
            return
        webbrowser.open(pathlib.Path(path).as_uri())

    # ------------------------------------------------------------------ 작업 관리
    def running_tasks(self):
        return [t for t in self.tasks.values() if t.running]

    def start_task(self, name, targets, work, done=None, task=None):
        """targets(채널 id 목록)가 비어 있어야 시작. work(task) -> 결과 dict 를 작업 스레드에서 실행."""
        for t in targets:
            other = self.busy.get(t)
            if other is not None:
                self.tasks_tv.selection_set(other.id)
                self.tasks_tv.see(other.id)
                messagebox.showwarning(
                    APP_TITLE,
                    f"'{t}' 는 지금 [{other.name}] 작업 중입니다.\n\n"
                    f"화면 아래 [작업 현황]에 해당 작업을 표시해 두었습니다.\n"
                    f"끝날 때까지 기다리거나, [선택 작업 중지]를 누른 뒤 다시 실행하세요.")
                return None
        task = task or Task(name, targets)
        self.tasks[task.id] = task
        for t in targets:
            self.busy[t] = task
        self.tasks_tv.insert("", 0, iid=task.id, values=(task.name, ", ".join(targets) or "-", "진행 중", "", "", ""))
        self.tasks_tv.selection_set(task.id)

        def run():
            res = None
            try:
                res = work(task)
                task.state = "중지됨" if task.is_set() else "완료"
            except TransportError as e:
                res = {"suggest": "FAIL", "summary": f"통신 오류: {e}"}
                task.state = "오류"
                self.log(f"[{task.name}] 통신 오류: {e}")
            except Exception as e:
                res = {"suggest": None, "summary": f"오류: {e!r}"}
                task.state = "오류"
                self.log(f"[{task.name}] 오류: {e!r}")
            finally:
                task.ended = time.time()
                if res and res.get("summary"):
                    task.msg = res["summary"]

                def fin():
                    for t in targets:
                        if self.busy.get(t) is task:
                            del self.busy[t]
                    if done:
                        done(res or {})
                self.on_main(fin)
        threading.Thread(target=run, daemon=True).start()
        return task

    def stop_selected_tasks(self):
        sel = [self.tasks[i] for i in self.tasks_tv.selection() if i in self.tasks]
        running = [t for t in sel if t.running]
        if not running:
            messagebox.showinfo(APP_TITLE, "[작업 현황]에서 '진행 중'인 작업을 선택한 뒤 누르세요.")
            return
        for t in running:
            t.set()
            self.log(f"[{t.name}] 중지 요청 ({', '.join(t.targets)}) — 현재 동작을 마치고 멈춥니다")

    def stop_all_tasks(self):
        running = self.running_tasks()
        if not running:
            messagebox.showinfo(APP_TITLE, "진행 중인 작업이 없습니다.")
            return
        if not messagebox.askyesno(APP_TITLE, f"진행 중인 작업 {len(running)}개(에이징 포함)를 모두 중지할까요?"):
            return
        for t in running:
            t.set()
        self.log(f"모두 중지 요청 — {len(running)}개 작업")

    def clear_finished_tasks(self):
        for tid in [i for i, t in self.tasks.items() if not t.running]:
            self.tasks_tv.delete(tid)
            del self.tasks[tid]

    @staticmethod
    def _hms(sec):
        e = int(sec)
        return f"{e // 3600:02d}:{e % 3600 // 60:02d}:{e % 60:02d}"

    def _tick(self):
        """0.5초마다 작업 현황·에이징 표 갱신."""
        n_run = 0
        for t in self.tasks.values():
            if not self.tasks_tv.exists(t.id):
                continue
            n_run += t.running
            state = t.state if not t.running or not t.is_set() else "중지 중…"
            self.tasks_tv.item(t.id, values=(t.name, ", ".join(t.targets) or "-", state, t.progress_text(),
                                             self._hms(t.elapsed()), t.msg),
                               tags=("run",) if t.running else (("err",) if t.state == "오류" else ()))
        self.tasks_head.set(f"작업 현황 — 진행 중 {n_run}개" if n_run else "작업 현황 — 진행 중인 작업 없음")
        self.title(f"{APP_TITLE}  (진행 중 {n_run})" if n_run else APP_TITLE)
        self._ag_tick()
        self.after(500, self._tick)

    # ------------------------------------------------------------------ 화면
    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        style.configure("Big.TButton", padding=6)
        style.configure("Title.TLabel", font=("", 13, "bold"))

        top = ttk.Frame(self, padding=(8, 6, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="사용 설명서 (도움말)", command=self.open_manual).pack(side="right")
        ttk.Button(top, text="로그 폴더 열기", command=lambda: self._open_folder(engine.LOG_DIR)).pack(side="right", padx=6)

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=6, pady=6)
        nb = ttk.Notebook(paned)
        self.nb = nb
        paned.add(nb, weight=5)

        # -- 작업 현황 (항상 보임) --
        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=2)
        bar = ttk.Frame(bottom)
        bar.pack(fill="x")
        self.tasks_head = tk.StringVar(value="작업 현황")
        ttk.Label(bar, textvariable=self.tasks_head, font=("", 10, "bold")).pack(side="left")
        ttk.Button(bar, text="끝난 작업 지우기", command=self.clear_finished_tasks).pack(side="right")
        ttk.Button(bar, text="■ 모두 중지", command=self.stop_all_tasks).pack(side="right", padx=4)
        ttk.Button(bar, text="■ 선택 작업 중지", command=self.stop_selected_tasks).pack(side="right")
        cols = ("name", "target", "state", "prog", "elapsed", "msg")
        tv = ttk.Treeview(bottom, columns=cols, show="headings", height=4, selectmode="extended")
        for c, t, w in zip(cols, ("작업", "대상 (프린터/통신)", "상태", "진행", "경과", "최근 내용"),
                           (170, 190, 70, 170, 70, 560)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w" if c in ("name", "target", "msg") else "center")
        tv.tag_configure("run", background="#E2EFDA")
        tv.tag_configure("err", background="#FFC7CE")
        tv.pack(fill="x")
        self.tasks_tv = tv
        self.logbox = ScrolledText(bottom, height=6, font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, pady=(4, 0))

        self._build_printers(nb)
        self._build_tc(nb)
        self._build_aging(nb)
        self._build_manual(nb)
        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab())

    def _open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # noqa
        else:
            messagebox.showinfo(APP_TITLE, path)

    def _on_tab(self):
        self._refresh_targets_ui()
        self._ag_rebuild()

    # ================================================================ 1. 프린터 연결
    def _build_printers(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=" 1. 프린터 연결 ")

        c = self.cfg.get("common", {})
        box = ttk.LabelFrame(f, text="공통 설정", padding=6)
        box.pack(fill="x")
        self.common = {
            "tester": tk.StringVar(value=c.get("tester", "")),
            "dots": tk.StringVar(value=c.get("dots", "576")),
            "encoding": tk.StringVar(value=c.get("encoding", "cp949")),
            "korean": tk.BooleanVar(value=c.get("korean", True)),
            "cut": tk.StringVar(value=c.get("cut", "partial")),
            "length": tk.StringVar(value=c.get("length", "120")),
        }
        items = [("시험자", ttk.Entry(box, textvariable=self.common["tester"], width=12)),
                 ("영수증 길이(mm)", ttk.Combobox(box, textvariable=self.common["length"],
                                              values=("80", "100", "120", "150", "200"), width=5)),
                 ("인쇄 폭(도트)", ttk.Combobox(box, textvariable=self.common["dots"], values=("576", "512", "432"), width=5)),
                 ("문자 인코딩", ttk.Combobox(box, textvariable=self.common["encoding"], values=("cp949", "utf-8"), width=6)),
                 ("컷", ttk.Combobox(box, textvariable=self.common["cut"], values=("partial", "full", "none"), width=7))]
        for i, (lbl, w) in enumerate(items):
            ttk.Label(box, text=lbl).grid(row=0, column=i * 2, sticky="e", padx=(8, 2))
            w.grid(row=0, column=i * 2 + 1, sticky="w")
        ttk.Checkbutton(box, text="한글 모드(FS &)", variable=self.common["korean"]).grid(row=0, column=10, padx=8)
        for v in self.common.values():
            v.trace_add("write", lambda *a: self._apply_common())
        self._apply_common()

        tb = ttk.Frame(f)
        tb.pack(fill="x", pady=6)
        ttk.Button(tb, text="+ 프린터 추가", command=lambda: self._add_printer({})).pack(side="left")
        ttk.Button(tb, text="포트 목록 새로고침", command=self._refresh_ports).pack(side="left", padx=4)
        ttk.Button(tb, text="전체 연결", command=lambda: [p.connect_all() for p in self.printers]).pack(side="left", padx=4)
        ttk.Button(tb, text="전체 해제", command=lambda: [p.disconnect_all() for p in self.printers]).pack(side="left")
        ttk.Button(tb, text="▶ 전체 빠른 점검", command=lambda: self.quick_check(self.printers)).pack(side="left", padx=4)
        ttk.Label(tb, text="※ '사용' 체크한 통신만 연결·시험 대상이 됩니다", foreground="#606060").pack(side="left", padx=8)

        # 스크롤 영역
        outer = ttk.Frame(f)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.pbox = ttk.Frame(canvas)
        self.pbox.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.pbox, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units")
                        if self.nb.index("current") == 0 else None)

        saved = self.cfg.get("printers") or [{"name": f"프린터{i}"} for i in (1, 2, 3)]
        for d in saved:
            self._add_printer(d)

    def _apply_common(self):
        try:
            dots = int(self.common["dots"].get())
        except ValueError:
            dots = 576
        try:
            length = float(self.common["length"].get() or 0)
        except ValueError:
            length = 120
        self.session.opts = {"dots": dots, "encoding": self.common["encoding"].get() or "cp949",
                             "korean_mode": bool(self.common["korean"].get()), "cut": self.common["cut"].get(),
                             "length_mm": length}

    def _add_printer(self, d):
        if len(self.printers) >= MAX_PRINTERS:
            messagebox.showwarning(APP_TITLE, f"최대 {MAX_PRINTERS}대까지 등록할 수 있습니다.")
            return
        if not d.get("name"):
            names = {p.name for p in self.printers}
            n = 1
            while f"프린터{n}" in names:
                n += 1
            d = dict(d, name=f"프린터{n}")
        self.printers.append(PrinterPanel(self, self.pbox, d))
        self._refresh_targets_ui()

    def _remove_printer(self, panel):
        if any(self.busy.get(c) for c in panel.connected.values()):
            messagebox.showwarning(APP_TITLE, "진행 중인 작업이 있는 프린터는 삭제할 수 없습니다. 먼저 중지하세요.")
            return
        if not messagebox.askyesno(APP_TITLE, f"'{panel.name}' 을(를) 목록에서 삭제할까요? (시험 결과는 남습니다)"):
            return
        panel.disconnect_all()
        panel.frame.destroy()
        self.printers.remove(panel)
        self._refresh_targets_ui()
        self._ag_rebuild()

    def _refresh_ports(self):
        for p in self.printers:
            p.fill_targets()

    def printer_by_name(self, name):
        return next((p for p in self.printers if p.name == name), None)

    def ensure(self, printer, iface):
        """해당 채널이 연결돼 있으면 id, 아니면 연결 시도 후 id (실패 시 None)."""
        p = self.printer_by_name(printer)
        if p is None:
            return None
        return p.connect(iface, quiet=True)

    def quick_check(self, panels):
        for p in panels:
            ifaces = [i for i in IFACES if p.rows[i]["use"].get() and p.rows[i]["target"].get()]
            labels = [x for x in (p.connect(i, quiet=True) for i in ifaces) if x]
            if not labels:
                continue

            def work(task, labels=labels, p=p):
                out = []
                for k, lab in enumerate(labels):
                    if task.is_set():
                        break
                    task.report(f"{lab} 점검 중", k, len(labels))
                    try:
                        r = engine.act_quick_check(self.session, lab, task)
                    except TransportError as e:
                        r = {"summary": f"통신 오류: {e}"}
                    fw = r.get("info", {}).get("펌웨어 버전")
                    if fw:
                        self.on_main(lambda fw=fw, p=p: p.fw.set(fw))
                    out.append(f"[{lab.split('/')[-1]}] {r['summary']}")
                task.report(None, len(labels), len(labels))
                return {"summary": " | ".join(out)}
            self.start_task(f"빠른 점검 {p.name}", labels, work, lambda r: self.log(r.get("summary", "")))

    # ================================================================ 대상 선택 (프린터 + 통신)
    def _make_target_picker(self, parent):
        """프린터 콤보 + 통신 체크박스."""
        fr = ttk.Frame(parent)
        pv = tk.StringVar()
        ttk.Label(fr, text="프린터").pack(side="left")
        cb = ttk.Combobox(fr, textvariable=pv, width=14, state="readonly")
        cb.pack(side="left", padx=4)
        ttk.Label(fr, text="  통신").pack(side="left")
        iv, checks = {}, {}
        for i in IFACES:
            iv[i] = tk.BooleanVar(value=False)
            checks[i] = ttk.Checkbutton(fr, text=i, variable=iv[i])
            checks[i].pack(side="left")
        picker = {"printer": pv, "ifaces": iv, "combo": cb, "checks": checks, "frame": fr}
        pv.trace_add("write", lambda *a: self._update_picker(picker))
        self._pickers = getattr(self, "_pickers", []) + [picker]
        return picker

    def _update_picker(self, picker):
        p = self.printer_by_name(picker["printer"].get())
        for i in IFACES:
            used = p is not None and p.rows[i]["use"].get()
            mark = "●" if p and p.is_connected(i) else ""
            picker["checks"][i].configure(text=f"{i}{mark}", state="normal" if used else "disabled")
            if not used:
                picker["ifaces"][i].set(False)

    def _refresh_targets_ui(self):
        names = [p.name for p in self.printers]
        for pk in getattr(self, "_pickers", []):
            pk["combo"]["values"] = names
            if pk["printer"].get() not in names:
                pk["printer"].set(names[0] if names else "")
            self._update_picker(pk)
        if hasattr(self, "tv"):
            self._refresh_tv()

    def picked(self, picker):
        """선택된 (프린터이름, [통신...])"""
        return picker["printer"].get(), [i for i in IFACES if picker["ifaces"][i].get()]

    # ================================================================ 2. 테스트 케이스
    def _build_tc(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=" 2. 테스트 케이스 ")
        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True)
        cols = ("id", "cat", "name", "result")
        tv = ttk.Treeview(left, columns=cols, show="headings", height=20, selectmode="browse")
        for c, t, w in zip(cols, ("ID", "구분", "항목", "결과"), (48, 92, 180, 64)):
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
        self.tc_info = tk.Text(right, height=7, wrap="word", relief="flat", background="#F7F7F7")
        self.tc_info.pack(fill="x", pady=4)

        run = ttk.LabelFrame(right, text="실행 대상 — 체크한 통신마다 따로 인쇄 (●=연결됨)", padding=6)
        run.pack(fill="x")
        self.tc_pick = self._make_target_picker(run)
        self.tc_pick["frame"].pack(side="left")
        self.tc_pick["printer"].trace_add("write", lambda *a: self._refresh_tv())
        self.run_btn = ttk.Button(run, text="▶ 실행", style="Big.TButton", command=self._tc_run)
        self.run_btn.pack(side="left", padx=8)
        self.suggest_var = tk.StringVar()
        ttk.Label(right, textvariable=self.suggest_var, foreground="#1F4E78").pack(anchor="w")

        res = ttk.LabelFrame(right, text="판정 — 선택한 프린터의 결과로 저장", padding=6)
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
        self._refresh_targets_ui()
        tv.selection_set(TC[0]["id"])

    def _cur_printer(self):
        return self.tc_pick["printer"].get()

    def _refresh_tv(self):
        pr = self._cur_printer()
        for t in TC:
            r = self.results.get(pr, t["id"])["result"]
            self.tv.item(t["id"], values=(t["id"], t["cat"], t["name"], r), tags=(r,))
        c = self.results.counts(pr)
        done = c["Pass"] + c["Fail"]
        rate = f"{c['Pass'] / done * 100:.0f}%" if done else "-"
        self.count_var.set(f"[{pr or '-'}] 전체 {len(TC)} | Pass {c['Pass']} | Fail {c['Fail']} | N/A {c['N/A']} | "
                           f"미실시 {c['미실시']} | 합격률 {rate}")
        if self._cur():
            self._load_result()

    def _cur(self):
        sel = self.tv.selection()
        return BY_ID[sel[0]] if sel else None

    def _load_result(self):
        t = self._cur()
        r = self.results.get(self._cur_printer(), t["id"])
        self.res_var.set(r["result"])
        self.defect_var.set(r["defect"])
        self.note.delete("1.0", "end")
        self.note.insert("end", r["note"])

    def _tc_select(self):
        t = self._cur()
        if not t:
            return
        self.tc_title.set(f"{t['id']}  {t['name']}  ({t['cat']})")
        self.tc_info.configure(state="normal")
        self.tc_info.delete("1.0", "end")
        how = {"RS232": "RS232 에서 실행", "USB": "USB 에서 실행", "BT": "BT 에서 실행",
               "ANY": "체크한 통신마다 각각 실행", "ALL": "체크한 통신을 함께 사용"}[t["channel"]]
        auto = "수동 확인 항목 (실행 버튼 없음)" if t["action"] is None else f"프로그램 실행 지원 — {how}"
        self.tc_info.insert("end", f"방법: {t['method']}\n합격 기준: {t['criterion']}\n{auto}\n\n{t['guide']}")
        self.tc_info.configure(state="disabled")
        p = self.printer_by_name(self._cur_printer())
        for i in IFACES:
            usable = p is not None and p.rows[i]["use"].get()
            want = (t["channel"] == i) or (t["channel"] in ("ANY", "ALL"))
            self.tc_pick["ifaces"][i].set(bool(usable and want))
        self.run_btn.configure(state="disabled" if t["action"] is None else "normal")
        self._load_result()
        self.suggest_var.set("")

    def _tc_save(self, next_=False):
        t = self._cur()
        pr = self._cur_printer()
        if not t or not pr:
            return
        p = self.printer_by_name(pr)
        self.results.set(pr, t["id"], result=self.res_var.get(), tester=self.common["tester"].get(),
                         fw=p.fw.get() if p else "", defect=self.defect_var.get(),
                         note=self.note.get("1.0", "end").strip())
        self._refresh_tv()
        self.log(f"[{pr}][{t['id']}] 결과 저장: {self.res_var.get()}")
        if next_:
            i = [x["id"] for x in TC].index(t["id"])
            if i + 1 < len(TC):
                self.tv.selection_set(TC[i + 1]["id"])
                self.tv.see(TC[i + 1]["id"])

    def _tc_done(self, printer, tid, res):
        line = f"[{time.strftime('%m-%d %H:%M')}] {res.get('summary', '')}"
        p = self.printer_by_name(printer)
        self.results.add_note(printer, tid, line, fw=p.fw.get() if p else None)
        sug = res.get("suggest")
        if sug in ("PASS", "FAIL", "N/A"):
            self.results.set(printer, tid, result={"PASS": "Pass", "FAIL": "Fail", "N/A": "N/A"}[sug],
                             tester=self.common["tester"].get())
        self.log(f"[{printer}][{tid}] {res.get('summary', '')}")
        if self._cur() and self._cur()["id"] == tid and self._cur_printer() == printer:
            self.suggest_var.set(f"자동 판정: {sug} (확인 후 필요하면 바꿔서 [결과 저장])" if sug in ("PASS", "FAIL", "N/A")
                                 else "출력물을 보고 판정한 뒤 [결과 저장]을 누르세요")
        self._refresh_tv()

    def _tc_run(self):
        t = self._cur()
        if not t or t["action"] is None:
            return
        pr, ifaces = self.picked(self.tc_pick)
        if not pr:
            messagebox.showwarning(APP_TITLE, "프린터를 선택하세요 (1. 프린터 연결 탭에서 등록).")
            return
        a, kind, tid, s = t["action"], t["action"][0], t["id"], self.session
        if kind == "aging":
            self.nb.select(2)
            return
        if kind == "devices":
            self._show_devices()
            return
        if not ifaces:
            messagebox.showwarning(APP_TITLE, "통신(RS232/USB/BT)을 하나 이상 체크하세요.\n"
                                              "체크가 안 되면 1. 프린터 연결 탭에서 '사용'을 켜세요.")
            return
        labels = []
        for i in ifaces:
            lab = self.ensure(pr, i)
            if lab is None:
                return
            labels.append(lab)
        if kind == "speed":
            self._speed_test(pr, tid, labels)
            return

        # ---- 실행 전에 필요한 값 묻기 (메인 스레드) ----
        params = {}
        if kind == "burst":
            if tid == "T03":
                d = simpledialog.askstring(APP_TITLE, "현재 거리(예: 1m, 5m, 10m)", parent=self)
                if d is None:
                    return
                params["tag"] = f"@{d}"
            params["n"] = simpledialog.askinteger(APP_TITLE, "인쇄 장수", initialvalue=a[2], minvalue=1, parent=self)
            if not params["n"]:
                return
        elif kind == "reconnect":
            params["n"] = simpledialog.askinteger(APP_TITLE, "목표 재연결 횟수", initialvalue=a[1], minvalue=1, parent=self)
            if not params["n"]:
                return
        elif kind == "cut":
            params["n"] = simpledialog.askinteger(APP_TITLE, "부분/전체 컷 각각 몇 회? (영수증 1장씩)",
                                                  initialvalue=10, minvalue=1, parent=self)
            if not params["n"]:
                return
        elif kind == "comm":
            if tid == "R01":
                bauds = simpledialog.askstring(APP_TITLE, "시험할 속도(쉼표 구분)",
                                               initialvalue="9600,19200,38400,57600,115200", parent=self)
                fmts = "8N1"
            else:
                bauds = self.printer_by_name(pr).rows[ifaces[0]]["baud"].get()
                fmts = simpledialog.askstring(APP_TITLE, "시험할 형식(쉼표 구분)", initialvalue="8N1,7E1,8E1,8O1", parent=self)
            if not bauds or not fmts:
                return
            try:
                params["cfgs"] = [(int(b), f.strip().upper()) for b in bauds.split(",") for f in fmts.split(",")]
            except ValueError:
                messagebox.showerror(APP_TITLE, "입력 형식 오류")
                return
        elif kind == "mismatch":
            params["wb"] = simpledialog.askinteger(APP_TITLE, "일부러 틀리게 보낼 속도", initialvalue=9600, parent=self)
            if not params["wb"]:
                return
        elif kind in ("x02", "x03") and len(labels) < 2:
            messagebox.showwarning(APP_TITLE, "이 시험은 통신을 2개 이상 체크해야 합니다.")
            return

        def one(task, lab):
            """통신 하나에 대해 실행."""
            if kind == "print":
                return engine.act_print(s, lab, a[1], task)
            if kind == "burst":
                return engine.act_burst(s, lab, a[1], params["n"], task, params.get("tag", ""))
            if kind == "burst_pat":
                return engine.act_burst_pattern(s, lab, a[1], a[2], task)
            if kind == "reconnect":
                return engine.act_reconnect(s, lab, params["n"], task, a[2])
            if kind == "status":
                return engine.act_status(s, lab, task)
            if kind == "monitor":
                return engine.act_status_monitor(s, lab, a[1], task, a[2])
            if kind == "cut":
                return engine.act_cut(s, lab, params["n"], task)
            if kind == "drawer":
                return engine.act_drawer(s, lab, task)
            if kind == "comm":
                return engine.act_comm_configs(s, lab, params["cfgs"], self.ask_main, task)
            if kind == "mismatch":
                return engine.act_mismatch(s, lab, params["wb"], task)
            if kind == "info":
                r = engine.act_info(s, lab, task)
                self._apply_fw(pr, r)
                return r
            if kind == "quick":
                r = engine.act_quick_check(s, lab, task)
                self._apply_fw(pr, r)
                return r
            raise ValueError(kind)

        def work(task):
            if kind == "x01":
                return engine.act_all_channels(s, task, labels)
            if kind == "x02":
                return engine.act_concurrent(s, task, labels=labels)
            if kind == "x03":
                main = next((lb for lb in labels if lb.endswith("/USB")), labels[0])
                other = next((lb for lb in labels if lb.endswith("/BT") and lb != main), None) or \
                    next(lb for lb in labels if lb != main)
                return engine.act_interleave(s, main, other, task)
            outs, sugg = [], []
            for k, lab in enumerate(labels):
                if task.is_set():
                    break
                iface = lab.split("/")[-1]
                task.report(f"[{iface}] 실행 중 ({k + 1}/{len(labels)})")
                try:
                    r = one(task, lab)
                except TransportError as e:
                    r = {"suggest": "FAIL", "summary": f"통신 오류: {e}"}
                outs.append(f"[{iface}] {r.get('summary', '')}")
                sugg.append(r.get("suggest"))
            if sugg and all(x == "PASS" for x in sugg):
                sug = "PASS"
            elif "FAIL" in sugg:
                sug = "FAIL"
            elif sugg and all(x == "N/A" for x in sugg):
                sug = "N/A"
            else:
                sug = None
            return {"suggest": sug, "summary": " / ".join(outs) or "중지됨"}

        self.log(f"[{pr}][{tid}] 실행 — {', '.join(ifaces)}")
        self.start_task(f"{tid} {t['name']}", labels, work, lambda r: self._tc_done(pr, tid, r))

    def _apply_fw(self, printer, r):
        """작업 스레드에서 호출됨 — 화면 변수는 메인 스레드에서만 만진다."""
        fw = r.get("info", {}).get("펌웨어 버전")
        if not fw:
            return

        def apply():
            p = self.printer_by_name(printer)
            if p:
                p.fw.set(fw)
        self.on_main(apply)

    def _show_devices(self):
        ports = list_com_ports()
        prs = list_win_printers()
        lines = ["[COM 포트]"] + [f"  {p}  {d}" for p, d in ports] + ["", "[Windows 프린터]"] + [f"  {p}" for p in prs]
        text = "\n".join(lines)
        self.log(text)
        messagebox.showinfo(APP_TITLE, text or "장치 없음")

    def _speed_test(self, printer, tid, labels):
        length = simpledialog.askinteger(APP_TITLE, "인쇄 길이(mm) — 속도 측정만 예외로 길게 인쇄합니다",
                                         initialvalue=500, minvalue=100, parent=self)
        if not length:
            return
        outs = []
        for lab in labels:
            if self.busy.get(lab):
                messagebox.showwarning(APP_TITLE, f"'{lab}' 는 다른 작업 중입니다. [작업 현황]을 확인하세요.")
                return
            data = patterns.pattern_speed(self.session.opts, lab, length)
            t0 = time.perf_counter()
            threading.Thread(target=lambda d=data, lb=lab: engine._safe_write(self.session, lb, d), daemon=True).start()
            messagebox.showinfo(APP_TITLE, f"[{lab}]\n인쇄가 끝나는 순간(컷) [확인]을 누르세요.", parent=self)
            secs = time.perf_counter() - t0
            outs.append(f"[{lab.split('/')[-1]}] {length}mm / {secs:.1f}s = {length / secs:.1f} mm/s")
        self._tc_done(printer, tid, {"suggest": None, "summary": " / ".join(outs) + " (전송 시작~확인 클릭 기준)"})

    def _export_csv(self):
        p = self.results.export_csv()
        self.log(f"CSV 저장: {p}")
        messagebox.showinfo(APP_TITLE, f"모든 프린터의 결과를 저장했습니다.\n{p}")

    def _export_xlsx(self):
        printers = [p for p in self.results.printers() if self.results.data.get(p)]
        if not printers:
            messagebox.showinfo(APP_TITLE, "저장된 결과가 없습니다.")
            return
        path = filedialog.askopenfilename(title="검증 계획표 엑셀 선택", filetypes=[("Excel", "*.xlsx")],
                                          initialfile=os.path.basename(self.cfg.get("plan_path", "")))
        if not path:
            return
        outs = []
        try:
            for pr in printers:
                out, n = self.results.export_xlsx(path, pr)
                outs.append(f"{pr}: {n}개 항목 → {os.path.basename(out)}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"반영 실패: {e}")
            return
        self.cfg["plan_path"] = path
        self.log("엑셀 반영: " + " | ".join(outs))
        messagebox.showinfo(APP_TITLE, "프린터별로 새 파일을 만들었습니다 (계획표와 같은 폴더).\n\n" + "\n".join(outs))

    # ================================================================ 3. 에이징
    def _build_aging(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=" 3. 에이징 ")
        c = self.cfg.get("aging", {})
        self.ag = {"pattern": tk.StringVar(value=c.get("pattern", "영수증")),
                   "hours": tk.StringVar(value=c.get("hours", "12")),
                   "count": tk.StringVar(value=c.get("count", "0")),
                   "interval": tk.StringVar(value=c.get("interval", "2")),
                   "status": tk.BooleanVar(value=c.get("status", True)),
                   "pause": tk.BooleanVar(value=c.get("pause", True)),
                   "reconnect": tk.BooleanVar(value=c.get("reconnect", True)),
                   "stopfail": tk.BooleanVar(value=c.get("stopfail", False))}
        if self.ag["pattern"].get() not in patterns.AGING_PATTERNS:
            self.ag["pattern"].set("영수증")
        cfg = ttk.LabelFrame(f, text="설정 (체크한 모든 대상에 공통)", padding=6)
        cfg.pack(fill="x")
        ttk.Label(cfg, text="패턴").pack(side="left")
        ttk.Combobox(cfg, textvariable=self.ag["pattern"], values=list(patterns.AGING_PATTERNS), width=13,
                     state="readonly").pack(side="left", padx=(2, 10))
        for k, t, w in (("hours", "시간(h)", 5), ("count", "대상당 장수", 6), ("interval", "간격(초)", 5)):
            ttk.Label(cfg, text=t).pack(side="left")
            ttk.Entry(cfg, textvariable=self.ag[k], width=w).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(cfg, text="상태 조회", variable=self.ag["status"]).pack(side="left")
        ttk.Checkbutton(cfg, text="에러 시 일시정지/재개", variable=self.ag["pause"]).pack(side="left", padx=4)
        ttk.Checkbutton(cfg, text="자동 재연결", variable=self.ag["reconnect"]).pack(side="left")
        ttk.Checkbutton(cfg, text="실패 시 중지", variable=self.ag["stopfail"]).pack(side="left", padx=4)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="▶ 체크한 대상 시작", style="Big.TButton", command=self._ag_start).pack(side="left")
        ttk.Button(btns, text="■ 체크한 대상 중지", style="Big.TButton", command=self._ag_stop_checked).pack(side="left", padx=6)
        ttk.Button(btns, text="전체 체크", command=lambda: self._ag_check_all(True)).pack(side="left")
        ttk.Button(btns, text="전체 해제", command=lambda: self._ag_check_all(False)).pack(side="left", padx=4)
        ttk.Label(btns, text="시간·장수 0 = 제한 없음", foreground="#606060").pack(side="left", padx=8)

        cols = ("sel", "printer", "iface", "port", "state", "elapsed", "sent", "ok", "fail", "pause", "reconn", "last")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=10, selectmode="none")
        for col, t, w in zip(cols, ("선택", "프린터", "통신", "포트", "상태", "경과", "전송", "정상", "실패", "일시정지",
                                    "재연결", "최근"),
                             (44, 110, 60, 110, 70, 75, 55, 55, 55, 65, 55, 330)):
            tv.heading(col, text=t)
            tv.column(col, width=w, anchor="w" if col in ("printer", "last", "port") else "center")
        tv.tag_configure("fail", background="#FFC7CE")
        tv.tag_configure("run", background="#E2EFDA")
        tv.pack(fill="both", expand=True)
        tv.bind("<Button-1>", self._ag_click)
        self.ag_tv = tv
        self.ag_checked = set(c.get("checked", []))
        ttk.Label(f, justify="left", foreground="#404040", text=(
            "■ 목록 = 1. 프린터 연결 탭에서 '사용' 체크한 프린터·통신. 줄을 클릭하면 ☑/☐ 가 바뀝니다 → [체크한 대상 시작]\n"
            "■ 대상마다 독립 실행 — 한 대가 실패·일시정지해도 나머지는 계속. 진행 상황은 이 표와 화면 아래 [작업 현황]에 표시\n"
            "■ 영수증마다 프린터 이름·통신·순번·시각 인쇄, 로그 CSV 는 대상별로 따로 생성 (logs 폴더)\n"
            "■ 용지가 떨어지면 일시정지 → 보충하면 자동 재개 · PC 절전 모드는 꺼 두세요"
        )).pack(anchor="w", pady=6)
        self._ag_rebuild()

    def _ag_targets(self):
        out = []
        for p in self.printers:
            for i in IFACES:
                if p.rows[i]["use"].get() and p.name:
                    out.append((p, i, cid(p.name, i)))
        return out

    def _ag_rebuild(self):
        if not hasattr(self, "ag_tv"):
            return
        want = [c for _, _, c in self._ag_targets()]
        for iid in self.ag_tv.get_children():
            t = self.busy.get(iid)
            if iid not in want and not (t and t.runner):
                self.ag_tv.delete(iid)
        for p, i, c in self._ag_targets():
            port = p.rows[i]["target"].get().split(" — ")[0]
            vals = ("☑" if c in self.ag_checked else "☐", p.name, i, port, "대기", "", "", "", "", "", "", "")
            if not self.ag_tv.exists(c):
                self.ag_tv.insert("", "end", iid=c, values=vals)
            else:
                cur = list(self.ag_tv.item(c)["values"])
                cur[0], cur[3] = vals[0], port
                self.ag_tv.item(c, values=cur)

    def _ag_click(self, e):
        row = self.ag_tv.identify_row(e.y)
        if not row:
            return
        if row in self.ag_checked:
            self.ag_checked.discard(row)
        else:
            self.ag_checked.add(row)
        vals = list(self.ag_tv.item(row)["values"])
        vals[0] = "☑" if row in self.ag_checked else "☐"
        self.ag_tv.item(row, values=vals)

    def _ag_check_all(self, on):
        self.ag_checked = set(self.ag_tv.get_children()) if on else set()
        self._ag_rebuild()

    def _ag_start(self):
        targets = [(p, i, c) for p, i, c in self._ag_targets() if c in self.ag_checked]
        if not targets:
            messagebox.showwarning(APP_TITLE, "표에서 줄을 클릭해 ☑ 로 체크한 뒤 시작하세요.")
            return
        try:
            pattern = self.ag["pattern"].get()
            count, hours = int(self.ag["count"].get() or 0), float(self.ag["hours"].get() or 0)
            interval = float(self.ag["interval"].get() or 0)
        except ValueError:
            messagebox.showerror(APP_TITLE, "시간/장수/간격을 숫자로 입력하세요")
            return
        if count == 0 and hours == 0 and not messagebox.askyesno(
                APP_TITLE, "종료 조건이 없습니다(중지할 때까지 계속). 시작할까요?"):
            return
        started, errors = [], []
        for p, i, c in targets:
            if self.busy.get(c):
                errors.append(f"{c}: 이미 [{self.busy[c].name}] 진행 중")
                continue
            lab = p.connect(i, quiet=True)
            if lab is None:
                errors.append(f"{c}: 연결 실패")
                continue
            runner = engine.AgingRunner(self.session, [lab], "기본", pattern, count, hours, interval,
                                        self.ag["status"].get(), self.ag["pause"].get(), self.ag["reconnect"].get(),
                                        self.ag["stopfail"].get())
            runner.running = True
            task = Task("에이징", [lab], cancel=runner.cancel)
            task.runner = runner
            self.start_task("에이징", [lab], lambda tk_, r=runner: {"summary": r.run()},
                            lambda res, r=runner, lab=lab: self._ag_finished(lab, r, res), task=task)
            started.append(lab)
        self._save_settings()
        self.log(f"[에이징] 시작: {', '.join(started) or '없음'}")
        if errors:
            messagebox.showwarning(APP_TITLE, "시작하지 못한 대상:\n\n" + "\n".join(errors))

    def _ag_stop_checked(self):
        n = 0
        for c in self.ag_checked:
            t = self.busy.get(c)
            if t and t.runner:
                t.set()
                n += 1
        self.log(f"[에이징] 중지 요청 {n}개 — 현재 장 전송 후 멈춥니다")

    def _ag_tick(self):
        if not hasattr(self, "ag_tv"):
            return
        latest = {}
        for t in self.tasks.values():
            if t.runner:
                latest[t.targets[0]] = t
        for c, t in latest.items():
            if not self.ag_tv.exists(c):
                continue
            r, st = t.runner, t.runner.stats[c]
            vals = list(self.ag_tv.item(c)["values"])
            vals[4:] = ["진행 중" if t.running else t.state, self._hms(r.elapsed()), st["sent"], st["ok"], st["fail"],
                        st["pause"], st["reconn"], st["last"]]
            self.ag_tv.item(c, values=vals, tags=("fail",) if st["fail"] else (("run",) if t.running else ()))

    def _ag_finished(self, lab, runner, res):
        printer, iface = lab.rsplit("/", 1)
        p = self.printer_by_name(printer)
        self.results.add_note(printer, "X04", f"[{time.strftime('%m-%d %H:%M')}] 에이징 {iface}: {res.get('summary', '')}",
                              tester=self.common["tester"].get(), fw=p.fw.get() if p else "")
        self._refresh_tv()
        if not any(t.runner and t.running for t in self.tasks.values()) and not self._closing:
            lines = []
            for t in self.tasks.values():
                if t.runner:
                    st = t.runner.stats[t.targets[0]]
                    lines.append(f"{t.targets[0]}: 전송 {st['sent']} / 정상 {st['ok']} / 실패 {st['fail']}")
            messagebox.showinfo(APP_TITLE, "진행 중인 에이징이 모두 끝났습니다.\n\n" + "\n".join(lines[-12:]) +
                                "\n\n자세한 내용은 X04 비고와 logs 폴더 CSV 를 확인하세요.")

    # ================================================================ 4. 패턴 인쇄 / 명령
    def _build_manual(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=" 4. 패턴 인쇄 / 명령 ")
        tg = ttk.LabelFrame(f, text="대상 (체크한 통신마다 각각 인쇄)", padding=6)
        tg.pack(fill="x")
        self.m_pick = self._make_target_picker(tg)
        self.m_pick["frame"].pack(side="left")
        ttk.Button(tg, text="모든 통신 체크",
                   command=lambda: [self.m_pick["ifaces"][i].set(str(self.m_pick["checks"][i]["state"]) != "disabled")
                                    for i in IFACES]).pack(side="left", padx=8)

        a = ttk.LabelFrame(f, text="패턴 인쇄 (모두 영수증 길이로 출력)", padding=8)
        a.pack(fill="x", pady=6)
        self.m_pat = tk.StringVar(value="연결 확인")
        self.m_rep = tk.StringVar(value="1")
        ttk.Label(a, text="패턴").pack(side="left")
        ttk.Combobox(a, textvariable=self.m_pat, values=list(patterns.PATTERNS), width=16, state="readonly").pack(
            side="left", padx=4)
        ttk.Label(a, text="반복").pack(side="left", padx=(10, 0))
        ttk.Entry(a, textvariable=self.m_rep, width=5).pack(side="left", padx=4)
        ttk.Button(a, text="인쇄", command=self._m_print).pack(side="left", padx=8)

        b = ttk.LabelFrame(f, text="조회", padding=8)
        b.pack(fill="x")
        ttk.Button(b, text="상태 조회", command=lambda: self._m_run("상태 조회", engine.act_status)).pack(side="left")
        ttk.Button(b, text="프린터 정보(FW)", command=lambda: self._m_run("프린터 정보", engine.act_info)).pack(side="left", padx=4)
        ttk.Button(b, text="빠른 점검", command=lambda: self._m_run("빠른 점검", engine.act_quick_check)).pack(side="left")
        ttk.Button(b, text="상태 감시 60초",
                   command=lambda: self._m_run("상태 감시", lambda s, lb, t: engine.act_status_monitor(s, lb, 60, t))).pack(
            side="left", padx=4)

        c = ttk.LabelFrame(f, text="명령 직접 전송 (HEX 또는 텍스트)", padding=8)
        c.pack(fill="x", pady=6)
        self.m_hex = tk.StringVar(value="1B 40 1B 61 01 48 45 4C 4C 4F 0A 1D 56 42 00")
        self.m_mode = tk.StringVar(value="HEX")
        ttk.Combobox(c, textvariable=self.m_mode, values=("HEX", "텍스트"), width=6, state="readonly").pack(side="left")
        ttk.Entry(c, textvariable=self.m_hex, width=70).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(c, text="전송", command=self._m_send).pack(side="left")
        self.m_wait = tk.BooleanVar(value=False)
        ttk.Checkbutton(c, text="응답 읽기", variable=self.m_wait).pack(side="left", padx=4)
        ttk.Label(f, justify="left", foreground="#404040", text=(
            "자주 쓰는 명령 (HEX)\n"
            "  초기화 1B 40   |  컷(부분) 1D 56 42 00   |  컷(전체) 1D 56 41 00   |  급지 3줄 1B 64 03\n"
            "  상태 조회 10 04 01~04   |  펌웨어 1D 49 41   |  드로어 1B 70 00 19 FA   |  셀프테스트(일부 모델) 1D 28 41 02 00 00 02"
        )).pack(anchor="w", pady=6)

    def _m_labels(self):
        pr, ifaces = self.picked(self.m_pick)
        if not pr or not ifaces:
            messagebox.showwarning(APP_TITLE, "프린터와 통신(RS232/USB/BT)을 체크하세요.")
            return None, []
        labels = []
        for i in ifaces:
            lab = self.ensure(pr, i)
            if lab is None:
                return None, []
            labels.append(lab)
        return pr, labels

    def _m_print(self):
        pr, labels = self._m_labels()
        if not labels:
            return
        try:
            n = max(1, int(self.m_rep.get()))
        except ValueError:
            n = 1
        pat = self.m_pat.get()

        def work(task):
            for k, lab in enumerate(labels):
                for i in range(n):
                    if task.is_set():
                        return {"summary": "중지됨"}
                    task.report(f"{lab} {pat} {i + 1}/{n}", k * n + i, len(labels) * n)
                    engine.act_print(self.session, lab, pat, task)
            task.report(None, len(labels) * n, len(labels) * n)
            return {"summary": f"{pat} × {n} 완료 ({', '.join(lb.split('/')[-1] for lb in labels)})"}
        self.start_task(f"패턴 인쇄: {pat}", labels, work, lambda r: self.log(r.get("summary", "")))

    def _m_run(self, name, fn):
        pr, labels = self._m_labels()
        if not labels:
            return

        def work(task):
            out = []
            for lab in labels:
                if task.is_set():
                    break
                task.report(f"{lab} {name}")
                r = fn(self.session, lab, task)
                self._apply_fw(pr, r)
                out.append(f"[{lab.split('/')[-1]}] {r['summary']}")
            return {"summary": " / ".join(out)}
        self.start_task(name, labels, work, lambda r: self.log(r.get("summary", "")))

    def _m_send(self):
        pr, labels = self._m_labels()
        if not labels:
            return
        txt = self.m_hex.get()
        try:
            data = bytes.fromhex(txt.replace(",", " ")) if self.m_mode.get() == "HEX" else \
                txt.encode(self.session.opts["encoding"]) + b"\n"
        except ValueError:
            messagebox.showerror(APP_TITLE, "HEX 형식 오류 (예: 1B 40 0A)")
            return
        want = self.m_wait.get()

        def work(task):
            out = []
            for lab in labels:
                tr = self.session.get(lab)
                if want:
                    resp = tr.query(data, 64, 1.0)
                    out.append(f"[{lab}] 응답: " + (resp.hex(" ").upper() if resp else "없음"))
                else:
                    tr.write(data)
                    out.append(f"[{lab}] {len(data)}B 전송")
            return {"summary": " / ".join(out)}
        self.start_task("명령 전송", labels, work, lambda r: self.log(r.get("summary", "")))


# ======================================================================== 프린터 패널
class PrinterPanel:
    """1. 프린터 연결 탭의 프린터 한 대 (이름 + RS232/USB/BT 연결 설정)."""

    def __init__(self, app, parent, d):
        self.app = app
        self.name_var = tk.StringVar(value=d.get("name", "프린터"))
        self.fw = tk.StringVar(value=d.get("fw", ""))
        self.connected = {}          # iface -> 연결된 채널 id
        self.frame = ttk.LabelFrame(parent, padding=6)
        self.frame.pack(fill="x", pady=4, padx=2)

        head = ttk.Frame(self.frame)
        head.grid(row=0, column=0, columnspan=12, sticky="w", pady=(0, 4))
        ttk.Label(head, text="프린터 이름").pack(side="left")
        ttk.Entry(head, textvariable=self.name_var, width=16, font=("", 10, "bold")).pack(side="left", padx=4)
        ttk.Label(head, text="FW").pack(side="left", padx=(8, 0))
        ttk.Entry(head, textvariable=self.fw, width=12).pack(side="left", padx=4)
        ttk.Button(head, text="이 프린터 연결", command=self.connect_all).pack(side="left", padx=(12, 2))
        ttk.Button(head, text="해제", command=self.disconnect_all).pack(side="left", padx=2)
        ttk.Button(head, text="▶ 빠른 점검", command=lambda: app.quick_check([self])).pack(side="left", padx=2)
        ttk.Button(head, text="삭제", command=lambda: app._remove_printer(self)).pack(side="left", padx=(12, 0))

        for j, h in enumerate(("사용", "통신", "연결 방식", "포트 / 프린터 / 파일", "속도", "형식", "흐름제어", "", "", "", "상태")):
            ttk.Label(self.frame, text=h, foreground="#606060").grid(row=1, column=j, padx=2, sticky="w")
        self.rows = {}
        saved = d.get("ifaces", {})
        for r, iface in enumerate(IFACES, 2):
            sv = saved.get(iface, {})
            dflt = IFACE_DEFAULTS[iface]
            v = {"use": tk.BooleanVar(value=sv.get("use", True)),
                 "kind": tk.StringVar(value=sv.get("kind", "COM")),
                 "target": tk.StringVar(value=sv.get("target", "")),
                 "baud": tk.StringVar(value=sv.get("baud", dflt["baud"])),
                 "fmt": tk.StringVar(value=sv.get("fmt", "8N1")),
                 "flow": tk.StringVar(value=sv.get("flow", dflt["flow"])),
                 "state": tk.StringVar(value="미연결")}
            ttk.Checkbutton(self.frame, variable=v["use"]).grid(row=r, column=0)
            ttk.Label(self.frame, text=iface, font=("", 10, "bold"), width=6).grid(row=r, column=1, sticky="w")
            ttk.Combobox(self.frame, textvariable=v["kind"], values=KINDS, width=10, state="readonly").grid(row=r, column=2)
            target_cb = ttk.Combobox(self.frame, textvariable=v["target"], width=38)
            target_cb.grid(row=r, column=3, padx=2)
            ttk.Combobox(self.frame, textvariable=v["baud"], values=BAUDS, width=7).grid(row=r, column=4)
            ttk.Combobox(self.frame, textvariable=v["fmt"], values=FORMATS, width=5).grid(row=r, column=5)
            ttk.Combobox(self.frame, textvariable=v["flow"], values=FLOWS, width=9, state="readonly").grid(row=r, column=6)
            ttk.Button(self.frame, text="연결", width=5, command=lambda i=iface: self.connect(i)).grid(row=r, column=7, padx=1)
            ttk.Button(self.frame, text="해제", width=5, command=lambda i=iface: self.disconnect(i)).grid(row=r, column=8, padx=1)
            ttk.Button(self.frame, text="확인 인쇄", width=8,
                       command=lambda i=iface: self.test_print(i)).grid(row=r, column=9, padx=1)
            ttk.Label(self.frame, textvariable=v["state"], width=14).grid(row=r, column=10, sticky="w")
            v["kind"].trace_add("write", lambda *a, i=iface: self.fill_targets(i))
            v["use"].trace_add("write", lambda *a: app._on_tab())
            self.rows[iface] = v
            self.rows[iface]["_cb"] = target_cb
        self.fill_targets()
        self.name_var.trace_add("write", lambda *a: self._on_rename())
        self._on_rename()

    @property
    def name(self):
        return self.name_var.get().strip()

    def _on_rename(self):
        self.frame.configure(text=f" {self.name or '(이름 없음)'} ")
        if hasattr(self.app, "tv"):
            self.app._refresh_targets_ui()
            self.app._ag_rebuild()

    def to_dict(self):
        keys = ("use", "kind", "target", "baud", "fmt", "flow")
        return {"name": self.name, "fw": self.fw.get(),
                "ifaces": {i: {k: r[k].get() for k in keys} for i, r in self.rows.items()}}

    def fill_targets(self, iface=None):
        for i in ([iface] if iface else IFACES):
            v = self.rows[i]
            kind = v["kind"].get()
            if kind == "COM":
                vals = [f"{p} — {d}" for p, d in list_com_ports()]
            elif kind == "WinPrinter":
                vals = list_win_printers()
            else:
                vals = [os.path.join(engine.LOG_DIR, f"dump_{self.name}_{i}.bin")]
                if not v["target"].get().endswith(".bin"):
                    v["target"].set(vals[0])
            v["_cb"]["values"] = vals

    def is_connected(self, iface):
        c = self.connected.get(iface)
        tr = self.app.session.channels.get(c) if c else None
        return bool(tr and tr.is_open)

    def _cfg(self, iface):
        v = self.rows[iface]
        tgt = v["target"].get().split(" — ")[0].strip()
        if not tgt:
            raise TransportError(f"{self.name} {iface}: 포트/프린터를 선택하세요")
        fmt = (v["fmt"].get() or "8N1").upper()
        if v["kind"].get() == "COM":
            return {"kind": "COM", "port": tgt, "baudrate": int(v["baud"].get()), "bytesize": int(fmt[0]),
                    "parity": fmt[1], "stopbits": int(fmt[2]), "flow": v["flow"].get()}
        if v["kind"].get() == "WinPrinter":
            return {"kind": "WinPrinter", "printer": tgt}
        return {"kind": "File", "path": tgt}

    def connect(self, iface, quiet=False):
        """연결하고 채널 id 반환. quiet=True 면 이미 연결돼 있을 때 그대로 사용. 실패하면 None."""
        app = self.app
        if not self.name:
            messagebox.showerror(APP_TITLE, "프린터 이름을 입력하세요.")
            return None
        if [p.name for p in app.printers].count(self.name) > 1:
            messagebox.showerror(APP_TITLE, f"프린터 이름 '{self.name}' 이 중복됩니다. 이름을 다르게 지어 주세요.")
            return None
        if not self.rows[iface]["use"].get():
            messagebox.showwarning(APP_TITLE, f"{self.name} 의 {iface} '사용'이 꺼져 있습니다.")
            return None
        want = cid(self.name, iface)
        if quiet and self.connected.get(iface) == want and self.is_connected(iface):
            return want
        prev = self.connected.get(iface)
        if (prev and app.busy.get(prev)) or app.busy.get(want):
            messagebox.showwarning(APP_TITLE, f"{want} 는 작업 중이라 다시 연결할 수 없습니다. [작업 현황]을 확인하세요.")
            return None
        try:
            cfg = self._cfg(iface)
            port = cfg.get("port")
            for p in app.printers:    # 다른 줄이 같은 포트를 쓰고 있으면 막는다
                for c in p.connected.values():
                    tr = app.session.channels.get(c)
                    if port and c not in (want, prev) and tr is not None and tr.is_open and \
                            getattr(tr, "port", None) == port:
                        raise TransportError(f"{port} 는 이미 '{c}' 에서 사용 중입니다")
            for c in {prev, want} - {None}:   # Windows COM 포트는 동시에 두 번 열 수 없으므로 기존 연결을 먼저 닫는다
                old = app.session.channels.pop(c, None)
                if old:
                    old.close()
            tr = make_transport(want, cfg)
            tr.open()
        except (TransportError, ValueError, IndexError) as e:
            self.connected.pop(iface, None)
            self.rows[iface]["state"].set("연결 실패")
            messagebox.showerror(APP_TITLE, str(e))
            app._refresh_targets_ui()
            return None
        app.session.add(tr)
        self.connected[iface] = want
        self.rows[iface]["state"].set("● 연결됨")
        app.log(f"[{want}] 연결: {tr.describe()}")
        app._refresh_targets_ui()
        app._save_settings()
        return want

    def disconnect(self, iface):
        app = self.app
        c = self.connected.get(iface)
        if c and app.busy.get(c):
            messagebox.showwarning(APP_TITLE, f"{c} 는 [{app.busy[c].name}] 작업 중입니다. 먼저 [작업 현황]에서 중지하세요.")
            return
        tr = app.session.channels.pop(c, None) if c else None
        if tr:
            tr.close()
            app.log(f"[{c}] 연결 해제")
        self.connected.pop(iface, None)
        self.rows[iface]["state"].set("미연결")
        app._refresh_targets_ui()

    def connect_all(self):
        for i in IFACES:
            if self.rows[i]["use"].get() and self.rows[i]["target"].get():
                self.connect(i, quiet=True)

    def disconnect_all(self):
        for i in IFACES:
            self.disconnect(i)

    def test_print(self, iface):
        lab = self.connect(iface, quiet=True)
        if lab is None:
            return
        self.app.start_task("확인 인쇄", [lab], lambda task: engine.act_print(self.app.session, lab, "연결 확인", task),
                            lambda r: self.app.log(f"[{lab}] {r.get('summary', '')}"))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
