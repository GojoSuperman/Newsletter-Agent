import json

from newsletter.store import list_runs, load_run, metrics_path, runs_dir, save_run


def test_github_and_local_paths_are_separate(tmp_path):
    assert runs_dir(tmp_path, "github") == tmp_path / "runs"
    assert runs_dir(tmp_path, "local") == tmp_path / "local" / "runs"
    assert metrics_path(tmp_path, "github") == tmp_path / "metrics.jsonl"
    assert metrics_path(tmp_path, "local") == tmp_path / "local" / "metrics.jsonl"


def test_save_then_load_searches_both_origins(tmp_path):
    save_run(tmp_path, "github", "g1", {"log": ["github"]})
    save_run(tmp_path, "local", "l1", {"log": ["local"]})
    assert load_run(tmp_path, "g1")["log"] == ["github"]
    assert load_run(tmp_path, "l1")["log"] == ["local"]
    assert load_run(tmp_path, "none") is None
    assert json.loads((tmp_path / "local" / "runs" / "l1.json").read_text())["log"] == ["local"]


def test_list_runs_merges_origins_sorted_by_run_id(tmp_path):
    metrics_path(tmp_path, "github").write_text('{"run_id":"20260914T060000","collected":1}\n')
    (tmp_path / "local").mkdir()
    metrics_path(tmp_path, "local").write_text(
        '{"run_id":"20260914T010000","collected":2}\n{"run_id":"20260914T090000","collected":3}\n')
    rows = list_runs(tmp_path)
    assert [(r["run_id"], r["origin"]) for r in rows] == [
        ("20260914T010000", "local"), ("20260914T060000", "github"), ("20260914T090000", "local")]


def test_list_runs_empty_store(tmp_path):
    assert list_runs(tmp_path) == []
