"""① 자료 수집. RSS(2칸)와 Hacker News 공개 API(1칸)에서 시간 창 안의 글을 모은다."""
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from newsletter.config import Source
from newsletter.state import Article

UA = {"User-Agent": "Mozilla/5.0 (newsletter-agent)"}
TIMEOUT = 20


def strip_tags(s: str | None) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def dedupe_key(url: str) -> str:
    """추적용 꼬리표(?utm=...)와 끝 슬래시를 떼고 비교한다."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def parse_rss(name: str, tier: int, content: bytes) -> list[Article]:
    out: list[Article] = []
    for e in feedparser.parse(content).entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t or not e.get("link"):
            continue                                  # 날짜·링크 없는 항목은 결과를 바꾸지 않으므로 조용히 버린다
        at = datetime(*t[:6], tzinfo=timezone.utc)
        body = e.get("content", [{}])[0].get("value") if e.get("content") else e.get("summary", "")
        out.append({"title": strip_tags(e.get("title")), "url": e.link, "source": name, "tier": tier,
                    "at": at.isoformat(), "summary": strip_tags(body)[:300]})
    return out


def parse_hn(name: str, tier: int, payload: dict) -> list[Article]:
    out: list[Article] = []
    for h in payload.get("hits", []):
        if not h.get("url"):
            continue
        try:
            at = datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue                                  # 날짜 없거나 형식이 이상한 항목은 결과를 바꾸지 않으므로 조용히 버린다
        out.append({"title": h.get("title", ""), "url": h["url"], "source": name, "tier": tier,
                    "at": at.isoformat(),
                    "summary": f"HN 추천 {h.get('points', 0)} · 댓글 {h.get('num_comments', 0)}"})
    return out


def fetch(source: Source, http_get=requests.get) -> list[Article]:
    r = http_get(source.url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    if source.kind == "hn":
        return parse_hn(source.name, source.tier, r.json())
    return parse_rss(source.name, source.tier, r.content)


def collect(state: dict, sources: list[Source], http_get=requests.get, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=state["hours"])
    items: list[Article] = []
    dead: list[str] = []
    seen: set[str] = set()
    for src in sources:
        try:
            fetched = fetch(src, http_get)
        except Exception:
            dead.append(src.name)                     # 한 곳이 죽어도 나머지는 계속. 죽은 곳은 반드시 남긴다
            continue
        for a in fetched:
            if datetime.fromisoformat(a["at"]) < cutoff:
                continue
            key = dedupe_key(a["url"])
            if key in seen:
                continue
            seen.add(key)
            items.append(a)
    items.sort(key=lambda a: a["at"], reverse=True)
    dead_note = f" · 실패 {', '.join(dead)}" if dead else ""
    return {"collected": items,
            "log": [f"① 수집    {state['hours']}시간 창 · {len(items)}건 · 소스 {len(sources) - len(dead)}/{len(sources)}{dead_note}"]}
