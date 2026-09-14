"""audience.yaml 로더. 오타는 런타임이 아니라 시작 시점에 잡는다."""
from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED = {
    "audience": str, "question": str, "topics": list, "pick_count": int, "tone": str,
    "min_body": int, "shortlist_batch": int, "tier1_max": int, "sources": list,
}
KINDS = ("rss", "hn")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    tier: int
    kind: str


@dataclass(frozen=True)
class Config:
    audience: str
    question: str
    topics: list[str]
    pick_count: int
    tone: str
    min_body: int
    shortlist_batch: int
    tier1_max: int
    sources: list[Source]


def load_config(path: str | Path = "audience.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for key, typ in REQUIRED.items():
        if key not in raw:
            raise ConfigError(f"audience.yaml에 '{key}'가 없습니다")
        if not isinstance(raw[key], typ):
            raise ConfigError(f"'{key}'는 {typ.__name__}이어야 합니다")
    sources = []
    for i, s in enumerate(raw["sources"]):
        for k in ("name", "url", "tier", "kind"):
            if k not in s:
                raise ConfigError(f"sources[{i}]에 '{k}'가 없습니다")
        if s["kind"] not in KINDS:
            raise ConfigError(f"sources[{i}].kind는 {KINDS} 중 하나여야 합니다: {s['kind']}")
        sources.append(Source(str(s["name"]), str(s["url"]), int(s["tier"]), s["kind"]))
    return Config(**{k: raw[k] for k in REQUIRED if k != "sources"}, sources=sources)
