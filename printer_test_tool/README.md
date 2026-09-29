# 열전사 프린터 검증 도구 (80mm, RS232 / USB / Bluetooth)

`열전사프린터_정상작동_검증계획표` 엑셀의 43개 테스트 케이스를 프로그램으로 실행하고,
결과를 다시 계획표 엑셀에 채워 넣는 Windows용 시험 도구입니다. (Linux/macOS 에서도 COM 연결은 동작)

## 1. 설치 / 실행

| 방법 | 절차 |
|---|---|
| **exe (권장, 설치 불필요)** | GitHub → Actions → `printer-test-tool` → 최신 실행 → `PrinterTester-windows`(Win10/11 64비트) 또는 `PrinterTester-win7-32bit`(Win7·POSReady 7·32비트, 64비트에서도 실행) 다운로드 → 압축 해제 → `PrinterTester.exe` 실행. 파이썬 등 설치 없음 |
| exe 직접 빌드 | Python 3.9+ 설치 후 `build_exe.bat` 더블클릭 → `dist\PrinterTester.exe` |
| Python 으로 실행 | Python 3.9+ 설치 후 `run.bat` 더블클릭 (처음 한 번 패키지 자동 설치) |

`logs\`(시험 로그 CSV), `results\`(판정 결과), `settings.json`(연결 설정)은 exe/프로그램 폴더에 생깁니다.

## 2. 프린터 연결 방식

| 인터페이스 | PC에서 보이는 형태 | 프로그램 설정 |
|---|---|---|
| RS232 (RJ45) | RJ45↔DB9 케이블 또는 USB-시리얼 변환기의 `COMx` | **COM**, 속도/형식/흐름제어를 프린터와 동일하게 |
| USB B-type | 가상 COM(CDC)이면 `COMx` / 프린터 클래스면 Windows 프린터 | **COM** 또는 **WinPrinter** |
| Bluetooth | 페어링 후 `Bluetooth 링크를 통한 표준 직렬(COMx)` | **COM** (포트가 2개면 '발신' 포트) |

- 상태 조회(DLE EOT)·재연결 자동 감지·에이징 중 상태 확인은 **COM 연결에서만** 됩니다.
  USB 가 WinPrinter 로만 잡히면 해당 항목은 출력물로 판정하세요.
- Bluetooth 는 Classic(SPP) 기준입니다. BLE 전용 프린터라면 별도 지원이 필요합니다.
- 프린터 없이 동작만 보려면 **File** 을 선택하세요(전송 데이터가 파일로 저장).

## 3. 화면 구성 (자세한 사용법은 `manual.html` — 프로그램의 [사용 설명서 (도움말)] 버튼)

1. **프린터 연결** — 프린터(최대 9대)마다 **이름**을 붙이고 RS232 / USB / BT 연결을 **각각** 설정·연결.
   공통 설정의 **영수증 길이**(기본 120mm)로 모든 출력물 길이를 맞춥니다(속도 시험만 예외). **빠른 점검**:
   연결 → 프린터 정보(FW, GS I) → 상태 → 확인 영수증.
2. **테스트 케이스** — 계획표 43개 + 추가 시험 7개(E01~E07). 프린터를 고르고 통신을 체크해 `▶ 실행` →
   **체크한 통신마다 따로 인쇄**(영수증 머리에 프린터 이름·통신 표시) → 판정 저장. 결과는 **프린터별**로 저장.
   `계획표 엑셀에 결과 반영`은 프린터마다 새 파일을 만듭니다.
3. **에이징** — '사용' 체크한 모든 프린터·통신이 표로 나옵니다. 줄을 클릭해 ☑ → `체크한 대상 시작`.
   대상마다 독립 실행(한 대가 실패·일시정지해도 나머지 계속), 대상별 CSV 로그, 종료 요약은 X04 비고에 기록.
4. **패턴 인쇄 / 명령** — 16종 패턴, 상태·프린터 정보 조회, 상태 감시, HEX 명령 전송.

**작업 현황**(화면 아래, 항상 보임) — 실행 중인 모든 작업의 대상(프린터/통신)·진행률·경과·최근 내용.
`선택 작업 중지` / `모두 중지`. 같은 통신에 다른 작업이 돌고 있으면 어떤 작업인지 표시해 줍니다.

## 4. 추가 시험 (열전사 프린터 일반 점검)

| ID | 내용 |
|---|---|
| E01 | 프린터 정보 조회(GS I) — FW/제조사/모델/시리얼, FW 칸 자동 입력 |
| E02 | 급지 정확도·여백 — 가로/세로 mm 눈금자 |
| E03 | 컷 위치 — 컷 직전 기준선 |
| E04 | 문자표(코드페이지) — ASCII·상위 문자 전체, 한글 모드 복귀 |
| E05 | 회전·뒤집기 인쇄(ESC { / ESC V) |
| E06 | 헤드 과열 보호 — 전면 검정 연속 |
| E07 | 빠른 점검 — 통신별 연결·정보·상태·확인 영수증 |

## 5. 명령줄(CLI) — 에이징만 따로 돌릴 때

```
python cli.py ports
python cli.py status --ch RS232=COM3:115200:RTS/CTS
python cli.py print  --ch USB=COM7 --pattern all
python cli.py aging  --ch RS232=COM3:115200:RTS/CTS --hours 12
python cli.py aging  --ch USB=COM7 --ch BT=COM9 --mode 교대 --hours 12 --pattern 영수증+이미지
python cli.py aging  --ch 프린터1=COM3:115200:RTS/CTS --ch 프린터2=COM7 --ch 프린터3=COM9 --mode 개별 --hours 12
```

## 6. 주의

- ESC/POS 호환 프린터 기준입니다. 한글이 깨지면 연결 탭의 `한글 모드 명령(FS &)` 을 끄거나 인코딩을 바꿔 보세요.
- 야간 에이징 전 **PC 절전 모드 해제**, 감열지 여유분 확인.
- R01/R02 시험 후에는 프린터와 프로그램 통신 설정을 원래대로 되돌리세요.

## 7. 개발자용

- 설명서: `python make_manual.py` 로 `manual.html` 재생성 (테스트 케이스 표는 `testcases.py` 에서 자동 생성, exe 에 포함)
- 구조: `escpos.py`(명령 생성) · `patterns.py`(인쇄 패턴) · `transports.py`(COM/WinPrinter/File) ·
  `engine.py`(시험 동작·에이징) · `testcases.py`(계획표 항목↔동작) · `results.py`(결과/엑셀) · `gui.py` · `cli.py`
- 테스트: `python -m unittest discover -s tests -v` — 가상 시리얼(pty) 가짜 프린터가 ESC/POS 스트림을 해석해
  명령 구조를 검증하고 상태 조회에 응답합니다 (Linux/macOS).
