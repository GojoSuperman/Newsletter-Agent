# 뉴스레터 에이전트

AI 뉴스를 매일 아침 수집 → 선별 → 요약 → 검수 → Discord 발행하는 LangGraph 파이프라인과 대시보드.

## 실행
```bash
cp .env.example .env   # 키 입력
uv sync
uv run python run.py --hours 24 --dry-run      # 터미널 한 번 실행
uv run uvicorn web.app:app --reload            # 대시보드 http://127.0.0.1:8000
uv run pytest
```
