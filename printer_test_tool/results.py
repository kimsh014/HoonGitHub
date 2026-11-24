# -*- coding: utf-8 -*-
"""시험 결과 저장 (프린터별) / CSV 내보내기 / 계획표 엑셀에 결과 반영."""
import csv
import datetime
import json
import os

from engine import BASE_DIR
from testcases import TC

RESULT_DIR = os.path.join(BASE_DIR, "results")
RESULT_FILE = os.path.join(RESULT_DIR, "results.json")

EMPTY = {"result": "미실시", "tester": "", "date": "", "fw": "", "defect": "", "note": ""}


def _safe(name):
    return "".join("_" if c in '\\/:*?"<>|' else c for c in name)


class Results:
    """data = {프린터이름: {TC ID: {result, tester, date, fw, defect, note}}}"""

    def __init__(self, path=RESULT_FILE):
        self.path = os.path.abspath(path)
        self.data = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                # 예전(프린터 구분 없는) 형식이면 '기본' 프린터로 옮긴다
                if raw and all(isinstance(v, dict) and "result" in v for v in raw.values()):
                    raw = {"기본": raw}
                self.data = raw
            except (OSError, ValueError):
                self.data = {}

    def get(self, printer, tcid):
        return dict(EMPTY, **self.data.get(printer, {}).get(tcid, {}))

    def set(self, printer, tcid, **kw):
        r = self.get(printer, tcid)
        r.update({k: v for k, v in kw.items() if v is not None})
        if "result" in kw and not kw.get("date"):
            r["date"] = datetime.date.today().isoformat()
        self.data.setdefault(printer, {})[tcid] = r
        self.save()

    def add_note(self, printer, tcid, line, **kw):
        r = self.get(printer, tcid)
        note = (r["note"] + "\n" if r["note"] else "") + line
        self.set(printer, tcid, note=note, **kw)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def printers(self):
        return list(self.data)

    def counts(self, printer):
        c = {"Pass": 0, "Fail": 0, "N/A": 0, "미실시": 0}
        for t in TC:
            res = self.get(printer, t["id"])["result"]
            c[res] = c.get(res, 0) + 1
        return c

    def export_csv(self, path=None):
        os.makedirs(RESULT_DIR, exist_ok=True)
        path = path or os.path.join(RESULT_DIR, f"결과_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["프린터", "파트", "분류", "ID", "항목", "우선", "합격 기준", "결과", "시험자", "시험일", "FW 버전", "결함 ID", "비고"])
            for printer in self.printers():
                for t in TC:
                    r = self.get(printer, t["id"])
                    w.writerow([printer, t["part"], t["cat"], t["id"], t["name"], t["prio"], t["criterion"], r["result"],
                                r["tester"], r["date"], r["fw"], r["defect"], r["note"]])
        return path

    def export_xlsx(self, plan_path, printer, out_path=None):
        """계획표 엑셀의 '체크리스트' 시트에 해당 프린터 결과를 채워 새 파일로 저장.

        열은 머리글 이름으로 찾는다 (ID / 결과 / 완료 / 시험자 / 시험일 / 결함ID / 측정값·메모 / FW 버전) —
        새 145항목 계획표와 예전 계획표 모두 지원.
        """
        from openpyxl import load_workbook
        wb = load_workbook(plan_path)
        if "체크리스트" not in wb.sheetnames:
            raise ValueError("'체크리스트' 시트가 없습니다. 시험 계획표 파일을 선택하세요.")
        ws = wb["체크리스트"]
        hrow, cols = find_columns(ws)
        if not hrow or "id" not in cols or "result" not in cols:
            raise ValueError("체크리스트 시트에서 'ID' 와 '결과' 머리글을 찾지 못했습니다.")
        mine = self.data.get(printer, {})
        written = 0
        for row in range(hrow + 1, ws.max_row + 1):
            tcid = ws.cell(row, cols["id"]).value
            if tcid not in mine:
                continue
            r = self.get(printer, tcid)
            if r["result"] == "미실시" and not r["note"]:
                continue
            put = {"result": "" if r["result"] == "미실시" else r["result"], "tester": r["tester"], "date": r["date"],
                   "fw": r["fw"], "defect": r["defect"], "note": r["note"],
                   "done": "✔" if r["result"] in ("Pass", "Fail", "N/A") else ""}
            for key, val in put.items():
                if key in cols and val != "":
                    ws.cell(row, cols[key]).value = val
            written += 1
        wb.calculation.fullCalcOnLoad = True
        if not out_path:
            root, ext = os.path.splitext(plan_path)
            out_path = f"{root}_결과_{_safe(printer)}_{datetime.datetime.now():%m%d_%H%M}{ext}"
        wb.save(out_path)
        return out_path, written


HEADERS = {
    "id": ("ID",),
    "result": ("결과",),
    "done": ("완료",),
    "tester": ("시험자",),
    "date": ("시험일", "일시"),
    "defect": ("결함ID", "결함 ID"),
    "note": ("측정값 / 메모", "측정값/메모", "비고"),
    "fw": ("FW 버전", "FW"),
}


def find_columns(ws, max_rows=10):
    """머리글 행과 {키: 열 번호}. 머리글은 위쪽 max_rows 행 안에서 'ID' 가 있는 행."""
    for row in range(1, max_rows + 1):
        names = {str(ws.cell(row, c).value or "").strip(): c for c in range(1, ws.max_column + 1)}
        if "ID" in names:
            cols = {}
            for key, cands in HEADERS.items():
                for cand in cands:
                    if cand in names:
                        cols[key] = names[cand]
                        break
            return row, cols
    return None, {}
