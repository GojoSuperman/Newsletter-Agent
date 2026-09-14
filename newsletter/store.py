"""실행 결과 저장 위치. GitHub Actions 기록(store/)과 로컬 기록(store/local/)을 분리한다.

- github: 러너가 만들고 커밋해서 push하는 기록. `git pull`로 내려온다.
- local : 이 컴퓨터에서 대시보드/터미널로 돌린 기록. gitignore라 커밋되지 않는다.
두 기록이 한 파일에 섞이면 pull 때 로컬 기록이 덮어써지므로 경로를 나눈다.
"""
import json
from pathlib import Path

from newsletter.metrics import read_metrics

ORIGINS = ("github", "local")


def _root(store: Path, origin: str) -> Path:
    if origin not in ORIGINS:
        raise ValueError(f"origin은 {ORIGINS} 중 하나여야 합니다: {origin}")
    return store if origin == "github" else store / "local"


def runs_dir(store: Path, origin: str) -> Path:
    return _root(store, origin) / "runs"


def metrics_path(store: Path, origin: str) -> Path:
    return _root(store, origin) / "metrics.jsonl"


def save_run(store: Path, origin: str, run_id: str, state: dict) -> Path:
    d = runs_dir(store, origin)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{run_id}.json"
    f.write_text(json.dumps(state, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return f


def load_run(store: Path, run_id: str) -> dict | None:
    """run_id는 UTC 타임스탬프라 출처가 달라도 겹치지 않는다. github → local 순으로 찾는다."""
    for origin in ORIGINS:
        f = runs_dir(store, origin) / f"{run_id}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def list_runs(store: Path) -> list[dict]:
    """두 출처의 지표를 합쳐 run_id(시각) 순으로 돌려준다. 각 행에 origin을 붙인다."""
    rows: list[dict] = []
    for origin in ORIGINS:
        for row in read_metrics(metrics_path(store, origin)):
            rows.append({**row, "origin": origin})
    rows.sort(key=lambda r: r.get("run_id", ""))
    return rows
