"""관문 G1(본문)·G2(생존)·G3(접근) 검사. 매일 돌리지 않고 소스를 채택할 때 한 번 돌린다."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
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


def gate_access(url: str, http_get=requests.get) -> bool:
    """robots.txt를 우리 UA로 직접 받아 판단한다.

    urllib.robotparser.read()의 기본 UA(Python-urllib)로 robots.txt를 받으면
    일부 사이트가 그 UA 자체를 403으로 차단해 disallow_all로 오판될 수 있어,
    실제로 기사 수집에 쓰는 UA로 직접 요청한다.
    """
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = http_get(robots_url, headers=UA, timeout=10)
        if r.status_code == 404:
            return True                              # robots.txt가 없으면 허용으로 본다
        if r.status_code in (401, 403):
            return False                             # robots.txt 접근 자체가 막히면 불허로 본다
        rp = RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(UA["User-Agent"], url)
    except Exception:
        return True                                  # 네트워크 오류 등은 허용으로 본다


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
