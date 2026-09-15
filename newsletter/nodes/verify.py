"""④ 검수. 요약과 원문을 함께 주고 근거가 있는지 묻는다. 숫자 문자열 대조는 번역·단위 환산을 오탐해서 쓰지 않는다.

탈락하면 탈락 사유를 들려주고 한 번 다시 쓰게 한 뒤 재검수한다. 그래도 탈락이면 건너뛴다(스킵).
"""
from collections.abc import Callable

from pydantic import BaseModel

from newsletter import llm
from newsletter.config import Config
from newsletter.nodes.report import DraftOut
from newsletter.state import Draft, Verdict

SYSTEM = ("당신은 팩트체커입니다. 아래 headline과 summary의 모든 사실(숫자·이름·사건)이 원문에 근거하는지 판정합니다. "
          "번역이나 단위 환산(three months→3개월, $60 million→6000만 달러)은 근거 있음으로 봅니다. "
          "원문에 없는 주장('업계 최초' 등)이 하나라도 있으면 grounded=false. reason은 한국어 한 문장.")

Rewrite = Callable[[Draft, str], Draft]


class VerdictOut(BaseModel):
    grounded: bool
    reason: str


def check(d: Draft, ask=llm.ask_structured) -> Verdict:
    user = f"headline: {d['headline']}\nsummary: {d['summary']}\n\n원문:\n{d['body'][:6000]}"
    r = ask(SYSTEM, user, VerdictOut)
    return {"url": d["url"], "ok": bool(r.grounded), "reason": r.reason}


def rewrite_draft(d: Draft, reason: str, cfg: Config, ask=llm.ask_structured) -> Draft:
    """검수 탈락 사유를 들려주고 같은 원문으로 headline·summary·why를 다시 쓴다."""
    system = (f"당신은 '{cfg.audience}'을 위한 뉴스레터 기자입니다. 톤: {cfg.tone}. "
              "앞서 쓴 요약이 팩트체크에서 탈락했습니다. 원문에 없는 내용은 절대 넣지 말고 다시 씁니다. "
              "headline은 한 줄, summary는 원문 사실만으로 정확히 세 문장, "
              f"why는 '{cfg.question}' 관점에서 독자에게 왜 중요한지 한 문장. 한국어로 씁니다.")
    user = (f"탈락 사유: {reason}\n\n이전 headline: {d['headline']}\n이전 summary: {d['summary']}\n\n"
            f"제목: {d['title']}\n출처: {d['source']}\n\n원문:\n{d['body'][:6000]}")
    r = ask(system, user, DraftOut)
    return {**d, "headline": r.headline, "summary": r.summary, "why": r.why, "regenerated": True}


def verify(state: dict, ask=llm.ask_structured, rewrite: Rewrite | None = None) -> dict:
    drafted: list[Draft] = state["drafted"]
    verified: list[Draft] = []
    log: list[str] = []
    for d in drafted:
        try:
            v = check(d, ask)
        except Exception as e:                                     # noqa: BLE001 — 검수 못 한 글은 내보내지 않고 건너뛴다. 조용히는 아니다
            log.append(f"   ✗ 검수 실패 → 스킵 · {d['source']} · {d['headline'][:30]} · {e!r}")
            continue
        if v["ok"]:
            verified.append(d)
            continue
        if rewrite is None:                                        # 재생성 수단이 없으면 곧장 스킵
            log.append(f"   ✗ 탈락 · {d['source']} · {d['headline'][:30]} · {v['reason']}")
            continue
        try:
            d2 = {**rewrite(d, v["reason"]), "regenerated": True}  # 딱 한 번만 다시 쓴다
            v2 = check(d2, ask)
        except Exception as e:                                     # noqa: BLE001
            log.append(f"   ↻ 재생성 실패 → 스킵 · {d['source']} · {d['headline'][:30]} · {e!r}")
            continue
        if v2["ok"]:
            verified.append(d2)
            log.append(f"   ↻ 재생성 후 통과 · {d['source']} · {d2['headline'][:30]} · 1차 사유: {v['reason']}")
        else:
            log.append(f"   ↻ 재생성 후 탈락 · {d['source']} · {d2['headline'][:30]} · {v2['reason']}")
    return {"verified": verified, "log": [f"④ 검수    {len(verified)}/{len(drafted)} 통과", *log]}
