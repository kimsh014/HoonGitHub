# 저장소 안내 (Claude Code)

- 사용자와는 한국어로 이야기한다.
- 디지털 메뉴판 코드는 `digital-menu/`에 있다. 구조와 실행 방법은 `digital-menu/README.md`.
- 프로젝트 에이전트는 `.claude/agents/`, 명령은 `.claude/commands/`에 있다.
  - `/menu-review [계약|보안|설치|화면|전체]`: 분야별 검토단(3명씩).
  - `/menu-risk [PR 번호|브랜치]`: 위험 점검단(4명)이 `digital-menu/docs/risk-register.md`를 갱신.
  - `/menu-simulate [시나리오 수]`: 사장님·환경·사건 조합으로 매장의 하루를 시뮬레이션해 위험 점검표에 더한다. 사용자가 그만두라고 할 때까지 정기적으로 돈다.
  - `/menu-ui-handoff [PR 번호|커밋 범위]`: UI 담당자에게 넘길 작업 안내와 Claude·GPT용 작업 지시를 `digital-menu/docs/ui-handoff/`에 만든다.
- `digital-menu/`의 코드를 바꾼 PR은 병합 전에 `/menu-risk <PR 번호>`를 돌려 위험 점검표를 갱신하고, 그 결과를 같은 PR에 커밋한다.
- `digital-menu/server/pb_public/`, `pb_migrations`, `pb_hooks`, `digital-menu/ui-prompt.md`를 바꾼 PR은 병합 전에 `/menu-ui-handoff <PR 번호>`도 돌려 같은 PR에 커밋한다.
