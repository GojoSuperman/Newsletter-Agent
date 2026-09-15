"""실행마다 JSON 한 줄. DB도 대시보드 도구도 없이 파일 append."""
import json
import re
from collections import Counter
from pathlib import Path


def summarize(state: dict, run_id: str, seconds: dict[str, float]) -> dict:
    dead: list[str] = []
    for line in state.get("log", []):
        m = re.search(r"실패 (.+)$", line) if line.startswith("① 수집") else None
        if m:
            dead = [s.strip() for s in m.group(1).split(",")]
    log = state.get("log", [])
    regen = [l for l in log if "↻ 재생성" in l]
    return {
        "run_id": run_id,
        "hours": state.get("hours"),
        "collected": len(state.get("collected", [])),
        "picked": len(state.get("picked", [])),
        "drafted": len(state.get("drafted", [])),
        "extract_ok": len(state.get("drafted", [])),          # drafted에 남은 것 = 본문 추출 성공
        "verified": len(state.get("verified", [])),
        "published": len(state.get("verified", [])),
        "regenerated": len(regen),                              # 검수 탈락 후 다시 쓴 건수
        "regen_passed": sum(1 for l in regen if "통과" in l),   # 그중 재검수 통과
        "dead_sources": dead,
        "by_source": dict(Counter(d["source"] for d in state.get("verified", []))),
        "seconds": {k: round(v, 2) for k, v in seconds.items()},
        "dry_run": bool(state.get("dry_run")),
    }


def append_metrics(row: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_metrics(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
