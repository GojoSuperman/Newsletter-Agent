import json

from fastapi.testclient import TestClient

import app.server as srv
from newsletter.graph import stub_nodes
from newsletter.store import save_run

D = {"title": "t", "url": "https://x/1", "source": "TechCrunch", "tier": 2, "at": "2026-09-14T00:00:00+00:00",
     "summary": "S", "reason": "r", "headline": "H", "why": "W", "body": "b"}


def _client(tmp_path, monkeypatch, key="sk-test"):
    srv._pending.clear()
    monkeypatch.setattr(srv, "STORE_DIR", tmp_path)
    monkeypatch.setattr(srv, "SETTINGS_PATH", tmp_path / "local" / "settings.json")
    monkeypatch.setattr(srv, "get_nodes", stub_nodes)
    monkeypatch.setattr(srv, "validate_openai", lambda k, m: None)
    c = TestClient(srv.app)
    if key:
        assert c.put("/api/settings", json={"openai_api_key": key}).status_code == 200
    return c


def test_settings_roundtrip_is_masked(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, key="sk-test-1234567Qx")
    m = c.get("/api/settings").json()
    assert m["openai_key_tail"] == "…7Qx" and m["webhook_registered"] is False
    assert "sk-test" not in c.get("/api/settings").text


def test_settings_rejects_bad_webhook(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.put("/api/settings", json={"discord_webhook_url": "https://example.com"})
    assert r.status_code == 400 and "웹훅" in r.json()["detail"]


def test_run_requires_openai_key(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, key="")
    r = c.post("/api/run", json={})
    assert r.status_code == 400 and "OpenAI" in r.json()["detail"]


def test_run_streams_and_creates_issue(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    run_id = c.post("/api/run", json={"hours": 24}).json()["run_id"]
    with c.stream("GET", f"/api/run/{run_id}/events") as r:
        events = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
    assert [e["node"] for e in events] == ["collect", "select", "verify", "publish", "__end__"]
    assert events[-1]["state"]["dry_run"] is True
    issues = c.get("/api/issues").json()
    assert issues[0]["run_id"] == run_id and issues[0]["origin"] == "local" and issues[0]["sent_at"] is None
    assert issues[0]["date"] == f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"
    assert c.get(f"/api/issues/{run_id}").json()["log"] == events[-1]["state"]["log"]


def test_issues_lists_both_origins_newest_first(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    save_run(tmp_path, "github", "20260913T223000", {"collected": [1, 2], "verified": [D], "dry_run": False})
    save_run(tmp_path, "local", "20260914T010000", {"collected": [1], "verified": [], "dry_run": True})
    rows = c.get("/api/issues").json()
    assert [(r["run_id"], r["origin"], r["published"], r["collected"]) for r in rows] == [
        ("20260914T010000", "local", 0, 1), ("20260913T223000", "github", 1, 2)]


def test_send_posts_once_records_sent_at_and_blocks_repeat(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.put("/api/settings", json={"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"})
    save_run(tmp_path, "local", "r1", {"collected": [], "verified": [D], "dry_run": True})
    calls = []
    class R:
        def raise_for_status(self): pass
    monkeypatch.setattr(srv, "post_fn", lambda url, json, timeout: calls.append(url) or R())
    r = c.post("/api/issues/r1/send")
    assert r.status_code == 200 and r.json()["sent"] == 1 and calls == ["https://discord.com/api/webhooks/1/abc"]
    assert c.get("/api/issues/r1").json()["sent_at"]
    assert c.post("/api/issues/r1/send").status_code == 409


def test_send_requires_webhook_and_articles(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    save_run(tmp_path, "local", "empty", {"collected": [], "verified": [], "dry_run": True})
    save_run(tmp_path, "local", "full", {"collected": [], "verified": [D], "dry_run": True})
    assert c.post("/api/issues/empty/send").status_code == 400
    r = c.post("/api/issues/full/send")
    assert r.status_code == 400 and "웹훅" in r.json()["detail"]
    assert c.post("/api/issues/none/send").status_code == 404


def test_index_served():
    r = TestClient(srv.app).get("/")
    assert r.status_code == 200 and "뉴스레터" in r.text


def test_malformed_settings_returns_clear_error(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, key="")
    (tmp_path / "local").mkdir(parents=True, exist_ok=True)
    (tmp_path / "local" / "settings.json").write_text("{not json", encoding="utf-8")
    r = c.get("/api/settings")
    assert r.status_code == 500 and "설정 파일" in r.json()["detail"]
    r = c.post("/api/run", json={})
    assert r.status_code == 500 and "설정 파일" in r.json()["detail"]


def test_send_blocked_for_already_published_run(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.put("/api/settings", json={"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"})
    save_run(tmp_path, "github", "g1", {"collected": [], "verified": [D], "dry_run": False})
    calls = []
    class R:
        def raise_for_status(self): pass
    monkeypatch.setattr(srv, "post_fn", lambda url, json, timeout: calls.append(url) or R())
    r = c.post("/api/issues/g1/send")
    assert r.status_code == 409 and "이미 발행된" in r.json()["detail"]
    assert calls == []


def test_run_rejects_out_of_range_hours(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/run", json={"hours": 0})
    assert r.status_code == 422
