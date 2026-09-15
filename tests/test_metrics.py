import json

from newsletter.metrics import append_metrics, read_metrics, summarize

STATE = {"hours": 24, "dry_run": True,
         "collected": [{"source": "A", "url": "1"}, {"source": "B", "url": "2"}, {"source": "A", "url": "3"}],
         "picked": [{"source": "A", "url": "1"}, {"source": "B", "url": "2"}],
         "drafted": [{"source": "A", "url": "1"}],
         "verified": [{"source": "A", "url": "1"}],
         "log": ["① 수집    24시간 창 · 3건 · 소스 1/2 · 실패 Dead", "③ 취재    본문 부족 → 제외 · B · x"]}


def test_summarize_builds_funnel_row():
    row = summarize(STATE, "r1", {"collect": 1.5, "report": 3.0})
    assert row["run_id"] == "r1" and row["collected"] == 3 and row["picked"] == 2
    assert row["drafted"] == 1 and row["verified"] == 1 and row["published"] == 1
    assert row["extract_ok"] == 1 and row["dead_sources"] == ["Dead"]
    assert row["by_source"] == {"A": 1} and row["seconds"]["report"] == 3.0 and row["dry_run"] is True


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "m.jsonl"
    append_metrics({"run_id": "a", "collected": 1}, p)
    append_metrics({"run_id": "b", "collected": 2}, p)
    assert [r["run_id"] for r in read_metrics(p)] == ["a", "b"]
    assert len(p.read_text().strip().splitlines()) == 2


def test_read_missing_file_is_empty(tmp_path):
    assert read_metrics(tmp_path / "none.jsonl") == []


def test_summarize_counts_regenerated_from_log():
    from newsletter.metrics import summarize
    state = {"hours": 24, "collected": [], "picked": [], "drafted": [], "verified": [],
             "log": ["④ 검수    1/2 통과", "   ↻ 재생성 후 통과 · s · h", "   ↻ 재생성 후 탈락 · s · h · 사유"]}
    row = summarize(state, "r", {})
    assert row["regenerated"] == 2 and row["regen_passed"] == 1
