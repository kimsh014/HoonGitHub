# 시놀로지 DS415+ × Claude 연동 설명서

> 목표: **회사 PC와 집 PC에서 같은 작업 폴더를 쓰고**, 그 폴더를 **Claude(Claude Desktop / Claude Code)가 직접 읽고 쓰게** 하며, **내 작업물은 나만 볼 수 있게 암호화해서 NAS에 보관**한다.
> 기한: 이번 주(2026-09-28 월 ~ 10-04 일) 안에 실사용 시작.

---

## 0. 전체 구조 한눈에 보기

```
            ┌──────────────── 인터넷 ────────────────┐
            │     (Tailscale 사설 VPN, 포트 개방 없음)   │
  [회사 PC]  ◀──────────────▶  [DS415+ 집]  ◀──────────────▶  [집 PC]
  Synology Drive Client         Synology Drive Server         Synology Drive Client
  └ D:\Work (동기화 폴더)          └ 암호화 공유폴더 /PrivateWork     └ D:\Work (동기화 폴더)
        │                                                          │
   Claude Desktop / Claude Code  ── 로컬 동기화 폴더만 읽고 씀 ──  Claude Desktop / Claude Code
```

핵심 원칙
1. **Claude는 NAS에 직접 붙지 않는다.** 각 PC의 *로컬 동기화 폴더*를 Claude가 다루고, 동기화는 Synology Drive가 맡는다. (가장 안정적이고 설정이 쉬움)
2. **NAS를 인터넷에 직접 노출하지 않는다.** 포트포워딩 대신 Tailscale(사설 VPN)로만 접속한다.
3. **민감 자료는 암호화 공유폴더 + 2단계 인증 + 버전 백업**으로 3중 보호한다.

---

## 1. 사전 점검 (월요일, 30분)

| 항목 | 확인 방법 | 기준 |
|---|---|---|
| DSM 버전 | 제어판 → 정보 센터 | DSM 7.1 이상 (DS415+는 DSM 7.2 지원). 최신 업데이트 적용 |
| 디스크 상태 | 저장소 관리자 → HDD/SSD | 모두 "정상". 경고가 있으면 교체부터 |
| 볼륨 여유 공간 | 저장소 관리자 | 작업 데이터 + 버전 보관분의 2배 이상 |
| 메모리 | 정보 센터 | 기본 2GB. Drive + Tailscale 정도는 충분 |
| 회사 보안 정책 | 사내 규정/IT팀 | **회사 자료를 개인 NAS·외부 AI에 저장·업로드해도 되는지 반드시 확인** |

> ⚠️ **DS415+ 하드웨어 주의**: DS415+에 쓰인 Intel Atom C2538은 장기 사용 시 갑자기 부팅이 안 되는 알려진 결함이 있습니다(시놀로지가 과거 보증 연장 처리). 10년 가까이 된 장비이므로 **아래 6장의 백업은 선택이 아니라 필수**입니다.

---

## 2. NAS 기본 보안 설정 (월요일, 30분)

1. **관리자 계정 정리**
   - 제어판 → 사용자 및 그룹 → 새 관리자 계정 생성(예: `hoon_admin`) → 기본 `admin` 계정 **비활성화**.
   - 일상 작업용 일반 계정도 따로 생성(예: `hoon`). Drive 동기화는 이 계정으로 한다.
2. **2단계 인증(2FA)**
   - 우측 상단 사용자 아이콘 → 개인 → 보안 → 2단계 인증 → Synology Secure SignIn 앱 또는 OTP 앱 등록.
   - 제어판 → 보안 → 계정 → "다음 사용자에게 2단계 인증 적용: 관리자 그룹" 체크.
3. **자동 차단**: 제어판 → 보안 → 보호 → 자동 차단 활성화 (예: 5분 내 5회 실패 시 차단).
4. **불필요한 서비스 끄기**: 제어판 → 파일 서비스에서 쓰지 않는 AFP/FTP/NFS 비활성화. 제어판 → 외부 액세스 → **QuickConnect 비활성화**, 공유기 **포트포워딩 제거**(Tailscale만 쓸 예정).
5. **방화벽**: 제어판 → 보안 → 방화벽 활성화 → 규칙: *로컬 네트워크(192.168.x.0/24)* 와 *Tailscale 대역(100.64.0.0/10)* 만 허용, 나머지 거부.

