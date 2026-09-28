"""명령줄 버전 (GUI 없이 에이징/인쇄/상태 조회).

예)
  python cli.py ports
  python cli.py status  --ch RS232=COM3:115200:RTS/CTS
  python cli.py print   --ch USB=COM7 --pattern 한글
  python cli.py aging   --ch RS232=COM3:115200:RTS/CTS --hours 12
  python cli.py aging   --ch USB=COM7 --ch BT=COM9 --mode 교대 --hours 12 --pattern 영수증+이미지

--ch 형식:  이름=COM포트[:속도[:흐름제어[:형식]]]   (흐름제어: 없음/RTS/CTS/DTR/DSR/XON/XOFF, 형식: 8N1 등)
           이름=printer:Windows프린터이름          이름=file:경로
"""
import argparse
import signal
import sys

import engine
import patterns
from transports import list_com_ports, list_win_printers, make_transport


def parse_ch(spec):
    label, _, rest = spec.partition("=")
    if rest.startswith("printer:"):
        return label, {"kind": "WinPrinter", "printer": rest[8:]}
    if rest.startswith("file:"):
        return label, {"kind": "File", "path": rest[5:]}
    # COM3:115200:RTS/CTS:8N1  (흐름제어에 '/' 가 있어 ':' 로만 나눈다)
    parts = rest.split(":")
    cfg = {"kind": "COM", "port": parts[0]}
    if len(parts) > 1 and parts[1]:
        cfg["baudrate"] = int(parts[1])
    cfg["flow"] = parts[2] if len(parts) > 2 and parts[2] else "없음"
    if len(parts) > 3 and parts[3]:
        f = parts[3].upper()
        cfg.update(bytesize=int(f[0]), parity=f[1], stopbits=int(f[2]))
    return label, cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="열전사 프린터 검증 도구 (CLI)")
    ap.add_argument("cmd", choices=["ports", "status", "print", "aging", "concurrent"])
    ap.add_argument("--ch", action="append", default=[], help="채널 (여러 번 지정 가능)")
    ap.add_argument("--pattern", default="영수증")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--mode", default="기본", choices=["기본", "교대", "동시"])
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--interval", type=float, default=2)
    ap.add_argument("--no-status", action="store_true", help="매 장 상태 조회 끄기")
    ap.add_argument("--dots", type=int, default=576)
    ap.add_argument("--encoding", default="cp949")
    a = ap.parse_args(argv)

    if a.cmd == "ports":
        for p, d in list_com_ports():
            print(f"{p}\t{d}")
        for p in list_win_printers():
            print(f"[printer] {p}")
        return 0

    s = engine.Session(log=lambda m: print(m, flush=True))
    s.opts.update(dots=a.dots, encoding=a.encoding)
    if not a.ch:
        ap.error("--ch 를 지정하세요")
    for spec in a.ch:
        label, cfg = parse_ch(spec)
        tr = make_transport(label, cfg)
        tr.open()
        s.add(tr)
        print(f"연결: {tr.describe()}")
    labels = list(s.channels)

    try:
        if a.cmd == "status":
            for l in labels:
                print(engine.act_status(s, l)["summary"])
        elif a.cmd == "print":
            names = list(patterns.PATTERNS) if a.pattern == "all" else [a.pattern]
            for l in labels:
                for _ in range(a.repeat):
                    for n in names:
                        print(engine.act_print(s, l, n)["summary"])
        elif a.cmd == "concurrent":
            print(engine.act_concurrent(s)["summary"])
        elif a.cmd == "aging":
            r = engine.AgingRunner(s, labels, a.mode, a.pattern, a.count, a.hours, a.interval,
                                   check_status=not a.no_status)
            signal.signal(signal.SIGINT, lambda *x: r.cancel.set())
            r.run()
            return 1 if any(st["fail"] for st in r.stats.values()) else 0
    finally:
        s.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
