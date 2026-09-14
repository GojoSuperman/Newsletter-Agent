from newsletter.graph import build, initial_state, run, stub_nodes


def test_stub_pipeline_runs_five_nodes_in_order():
    result = run(stub_nodes(), hours=24, dry_run=True)
    assert len(result["log"]) == 5
    assert [line[0] for line in result["log"]] == ["①", "②", "③", "④", "⑤"]
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
