"""시험 실행 엔진 — GUI/CLI 공용.

모든 동작은 작업 스레드에서 실행되며, cancel(threading.Event)로 중지하고
log(msg) 콜백으로 진행 상황을 알린다.
"""
import csv
import datetime
import os
import sys
import threading
import time

import patterns
from escpos import Receipt, dle_eot, parse_status
from transports import SerialTransport, TransportError, list_com_ports

# exe(PyInstaller)로 실행하면 exe 가 있는 폴더에 logs/results/settings 를 만든다
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CsvLog:
    """시험 이벤트를 CSV 로 남긴다(엑셀로 바로 열림, UTF-8 BOM)."""
    FIELDS = ["시각", "시험", "채널", "순번", "결과", "바이트", "전송(s)", "상태1", "상태2", "상태3", "상태4", "메시지"]

    def __init__(self, name):
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in name)  # 파일명에 못 쓰는 문자
        self.path = os.path.join(LOG_DIR, f"{stamp}_{name}.csv")
        self.lock = threading.Lock()
        self.pending = []
        with open(self.path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(self.FIELDS)

    def row(self, test, channel, seq, result, nbytes="", secs="", status=None, msg=""):
        """한 줄 기록. 파일이 잠겨 있으면(엑셀로 열어 둔 경우 등) 메모리에 보관했다가 다음 기록 때 함께 쓴다.
        로그 기록 실패로 시험이 멈추는 일은 없어야 한다."""
        st = ["", "", "", ""]
        if status:
            for s in status:
                st[s["n"] - 1] = f'{s["hex"]} {s["text"]}'
        line = [now_str(), test, channel, seq, result, nbytes,
                f"{secs:.3f}" if isinstance(secs, float) else secs, *st, msg]
        with self.lock:
            self.pending.append(line)
            try:
                with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerows(self.pending)
                self.pending = []
            except OSError:
                self.pending = self.pending[-100000:]   # 메모리 보호


# ---------------- 상태 ----------------

def read_status(tr, timeout=1.0, urgent=False):
    """DLE EOT 1~4 조회. 지원 안 하면 None, 응답 없으면 [] 반환.
    urgent=True: 흐름제어로 송신이 막힌 상태에서 조회 (SerialTransport.urgent_query)."""
    if not tr.supports_status:
        return None
    q = tr.urgent_query if urgent and hasattr(tr, "urgent_query") else tr.query
    out = []
    for n in (1, 2, 3, 4):
        resp = q(dle_eot(n), 1, timeout)
        if not resp:
            return []
        out.append(parse_status(n, resp[0]))
    return out


OPERATOR_FLAGS = {"용지 없음", "용지 없음으로 정지", "커버 열림", "오프라인", "에러 발생", "용지 잔량 부족", "FEED 버튼 누름",
                  "드로어 핀 High"}


def is_operator_event(st):
    """용지 없음/커버 열림처럼 작업자가 해소하는 상태인지 (커터·헤드 등 기기 에러가 섞이면 False)."""
    if not st:
        return False
    flags = {f for s in st for f in s["flags"]}
    return bool(flags & {"용지 없음", "용지 없음으로 정지", "커버 열림"}) and flags <= OPERATOR_FLAGS


def status_summary(st):
    if st is None:
        return "상태조회 미지원", "NA"
    if not st:
        return "상태 응답 없음", "NORESP"
    if any(not s["valid"] for s in st):
        return "상태 응답 형식 오류: " + " ".join(s["hex"] for s in st), "INVALID"
    errs = [f for s in st if s["error"] for f in s["flags"]]
    warns = [f for s in st if s["warn"] for f in s["flags"]]
    if errs:
        return "에러: " + ", ".join(dict.fromkeys(errs)), "ERROR"
    if warns:
        return "경고: " + ", ".join(dict.fromkeys(warns)), "WARN"
    return "정상", "OK"


# ---------------- 세션 ----------------

class Session:
    """연결된 채널(RS232/USB/BT)과 공통 인쇄 옵션."""

    def __init__(self, log=print):
        self.channels = {}          # label -> Transport
        self.opts = dict(patterns.DEFAULT_OPTS)
        self.log = log
        self.pattern_extra = {}

    def add(self, tr):
        old = self.channels.get(tr.label)
        if old:
            old.close()
        self.channels[tr.label] = tr

    def get(self, label):
        tr = self.channels.get(label)
        if tr is None:
            raise TransportError(f"채널 '{label}' 이 설정되어 있지 않습니다")
        if not tr.is_open:
            tr.open()
        return tr

    def open_channels(self):
        return [t for t in self.channels.values() if t.is_open]

    def close_all(self):
        for t in self.channels.values():
            t.close()


# ---------------- 개별 동작 ----------------

def send(session, label, data, what="", csvlog=None, seq="", check_status=False, cancel=None):
    """전송 + (선택) 상태 확인. 결과 dict."""
    tr = session.get(label)
    secs = tr.write(data, cancel)
    rate = len(data) / secs if secs > 0 else 0
    st = None
    if check_status and tr.supports_status:
        time.sleep(0.2)
        st = read_status(tr)
    text, code = status_summary(st) if check_status else ("", "OK")
    session.log(f"[{label}] {what} {len(data):,}B 전송 {secs:.2f}s ({rate / 1024:.1f}KB/s) {text}")
    if csvlog:
        csvlog.row(what, label, seq, "FAIL" if code == "ERROR" else "OK", len(data), secs, st, text)
    return {"secs": secs, "bytes": len(data), "status": st, "code": code, "text": text}


def act_print(session, label, pattern_name, cancel=None, **kw):
    fn = patterns.PATTERNS[pattern_name]
    data = fn(session.opts, channel=label, **kw)
    r = send(session, label, data, pattern_name, check_status=True, cancel=cancel)
    return {"suggest": "FAIL" if r["code"] == "ERROR" else None,
            "summary": f"{pattern_name} 인쇄 완료 — 출력물을 확인하세요. {r['text']}"}


def act_burst(session, label, pattern_name, count, cancel, tag=""):
    """같은 패턴을 순번을 붙여 연속 인쇄 (대용량/거리/누락 시험)."""
    csvlog = CsvLog(f"burst_{label}")
    fn = patterns.AGING_PATTERNS[pattern_name]
    ch = f"{label}{tag}"
    ok = fail = 0
    total_b = total_s = 0.0
    for i in range(1, count + 1):
        if cancel.is_set():
            break
        try:
            r = send(session, label, fn(session.opts, ch, i), pattern_name, csvlog, i, check_status=(i == count), cancel=cancel)
            total_b += r["bytes"]
            total_s += r["secs"]
            ok += r["code"] != "ERROR"
            fail += r["code"] == "ERROR"
        except TransportError as e:
            fail += 1
            session.log(f"[{label}] #{i} 실패: {e}")
            csvlog.row(pattern_name, label, i, "FAIL", msg=str(e))
    rate = total_b / total_s / 1024 if total_s else 0
    s = f"{count}장 중 전송 성공 {ok}, 실패 {fail}, 평균 {rate:.1f}KB/s. 순번 1~{count} 누락 여부를 출력물로 확인. 로그: {csvlog.path}"
    return {"suggest": "FAIL" if fail else None, "summary": s}


def act_cut(session, label, count, cancel):
    for partial in (True, False):
        for i in range(1, count + 1):
            if cancel.is_set():
                return {"suggest": None, "summary": "중지됨"}
            session.get(label).write(patterns.pattern_cut(session.opts, label, i, partial))
            time.sleep(0.3)
    st = read_status(session.get(label))
    text, code = status_summary(st)
    return {"suggest": "FAIL" if code == "ERROR" else None,
            "summary": f"Partial {count}회 + Full {count}회 컷 완료. 상태: {text}. 절단면·걸림 확인"}


def act_drawer(session, label, cancel=None):
    data = Receipt().init().drawer(0).drawer(1).bytes()
    session.get(label).write(data)
    return {"suggest": None, "summary": "드로어 킥(핀2, 핀5) 전송. 드로어 열림 확인"}


def act_status(session, label, cancel=None):
    tr = session.get(label)
    st = read_status(tr)
    text, code = status_summary(st)
    if st:
        for s in st:
            session.log(f"[{label}] DLE EOT {s['n']} ({s['name']}): {s['hex']} {'형식OK' if s['valid'] else '형식오류'} — {s['text']}")
    session.log(f"[{label}] 상태 요약: {text}")
    suggest = {"OK": "PASS", "WARN": "PASS", "ERROR": None, "NORESP": "FAIL", "INVALID": "FAIL", "NA": "N/A"}[code]
    return {"suggest": suggest, "summary": f"상태 조회: {text}"}


def act_status_monitor(session, label, seconds, cancel, long_print=False):
    """상태를 0.5초마다 조회하며 변화만 기록 (용지/커버/잔량 센서 시험)."""
    tr = session.get(label)
    if not tr.supports_status:
        return {"suggest": "N/A", "summary": "이 연결은 상태 조회를 지원하지 않습니다"}
    if long_print:
        threading.Thread(target=lambda: _safe_write(session, label, patterns.pattern_speed(session.opts, label, 500)),
                         daemon=True).start()
        session.log(f"[{label}] 500mm 인쇄 전송 — 인쇄 중에 커버를 열어 보세요")
    last = None
    changes = []
    t_end = time.time() + seconds
    session.log(f"[{label}] 상태 감시 {seconds}초 시작 (센서를 조작하세요)")
    while time.time() < t_end and not cancel.is_set():
        try:
            text = status_summary(read_status(tr, 0.5))[0]
        except TransportError as e:
            text = str(e)
        if text != last:
            session.log(f"[{label}] {now_str()} 상태 변화 → {text}")
            changes.append(text)
            last = text
        time.sleep(0.5)
    return {"suggest": None, "summary": "상태 변화: " + " → ".join(changes)}


def _safe_write(session, label, data):
    try:
        session.get(label).write(data)
    except TransportError as e:
        session.log(f"[{label}] 전송 중단: {e}")


def probe(tr):
    """연결 살아있는지 확인. 상태 조회가 되면 그것으로, 아니면 포트 존재로 판단."""
    try:
        if isinstance(tr, SerialTransport):
            if tr.port not in [p for p, _ in list_com_ports()]:
                tr.close()
                return False
            if not tr.is_open:
                tr.open()
            resp = tr.query(dle_eot(1), 1, 0.8)
            return resp is not None
        if not tr.is_open:
            tr.open()
        return True
    except TransportError:
        tr.close()
        return False


def act_reconnect(session, label, cycles, cancel, long_print_first=False, timeout_s=3600):
    """분리→재연결(또는 전원 OFF→ON)을 감지해 매 재연결마다 인쇄로 확인.

    핫플러그(U05), 케이블 분리 복구(R06), BT 재연결(T04/T05), 전원 반복(B01)에 사용.
    """
    tr = session.channels[label]
    if not isinstance(tr, SerialTransport):
        return {"suggest": None, "summary": "COM 연결에서만 자동 감지됩니다. Windows 프린터 연결은 분리/재연결 후 [패턴 인쇄]로 확인하세요"}
    csvlog = CsvLog(f"reconnect_{label}")
    if long_print_first:
        threading.Thread(target=lambda: _safe_write(session, label, patterns.pattern_speed(session.opts, label, 500)),
                         daemon=True).start()
        session.log(f"[{label}] 긴 인쇄 전송 중 — 인쇄 도중에 분리/끊기 하세요")
        time.sleep(1.5)
    done = fail = 0
    was_up = probe(tr)
    session.log(f"[{label}] 재연결 감시 시작 (목표 {cycles}회). 현재 {'연결됨' if was_up else '끊김'} — 분리 후 다시 연결하세요")
    t_end = time.time() + timeout_s
    while done < cycles and time.time() < t_end and not cancel.is_set():
        up = probe(tr)
        if was_up and not up:
            session.log(f"[{label}] {now_str()} 끊김 감지")
            csvlog.row("재연결", label, done + 1, "DOWN")
        elif not was_up and up:
            done += 1
            time.sleep(1.0)
            try:
                r = send(session, label, patterns.pattern_info(session.opts, label, f"재연결 {done}/{cycles}회"),
                         "재연결 확인", csvlog, done, check_status=True)
                if r["code"] == "ERROR":
                    fail += 1
            except TransportError as e:
                fail += 1
                session.log(f"[{label}] 재연결 후 인쇄 실패: {e}")
                csvlog.row("재연결", label, done, "FAIL", msg=str(e))
            session.log(f"[{label}] 재연결 {done}/{cycles}")
        was_up = up
        time.sleep(0.5)
    s = f"재연결 {done}/{cycles}회, 재연결 후 인쇄 실패 {fail}회. 로그: {csvlog.path}"
    return {"suggest": "PASS" if done >= cycles and not fail else ("FAIL" if fail else None), "summary": s}


def act_comm_configs(session, label, configs, confirm, cancel):
    """R01/R02 — 통신 설정을 바꿔 가며 인쇄. confirm(msg)->bool 로 작업자에게 프린터 설정 변경을 요청."""
    tr = session.channels[label]
    if not isinstance(tr, SerialTransport):
        return {"suggest": "N/A", "summary": "COM 연결에서만 가능합니다"}
    orig = (tr.baudrate, tr.bytesize, tr.parity, tr.stopbits)
    results = []
    try:
        for baud, fmt in configs:
            if cancel.is_set():
                break
            if not confirm(f"프린터 통신 설정을 {baud} bps, {fmt} 로 바꾼 뒤 [확인]을 누르세요.\n(건너뛰려면 [취소])"):
                results.append(f"{baud}/{fmt}:건너뜀")
                continue
            tr.close()
            tr.baudrate, tr.bytesize, tr.parity, tr.stopbits = baud, int(fmt[0]), fmt[1], float(fmt[2])
            try:
                tr.open()
                send(session, label, patterns.pattern_baud(session.opts, label, f"{baud} {fmt}"), f"BAUD {baud} {fmt}")
                text, code = status_summary(read_status(tr))
            except TransportError as e:
                text, code = str(e), "FAIL"
            results.append(f"{baud}/{fmt}:{code}")
            session.log(f"[{label}] {baud} {fmt} → 상태 {text}")
    finally:
        tr.close()
        tr.baudrate, tr.bytesize, tr.parity, tr.stopbits = orig
    bad = [r for r in results if not r.endswith(":OK") and not r.endswith("건너뜀")]
    return {"suggest": "FAIL" if bad else None,
            "summary": "결과: " + ", ".join(results) + " — 출력물 깨짐 여부 확인. 시험 후 프린터와 프로그램 설정을 원래대로 맞추세요"}


def act_mismatch(session, label, wrong_baud, cancel=None):
    """R07 — 틀린 Baud 로 보낸 뒤 정상 Baud 로 인쇄가 되는지."""
    tr = session.channels[label]
    if not isinstance(tr, SerialTransport):
        return {"suggest": "N/A", "summary": "COM 연결에서만 가능합니다"}
    right = tr.baudrate
    tr.close()
    tr.baudrate = wrong_baud
    try:
        tr.open()
        tr.write(("MISMATCH TEST 잘못된 속도 " * 20).encode("cp949"))
        time.sleep(2)
    finally:
        tr.close()
        tr.baudrate = right
    tr.open()
    tr.write(b"\x1b@")
    r = send(session, label, patterns.pattern_info(session.opts, label, "설정 불일치 후 정상 복귀"), "불일치 복귀",
             check_status=True)
    ok = r["code"] in ("OK", "WARN", "NA")
    return {"suggest": "PASS" if ok and r["code"] != "NA" else None,
            "summary": f"{wrong_baud}bps 로 쓰레기 데이터 전송 후 {right}bps 복귀 인쇄. 상태: {r['text']}"}


def act_all_channels(session, cancel=None):
    """X01 — 연결된 모든 채널로 차례로 인쇄."""
    res = []
    for tr in session.open_channels():
        r = send(session, tr.label, patterns.pattern_info(session.opts, tr.label, "3포트 순차 인쇄"), "순차 인쇄",
                 check_status=True)
        res.append(f"{tr.label}:{r['code']}")
    return {"suggest": None, "summary": "채널별: " + ", ".join(res) + " — 각 채널 출력 확인"}


def act_concurrent(session, cancel=None, lines=30):
    """X02 — 모든 채널에 동시에 전송. 줄마다 채널 이름이 있어 섞이면 바로 보인다."""
    chans = session.open_channels()
    if len(chans) < 2:
        return {"suggest": None, "summary": "2개 이상 채널을 연결해야 합니다"}
    barrier = threading.Barrier(len(chans))
    errs = []

    def worker(tr):
        data = patterns.pattern_channel_mark(session.opts, tr.label, 1, lines)
        barrier.wait()
        try:
            tr.write(data)
        except TransportError as e:
            errs.append(str(e))

    ths = [threading.Thread(target=worker, args=(t,)) for t in chans]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    names = ", ".join(t.label for t in chans)
    return {"suggest": "FAIL" if errs else None,
            "summary": f"{names} 동시 전송 완료{' (오류: ' + '; '.join(errs) + ')' if errs else ''}. "
                       "각 영수증 안에 다른 채널 줄이 섞였는지 확인"}


def act_interleave(session, main_label, other_label, cancel=None):
    """X03 — main 채널로 긴 인쇄 중 other 채널로 전송."""
    t = threading.Thread(target=lambda: _safe_write(session, main_label,
                                                    patterns.pattern_channel_mark(session.opts, main_label, 1, 120)))
    t.start()
    time.sleep(1.0)
    _safe_write(session, other_label, patterns.pattern_channel_mark(session.opts, other_label, 2, 10))
    t.join()
    return {"suggest": None,
            "summary": f"{main_label} 긴 인쇄(120줄) 중 {other_label} 10줄 전송. 섞임 없이 순서대로 나왔는지(또는 사양대로) 확인"}


# ---------------- 에이징 ----------------

class AgingRunner:
    """에이징 시험.

    mode:
      "기본"  : 선택한 채널 1개로 연속 인쇄
      "교대"  : 선택한 채널들을 번갈아 가며 인쇄 (예: USB+BT)
      "동시"  : 선택한 채널마다 별도 스레드로 동시에 인쇄
    """

    def __init__(self, session, labels, mode="기본", pattern="영수증", count=0, hours=0.0, interval=2.0,
                 check_status=True, pause_on_error=True, reconnect=True, stop_on_fail=False, log=None):
        self.s = session
        self.labels = list(labels)
        self.mode = mode
        self.pattern = patterns.AGING_PATTERNS[pattern]
        self.pattern_name = pattern
        self.count = int(count)
        self.hours = float(hours)
        self.interval = float(interval)
        self.check_status = check_status
        self.pause_on_error = pause_on_error
        self.reconnect = reconnect
        self.stop_on_fail = stop_on_fail
        self.log = log or session.log
        self.cancel = threading.Event()
        self.stats = {l: {"sent": 0, "ok": 0, "fail": 0, "pause": 0, "reconn": 0, "bytes": 0, "secs": 0.0,
                          "last": ""} for l in self.labels}
        self.total = 0
        self.lock = threading.Lock()
        self.started = None
        self.csv = None
        self.running = False
        self.ended = None

    def elapsed(self):
        if not self.started:
            return 0
        return (self.ended or time.time()) - self.started

    def _time_up(self):
        if self.hours > 0 and self.elapsed() >= self.hours * 3600:
            return True
        if self.count > 0 and self.total >= self.count:
            return True
        return False

    def _next_seq(self):
        with self.lock:
            if self.count > 0 and self.total >= self.count:
                return None
            self.total += 1
            return self.total

    def _wait_recover(self, label, tr):
        st = self.stats[label]
        st["pause"] += 1
        self.log(f"[에이징][{label}] 에러로 일시정지 — 원인 해소(용지 보충, 커버 닫기 등) 시 자동 재개")
        while not self.cancel.is_set():
            time.sleep(2)
            try:
                if not tr.is_open:
                    tr.open()
                text, code = status_summary(read_status(tr))
            except TransportError:
                # 일시정지 중 프린터 재부팅 등으로 핸들이 죽은 경우: 닫고 다음 회차에 다시 연다
                tr.close()
                continue
            if code in ("OK", "WARN"):
                self.log(f"[에이징][{label}] 복구됨, 재개")
                self.csv.row("에이징", label, "", "RESUME", msg=text)
                return

    def _reconnect(self, label):
        tr = self.s.channels[label]
        self.stats[label]["reconn"] += 1
        for attempt in range(1, 31):
            if self.cancel.is_set():
                return False
            tr.close()
            time.sleep(min(2 * attempt, 10))
            try:
                tr.open()
                self.log(f"[에이징][{label}] 재연결 성공 ({attempt}회차)")
                self.csv.row("에이징", label, "", "RECONNECT", msg=f"{attempt}회차")
                return True
            except TransportError as e:
                self.log(f"[에이징][{label}] 재연결 시도 {attempt} 실패: {e}")
        return False

    def _job(self, label, seq):
        st = self.stats[label]
        data = self.pattern(self.s.opts, label, seq)
        try:
            tr = self.s.get(label)
            secs = tr.write(data, self.cancel)
        except TransportError as e:
            # 흐름제어 BUSY(용지 없음 등)로 전송이 막힌 경우: 작업자 조치 대상이면 일시정지로 처리
            tr0 = self.s.channels.get(label)
            if self.pause_on_error and tr0 is not None and tr0.is_open and tr0.supports_status:
                try:
                    status = read_status(tr0, urgent=True)
                except TransportError:
                    status = None
                if is_operator_event(status):
                    text = status_summary(status)[0]
                    st["last"] = f"#{seq} {text}"
                    self.log(f"[에이징][{label}] #{seq} 전송 중단 — {text}")
                    self.csv.row("에이징", label, seq, "ERROR", len(data), status=status, msg=f"{text} / {e}")
                    self._wait_recover(label, tr0)
                    return
            st["fail"] += 1
            st["last"] = f"#{seq} 전송 실패"
            self.log(f"[에이징][{label}] #{seq} 전송 실패: {e}")
            self.csv.row("에이징", label, seq, "FAIL", len(data), msg=str(e))
            if self.stop_on_fail:
                self.cancel.set()
            elif self.reconnect and not self.cancel.is_set():
                self._reconnect(label)
            return
        st["sent"] += 1
        st["bytes"] += len(data)
        st["secs"] += secs
        status = None
        text, code = "", "OK"
        if self.check_status and tr.supports_status:
            time.sleep(0.2)
            try:
                status = read_status(tr)
            except TransportError:
                status = []
            text, code = status_summary(status)
        if code == "ERROR":
            # 용지 없음/커버 열림은 작업자 조치 대상 → 일시정지로만 집계(실패 아님)
            if not (self.pause_on_error and is_operator_event(status)):
                st["fail"] += 1
            st["last"] = f"#{seq} {text}"
            self.csv.row("에이징", label, seq, "ERROR", len(data), secs, status, text)
            self.log(f"[에이징][{label}] #{seq} {text}")
            if self.stop_on_fail:
                self.cancel.set()
            elif self.pause_on_error:
                self._wait_recover(label, tr)
        elif code in ("NORESP", "INVALID"):
            st["fail"] += 1
            st["last"] = f"#{seq} {text}"
            self.csv.row("에이징", label, seq, code, len(data), secs, status, text)
            self.log(f"[에이징][{label}] #{seq} {text}")
            if self.stop_on_fail:
                self.cancel.set()
        else:
            st["ok"] += 1
            st["last"] = f"#{seq} OK {text}"
            self.csv.row("에이징", label, seq, "OK", len(data), secs, status, text)

    def _sleep(self):
        end = time.time() + self.interval
        while time.time() < end and not self.cancel.is_set():
            time.sleep(0.1)

    def _loop(self, labels):
        i = 0
        while not self.cancel.is_set() and not self._time_up():
            label = labels[i % len(labels)]
            seq = self._next_seq()
            if seq is None:
                break
            self._job(label, seq)
            i += 1
            self._sleep()

    def run(self):
        self.running = True
        self.started = time.time()
        self.csv = CsvLog(f"aging_{self.mode}_{'+'.join(self.labels)}")
        cond = []
        if self.count:
            cond.append(f"{self.count}장")
        if self.hours:
            cond.append(f"{self.hours:g}시간")
        self.log(f"[에이징] 시작 — 모드 {self.mode}, 채널 {'+'.join(self.labels)}, 패턴 {self.pattern_name}, "
                 f"종료조건 {' 또는 '.join(cond) or '수동 중지'}, 로그 {self.csv.path}")
        try:
            if self.mode == "동시":
                ths = [threading.Thread(target=self._loop, args=([l],), daemon=True) for l in self.labels]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join()
            else:
                self._loop(self.labels if self.mode == "교대" else self.labels[:1])
        finally:
            self.ended = time.time()
            self.running = False
            self.log("[에이징] 종료 — " + self.summary())
        return self.summary()

    def summary(self):
        h = self.elapsed() / 3600
        parts = []
        for l, st in self.stats.items():
            rate = st["bytes"] / st["secs"] / 1024 if st["secs"] else 0
            parts.append(f"{l}: 전송 {st['sent']} / 정상 {st['ok']} / 실패 {st['fail']} / 일시정지 {st['pause']} / "
                         f"재연결 {st['reconn']} / {rate:.1f}KB/s")
        return f"경과 {h:.2f}h, 총 {self.total}장 — " + " | ".join(parts)