---

## 3. 비밀 작업용 암호화 공유폴더 만들기 (월요일, 20분)

1. 제어판 → 공유 폴더 → 생성
   - 이름: `PrivateWork`
   - "네트워크 환경에서 이 공유 폴더 숨기기" ✔
   - "권한이 없는 사용자에게서 하위 폴더 및 파일 숨기기" ✔
   - **"이 공유 폴더 암호화"** ✔ → 강력한 암호 입력
   - (Btrfs 볼륨이면) "데이터 체크섬 활성화" ✔
2. **암호화 키 파일(.key) 내보내기** → NAS가 아닌 곳 2군데에 보관(예: 암호 관리자 + 오프라인 USB). *이 키를 잃어버리면 데이터 복구 불가.*
3. 권한: `hoon` 계정만 읽기/쓰기, 그 외 모든 사용자·그룹 **액세스 금지**.
4. 재부팅 후 자동 마운트 여부
   - DSM 7.2: 제어판 → 공유 폴더 → 암호화 키 관리자에서 "부팅 시 자동 마운트" 설정 가능.
   - 보안 우선이면 자동 마운트를 끄고 재부팅 시 수동 마운트(더 안전, 대신 불편).

폴더 구조 예시
```
PrivateWork/
├── 00_Inbox/          # 임시로 던져두는 곳
├── 10_Projects/       # 프로젝트별 작업
├── 20_Reference/      # 참고 자료
├── 90_Claude/         # Claude 대화 결과물, 프롬프트, CLAUDE.md
└── 99_NoAI/           # ★ Claude에게 절대 보여주지 않을 자료 (5장 참고)
```

---

## 4. 회사 ↔ 집 동기화: Synology Drive + Tailscale (화~수요일)

### 4-1. NAS에 패키지 설치
패키지 센터에서 설치:
- **Synology Drive Server**
- **Tailscale** (패키지 센터에서 검색, 없으면 tailscale.com의 Synology 안내에 따라 설치)

### 4-2. Tailscale 연결 (포트 개방 없는 사설 접속)
1. NAS의 Tailscale 앱 실행 → 로그인(개인 계정) → 기기 등록.
2. 집 PC, 회사 PC(설치가 허용되는 경우)에 Tailscale 설치 → 같은 계정으로 로그인.
3. Tailscale 관리 콘솔에서
   - NAS 기기 **"Disable key expiry"** 설정(주기적 재인증으로 끊기는 것 방지)
   - NAS의 Tailscale IP(`100.x.y.z`) 또는 MagicDNS 이름(예: `ds415`) 메모.
4. 확인: 회사 PC 브라우저에서 `http://100.x.y.z:5000` → DSM 로그인 화면이 뜨면 성공.

> 회사 PC에 Tailscale 설치가 금지된 경우: IT팀 승인 요청이 원칙입니다. 대안으로 QuickConnect(시놀로지 중계)를 쓸 수 있지만 속도가 느리고 NAS가 외부에 노출되므로, 사용한다면 2FA·자동 차단을 반드시 켜 두세요.

### 4-3. Synology Drive 설정
1. NAS: Synology Drive 관리 콘솔 → 팀 폴더 → `PrivateWork` **활성화** → 버전 관리: 최대 32개 버전, "인텔리버전" 사용.
2. 집 PC / 회사 PC: **Synology Drive Client** 설치 → 동기화 작업 생성
   - 서버 주소: `100.x.y.z` (Tailscale IP) 또는 `ds415`
   - 계정: `hoon`
   - 원격 폴더: `/PrivateWork`
   - 로컬 폴더: `D:\Work` (두 PC에서 **같은 경로**로 맞추면 Claude 설정을 그대로 복사 가능)
   - 동기화 규칙: 필터에서 `*.tmp`, `~$*`, `node_modules`, `.venv` 제외
