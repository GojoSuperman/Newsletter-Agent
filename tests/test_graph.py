from newsletter.graph import build, initial_state, merge_delta, run, stub_nodes


def test_merge_delta_accumulates_only_reducer_keys():
    state = {"drafted": [{"url": "a"}], "log": ["1"], "picked": [{"url": "x"}], "hours": 24}
    out = merge_delta(state, {"drafted": [{"url": "b"}], "log": ["2"], "picked": [{"url": "y"}]})
    assert out["drafted"] == [{"url": "a"}, {"url": "b"}]
    assert out["log"] == ["1", "2"]
    assert out["picked"] == [{"url": "y"}]
    assert out is not state
    assert state["drafted"] == [{"url": "a"}]  # 원본 불변


def test_stub_pipeline_runs_five_nodes_in_order():
    result = run(stub_nodes(), hours=24, dry_run=True)
    assert len(result["log"]) == 4
    assert [line[0] for line in result["log"]] == ["①", "②", "④", "⑤"]
    assert result["collected"] == [] and result["picked"] == []


def test_initial_state_has_all_keys():
    s = initial_state(24, True)
    assert set(s) == {"hours", "dry_run", "collected", "picked", "drafted", "verified", "log"}


def test_build_accepts_replaced_node():
    nodes = stub_nodes()
    nodes["collect"] = lambda s: {"collected": [{"title": "x"}], "log": ["① 가짜 1건"]}
    out = build(nodes).compile().invoke(initial_state(24, True))
    assert out["collected"] == [{"title": "x"}]
    assert out["log"][1].startswith("② 선별    1 → 0건")


def test_report_fans_out_per_pick():
    nodes = stub_nodes()
    nodes["select"] = lambda s: {"picked": [{"url": "a"}, {"url": "b"}], "log": ["② 2건"]}
    nodes["report"] = lambda s: {"drafted": [{"url": s["pick"]["url"]}], "log": [f"③ {s['pick']['url']}"]}
    out = build(nodes).compile().invoke(initial_state(24, True))
    assert sorted(d["url"] for d in out["drafted"]) == ["a", "b"]


def test_no_picks_goes_straight_to_verify():
    out = run(stub_nodes(), hours=24, dry_run=True)
    assert [l[0] for l in out["log"]] == ["①", "②", "④", "⑤"]
