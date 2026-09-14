from newsletter.config import Config
from newsletter.nodes.select import Final, FinalPick, Shortlist, select

CFG = Config(audience="a", question="q", topics=["t"], pick_count=3, tone="", min_body=600,
             shortlist_batch=4, tier1_max=1, sources=[])


def art(i, tier=2):
    return {"title": f"t{i}", "url": f"https://x/{i}", "source": "s", "tier": tier,
            "at": f"2026-09-14T0{i % 10}:00:00+00:00", "summary": f"s{i}"}


def fake_ask_factory(calls):
    def ask(system, user, schema):
        calls.append(schema.__name__)
        urls = [l.split()[0] for l in user.splitlines() if l.startswith("https://")]
        if schema is Shortlist:
            return Shortlist(urls=urls[:3] + ["https://unknown"])
        return Final(picks=[FinalPick(url=u, reason="이유") for u in urls[:5]])   # 일부러 초과 반환
    return ask


def test_select_prelim_batches_then_final_and_enforces_count():
    calls = []
    state = {"collected": [art(i) for i in range(9)]}
    out = select(state, CFG, ask=fake_ask_factory(calls))
    assert calls == ["Shortlist", "Shortlist", "Shortlist", "Final"]    # 9건 / 4 = 예선 3묶음
    assert len(out["picked"]) == 3
    assert all(p["reason"] == "이유" for p in out["picked"])
    assert "9 → 3건" in out["log"][0]


def test_tier1_bypasses_competition_with_cap():
    calls = []
    state = {"collected": [art(1, tier=1), art(2, tier=1), art(3), art(4)]}
    out = select(state, CFG, ask=fake_ask_factory(calls))
    exempt = [p for p in out["picked"] if p["reason"] == "당사자 발표"]
    assert len(exempt) == 1 and exempt[0]["tier"] == 1
    assert len(out["picked"]) == 3


def test_small_input_skips_prelim():
    calls = []
    out = select({"collected": [art(1), art(2)]}, CFG, ask=fake_ask_factory(calls))
    assert calls == ["Final"] and len(out["picked"]) == 2
