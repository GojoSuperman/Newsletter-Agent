"""관문 G1(본문)·G2(생존)·G3(접근) 검사. 매일 돌리지 않고 소스를 채택할 때 한 번 돌린다."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import trafilatura

from newsletter.config import load_config
from newsletter.nodes.collect import UA, fetch


def extract_text(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    return (trafilatura.extract(downloaded) if downloaded else "") or ""


def gate_body(articles: list[dict], extract: Callable[[str], str], min_body: int, sample: int = 3) -> tuple[int, int]:
    picked = articles[:sample]
    ok = sum(1 for a in picked if len(extract(a["url"])) > min_body)
    return ok, len(picked)


def gate_alive(articles: list[dict], now: datetime, days: int = 14) -> int:
    cutoff = now - timedelta(days=days)
    return sum(1 for a in articles if datetime.fromisoformat(a["at"]) >= cutoff)


def gate_access(url: str) -> bool:
    p = urlparse(url)
    rp = RobotFileParser()
    try:
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA["User-Agent"], url)
    except Exception:
        return True                                  # robots.txt가 없으면 허용으로 본다


def main() -> None:
    cfg = load_config()
    now = datetime.now(timezone.utc)
    print(f"{'소스':<12}{'건수':>5}{'G1 본문':>9}{'G2 14일':>9}{'G3 접근':>9}")
    print("-" * 44)
    for src in cfg.sources:
        try:
            arts = fetch(src)
        except Exception as e:
            print(f"{src.name:<12}  실패: {e!r}")
            continue
        ok, n = gate_body(arts, extract_text, cfg.min_body)
        alive = gate_alive(arts, now)
        access = "허용" if gate_access(src.url) else "금지"
        print(f"{src.name:<12}{len(arts):>5}{f'{ok}/{n}':>9}{alive:>9}{access:>9}")


if __name__ == "__main__":
    main()
