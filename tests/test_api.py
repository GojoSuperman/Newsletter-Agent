import json

from fastapi.testclient import TestClient

import web.app as webapp
from newsletter.graph import stub_nodes


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
    saved = json.loads((tmp_path / "runs" / f"{run_id}.json").read_text())
    assert saved["log"] == events[-1]["state"]["log"]
    assert (tmp_path / "metrics.jsonl").exists()


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


def test_runs_and_config_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "metrics.jsonl").write_text('{"run_id":"a","collected":3}\n')
    c = TestClient(webapp.app)
    assert c.get("/api/runs").json() == [{"run_id": "a", "collected": 3}]
    cfg = c.get("/api/config").json()
    assert cfg["pick_count"] == 5 and isinstance(cfg["sources"], list)
