from datetime import datetime, timedelta, timezone

from newsletter.sources_check import gate_alive, gate_body

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def art(url, days_ago):
    return {"title": url, "url": url, "source": "s", "tier": 2, "summary": "",
            "at": (NOW - timedelta(days=days_ago)).isoformat()}


def test_gate_body_counts_extractions_over_threshold():
    arts = [art("a", 0), art("b", 0), art("c", 0)]
    extract = lambda u: "x" * 700 if u != "b" else "short"
    assert gate_body(arts, extract, min_body=600) == (2, 3)


def test_gate_alive_counts_recent_only():
    assert gate_alive([art("a", 1), art("b", 20)], NOW, days=14) == 1
