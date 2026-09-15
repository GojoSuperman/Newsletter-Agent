from newsletter.nodes.verify import VerdictOut, check, verify

D = {"title": "t", "url": "https://x/1", "source": "s", "tier": 2, "at": "", "summary": "3개월 전 6000만 달러",
     "reason": "r", "headline": "H", "why": "이건 해석", "body": "three months after raised $60 million"}


def test_check_sends_headline_and_summary_but_not_why():
    seen = {}
    def ask(system, user, schema):
        seen["user"] = user
        return VerdictOut(grounded=True, reason="번역·단위 환산일 뿐")
    v = check(D, ask)
    assert v == {"url": "https://x/1", "ok": True, "reason": "번역·단위 환산일 뿐"}
    assert "3개월 전" in seen["user"] and "이건 해석" not in seen["user"]


def test_verify_keeps_only_grounded_and_logs_rejections():
    bad = {**D, "url": "https://x/2", "summary": "업계 최초"}
    def ask(system, user, schema):
        return VerdictOut(grounded="업계 최초" not in user, reason="근거 없음")
    out = verify({"drafted": [D, bad]}, ask)
    assert [d["url"] for d in out["verified"]] == ["https://x/1"]
    assert "1/2 통과" in out["log"][0] and any("근거 없음" in l for l in out["log"])


def test_verify_zero_drafts():
    out = verify({"drafted": []}, ask=lambda *a: None)
    assert out["verified"] == [] and "0/0" in out["log"][0]


def test_verify_regenerates_once_then_passes():
    bad = {**D, "url": "https://x/2", "summary": "업계 최초"}
    calls = []
    def ask(system, user, schema):
        return VerdictOut(grounded="업계 최초" not in user, reason="근거 없음")
    def rewrite(d, reason):
        calls.append(reason)
        return {**d, "summary": "고쳐 쓴 요약"}
    out = verify({"drafted": [bad]}, ask, rewrite=rewrite)
    assert calls == ["근거 없음"]
    assert [d["url"] for d in out["verified"]] == ["https://x/2"]
    assert out["verified"][0]["regenerated"] is True
    assert any("재생성" in l and "통과" in l for l in out["log"])


def test_verify_regenerates_once_then_skips():
    bad = {**D, "url": "https://x/2", "summary": "업계 최초"}
    calls = []
    def ask(system, user, schema):
        return VerdictOut(grounded=False, reason="여전히 근거 없음")
    def rewrite(d, reason):
        calls.append(reason)
        return {**d, "summary": "여전히 업계 최초"}
    out = verify({"drafted": [bad]}, ask, rewrite=rewrite)
    assert calls == ["여전히 근거 없음"]                   # 재생성은 한 번만
    assert out["verified"] == []
    assert any("재생성" in l and "탈락" in l for l in out["log"])


def test_rewrite_draft_feeds_reason_to_llm():
    from newsletter.config import Config
    from newsletter.nodes.report import DraftOut
    from newsletter.nodes.verify import rewrite_draft
    cfg = Config(audience="a", question="q", topics=[], pick_count=5, tone="", min_body=10,
                 shortlist_batch=40, tier1_max=2, sources=[])
    seen = {}
    def ask(system, user, schema):
        seen["user"] = user
        return DraftOut(headline="H2", summary="S2", why="W2")
    d = rewrite_draft(D, "업계 최초가 원문에 없음", cfg, ask)
    assert "업계 최초가 원문에 없음" in seen["user"] and D["body"] in seen["user"]
    assert d["headline"] == "H2" and d["summary"] == "S2" and d["body"] == D["body"]
