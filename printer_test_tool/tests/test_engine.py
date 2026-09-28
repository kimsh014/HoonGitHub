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
        self.assertGreaterEqual(f.stats["qr_print"], 5)

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
        r = engine.AgingRunner(self.s, ["USB", "BT"], "동시", "채널 표시(짧게)", count=6, interval=0)
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


if __name__ == "__main__":
    unittest.main()
