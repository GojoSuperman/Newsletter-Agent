import os
from collections.abc import Callable
from functools import partial

from langgraph.graph import END, START, StateGraph

from newsletter.config import Config
from newsletter.nodes.collect import collect
from newsletter.nodes.publish import publish
from newsletter.nodes.report import fan_report, report_worker
from newsletter.nodes.select import select
from newsletter.nodes.verify import rewrite_draft, verify
from newsletter.state import Brief

NODE_ORDER = ("collect", "select", "report", "verify", "publish")


def stub_nodes() -> dict[str, Callable]:
    """섹션 2의 빈 노드 다섯 개. 로그 한 줄만 남기고 빈 값을 돌려준다."""
    return {
        "collect": lambda s: {"collected": [], "log": [f"① 수집    {s['hours']}시간 창 · 0건 (빈 노드)"]},
        "select": lambda s: {"picked": [], "log": [f"② 선별    {len(s['collected'])} → 0건 (빈 노드)"]},
        "report": lambda s: {"drafted": [], "log": [f"③ 취재    {s['pick']['title']} (빈 노드)"]},
        "verify": lambda s: {"verified": [], "log": [f"④ 검수    {len(s['drafted'])}건 (빈 노드)"]},
        "publish": lambda s: {"log": [f"⑤ 발행    {len(s['verified'])}건 (빈 노드)"]},
    }


def build(nodes: dict[str, Callable]) -> StateGraph:
    """이름→함수 매핑을 받아 다섯 노드를 순서대로 잇는다. 노드를 갈아 끼워도 이 함수는 안 바뀐다."""
    g = StateGraph(Brief)
    for name in NODE_ORDER:
        g.add_node(name, nodes[name])
    g.add_edge(START, "collect")
    g.add_edge("collect", "select")
    g.add_conditional_edges("select", fan_report, ["report", "verify"])   # 기사 수만큼 펼친다
    g.add_edge("report", "verify")
    g.add_edge("verify", "publish")
    g.add_edge("publish", END)
    return g


def initial_state(hours: int, dry_run: bool) -> Brief:
    return {"hours": hours, "dry_run": dry_run,
            "collected": [], "picked": [], "drafted": [], "verified": [], "log": []}


def merge_delta(state: dict, delta: dict) -> dict:
    """누적 리듀서 키(drafted/log)는 이어붙이고 나머지는 덮어쓴 새 dict를 돌려준다."""
    out = dict(state)
    for k, v in delta.items():
        out[k] = out.get(k, []) + v if k in ("drafted", "log") else v
    return out


def run(nodes: dict[str, Callable], hours: int = 24, dry_run: bool = True) -> Brief:
    return build(nodes).compile().invoke(initial_state(hours, dry_run))


def run_timed(nodes: dict[str, Callable], hours: int = 24, dry_run: bool = True) -> tuple[Brief, dict[str, float]]:
    """노드별 소요 시간을 함께 돌려준다. CLI 전용."""
    from newsletter.runner import stream_run     # 순환 import를 피하려고 지역 import
    for ev in stream_run(nodes, hours, dry_run):
        if ev["node"] == "__end__":
            return ev["state"], ev["seconds"]


def real_nodes(cfg: Config) -> dict[str, Callable]:
    """채워진 노드는 진짜, 아직 안 채운 노드는 stub. 섹션마다 한 줄씩 늘어난다."""
    nodes = stub_nodes()
    nodes["collect"] = partial(collect, sources=cfg.sources)
    nodes["select"] = partial(select, cfg=cfg)
    nodes["report"] = partial(report_worker, cfg=cfg)
    nodes["verify"] = partial(verify, rewrite=partial(rewrite_draft, cfg=cfg))
    nodes["publish"] = partial(publish, webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"))
    return nodes
