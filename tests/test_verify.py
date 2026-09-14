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
