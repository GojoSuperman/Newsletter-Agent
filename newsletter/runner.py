"""그래프를 stream()으로 돌리며 노드 단위 이벤트를 낸다. 대시보드(web/)와 리더 앱(app/)이 같이 쓴다."""
import time
from collections.abc import Callable, Iterator

from newsletter.graph import build, initial_state, merge_delta


def stream_run(nodes: dict[str, Callable], hours: int, dry_run: bool) -> Iterator[dict]:
    state = initial_state(hours, dry_run)
    graph = build(nodes).compile()
    seconds: dict[str, float] = {}
    t = time.perf_counter()
    for update in graph.stream(state, stream_mode="updates"):
        for node, delta in update.items():
            now = time.perf_counter()
            seconds[node] = seconds.get(node, 0.0) + (now - t)
            t = now
            yield {"node": node, "update": delta}
            state = merge_delta(state, delta)
    yield {"node": "__end__", "state": state, "seconds": seconds}
