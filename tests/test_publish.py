import pytest

from newsletter.nodes.publish import publish, render_discord

D = {"title": "t", "url": "https://x/1", "source": "TechCrunch", "tier": 2, "at": "", "summary": "S",
     "reason": "r", "headline": "H", "why": "W", "body": "b"}


def test_render_discord_has_embed_per_draft():
    p = render_discord([D, {**D, "url": "https://x/2"}], "오늘의 AI 뉴스")
    assert p["content"].startswith("**오늘의 AI 뉴스") and len(p["embeds"]) == 2
    assert p["embeds"][0]["url"] == "https://x/1" and "W" in p["embeds"][0]["description"]


def test_dry_run_never_posts():
    calls = []
    out = publish({"dry_run": True, "verified": [D]}, post=lambda *a, **k: calls.append(1), webhook_url="https://hook")
    assert calls == [] and "dry_run" in out["log"][0] and "1건" in out["log"][0]


def test_real_run_posts_once():
    calls = []
    class R:
        def raise_for_status(self): pass
    publish({"dry_run": False, "verified": [D]}, post=lambda url, json, timeout: calls.append(url) or R(), webhook_url="https://hook")
    assert calls == ["https://hook"]


def test_zero_verified_does_not_post():
    calls = []
    out = publish({"dry_run": False, "verified": []}, post=lambda *a, **k: calls.append(1), webhook_url="https://hook")
    assert calls == [] and "0건" in out["log"][0]


def test_missing_webhook_raises_when_not_dry_run():
    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        publish({"dry_run": False, "verified": [D]}, post=lambda *a, **k: None, webhook_url=None)