3. **동시 편집 주의**: 같은 파일을 두 PC에서 동시에 열어두지 말 것. 충돌 시 `파일명_Conflict...` 사본이 생기므로 주기적으로 정리.
4. 회사 PC를 떠나기 전 트레이 아이콘이 **"최신 상태"** 인지 확인하는 습관 들이기.

---

## 5. Claude 연동 (목요일)

두 PC 모두 동일하게 설정합니다. 둘 중 편한 것 하나만 써도 됩니다.

### 방법 A. Claude Desktop + 파일시스템 MCP (문서·기획·일반 업무용, 추천)
1. Claude Desktop 설치(claude.ai/download) → 로그인.
2. 파일 접근 연결
   - 설정 → 확장(Extensions)에서 **Filesystem** 확장을 설치하고 허용 폴더에 `D:\Work`만 지정.
   - 또는 수동 설정: 설정 → 개발자 → 설정 편집 → `claude_desktop_config.json`에 아래 추가 (Node.js 설치 필요)

```json
{
  "mcpServers": {
    "work": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "D:\\Work\\10_Projects",
        "D:\\Work\\20_Reference",
        "D:\\Work\\90_Claude"
      ]
    }
  }
}
```

   - **`99_NoAI`는 목록에 넣지 않습니다.** 허용한 폴더 밖은 Claude가 접근하지 못합니다.
3. Claude Desktop 재시작 → 대화창에서 "10_Projects 폴더에 있는 파일 목록 보여줘"로 확인.
4. 활용 예: "20_Reference의 회의록 3개를 요약해서 90_Claude/주간요약_0928.md로 저장해줘" → 저장된 파일이 자동으로 다른 PC로 동기화됨.

### 방법 B. Claude Code (코드·스크립트·대량 파일 작업용)
1. 터미널에서 설치: 공식 안내(code.claude.com) 참고 후 `claude` 실행 → 로그인.
2. 작업 폴더로 이동해서 실행:
   ```bash
   cd D:\Work\10_Projects\프로젝트A
   claude
   ```
3. `D:\Work\90_Claude\CLAUDE.md` 또는 각 프로젝트 폴더의 `CLAUDE.md`에 작업 규칙을 적어두면 회사/집 어디서 실행해도 같은 맥락으로 시작합니다. 예:
   ```markdown
   # 작업 규칙
   - 결과물은 한국어로, 파일은 90_Claude/ 아래에 저장
   - 99_NoAI 폴더는 절대 읽지 말 것
   ```
4. 민감 폴더 차단(Claude Code 설정 `.claude/settings.json`, `D:\Work` 기준):
   ```json
   {
     "permissions": {
       "deny": ["Read(./99_NoAI/**)", "Edit(./99_NoAI/**)"]
     }
   }
   ```

### 방법 C. Claude 프로젝트(Projects) 활용 (웹/앱)
- claude.ai → Projects에 자주 쓰는 참고 문서를 올려두면 회사·집 어디서든 같은 맥락으로 대화 가능.
- 단, 이 경우 파일이 Anthropic 서버에 업로드되므로 **99_NoAI 성격 자료는 올리지 말 것.**

---

## 6. "비밀스럽게" 지키기 위한 체크리스트

### 6-1. Claude 쪽 프라이버시
- Claude가 읽은 파일 내용은 대화 처리를 위해 Anthropic 서버로 전송됩니다. **NAS에 암호화 저장 ≠ Claude에 보여줘도 안전**입니다.
- claude.ai → 설정 → 개인정보(Privacy)에서 **모델 학습에 대화 데이터 사용 여부**를 확인하고 원하지 않으면 끄세요.
- 주민번호·계좌·고객 개인정보·회사 기밀 원본은 `99_NoAI`에만 두고 Claude 허용 폴더에 넣지 않기.
- 회사 업무 자료는 회사 정책상 허용된 범위(예: 회사가 계약한 Claude Team/Enterprise)에서만 다루기.

