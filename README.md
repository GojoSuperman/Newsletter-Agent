# 뉴스레터 에이전트

AI 뉴스를 매일 아침 수집 → 선별 → 요약 → 검수 → Discord 발행하는 LangGraph 파이프라인과 대시보드.

## 실행
```bash
cp .env.example .env   # 키 입력
uv sync
uv run python run.py --hours 24 --dry-run      # 터미널 한 번 실행 (기록은 store/local/)
uv run uvicorn web.app:app --reload            # 대시보드 http://127.0.0.1:8000
uv run pytest
```

## 필요한 키
`.env`에 아래 값을 설정한다.
- `OPENAI_API_KEY` (필수)
- `OPENAI_MODEL` (선택, 기본값 `gpt-4o-mini`)
- `DISCORD_WEBHOOK_URL` (실제 발행 시 필요, `--dry-run`이면 없어도 됨)

## 매일 아침 자동 실행
1. GitHub 저장소 → Settings → Secrets and variables → Actions
   - Secrets: `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`
   - Variables(선택): `OPENAI_MODEL`
2. Actions 탭 → daily-newsletter → Run workflow (dry_run 체크) 로 수동 1회 검증
3. 이후 매일 07:30 KST 자동 실행. 실행 기록은 `store/metrics.jsonl`에 커밋됨

## 실행 기록 두 곳
- `store/runs/`, `store/metrics.jsonl` — GitHub Actions가 매일 만들고 커밋하는 기록. 대시보드의 **⟳ GitHub에서 가져오기** 버튼(= `git pull`)으로 내려받는다.
- `store/local/` — 이 컴퓨터에서 대시보드나 `run.py`로 돌린 기록. 커밋되지 않는다.
- 대시보드 "과거 실행" 표의 출처 열이 GitHub / 로컬을 구분하고, 실행 ID를 누르면 그날의 카드와 탈락 사유를 다시 볼 수 있다.
