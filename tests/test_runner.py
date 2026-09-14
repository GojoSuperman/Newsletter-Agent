from newsletter.graph import stub_nodes
from newsletter.runner import stream_run


def test_stream_run_yields_node_events_then_end():
    events = list(stream_run(stub_nodes(), hours=24, dry_run=True))
    assert [e["node"] for e in events] == ["collect", "select", "verify", "publish", "__end__"]
    end = events[-1]
    assert len(end["state"]["log"]) == 4 and end["state"]["dry_run"] is True
    assert set(end["seconds"]) == {"collect", "select", "verify", "publish"}
    assert all(v >= 0 for v in end["seconds"].values())


def test_stream_run_merges_reducer_keys():
    nodes = stub_nodes()
    nodes["select"] = lambda s: {"picked": [{"url": "a", "title": "a"}, {"url": "b", "title": "b"}], "log": ["② 2건"]}
    nodes["report"] = lambda s: {"drafted": [{"url": s["pick"]["url"]}], "log": [f"③ {s['pick']['url']}"]}
    end = list(stream_run(nodes, 24, True))[-1]
    assert sorted(d["url"] for d in end["state"]["drafted"]) == ["a", "b"]
    assert end["seconds"]["report"] >= 0
