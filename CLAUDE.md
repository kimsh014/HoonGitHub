# 저장소 안내 (Claude Code)

- 사용자와는 한국어로 이야기한다.
- 디지털 메뉴판 코드는 `digital-menu/`에 있다. 구조와 실행 방법은 `digital-menu/README.md`.
- 프로젝트 에이전트는 `.claude/agents/`, 명령은 `.claude/commands/`에 있다.
  - `/menu-review [계약|보안|설치|화면|전체]`: 분야별 검토단(3명씩).
  - `/menu-risk [PR 번호|브랜치]`: 위험 점검단(4명)이 `digital-menu/docs/risk-register.md`를 갱신.
- `digital-menu/`의 코드를 바꾼 PR은 병합 전에 `/menu-risk <PR 번호>`를 돌려 위험 점검표를 갱신하고, 그 결과를 같은 PR에 커밋한다.
