"""그래프를 한 번 돌린다. 터미널과 GitHub Actions가 쓴다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from newsletter.config import load_config
from newsletter.graph import real_nodes, run_timed
from newsletter.metrics import append_metrics, summarize
from newsletter.store import ORIGINS, metrics_path, save_run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--origin", choices=ORIGINS, default="local",
                   help="기록 위치. github=Actions 러너(커밋됨), local=이 컴퓨터(커밋 안 됨)")
    a = p.parse_args()
    load_dotenv()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    state, seconds = run_timed(real_nodes(load_config()), hours=a.hours, dry_run=a.dry_run)
    for line in state["log"]:
        print(line)
    state["run_id"] = run_id
    store = Path("store")
    save_run(store, a.origin, run_id, state)                      # 대시보드가 카드까지 다시 볼 수 있게 전체 저장
    append_metrics(summarize(state, run_id, seconds), metrics_path(store, a.origin))


if __name__ == "__main__":
    main()
