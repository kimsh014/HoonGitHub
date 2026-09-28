"""프린터 연결(통신) 계층.

- SerialTransport : RS232, USB 가상 COM(CDC), 블루투스 SPP(가상 COM) 모두 여기로 연결
- WinPrinterTransport : Windows에 '프린터'로 설치된 USB(Printer Class) 장치에 RAW 전송
- FileTransport : 프린터 없이 동작 확인용(전송 바이트를 파일로 저장)
"""
import os
import sys
import threading
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover
    serial = None

try:
    import win32print  # pywin32
except ImportError:
    win32print = None


class TransportError(Exception):
    pass


def list_com_ports():
    """[(장치명, 설명)] — 설명으로 USB/Bluetooth 구분 가능."""
    if serial is None:
        return []
    return [(p.device, p.description or "") for p in serial.tools.list_ports.comports()]


def list_win_printers():
    if win32print is None:
        return []
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]


class Transport:
    kind = "base"
    supports_status = False

    def __init__(self, label):
        self.label = label          # 예: "RS232", "USB", "BT"
        self.lock = threading.Lock()

    @property
    def target(self):
        return ""

    def open(self):
        raise NotImplementedError

    def close(self):
        pass

    @property
    def is_open(self):
        return False

    def write(self, data: bytes, cancel=None) -> float:
        """전송하고 걸린 시간(초)을 돌려준다."""
        raise NotImplementedError

    def query(self, cmd: bytes, nbytes=1, timeout=1.0):
        """명령을 보내고 응답을 읽는다. 응답이 없으면 None."""
        return None

    def describe(self):
        return f"{self.label} [{self.kind}] {self.target}"


class SerialTransport(Transport):
    kind = "COM"
    supports_status = True

    def __init__(self, label, port, baudrate=115200, bytesize=8, parity="N",
                 stopbits=1, flow="RTS/CTS", write_timeout=30.0, chunk=1024):
        super().__init__(label)
        self.port = port
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = parity
        self.stopbits = float(stopbits)
        self.flow = flow
        self.write_timeout = float(write_timeout)
        self.chunk = int(chunk)
        self.ser = None

    @property
    def target(self):
        return f"{self.port} {self.baudrate} {self.bytesize}{self.parity}{self.stopbits:g} {self.flow}"

    def open(self):
        if serial is None:
            raise TransportError("pyserial 이 설치되어 있지 않습니다 (pip install pyserial)")
        if self.is_open:
            return
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                rtscts=self.flow == "RTS/CTS",
                dsrdtr=self.flow == "DTR/DSR",
                xonxoff=self.flow == "XON/XOFF",
                timeout=1.0,
                write_timeout=self.write_timeout,
            )
        except Exception as e:
            self.ser = None
            raise TransportError(f"{self.port} 열기 실패: {e}") from e

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def write(self, data, cancel=None):
        if not self.is_open:
            raise TransportError(f"{self.label}: 포트가 열려 있지 않습니다")
        t0 = time.perf_counter()
        with self.lock:
            try:
                for i in range(0, len(data), self.chunk):
                    if cancel is not None and cancel.is_set():
                        raise TransportError("사용자 중지")
                    self.ser.write(data[i:i + self.chunk])
                self.ser.flush()
            except serial.SerialTimeoutException as e:
                raise TransportError(f"{self.label}: 전송 시간 초과({self.write_timeout:g}s) — 흐름제어/BUSY 확인") from e
            except TransportError:
                raise
            except Exception as e:
                raise TransportError(f"{self.label}: 전송 실패: {e}") from e
        return time.perf_counter() - t0

    def query(self, cmd, nbytes=1, timeout=1.0):
        if not self.is_open:
            raise TransportError(f"{self.label}: 포트가 열려 있지 않습니다")
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(cmd)
                self.ser.flush()
                # 포트 재설정 없이 마감 시각까지 폴링
                resp = bytearray()
                deadline = time.perf_counter() + timeout
                while len(resp) < nbytes and time.perf_counter() < deadline:
                    waiting = self.ser.in_waiting
                    if waiting:
                        resp += self.ser.read(min(waiting, nbytes - len(resp)))
                    else:
                        time.sleep(0.01)
                resp = bytes(resp)
            except Exception as e:
                raise TransportError(f"{self.label}: 상태 조회 실패: {e}") from e
        return resp if resp else None


class WinPrinterTransport(Transport):
    """Windows 스풀러를 통한 RAW 전송. 상태(양방향) 조회는 드라이버 의존이라 지원하지 않는다."""
    kind = "WinPrinter"

    def __init__(self, label, printer_name):
        super().__init__(label)
        self.printer_name = printer_name
        self._open = False

    @property
    def target(self):
        return self.printer_name

    def open(self):
        if win32print is None:
            raise TransportError("pywin32 가 필요합니다 (Windows 전용, pip install pywin32)")
        try:
            h = win32print.OpenPrinter(self.printer_name)
            win32print.ClosePrinter(h)
        except Exception as e:
            raise TransportError(f"프린터 '{self.printer_name}' 열기 실패: {e}") from e
        self._open = True

    def close(self):
        self._open = False

    @property
    def is_open(self):
        return self._open

    def write(self, data, cancel=None):
        if not self._open:
            raise TransportError(f"{self.label}: 연결되어 있지 않습니다")
        t0 = time.perf_counter()
        with self.lock:
            try:
                h = win32print.OpenPrinter(self.printer_name)
                try:
                    win32print.StartDocPrinter(h, 1, ("PrinterTest", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(h)
                        win32print.WritePrinter(h, data)
                        win32print.EndPagePrinter(h)
                    finally:
                        win32print.EndDocPrinter(h)
                finally:
                    win32print.ClosePrinter(h)
            except Exception as e:
                raise TransportError(f"{self.label}: 스풀러 전송 실패: {e}") from e
        return time.perf_counter() - t0

    def spooler_status(self):
        """스풀러가 보고하는 상태(드라이버가 채워줄 때만 의미 있음)."""
        h = win32print.OpenPrinter(self.printer_name)
        try:
            info = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
        return {"status": info.get("Status", 0), "jobs": info.get("cJobs", 0)}


class FileTransport(Transport):
    """프린터 없이 시험할 때 사용. 전송 바이트를 파일에 이어서 기록."""
    kind = "File"

    def __init__(self, label, path):
        super().__init__(label)
        self.path = path
        self.f = None

    @property
    def target(self):
        return self.path

    def open(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.f = open(self.path, "ab")

    def close(self):
        if self.f:
            self.f.close()
        self.f = None

    @property
    def is_open(self):
        return self.f is not None

    def write(self, data, cancel=None):
        if not self.f:
            raise TransportError(f"{self.label}: 파일이 열려 있지 않습니다")
        t0 = time.perf_counter()
        with self.lock:
            self.f.write(data)
            self.f.flush()
        return time.perf_counter() - t0


def make_transport(label, cfg: dict) -> Transport:
    kind = cfg.get("kind", "COM")
    if kind == "COM":
        return SerialTransport(label, cfg["port"], cfg.get("baudrate", 115200), cfg.get("bytesize", 8),
                               cfg.get("parity", "N"), cfg.get("stopbits", 1), cfg.get("flow", "RTS/CTS"),
                               cfg.get("write_timeout", 30))
    if kind == "WinPrinter":
        return WinPrinterTransport(label, cfg["printer"])
    if kind == "File":
        return FileTransport(label, cfg["path"])
    raise ValueError(kind)


IS_WINDOWS = sys.platform.startswith("win")
