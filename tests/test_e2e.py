"""실노드 다섯 개를 가짜 의존성으로 이어 붙여 수집→발행을 한 번에 돈다. 네트워크·OpenAI·Discord 없음."""
from datetime import datetime, timezone
from functools import partial

from newsletter.config import Config, Source
from newsletter.graph import run
from newsletter.metrics import summarize
from newsletter.nodes.collect import collect
from newsletter.nodes.publish import publish
from newsletter.nodes.report import DraftOut, report_worker
from newsletter.nodes.select import Final, FinalPick, Shortlist, select
from newsletter.nodes.verify import VerdictOut, rewrite_draft, verify
from tests.test_collect import FakeResp, rss

NOW = datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc)
CFG = Config(audience="일반 독자", question="대화 소재가 되는가", topics=["우주", "생명"], pick_count=2, tone="존댓말",
             min_body=100, shortlist_batch=40, tier1_max=1,
             sources=[Source("ESA", "https://esa/rss", 1, "rss"), Source("SciDaily", "https://sd/rss", 2, "rss"),
                      Source("Dead", "https://dead/rss", 2, "rss")])


def http_get(url, headers, timeout):
    if url == "https://esa/rss":
        return FakeResp(rss([("ESA 발표", "https://esa/1", NOW)]))
    if url == "https://sd/rss":
        return FakeResp(rss([("좋은 기사", "https://sd/good", NOW), ("환각 기사", "https://sd/halu", NOW)]))
    return FakeResp(status=503)                                    # 죽은 소스


def ask(system, user, schema):
    if schema is Shortlist:
        return Shortlist(urls=[])
    if schema is Final:
        return Final(picks=[FinalPick(url="https://sd/good", reason="이유", topic="생명"),
                            FinalPick(url="https://sd/halu", reason="이유", topic="생명")])
    if schema is DraftOut:
        bad = "환각" in user and "탈락 사유" not in user
        return DraftOut(headline="H", summary="업계 최초" if bad else "원문 사실", why="W")
    if schema is VerdictOut:
        return VerdictOut(grounded="업계 최초" not in user, reason="원문에 없는 주장")
    raise AssertionError(schema)


def test_end_to_end_collect_to_publish_with_fakes():
    posted = []
    class R:
        def raise_for_status(self): pass
    nodes = {
        "collect": partial(collect, sources=CFG.sources, http_get=http_get, now=NOW),
        "select": partial(select, cfg=CFG, ask=ask),
        "report": partial(report_worker, cfg=CFG, ask=ask, extract=lambda u: "본문 " * 100),
        "verify": partial(verify, ask=ask, rewrite=partial(rewrite_draft, cfg=CFG, ask=ask)),
        "publish": partial(publish, post=lambda url, json, timeout: posted.append(json) or R(), webhook_url="https://hook"),
    }
    state = run(nodes, hours=24, dry_run=False)

    assert len(state["collected"]) == 3 and "실패 Dead" in state["log"][0]          # ① 죽은 소스 격리
    assert [p["url"] for p in state["picked"]] == ["https://esa/1", "https://sd/good"]  # ② 면제 1 + 본선 1 = 정확히 2
    assert all("topic" in p for p in state["picked"])
    assert len(state["drafted"]) == 2                                              # ③ 기사마다 워커
    assert [d["url"] for d in state["verified"]] == ["https://esa/1", "https://sd/good"]  # ④ 통과분만
    assert len(posted) == 1 and len(posted[0]["embeds"]) == 2                      # ⑤ 웹훅 1회, 카드 2장
    m = summarize(state, "r", {})
    assert (m["collected"], m["picked"], m["verified"], m["published"]) == (3, 2, 2, 2)


def test_end_to_end_regeneration_path():
    """환각 기사가 선별되면 검수 탈락 → 재생성 → 재검수 통과까지 한 번에 돈다."""
    cfg = Config(**{**CFG.__dict__, "tier1_max": 0})
    posted = []
    class R:
        def raise_for_status(self): pass
    nodes = {
        "collect": partial(collect, sources=cfg.sources, http_get=http_get, now=NOW),
        "select": partial(select, cfg=cfg, ask=ask),
        "report": partial(report_worker, cfg=cfg, ask=ask, extract=lambda u: "본문 " * 100),
        "verify": partial(verify, ask=ask, rewrite=partial(rewrite_draft, cfg=cfg, ask=ask)),
        "publish": partial(publish, post=lambda url, json, timeout: posted.append(json) or R(), webhook_url="https://hook"),
    }
    state = run(nodes, hours=24, dry_run=False)
    assert {d["url"] for d in state["verified"]} == {"https://sd/good", "https://sd/halu"}
    halu = next(d for d in state["verified"] if d["url"] == "https://sd/halu")
    assert halu["regenerated"] is True and halu["summary"] == "원문 사실"
    assert any("재생성 후 통과" in l for l in state["log"])
    assert summarize(state, "r", {})["regen_passed"] == 1
