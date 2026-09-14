import json
import os

import pytest

from app.settings import Settings, apply_env, is_valid_webhook, load, masked, save


def test_load_missing_returns_defaults(tmp_path):
    s = load(tmp_path / "settings.json")
    assert s == Settings() and s.openai_model == "gpt-4o-mini" and s.hours == 24


def test_save_partial_update_and_clear(tmp_path):
    p = tmp_path / "settings.json"
    save(p, {"openai_api_key": "sk-test-1234567Qx", "hours": 48})
    s = load(p)
    assert s.openai_api_key == "sk-test-1234567Qx" and s.hours == 48 and s.openai_model == "gpt-4o-mini"
    save(p, {"openai_api_key": ""})
    assert load(p).openai_api_key == "" and load(p).hours == 48
    assert json.loads(p.read_text())["hours"] == 48


def test_masked_never_exposes_key():
    m = masked(Settings(openai_api_key="sk-test-1234567Qx", discord_webhook_url="https://discord.com/api/webhooks/1/abc"))
    assert m == {"openai_key_tail": "…7Qx", "openai_model": "gpt-4o-mini", "webhook_registered": True, "hours": 24}
    assert "sk-test" not in json.dumps(m)
    assert masked(Settings())["openai_key_tail"] == "" and masked(Settings())["webhook_registered"] is False


def test_webhook_validation(tmp_path):
    assert is_valid_webhook("https://discord.com/api/webhooks/123/AbC_d-e")
    assert not is_valid_webhook("https://example.com/hook")
    with pytest.raises(ValueError, match="웹훅"):
        save(tmp_path / "s.json", {"discord_webhook_url": "https://example.com/hook"})


def test_hours_range(tmp_path):
    with pytest.raises(ValueError, match="hours"):
        save(tmp_path / "s.json", {"hours": 0})


def test_openai_validator_blocks_bad_key(tmp_path):
    p = tmp_path / "s.json"
    def bad(key, model): raise RuntimeError("401")
    with pytest.raises(ValueError, match="OpenAI"):
        save(p, {"openai_api_key": "sk-bad"}, validate_openai=bad)
    assert not p.exists()
    seen = {}
    save(p, {"openai_api_key": "sk-good"}, validate_openai=lambda k, m: seen.update(k=k, m=m))
    assert seen == {"k": "sk-good", "m": "gpt-4o-mini"}


def test_apply_env_sets_and_clears(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    apply_env(Settings(openai_api_key="sk-x", discord_webhook_url="https://discord.com/api/webhooks/1/a"))
    assert os.environ["OPENAI_API_KEY"] == "sk-x" and os.environ["DISCORD_WEBHOOK_URL"].endswith("/1/a")
    apply_env(Settings())
    assert "OPENAI_API_KEY" not in os.environ and "DISCORD_WEBHOOK_URL" not in os.environ
