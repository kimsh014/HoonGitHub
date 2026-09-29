"""가짜 프린터(pty)로 엔진을 검증한다. Linux/macOS 전용.

실행: python -m unittest discover -s tests -v   (printer_test_tool 폴더에서)
"""
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import engine  # noqa: E402
import patterns  # noqa: E402
from escpos import parse_status  # noqa: E402
from fakeprinter import Fake  # noqa: E402
from transports import make_transport  # noqa: E402

engine.LOG_DIR = tempfile.mkdtemp()


def connect(session, label, fake, **kw):
    tr = make_transport(label, {"kind": "COM", "port": fake.path, **kw})
    tr.open()
    session.add(tr)
    return tr


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.s = engine.Session(log=self.logs.append)
        self.cancel = threading.Event()

    def tearDown(self):
        self.s.close_all()

    def settle(self):
        time.sleep(0.5)

    def test_all_patterns_are_valid_escpos(self):
        f = Fake()
        connect(self.s, "RS232", f)
        for name in patterns.PATTERNS:
            engine.act_print(self.s, "RS232", name, self.cancel)
        self.settle()
        self.assertEqual(f.stats["errors"], [])
        self.assertEqual(f.stats["cuts"], len(patterns.PATTERNS))
        self.assertGreaterEqual(f.stats["qr_print"], 3)

    def test_patterns_fit_receipt_length(self):
        """모든 패턴(속도 시험 제외)은 기본 영수증 길이(120mm) 안에 들어가야 한다."""
        orig, heights = patterns._finish, {}

        def spy(r, o, fixed_length=True):
            heights[name] = r.height_mm()
            return orig(r, o, fixed_length)
        patterns._finish = spy
        try:
            for name, fn in patterns.PATTERNS.items():
                fn({"length_mm": 0}, "프린터1/RS232")
        finally:
            patterns._finish = orig
        too_long = {k: round(v) for k, v in heights.items() if v > 120}
        self.assertEqual(too_long, {})

    def test_status_parse(self):
        self.assertEqual(parse_status(1, 0x16)["text"], "드로어 핀 High")
        self.assertTrue(parse_status(4, 0x72)["error"])
        self.assertTrue(parse_status(2, 0x16)["error"])        # 커버 열림
        self.assertFalse(parse_status(1, 0x01)["valid"])       # 고정 비트 위반

    def test_status_query(self):
        f = Fake()
        connect(self.s, "RS232", f)
        self.assertEqual(engine.act_status(self.s, "RS232")["suggest"], "PASS")

    def test_aging_alternate_and_concurrent(self):
        a, b = Fake(), Fake()
        connect(self.s, "USB", a)
        connect(self.s, "BT", b)
        r = engine.AgingRunner(self.s, ["USB", "BT"], "교대", "영수증", count=6, interval=0)
        r.run()
        self.assertEqual((r.stats["USB"]["ok"], r.stats["BT"]["ok"]), (3, 3))
        r = engine.AgingRunner(self.s, ["USB", "BT"], "동시", "채널 표시", count=6, interval=0)
        r.run()
        self.settle()
        self.assertEqual(r.total, 6)
        self.assertFalse([l for l in b.stats["text"] if "[USB]" in l])  # 섞임 없음

    def test_aging_pauses_on_paper_out(self):
        f = Fake(paper_out_after=1)
        connect(self.s, "RS232", f)
        r = engine.AgingRunner(self.s, ["RS232"], "기본", "영수증", count=3, interval=0)
        th = threading.Thread(target=r.run)
        th.start()
        time.sleep(3)
        self.assertEqual(r.stats["RS232"]["pause"], 1)
        f.paper_out_after = None           # 용지 보충
        th.join(15)
        self.assertEqual(r.total, 3)
        self.assertEqual(r.stats["RS232"]["fail"], 0)

    def test_reconnect_monitor(self):
        f = Fake()
        connect(self.s, "USB", f)
        present = {"on": True}
        orig = engine.list_com_ports
        engine.list_com_ports = lambda: [(f.path, "fake")] if present["on"] else []

        def toggle():
            for _ in range(2):
                time.sleep(1.0)
                present["on"] = False
                time.sleep(1.0)
                present["on"] = True
        threading.Thread(target=toggle, daemon=True).start()
        try:
            r = engine.act_reconnect(self.s, "USB", 2, self.cancel, timeout_s=15)
        finally:
            engine.list_com_ports = orig
        self.assertEqual(r["suggest"], "PASS")

    def test_csv_log_survives_locked_file(self):
        log = engine.CsvLog("locktest")
        real = log.path
        log.path = engine.LOG_DIR            # 디렉터리 → 열기 실패(엑셀이 잠근 상황 흉내)
        log.row("t", "c", 1, "OK")           # 예외 없이 보관만 해야 함
        self.assertEqual(len(log.pending), 1)
        log.path = real
        log.row("t", "c", 2, "OK")           # 잠금 해제 후 밀린 줄까지 기록
        with open(real, encoding="utf-8-sig") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 3)   # 헤더 + 2줄

    def test_urgent_status_query(self):
        f = Fake()
        tr = connect(self.s, "RS232", f, flow="RTS/CTS")
        st = engine.read_status(tr, urgent=True)
        self.assertEqual(len(st), 4)
        self.assertTrue(tr.ser.rtscts)       # 흐름제어 설정 복원

    def test_pause_recovers_after_handle_dies(self):
        f = Fake(paper_out_after=1)
        tr = connect(self.s, "RS232", f)
        r = engine.AgingRunner(self.s, ["RS232"], "기본", "영수증", count=2, interval=0)
        th = threading.Thread(target=r.run)
        th.start()
        time.sleep(2.5)
        self.assertEqual(r.stats["RS232"]["pause"], 1)
        tr.ser.close()                       # 일시정지 중 핸들이 죽음(프린터 재부팅 등)
        f.paper_out_after = None
        th.join(20)
        self.assertFalse(th.is_alive())
        self.assertEqual(r.total, 2)
        self.assertIsNotNone(r.ended)
        e1 = r.elapsed()
        time.sleep(0.3)
        self.assertEqual(r.elapsed(), e1)    # 종료 후 경과 시간 고정


class DiagnoseTest(unittest.TestCase):
    def test_diagnose_finds_settings(self):
        f = Fake()
        r = engine.act_diagnose(f.path, log=lambda m: None)
        self.assertEqual(r["found"], {"baud": 9600, "flow": "없음"})

    def test_diagnose_one_way_prints_each_baud(self):
        f = Fake(status_reply=False)
        r = engine.act_diagnose(f.path, log=lambda m: None)
        time.sleep(0.5)
        self.assertIsNone(r["found"])
        printed = [t for t in f.stats["text"] if t.startswith("==== BAUD")]
        self.assertEqual(len(printed), len(engine.DIAG_BAUDS))


class ManualTest(unittest.TestCase):
    def test_manual_is_up_to_date(self):
        """manual.html 은 make_manual.py 로 만든 최신본이어야 한다 (테스트 케이스 표 자동 생성)."""
        import make_manual
        path = make_manual.OUT
        with open(path, encoding="utf-8") as f:
            before = f.read()
        make_manual.main()
        with open(path, encoding="utf-8") as f:
            self.assertEqual(before, f.read(), "manual.html 이 최신이 아닙니다: python make_manual.py 실행 후 커밋")


if __name__ == "__main__":
    unittest.main()
