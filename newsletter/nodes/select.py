"""② 중요도 선별. 2단 상대평가 — 묶음 예선 → 본선. 건수는 코드가 강제한다."""
from pydantic import BaseModel

from newsletter import llm
from newsletter.config import Config
from newsletter.state import Article, Pick


class Shortlist(BaseModel):
    urls: list[str]


class FinalPick(BaseModel):
    url: str
    reason: str
    topic: str         # 관심 토픽 중 하나. 기준이 의도대로 작동했는지 보는 라벨


class Final(BaseModel):
    picks: list[FinalPick]


def _lines(arts: list[Article]) -> str:
    return "\n".join(f"{a['url']} | {a['source']} | {a['title']} | {a['summary'][:120]}" for a in arts)


def _pick_lines(picks: list[Pick]) -> list[str]:
    """고른 건마다 라벨과 이유를 한 줄씩. 선별 기준이 의도대로 작동했는지 로그로 남긴다."""
    return [f"   · [{p['topic']}] {p['source']} · {p['title'][:40]} · {p['reason']}" for p in picks]


def _system(cfg: Config) -> str:
    return (f"당신은 '{cfg.audience}'을 위한 뉴스레터 편집자입니다. "
            f"기준: {cfg.question}. 관심 토픽: {', '.join(cfg.topics)}. "
            "같은 사건을 다룬 기사는 하나만 남깁니다. 홍보성 글은 제외합니다.")


def prelim(batch: list[Article], cfg: Config, ask) -> list[Article]:
    r = ask(_system(cfg),
            f"아래 기사 중 기준에 가장 맞는 {cfg.pick_count}건의 URL만 고르세요. 한 줄에 'URL | 출처 | 제목 | 요약'.\n\n{_lines(batch)}",
            Shortlist)
    by_url = {a["url"]: a for a in batch}
    return [by_url[u] for u in r.urls if u in by_url][:cfg.pick_count]


def final(cands: list[Article], n: int, cfg: Config, ask) -> list[Pick]:
    if n <= 0 or not cands:
        return []
    r = ask(_system(cfg),
            f"아래 후보를 서로 견주어 가장 중요한 순서로 정확히 {n}건을 고르고, 각각 한 문장 이유와 "
            f"관심 토픽({', '.join(cfg.topics)}) 중 가장 가까운 하나를 topic에 쓰세요.\n\n{_lines(cands)}",
            Final)
    by_url = {a["url"]: a for a in cands}
    out: list[Pick] = []
    for p in r.picks:
        if p.url in by_url and all(o["url"] != p.url for o in out):
            out.append({**by_url[p.url], "reason": p.reason, "topic": p.topic})
    return out[:n]                                    # 부탁은 지켜지지 않을 수 있다. 자르는 건 코드가 한다


def select(state: dict, cfg: Config, ask=llm.ask_structured) -> dict:
    collected: list[Article] = state["collected"]
    tier1 = sorted([a for a in collected if a["tier"] == 1], key=lambda a: a["at"], reverse=True)
    cap = min(cfg.tier1_max, cfg.pick_count)          # 면제도 pick_count는 넘지 않는다
    exempt: list[Pick] = [{**a, "reason": "당사자 발표", "topic": "당사자 발표"} for a in tier1[:cap]]
    rest = [a for a in collected if a["url"] not in {e["url"] for e in exempt}]
    slots = cfg.pick_count - len(exempt)

    if slots <= 0:                                    # 면제만으로 정원이 찼으면 LLM 호출 없이 종료
        return {"picked": exempt,
                "log": [f"② 선별    {len(collected)} → {len(exempt)}건 · 면제로 충족 · 면제 {len(exempt)}", *_pick_lines(exempt)]}

    if len(rest) > cfg.shortlist_batch:
        batches = [rest[i:i + cfg.shortlist_batch] for i in range(0, len(rest), cfg.shortlist_batch)]
        cands = [a for b in batches for a in prelim(b, cfg, ask)]
        stage = f"예선 {len(batches)}묶음 → {len(cands)}건 → 본선"
    else:
        cands, stage = rest, "본선만"
    picked = exempt + final(cands, slots, cfg, ask)
    return {"picked": picked,
            "log": [f"② 선별    {len(collected)} → {len(picked)}건 · {stage} · 면제 {len(exempt)}", *_pick_lines(picked)]}
