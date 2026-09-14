"""③ 요약(취재). 원문을 뽑아 headline / summary / why 세 칸으로 받는다. 기사마다 워커 하나."""
from collections.abc import Callable

import trafilatura
from langgraph.types import Send
from pydantic import BaseModel

from newsletter import llm
from newsletter.config import Config
from newsletter.state import Draft, Pick


class DraftOut(BaseModel):
    headline: str      # 카드 제목. 원문과 대조 가능
    summary: str       # 세 문장. 원문과 대조 가능
    why: str           # 독자에게 왜 중요한가. 해석이라 대조 대상 아님


def extract_body(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    return (trafilatura.extract(downloaded) if downloaded else "") or ""


def draft(pick: Pick, cfg: Config, ask=llm.ask_structured, extract: Callable[[str], str] = extract_body) -> Draft | None:
    body = extract(pick["url"])
    if len(body) < cfg.min_body:
        return None                                    # 재료가 없으면 지어내게 된다. 쓰지 않는다
    system = (f"당신은 '{cfg.audience}'을 위한 뉴스레터 기자입니다. 톤: {cfg.tone}. "
              "headline은 한 줄, summary는 원문 사실만으로 정확히 세 문장, "
              f"why는 '{cfg.question}' 관점에서 독자에게 왜 중요한지 한 문장. 한국어로 씁니다.")
    r = ask(system, f"제목: {pick['title']}\n출처: {pick['source']}\n\n원문:\n{body[:6000]}", DraftOut)
    return {**pick, "headline": r.headline, "summary": r.summary, "why": r.why, "body": body}


def report_worker(state: dict, cfg: Config, ask=llm.ask_structured, extract: Callable[[str], str] = extract_body) -> dict:
    pick: Pick = state["pick"]
    d = draft(pick, cfg, ask, extract)
    if d is None:
        return {"drafted": [], "log": [f"③ 취재    본문 부족 → 제외 · {pick['source']} · {pick['title'][:40]}"]}
    return {"drafted": [d], "log": [f"③ 취재    완료 · {pick['source']} · {d['headline'][:40]}"]}


def fan_report(state: dict) -> list[Send] | str:
    picks = state["picked"]
    if not picks:
        return "verify"                                # 고른 게 없으면 취재를 건너뛴다
    return [Send("report", {"pick": p}) for p in picks]