### 6-2. 기기 쪽
- 회사 PC: Windows 계정 잠금(Win+L), BitLocker 확인. 회사 PC를 IT팀이 관리한다면 **로컬 동기화 폴더는 관리자에게 보일 수 있음**을 인지.
- 집 PC: BitLocker(Windows) / FileVault(Mac) 켜기.
- 분실 대비: Synology Drive Client는 로컬 사본을 남기므로, 노트북이라면 디스크 암호화가 필수.

### 6-3. 백업 (3-2-1 원칙)
| 대상 | 방법 | 주기 |
|---|---|---|
| 실수로 삭제/덮어쓰기 | Synology Drive 버전 관리(4-3) | 실시간 |
| NAS 고장 대비 | **Hyper Backup** → 외장 USB HDD, 백업 암호화 ✔ | 매일 새벽 |
| 화재·도난 대비 | Hyper Backup → C2 Storage 또는 다른 클라우드, 클라이언트 측 암호화 ✔ | 매주 |
| (Btrfs 볼륨일 때) 랜섬웨어 대비 | Snapshot Replication 설치 → PrivateWork 스냅샷 | 매시간, 7일 보관 |

- Hyper Backup 암호화 비밀번호도 암호화 키와 함께 **NAS 밖**에 보관.
- 월 1회 Hyper Backup Explorer로 **복원 테스트** 1건 해보기.

---

## 7. 이번 주 실행 계획

| 요일 | 할 일 | 완료 기준 |
|---|---|---|
| 월 (9/28) | 1장 사전점검, 회사 정책 확인, 2장 보안 설정, 3장 암호화 폴더 | 2FA 로그인 성공, 키 파일 2곳 보관 |
| 화 (9/29) | 4-1, 4-2 Tailscale | 회사 PC에서 `http://100.x.y.z:5000` 접속 성공 |
| 수 (9/30) | 4-3 Synology Drive, 두 PC 동기화 | 집에서 만든 파일이 회사 PC에 나타남 |
| 목 (10/1) | 5장 Claude Desktop/Code 연결 | Claude가 90_Claude에 파일 저장 → 다른 PC에서 확인 |
| 금 (10/2) | 6장 Hyper Backup, 스냅샷, 개인정보 설정 | 첫 백업 완료 + 파일 1개 복원 테스트 |
| 주말 | 실제 업무 파일 이전, 폴더 정리 | 기존 USB/메일 기반 공유 중단 |

---

## 8. 문제 해결 (FAQ)

**Q. 회사에서 동기화가 안 돼요.**
- Tailscale이 연결 상태인지 확인 → `ping 100.x.y.z`.
- 회사 방화벽이 Tailscale을 막으면 IT팀에 문의(임의 우회 금지).
- Drive Client 포트는 6690(TCP). Tailscale 경유면 별도 개방 불필요.

**Q. 재부팅 후 파일이 안 보여요.**
- 암호화 공유폴더가 마운트되지 않은 상태 → 제어판 → 공유 폴더 → `PrivateWork` → 암호화 → 마운트.

**Q. Claude가 폴더를 못 찾아요.**
- MCP 설정 경로의 역슬래시를 `\\`로 두 번 썼는지 확인, Claude Desktop 완전 종료 후 재시작.
- Node.js 설치 여부 확인(`node -v`).

**Q. 충돌 파일(`_Conflict`)이 생겼어요.**
- 두 파일을 비교해 최신본만 남기고 삭제. 반복되면 PC를 옮기기 전에 파일을 닫고 동기화 완료를 확인.

**Q. DS415+가 갑자기 켜지지 않아요.**
- 디스크를 빼서 순서를 기록한 뒤, 같은 계열 신형 시놀로지로 옮기면 대부분 마이그레이션 가능. 그 전에 Hyper Backup 외장 백업이 있으면 안전합니다. 장기적으로 기기 교체(예: DS423+/DS224+)를 검토하세요.

---

### 요약
- **동기화는 Synology Drive**, **접속 경로는 Tailscale**, **Claude는 로컬 동기화 폴더만** 다룬다.
- **암호화 공유폴더 + 2FA + Hyper Backup**으로 나만의 작업 공간을 지킨다.
- **Claude에게 보여줄 폴더와 보여주지 않을 폴더(99_NoAI)를 처음부터 분리**한다.
