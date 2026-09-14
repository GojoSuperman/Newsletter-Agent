from datetime import datetime, timedelta, timezone

from newsletter.config import Source
from newsletter.nodes.collect import collect, dedupe_key, parse_hn, parse_rss

NOW = datetime(2026, 9, 14, 7, 30, tzinfo=timezone.utc)


def rss(items: list[tuple[str, str, datetime]]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        f"<pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
        f"<description>&lt;p&gt;요약 {t}&lt;/p&gt;</description></item>"
        for t, u, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class FakeResp:
    def __init__(self, content=b"", payload=None, status=200):
        self.content, self._payload, self.status_code = content, payload, status
    def json(self): return self._payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def test_parse_rss_strips_tags_and_isoformats_date():
    a = parse_rss("TC", 2, rss([("제목", "https://x/a", NOW)]))[0]
    assert a == {"title": "제목", "url": "https://x/a", "source": "TC", "tier": 2,
                 "at": "2026-09-14T07:30:00+00:00", "summary": "요약 제목"}


def test_parse_hn_uses_points_in_summary():
    payload = {"hits": [{"title": "HN글", "url": "https://y/b", "created_at": "2026-09-14T06:00:00Z",
                         "points": 120, "num_comments": 30}]}
    a = parse_hn("HN", 2, payload)[0]
    assert a["url"] == "https://y/b" and "120" in a["summary"]


def test_dedupe_key_drops_query_and_slash():
    assert dedupe_key("https://x/a/?utm_source=t") == dedupe_key("https://x/a")


def test_parse_hn_skips_hit_without_created_at():
    payload = {"hits": [
        {"title": "정상", "url": "https://y/ok", "created_at": "2026-09-14T06:00:00Z", "points": 1, "num_comments": 0},
        {"title": "날짜없음", "url": "https://y/no-date", "points": 1, "num_comments": 0},
        {"title": "날짜이상", "url": "https://y/bad-date", "created_at": "not-a-date", "points": 1, "num_comments": 0},
    ]}
    out = parse_hn("HN", 2, payload)
    assert [a["title"] for a in out] == ["정상"]


def test_collect_filters_window_dedupes_and_isolates_dead_source():
    fresh, old = NOW - timedelta(hours=2), NOW - timedelta(hours=30)
    feeds = {
        "https://s1": FakeResp(rss([("a", "https://x/a", fresh), ("a2", "https://x/a?utm=1", fresh), ("old", "https://x/o", old)])),
    }
    def http_get(url, **kw):
        if url == "https://dead": raise ConnectionError("boom")
        return feeds[url]
    sources = [Source("S1", "https://s1", 2, "rss"), Source("Dead", "https://dead", 2, "rss")]
    out = collect({"hours": 24}, sources, http_get=http_get, now=NOW)
    assert [a["title"] for a in out["collected"]] == ["a"]
    assert "1건" in out["log"][0] and "Dead" in out["log"][0]
