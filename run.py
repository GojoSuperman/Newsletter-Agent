"""그래프를 한 번 돌린다. 터미널과 GitHub Actions가 쓴다."""
import argparse

from dotenv import load_dotenv

from newsletter.config import load_config
from newsletter.graph import real_nodes, run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    load_dotenv()
    result = run(real_nodes(load_config()), hours=a.hours, dry_run=a.dry_run)
    for line in result["log"]:
        print(line)


if __name__ == "__main__":
    main()
