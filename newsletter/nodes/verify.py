"""④ 검수. 요약과 원문을 함께 주고 근거가 있는지 묻는다. 숫자 문자열 대조는 번역·단위 환산을 오탐해서 쓰지 않는다."""
from pydantic import BaseModel

from newsletter import llm
from newsletter.state import Draft, Verdict

SYSTEM = ("당신은 팩트체커입니다. 아래 headline과 summary의 모든 사실(숫자·이름·사건)이 원문에 근거하는지 판정합니다. "
          "번역이나 단위 환산(three months→3개월, $60 million→6000만 달러)은 근거 있음으로 봅니다. "
          "원문에 없는 주장('업계 최초' 등)이 하나라도 있으면 grounded=false. reason은 한국어 한 문장.")


class VerdictOut(BaseModel):
    grounded: bool
    reason: str


def check(d: Draft, ask=llm.ask_structured) -> Verdict:
    user = f"headline: {d['headline']}\nsummary: {d['summary']}\n\n원문:\n{d['body'][:6000]}"
    r = ask(SYSTEM, user, VerdictOut)
    return {"url": d["url"], "ok": bool(r.grounded), "reason": r.reason}


def verify(state: dict, ask=llm.ask_structured) -> dict:
    drafted: list[Draft] = state["drafted"]
    verified: list[Draft] = []
    log: list[str] = []
    for d in drafted:
        v = check(d, ask)
        if v["ok"]:
            verified.append(d)
        else:
            log.append(f"   ✗ 탈락 · {d['source']} · {d['headline'][:30]} · {v['reason']}")
    return {"verified": verified, "log": [f"④ 검수    {len(verified)}/{len(drafted)} 통과", *log]}
