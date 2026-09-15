from newsletter.config import Config
from newsletter.nodes.report import DraftOut, draft, report_worker

CFG = Config(audience="a", question="q", topics=[], pick_count=5, tone="존댓말", min_body=600,
             shortlist_batch=40, tier1_max=2, sources=[])
PICK = {"title": "t", "url": "https://x/1", "source": "s", "tier": 2, "at": "2026-09-14T00:00:00+00:00",
        "summary": "s", "reason": "r"}


def fake_ask(system, user, schema):
    assert "존댓말" in system
    return DraftOut(headline="H", summary="S1. S2. S3.", why="W")


def test_draft_returns_three_fields_and_body():
    d = draft(PICK, CFG, ask=fake_ask, extract=lambda u: "본문" * 400)
    assert d["headline"] == "H" and d["why"] == "W" and len(d["body"]) >= 600 and d["reason"] == "r"


def test_draft_returns_none_when_body_too_short():
    assert draft(PICK, CFG, ask=fake_ask, extract=lambda u: "짧음") is None


def test_worker_logs_extraction_failure_instead_of_silently_dropping():
    out = report_worker({"pick": PICK}, CFG, ask=fake_ask, extract=lambda u: "")
    assert out["drafted"] == [] and "본문 부족" in out["log"][0]


def test_worker_skips_article_when_llm_fails_instead_of_crashing():
    def broken_ask(system, user, schema):
        raise RuntimeError("LLM 호출 실패: 429")
    out = report_worker({"pick": PICK}, CFG, ask=broken_ask, extract=lambda u: "본문" * 400)
    assert out["drafted"] == [] and "취재 실패" in out["log"][0] and "429" in out["log"][0]
