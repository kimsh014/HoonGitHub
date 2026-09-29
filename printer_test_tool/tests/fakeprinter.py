# -*- coding: utf-8 -*-
"""pty 기반 가짜 ESC/POS 프린터: 스트림을 파싱해 명령 구조를 검증하고 DLE EOT 에 응답."""
import os
import pty
import threading
import tty
STATUS = {1: 0x16, 2: 0x12, 3: 0x12, 4: 0x12}   # 1: 0x16 = 드로어핀 High (정상)
class Fake:
    def __init__(self, paper_out_after=None, info=True, status_reply=True):
        self.status_reply = status_reply
        self.kanji = True
        self.info = info
        self.font_b = False
        self.m, self.s = pty.openpty()
        tty.setraw(self.s)
        self.path = os.ttyname(self.s)
        self.buf = bytearray()
        self.stats = {"cuts": 0, "rasters": 0, "raster_bytes": 0, "barcodes": 0, "qr_print": 0, "errors": [], "status_q": 0, "info_q": 0, "lines": 0, "text": []}
        self.cur = bytearray()
        self.paper_out_after = paper_out_after
        threading.Thread(target=self.loop, daemon=True).start()
    def loop(self):
        while True:
            try: d = os.read(self.m, 65536)
            except OSError: return
            self.buf += d
            self.parse()
    def need(self, n):
        return len(self.buf) >= n
    def parse(self):
        b = self.buf
        while b:
            c = b[0]
            if c == 0x10:
                if len(b) < 3: return
                if b[1] == 4:
                    n = b[2]; self.stats["status_q"] += 1
                    v = STATUS.get(n, 0x12)
                    if n == 4 and self.paper_out_after is not None and self.stats["cuts"] >= self.paper_out_after: v = 0x72
                    if self.status_reply:
                        os.write(self.m, bytes([v]))
                else: self.stats["errors"].append(f"DLE {b[1]}")
                del b[:3]; continue
            if c == 0x1b:
                if len(b) < 2: return
                k = b[1]
                ln = {0x40:2, 0x52:3, 0x61:3, 0x45:3, 0x2d:3, 0x64:3, 0x33:3, 0x32:2, 0x70:5, 0x74:3,
                      0x4a:3, 0x4d:3, 0x7b:3, 0x56:3}.get(k)
                if ln is None: self.stats["errors"].append(f"ESC {k:02x}"); del b[:2]; continue
                if len(b) < ln: return
                if k == 0x4d: self.font_b = b[2] == 1
                del b[:ln]; continue
            if c == 0x1c:
                if len(b) < 2: return
                if b[1] == 0x26: self.kanji = True; del b[:2]; continue
                if b[1] == 0x2e: self.kanji = False; del b[:2]; continue
                self.stats["errors"].append(f"FS {b[1]:02x}"); del b[:2]; continue
            if c == 0x1d:
                if len(b) < 2: return
                k = b[1]
                if k == 0x49:
                    if len(b) < 3: return
                    self.stats["info_q"] += 1
                    if self.info:
                        os.write(self.m, b"_" + {65: b"FW1.23", 66: b"ACME", 67: b"TP-80", 68: b"SN0001"}.get(b[2], b"?") + b"\x00")
                    del b[:3]; continue
                if k in (0x42, 0x21, 0x68, 0x77, 0x48):
                    if len(b) < 3: return
                    del b[:3]; continue
                if k == 0x56:
                    if len(b) < 3: return
                    if b[2] in (65, 66):
                        if len(b) < 4: return
                        del b[:4]
                    else: del b[:3]
                    self.stats["cuts"] += 1; self.flush_line(); continue
                if k == 0x6b:
                    if len(b) < 4: return
                    m = b[2]
                    if m < 65: self.stats["errors"].append("barcode A"); del b[:3]; continue
                    n = b[3]
                    if len(b) < 4+n: return
                    data = bytes(b[4:4+n])
                    if m == 67 and n not in (12, 13): self.stats["errors"].append("EAN len")
                    if m == 73 and not data.startswith(b"{"): self.stats["errors"].append("C128 set")
                    self.stats["barcodes"] += 1; del b[:4+n]; continue
                if k == 0x28:
                    if len(b) < 5: return
                    ln = b[3] | (b[4] << 8)
                    if len(b) < 5+ln: return
                    if b[2] != 0x6b: self.stats["errors"].append("GS ( ?")
                    if b[5] == 49 and b[6] == 81: self.stats["qr_print"] += 1
                    del b[:5+ln]; continue
                if k == 0x76:
                    if len(b) < 8: return
                    if b[2] != 0x30: self.stats["errors"].append("GS v ?")
                    xl = b[4] | (b[5] << 8); yl = b[6] | (b[7] << 8)
                    if xl > 72: self.stats["errors"].append(f"raster too wide {xl}")
                    if len(b) < 8 + xl*yl: return
                    self.stats["rasters"] += 1; self.stats["raster_bytes"] += xl*yl
                    del b[:8+xl*yl]; continue
                self.stats["errors"].append(f"GS {k:02x}"); del b[:2]; continue
            if c == 0x0a:
                self.flush_line(); del b[:1]; continue
            if c < 0x20:
                self.stats["errors"].append(f"ctrl {c:02x}"); del b[:1]; continue
            self.cur.append(c); del b[:1]
    def flush_line(self):
        if self.cur:
            self.stats["lines"] += 1
            t = bytes(self.cur).decode("cp949", "replace")
            if len(self.stats["text"]) < 4000: self.stats["text"].append(t)
            if "�" in t and self.kanji: self.stats["errors"].append("decode:" + t[:30])
            w = len(self.cur)
            if w > 48 and self.kanji and not self.font_b: self.stats["errors"].append(f"line too long {w}: {t[:40]}")
            self.cur = bytearray()
