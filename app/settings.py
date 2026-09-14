"""리더 앱 설정. store/local/settings.json — 이 컴퓨터에만 있고 Git에 올라가지 않는다."""
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from newsletter import llm

WEBHOOK_RE = re.compile(r"^https://(discord\.com|discordapp\.com)/api/webhooks/\d+/[\w-]+$")
ENV_KEYS = {"openai_api_key": "OPENAI_API_KEY", "openai_model": "OPENAI_MODEL", "discord_webhook_url": "DISCORD_WEBHOOK_URL"}


@dataclass
class Settings:
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    discord_webhook_url: str = ""
    hours: int = 24


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def is_valid_webhook(url: str) -> bool:
    return bool(WEBHOOK_RE.match(url or ""))


def check_openai_key(key: str, model: str) -> None:
    """실제 검증. 키가 틀리면 openai가 예외를 낸다. 테스트에서는 부르지 않는다."""
    from openai import OpenAI
    OpenAI(api_key=key).models.retrieve(model)


def save(path: Path, updates: dict, validate_openai: Callable[[str, str], None] | None = None) -> Settings:
    s = load(path)
    for k, v in updates.items():
        if k not in ENV_KEYS and k != "hours":
            continue
        setattr(s, k, v)
    if not isinstance(s.hours, int) or not 1 <= s.hours <= 168:
        raise ValueError("hours는 1~168 사이 정수여야 합니다")
    if s.discord_webhook_url and not is_valid_webhook(s.discord_webhook_url):
        raise ValueError("Discord 웹훅 URL 형식이 아닙니다")
    if validate_openai and updates.get("openai_api_key"):
        try:
            validate_openai(s.openai_api_key, s.openai_model)
        except Exception as e:                        # noqa: BLE001
            raise ValueError(f"OpenAI 키가 유효하지 않습니다: {e!r}") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def masked(s: Settings) -> dict:
    return {
        "openai_key_tail": f"…{s.openai_api_key[-3:]}" if s.openai_api_key else "",
        "openai_model": s.openai_model,
        "webhook_registered": bool(s.discord_webhook_url),
        "hours": s.hours,
    }


def apply_env(s: Settings) -> None:
    """실행 직전 환경 변수에 반영한다. 키가 바뀌었을 수 있으니 OpenAI 클라이언트 캐시를 비운다."""
    for attr, env in ENV_KEYS.items():
        v = getattr(s, attr)
        if v:
            os.environ[env] = v
        else:
            os.environ.pop(env, None)
    llm.get_client.cache_clear()
