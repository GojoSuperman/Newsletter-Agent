import operator
from typing import Annotated, TypedDict


class Article(TypedDict):
    title: str
    url: str
    source: str
    tier: int          # 1 = 당사자 발표, 2 = 매체
    at: str            # ISO 8601 UTC
    summary: str       # RSS가 준 짧은 요약


class Pick(Article):
    reason: str        # 본선에서 고른 이유


class Draft(Pick):
    headline: str
    summary: str       # 3문장 요약 (원문과 대조 가능)
    why: str           # 왜 중요한가 (해석, 대조 대상 아님)
    body: str          # 추출한 원문


class Verdict(TypedDict):
    url: str
    ok: bool
    reason: str


class Brief(TypedDict):
    hours: int
    dry_run: bool
    collected: list[Article]                     # ① 수집
    picked: list[Pick]                           # ② 선별
    drafted: Annotated[list[Draft], operator.add]  # ③ 취재 — 워커들이 나눠 채운다
    verified: list[Draft]                        # ④ 검수 통과분
    log: Annotated[list[str], operator.add]
