import pytest

from newsletter.config import Config, ConfigError, load_config

GOOD = """
audience: 국내 AI 개발팀
question: 이번 주 우리가 일하는 방식이 바뀔 만한가
topics: [모델·API, 인프라·비용]
pick_count: 5
tone: 간결한 존댓말
min_body: 600
shortlist_batch: 40
tier1_max: 2
sources:
  - {name: OpenAI, url: https://openai.com/blog/rss.xml, tier: 1, kind: rss}
  - {name: HN, url: "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI", tier: 2, kind: hn}
"""


def test_load_good_config(tmp_path):
    f = tmp_path / "a.yaml"; f.write_text(GOOD)
    cfg = load_config(f)
    assert isinstance(cfg, Config)
    assert cfg.pick_count == 5 and cfg.sources[0].tier == 1 and cfg.sources[1].kind == "hn"


def test_missing_key_raises(tmp_path):
    f = tmp_path / "a.yaml"; f.write_text(GOOD.replace("pick_count: 5\n", ""))
    with pytest.raises(ConfigError, match="pick_count"):
        load_config(f)


def test_bad_kind_raises(tmp_path):
    f = tmp_path / "a.yaml"; f.write_text(GOOD.replace("kind: hn", "kind: scrape"))
    with pytest.raises(ConfigError, match="kind"):
        load_config(f)


def test_repo_audience_yaml_loads():
    cfg = load_config("audience.yaml")
    assert cfg.pick_count == 5 and len(cfg.sources) >= 5
