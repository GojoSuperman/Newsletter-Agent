"""그래프를 한 번 돌린다. 터미널과 GitHub Actions가 쓴다."""
import argparse

from newsletter.graph import run, stub_nodes


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    result = run(stub_nodes(), hours=a.hours, dry_run=a.dry_run)
    for line in result["log"]:
        print(line)


if __name__ == "__main__":
    main()
