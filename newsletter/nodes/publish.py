"""⑤ 발행. 되돌릴 수 없는 단계라 LLM이 없고, dry_run이 먼저다."""
from datetime import datetime, timedelta, timezone

import requests

from newsletter.state import Draft

KST = timezone(timedelta(hours=9))


def render_discord(drafts: list[Draft], title: str) -> dict:
    embeds = [{
        "title": d["headline"][:256],
        "url": d["url"],
        "description": f"{d['summary']}\n\n**왜 중요한가** · {d['why']}"[:4096],
        "footer": {"text": d["source"]},
    } for d in drafts[:10]]                          # Discord 임베드 상한 10
    return {"content": f"**{title}** · {len(drafts)}건", "embeds": embeds}


def render_text(drafts: list[Draft]) -> str:
    return "\n".join(f"- [{d['source']}] {d['headline']}\n    {d['summary']}\n    → {d['why']}" for d in drafts)


def send_discord(drafts: list[Draft], webhook_url: str, title: str | None = None, post=requests.post) -> int:
    """검수 통과분을 Discord 웹훅으로 보낸다. 0건이면 보내지 않고 0. 실패는 예외."""
    if not drafts:
        return 0
    title = title or f"AI 뉴스레터 {datetime.now(KST).strftime('%Y-%m-%d')}"
    r = post(webhook_url, json=render_discord(drafts, title), timeout=20)
    r.raise_for_status()
    return len(drafts)


def publish(state: dict, post=requests.post, webhook_url: str | None = None) -> dict:
    drafts: list[Draft] = state["verified"]
    n = len(drafts)
    if n == 0:
        return {"log": ["⑤ 발행    0건 · 보낼 것이 없어 건너뜀"]}
    if state["dry_run"]:
        return {"log": [f"⑤ 발행    dry_run · {n}건 (보내지 않음)", *render_text(drafts).splitlines()]}
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL이 없습니다")
    n = send_discord(drafts, webhook_url, post=post)
    return {"log": [f"⑤ 발행    Discord · {n}건"]}
