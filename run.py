"""그래프를 한 번 돌린다. 터미널과 GitHub Actions가 쓴다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from newsletter.config import load_config
from newsletter.graph import real_nodes, run_timed
from newsletter.metrics import append_metrics, summarize


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    load_dotenv()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    state, seconds = run_timed(real_nodes(load_config()), hours=a.hours, dry_run=a.dry_run)
    for line in state["log"]:
        print(line)
    append_metrics(summarize(state, run_id, seconds), Path("store") / "metrics.jsonl")


if __name__ == "__main__":
    main()
