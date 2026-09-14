import importlib
import json
import os
import time

from fastapi.testclient import TestClient

import web.app as webapp
from newsletter.graph import stub_nodes


def test_app_loads_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("NEWSLETTER_TEST_FLAG=1\n")
    monkeypatch.delenv("NEWSLETTER_TEST_FLAG", raising=False)
    try:
        importlib.reload(webapp)
        assert os.environ.get("NEWSLETTER_TEST_FLAG") == "1"
    finally:
        monkeypatch.delenv("NEWSLETTER_TEST_FLAG", raising=False)
        importlib.reload(webapp)


def test_run_streams_five_node_events(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    monkeypatch.setattr(webapp, "get_nodes", stub_nodes)
    client = TestClient(webapp.app)
    run_id = client.post("/api/run", json={"hours": 24, "dry_run": True}).json()["run_id"]
    with client.stream("GET", f"/api/run/{run_id}/events") as r:
        events = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
    nodes = [e["node"] for e in events]
    assert nodes == ["collect", "select", "verify", "publish", "__end__"]
    assert len(events[-1]["state"]["log"]) == 4
    saved = json.loads((tmp_path / "local" / "runs" / f"{run_id}.json").read_text())
    assert saved["log"] == events[-1]["state"]["log"]
    assert (tmp_path / "local" / "metrics.jsonl").exists()   # 로컬 실행은 store/local/에 남는다


def test_get_run_returns_saved_state(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "abc.json").write_text(json.dumps({"log": ["x"]}))
    assert TestClient(webapp.app).get("/api/run/abc").json() == {"log": ["x"]}


def test_index_served():
    r = TestClient(webapp.app).get("/")
    assert r.status_code == 200 and "뉴스레터" in r.text


def test_second_run_rejected_until_first_stream_ends(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    monkeypatch.setattr(webapp, "get_nodes", stub_nodes)
    client = TestClient(webapp.app)
    run_id = client.post("/api/run", json={"hours": 24, "dry_run": True}).json()["run_id"]
    assert client.post("/api/run", json={"hours": 24, "dry_run": True}).status_code == 409
    with client.stream("GET", f"/api/run/{run_id}/events") as r:
        list(r.iter_lines())  # 끝까지 소진해 __end__ 까지 진행시킨다
    assert client.post("/api/run", json={"hours": 24, "dry_run": True}).status_code == 200


def test_stale_pending_run_is_evicted(tmp_path, monkeypatch):
    webapp._pending.clear()          # 이전 테스트가 남긴 pending 항목과 격리
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    monkeypatch.setattr(webapp, "get_nodes", stub_nodes)
    client = TestClient(webapp.app)
    run_id = client.post("/api/run", json={"hours": 24, "dry_run": True}).json()["run_id"]
    webapp._pending[run_id]["created_at"] = time.monotonic() - 120
    assert client.post("/api/run", json={"hours": 24, "dry_run": True}).status_code == 200


def test_runs_and_config_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "metrics.jsonl").write_text('{"run_id":"a","collected":3}\n')
    c = TestClient(webapp.app)
    assert c.get("/api/runs").json() == [{"run_id": "a", "collected": 3, "origin": "github"}]
    cfg = c.get("/api/config").json()
    assert cfg["pick_count"] == 5 and isinstance(cfg["sources"], list)


def test_get_run_finds_local_origin_too(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "local" / "runs").mkdir(parents=True)
    (tmp_path / "local" / "runs" / "loc.json").write_text(json.dumps({"log": ["local"]}))
    assert TestClient(webapp.app).get("/api/run/loc").json() == {"log": ["local"]}


def test_sync_runs_git_pull_and_reports(monkeypatch):
    calls = []
    monkeypatch.setattr(webapp, "_git_pull", lambda: calls.append(1) or (True, "Already up to date."))
    r = TestClient(webapp.app).post("/api/sync")
    assert r.status_code == 200 and r.json() == {"ok": True, "output": "Already up to date."}
    assert calls == [1]


def test_sync_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(webapp, "_git_pull", lambda: (False, "fatal: not a git repository"))
    r = TestClient(webapp.app).post("/api/sync")
    assert r.status_code == 200 and r.json()["ok"] is False and "fatal" in r.json()["output"]
