from datetime import datetime, timedelta, timezone

from newsletter.sources_check import gate_access, gate_alive, gate_body
from newsletter.nodes.collect import UA

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def art(url, days_ago):
    return {"title": url, "url": url, "source": "s", "tier": 2, "summary": "",
            "at": (NOW - timedelta(days=days_ago)).isoformat()}


def test_gate_body_counts_extractions_over_threshold():
    arts = [art("a", 0), art("b", 0), art("c", 0)]
    extract = lambda u: "x" * 700 if u != "b" else "short"
    assert gate_body(arts, extract, min_body=600) == (2, 3)


def test_gate_alive_counts_recent_only():
    assert gate_alive([art("a", 1), art("b", 20)], NOW, days=14) == 1


def test_gate_access_allows_when_robots_allows():
    http_get = lambda url, headers, timeout: FakeResponse(200, "User-agent: *\nAllow: /")
    assert gate_access("https://x/rss.xml", http_get=http_get) is True


def test_gate_access_denies_when_robots_disallows_path():
    http_get = lambda url, headers, timeout: FakeResponse(200, "User-agent: *\nDisallow: /blog/")
    assert gate_access("https://x/blog/rss.xml", http_get=http_get) is False


def test_gate_access_sends_our_user_agent():
    captured = {}

    def http_get(url, headers, timeout):
        captured["headers"] = headers
        return FakeResponse(200, "User-agent: *\nAllow: /")

    gate_access("https://x/rss.xml", http_get=http_get)
    assert captured["headers"] == UA


def test_gate_access_true_when_robots_missing():
    http_get = lambda url, headers, timeout: FakeResponse(404)
    assert gate_access("https://x/rss.xml", http_get=http_get) is True
