# 뉴스레터 리더 앱 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 파이프라인(`newsletter/`)을 재사용하는 로컬 전용 뉴스 리더 웹앱을 `app/`에 새로 만든다. 버튼 하나로 오늘 치를 만들고, 잡지처럼 읽고, 선택적으로 Discord로 보낸다. 키는 설정 화면에서 입력한다.

**Architecture:** `app/server.py`(FastAPI, 포트 8100)가 `newsletter/runner.py`(신규, SSE 실행 생성기 — 기존 `web/app.py`와 공유)를 통해 파이프라인을 항상 dry_run으로 돌리고 `store/local/runs/`에 저장한다. 발송은 별도 엔드포인트가 `publish.send_discord`로 수행하고 State에 `sent_at`을 기록한다. 설정은 `app/settings.py`가 `store/local/settings.json`을 읽고 쓰며 실행 직전 `os.environ`에 반영한다. 프론트는 프레임워크 없는 SPA(`index.html` + `app.js` + `style.css`): 3열 리더, 실행 오버레이, 설정 패널.

**Tech Stack:** Python 3.14, uv, FastAPI, langgraph, openai, pytest, 순수 HTML/JS/CSS.

**Spec:** `docs/superpowers/specs/2026-09-14-reader-app-design.md`

## Global Constraints

- `uv run pytest`로 테스트. 테스트는 네트워크·OpenAI·Discord를 절대 호출하지 않는다.
- 기존 대시보드(`web/`)의 동작과 기존 테스트 66개는 그대로 통과해야 한다. `web/app.py`는 `newsletter/runner.py`를 쓰도록 리팩터링만 하고 API 계약은 바꾸지 않는다.
- 설정 파일은 `store/local/settings.json`. `store/*`가 gitignore라 커밋되지 않는다. API 응답에 키 원문을 절대 넣지 않는다(마지막 4자만).
- 리더 앱의 실행은 항상 `dry_run=True`. Discord 발송은 `POST /api/issues/{run_id}/send`로만.
- SSE 계약은 기존과 동일: `data: {"node","update"}` … `{"node":"__end__","state"}` / `{"node":"__error__","error"}`.
- 화면의 모든 동적 텍스트는 `esc()`로 이스케이프. `<a href>`는 `^https?://`일 때만.
- 코드·식별자 영어, 주석·로그·UI 텍스트 한국어. 커밋 메시지 끝에:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017h4uY6imjmtQj5NonVo8TY
  ```

---

## File Structure

| 파일 | 책임 |
|---|---|
| `newsletter/runner.py` | `stream_run(nodes, hours, dry_run) -> Iterator[dict]`: 노드마다 `{"node","update"}` yield, 마지막에 `{"node":"__end__","state","seconds"}`. 두 서버가 공유 |
| `newsletter/nodes/publish.py` | (추가) `send_discord(drafts, webhook_url, title=None, post=requests.post) -> int` |
| `app/__init__.py` | 빈 파일 |
| `app/settings.py` | `Settings` dataclass, `load(path)`, `save(path, updates, validate_openai)`, `masked(s)`, `apply_env(s)`, `is_valid_webhook(url)` |
| `app/server.py` | FastAPI 앱: `/`, `/api/settings`, `/api/issues`, `/api/issues/{id}`, `/api/run`, `/api/run/{id}/events`, `/api/issues/{id}/send` |
| `app/static/index.html` | 레이아웃 뼈대(헤더·사이드바·본문·오버레이·설정 패널) |
| `app/static/app.js` | 상태 객체 → 렌더 함수들. fetch/SSE |
| `app/static/style.css` | 잡지형 리더 스타일 |
| `web/app.py` | (수정) SSE 생성기 본문을 `runner.stream_run`으로 교체 |
| `.github/workflows/daily.yml` | (수정) `schedule:` 제거 |
| `tests/test_runner.py`, `tests/test_app_settings.py`, `tests/test_app_api.py` | 태스크별 테스트 |

---

### Task 1: 공유 실행 생성기 `newsletter/runner.py` + `web/app.py` 리팩터링

**Files:**
- Create: `newsletter/runner.py`
- Modify: `web/app.py` (SSE 생성기 내부)
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces: `runner.stream_run(nodes: dict[str, Callable], hours: int, dry_run: bool) -> Iterator[dict]`. 노드 이벤트 `{"node": str, "update": dict}`; 마지막 `{"node": "__end__", "state": Brief, "seconds": dict[str, float]}`. 예외는 잡지 않고 올린다(호출자가 `__error__`로 변환).

- [ ] **Step 1: 실패하는 테스트**

`tests/test_runner.py`:
```python
from newsletter.graph import stub_nodes
from newsletter.runner import stream_run


def test_stream_run_yields_node_events_then_end():
    events = list(stream_run(stub_nodes(), hours=24, dry_run=True))
    assert [e["node"] for e in events] == ["collect", "select", "verify", "publish", "__end__"]
    end = events[-1]
    assert len(end["state"]["log"]) == 4 and end["state"]["dry_run"] is True
    assert set(end["seconds"]) == {"collect", "select", "verify", "publish"}
    assert all(v >= 0 for v in end["seconds"].values())


def test_stream_run_merges_reducer_keys():
    nodes = stub_nodes()
    nodes["select"] = lambda s: {"picked": [{"url": "a", "title": "a"}, {"url": "b", "title": "b"}], "log": ["② 2건"]}
    nodes["report"] = lambda s: {"drafted": [{"url": s["pick"]["url"]}], "log": [f"③ {s['pick']['url']}"]}
    end = list(stream_run(nodes, 24, True))[-1]
    assert sorted(d["url"] for d in end["state"]["drafted"]) == ["a", "b"]
    assert end["seconds"]["report"] >= 0
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_runner.py -q` → ModuleNotFoundError

- [ ] **Step 3: runner.py 작성**

```python
"""그래프를 stream()으로 돌리며 노드 단위 이벤트를 낸다. 대시보드(web/)와 리더 앱(app/)이 같이 쓴다."""
import time
from collections.abc import Callable, Iterator

from newsletter.graph import build, initial_state, merge_delta


def stream_run(nodes: dict[str, Callable], hours: int, dry_run: bool) -> Iterator[dict]:
    state = initial_state(hours, dry_run)
    graph = build(nodes).compile()
    seconds: dict[str, float] = {}
    t = time.perf_counter()
    for update in graph.stream(state, stream_mode="updates"):
        for node, delta in update.items():
            now = time.perf_counter()
            seconds[node] = seconds.get(node, 0.0) + (now - t)
            t = now
            yield {"node": node, "update": delta}
            state = merge_delta(state, delta)
    yield {"node": "__end__", "state": state, "seconds": seconds}
```

- [ ] **Step 4: web/app.py의 gen()을 runner로 교체**

`run_events`의 `gen()` 내부(try 블록)를 다음으로 바꾼다. `build`, `initial_state`, `merge_delta` import는 더 이상 안 쓰면 제거하고 `from newsletter.runner import stream_run`을 추가한다.
```python
        try:
            cfg = _pending[run_id]
            state = None
            for ev in stream_run(get_nodes(), cfg["hours"], cfg["dry_run"]):
                if ev["node"] == "__end__":
                    state, seconds = ev["state"], ev["seconds"]
                    break
                yield _sse(ev)
            state["run_id"] = run_id
            save_run(STORE_DIR, LOCAL, run_id, state)
            append_metrics(summarize(state, run_id, seconds), metrics_path(STORE_DIR, LOCAL))
            yield _sse({"node": "__end__", "state": state})
```

- [ ] **Step 5: 전체 테스트** — `uv run pytest -q` → 기존 66 + 2 통과, 경고 없음.

- [ ] **Step 6: Commit** — `git add newsletter/runner.py web/app.py tests/test_runner.py && git commit -m "refactor: SSE 실행 생성기를 newsletter/runner.py로 분리"`

---

### Task 2: Discord 발송 함수 + 설정 모듈

**Files:**
- Modify: `newsletter/nodes/publish.py` (`send_discord` 추가, `publish`가 이를 사용)
- Create: `app/__init__.py`, `app/settings.py`
- Test: `tests/test_publish.py`(추가), `tests/test_app_settings.py`

**Interfaces:**
- `publish.send_discord(drafts, webhook_url: str, title: str | None = None, post=requests.post) -> int` — 보낸 건수 반환, 0건이면 post 없이 0, 실패는 `raise_for_status`.
- `settings.Settings` dataclass: `openai_api_key: str = ""`, `openai_model: str = "gpt-4o-mini"`, `discord_webhook_url: str = ""`, `hours: int = 24`
- `settings.load(path: Path) -> Settings` (없으면 기본값)
- `settings.save(path, updates: dict, validate_openai: Callable[[str, str], None] | None = None) -> Settings` — updates에 있는 키만 갱신, 값이 `""`면 비움, `hours`는 1~168 정수, 웹훅은 `is_valid_webhook` 통과해야 함, `openai_api_key`가 새로 오면 `validate_openai(key, model)` 호출(예외면 저장 안 함)
- `settings.masked(s) -> dict` = `{"openai_key_tail": "…7Qx" | "", "openai_model", "webhook_registered": bool, "hours"}`
- `settings.apply_env(s) -> None` — `OPENAI_API_KEY`·`OPENAI_MODEL`·`DISCORD_WEBHOOK_URL`을 os.environ에 설정(빈 값이면 제거)하고 `llm.get_client.cache_clear()`
- `settings.is_valid_webhook(url) -> bool` — `^https://(discord\.com|discordapp\.com)/api/webhooks/\d+/[\w-]+$`
- `settings.check_openai_key(key, model)` — 실제 검증기: `OpenAI(api_key=key).models.retrieve(model)`. 테스트에서는 호출하지 않음.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_publish.py`에 추가:
```python
from newsletter.nodes.publish import send_discord


def test_send_discord_posts_once_and_returns_count():
    calls = []
    class R:
        def raise_for_status(self): pass
    n = send_discord([D, {**D, "url": "https://x/2"}], "https://hook", post=lambda url, json, timeout: calls.append(json) or R())
    assert n == 2 and len(calls) == 1 and len(calls[0]["embeds"]) == 2


def test_send_discord_zero_drafts_does_not_post():
    calls = []
    assert send_discord([], "https://hook", post=lambda *a, **k: calls.append(1)) == 0 and calls == []
```

`tests/test_app_settings.py`:
```python
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
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_publish.py tests/test_app_settings.py -q`

- [ ] **Step 3: publish.py에 send_discord 추가**

```python
def send_discord(drafts: list[Draft], webhook_url: str, title: str | None = None, post=requests.post) -> int:
    """검수 통과분을 Discord 웹훅으로 보낸다. 0건이면 보내지 않고 0. 실패는 예외."""
    if not drafts:
        return 0
    title = title or f"AI 뉴스레터 {datetime.now(KST).strftime('%Y-%m-%d')}"
    r = post(webhook_url, json=render_discord(drafts, title), timeout=20)
    r.raise_for_status()
    return len(drafts)
```
그리고 `publish()`의 마지막 세 줄(title/post/raise_for_status)을 `n = send_discord(drafts, webhook_url, post=post)`로 바꾼다. 기존 test_publish 5개는 그대로 통과해야 한다.

- [ ] **Step 4: app/settings.py 작성**

```python
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
```

- [ ] **Step 5: 테스트 통과** — `uv run pytest -q` → 전부 통과.

- [ ] **Step 6: Commit** — `git add app newsletter/nodes/publish.py tests && git commit -m "feat: Discord 발송 함수와 리더 앱 설정 모듈"`

---

### Task 3: 리더 앱 서버 `app/server.py`

**Files:**
- Create: `app/server.py`
- Test: `tests/test_app_api.py`

**Interfaces:**
- 모듈 상수 `STORE_DIR = Path("store")`, `SETTINGS_PATH = STORE_DIR / "local" / "settings.json"`, `STATIC = Path(__file__).parent / "static"`, `LOCAL = "local"`, `STALE_SECONDS = 60`.
- `get_nodes()` → `real_nodes(load_config())` (테스트가 stub으로 교체), `validate_openai` 모듈 변수 = `settings.check_openai_key` (테스트가 교체), `post_fn` 모듈 변수 = `requests.post` (테스트가 교체).
- `GET /api/settings` → `masked(load(SETTINGS_PATH))`
- `PUT /api/settings` body `{openai_api_key?, openai_model?, discord_webhook_url?, hours?}` → 저장 후 masked. `ValueError`는 400 `{"detail": msg}`.
- `GET /api/issues` → `[{run_id, date, origin, published, collected, sent_at, dry_run}]` — `store/runs/*.json`(github)과 `store/local/runs/*.json`(local)을 읽어 run_id 내림차순. `date`는 run_id 앞 8자를 `YYYY-MM-DD`로. `published = len(verified)`, `collected = len(collected)`, `sent_at = state.get("sent_at")`.
- `GET /api/issues/{run_id}` → `store.load_run` (없으면 404).
- `POST /api/run` body `{hours?}` → 설정에 OpenAI 키 없으면 400 "OpenAI 키를 설정하세요". 아니면 `apply_env` 후 `_pending` 등록(기존 대시보드와 같은 stale 정리·409 규칙). 항상 `dry_run=True`. `hours` 기본값은 설정의 hours.
- `GET /api/run/{run_id}/events` → `runner.stream_run` 기반 SSE. 끝나면 `save_run(STORE_DIR, LOCAL, ...)`, `append_metrics(... metrics_path(STORE_DIR, LOCAL))`.
- `POST /api/issues/{run_id}/send` → 해당 State 로드(404), `sent_at` 있으면 409, verified 0건이면 400 "보낼 기사가 없습니다", 웹훅 미등록이면 400 "Discord 웹훅을 설정하세요". `send_discord(verified, webhook, post=post_fn)` 후 State에 `sent_at`(UTC ISO) 기록해 같은 출처 경로에 다시 저장. 응답 `{"sent": n, "sent_at": ...}`. 웹훅 오류는 502 `{"detail": repr(e)}`.
- `GET /` → `index.html`, `/static` 마운트.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_app_api.py`:
```python
import json

from fastapi.testclient import TestClient

import app.server as srv
from newsletter.graph import stub_nodes
from newsletter.store import save_run

D = {"title": "t", "url": "https://x/1", "source": "TechCrunch", "tier": 2, "at": "2026-09-14T00:00:00+00:00",
     "summary": "S", "reason": "r", "headline": "H", "why": "W", "body": "b"}


def _client(tmp_path, monkeypatch, key="sk-test"):
    srv._pending.clear()
    monkeypatch.setattr(srv, "STORE_DIR", tmp_path)
    monkeypatch.setattr(srv, "SETTINGS_PATH", tmp_path / "local" / "settings.json")
    monkeypatch.setattr(srv, "get_nodes", stub_nodes)
    monkeypatch.setattr(srv, "validate_openai", lambda k, m: None)
    c = TestClient(srv.app)
    if key:
        assert c.put("/api/settings", json={"openai_api_key": key}).status_code == 200
    return c


def test_settings_roundtrip_is_masked(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, key="sk-test-1234567Qx")
    m = c.get("/api/settings").json()
    assert m["openai_key_tail"] == "…7Qx" and m["webhook_registered"] is False
    assert "sk-test" not in c.get("/api/settings").text


def test_settings_rejects_bad_webhook(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.put("/api/settings", json={"discord_webhook_url": "https://example.com"})
    assert r.status_code == 400 and "웹훅" in r.json()["detail"]


def test_run_requires_openai_key(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, key="")
    r = c.post("/api/run", json={})
    assert r.status_code == 400 and "OpenAI" in r.json()["detail"]


def test_run_streams_and_creates_issue(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    run_id = c.post("/api/run", json={"hours": 24}).json()["run_id"]
    with c.stream("GET", f"/api/run/{run_id}/events") as r:
        events = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
    assert [e["node"] for e in events] == ["collect", "select", "verify", "publish", "__end__"]
    assert events[-1]["state"]["dry_run"] is True
    issues = c.get("/api/issues").json()
    assert issues[0]["run_id"] == run_id and issues[0]["origin"] == "local" and issues[0]["sent_at"] is None
    assert issues[0]["date"] == f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"
    assert c.get(f"/api/issues/{run_id}").json()["log"] == events[-1]["state"]["log"]


def test_issues_lists_both_origins_newest_first(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    save_run(tmp_path, "github", "20260913T223000", {"collected": [1, 2], "verified": [D], "dry_run": False})
    save_run(tmp_path, "local", "20260914T010000", {"collected": [1], "verified": [], "dry_run": True})
    rows = c.get("/api/issues").json()
    assert [(r["run_id"], r["origin"], r["published"], r["collected"]) for r in rows] == [
        ("20260914T010000", "local", 0, 1), ("20260913T223000", "github", 1, 2)]


def test_send_posts_once_records_sent_at_and_blocks_repeat(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.put("/api/settings", json={"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"})
    save_run(tmp_path, "local", "r1", {"collected": [], "verified": [D], "dry_run": True})
    calls = []
    class R:
        def raise_for_status(self): pass
    monkeypatch.setattr(srv, "post_fn", lambda url, json, timeout: calls.append(url) or R())
    r = c.post("/api/issues/r1/send")
    assert r.status_code == 200 and r.json()["sent"] == 1 and calls == ["https://discord.com/api/webhooks/1/abc"]
    assert c.get("/api/issues/r1").json()["sent_at"]
    assert c.post("/api/issues/r1/send").status_code == 409


def test_send_requires_webhook_and_articles(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    save_run(tmp_path, "local", "empty", {"collected": [], "verified": [], "dry_run": True})
    save_run(tmp_path, "local", "full", {"collected": [], "verified": [D], "dry_run": True})
    assert c.post("/api/issues/empty/send").status_code == 400
    r = c.post("/api/issues/full/send")
    assert r.status_code == 400 and "웹훅" in r.json()["detail"]
    assert c.post("/api/issues/none/send").status_code == 404


def test_index_served():
    r = TestClient(srv.app).get("/")
    assert r.status_code == 200 and "뉴스레터" in r.text
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_app_api.py -q`

- [ ] **Step 3: app/server.py 작성**

```python
"""뉴스레터 리더 앱 서버. 파이프라인은 항상 dry_run으로 돌리고, 발송은 사람이 버튼으로 한다."""
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import settings as st
from newsletter.config import load_config
from newsletter.graph import real_nodes
from newsletter.metrics import append_metrics, summarize
from newsletter.nodes.publish import send_discord
from newsletter.runner import stream_run
from newsletter.store import ORIGINS, load_run, metrics_path, runs_dir, save_run

STORE_DIR = Path("store")
SETTINGS_PATH = STORE_DIR / "local" / "settings.json"
STATIC = Path(__file__).parent / "static"
LOCAL = "local"
STALE_SECONDS = 60

app = FastAPI(title="AI 뉴스레터 리더")
_pending: dict[str, dict] = {}
_lock = threading.Lock()

validate_openai = st.check_openai_key     # 테스트가 교체
post_fn = requests.post                    # 테스트가 교체


def get_nodes():
    return real_nodes(load_config())



# ---------- 설정 ----------
class SettingsIn(BaseModel):
    openai_api_key: str | None = None
    openai_model: str | None = None
    discord_webhook_url: str | None = None
    hours: int | None = None


@app.get("/api/settings")
def get_settings():
    return st.masked(st.load(SETTINGS_PATH))


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        s = st.save(SETTINGS_PATH, updates, validate_openai=validate_openai)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return st.masked(s)


# ---------- 호 목록/상세 ----------
def _issue_row(origin: str, f: Path) -> dict:
    state = json.loads(f.read_text(encoding="utf-8"))
    rid = f.stem
    return {"run_id": rid, "date": f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}", "origin": origin,
            "published": len(state.get("verified", [])), "collected": len(state.get("collected", [])),
            "sent_at": state.get("sent_at"), "dry_run": bool(state.get("dry_run"))}


@app.get("/api/issues")
def list_issues():
    rows = [_issue_row(o, f) for o in ORIGINS for f in sorted(runs_dir(STORE_DIR, o).glob("*.json"))]
    rows.sort(key=lambda r: r["run_id"], reverse=True)
    return rows


@app.get("/api/issues/{run_id}")
def get_issue(run_id: str):
    state = load_run(STORE_DIR, run_id)
    if state is None:
        raise HTTPException(404, "그 호가 없습니다")
    return state


# ---------- 실행 ----------
class RunIn(BaseModel):
    hours: int | None = None


@app.post("/api/run")
def start_run(body: RunIn):
    s = st.load(SETTINGS_PATH)
    if not s.openai_api_key:
        raise HTTPException(400, "OpenAI 키를 설정하세요")
    st.apply_env(s)
    with _lock:
        now = time.monotonic()
        for rid in [k for k, v in _pending.items() if not v["running"] and now - v["created_at"] > STALE_SECONDS]:
            _pending.pop(rid, None)
        if _pending:
            raise HTTPException(409, "이미 만드는 중입니다")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        _pending[run_id] = {"hours": body.hours or s.hours, "running": False, "created_at": now}
    return {"run_id": run_id}


def _sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/run/{run_id}/events")
def run_events(run_id: str):
    if run_id not in _pending:
        raise HTTPException(404, "모르는 run_id")

    def gen():
        _pending[run_id]["running"] = True
        try:
            hours = _pending[run_id]["hours"]
            state, seconds = None, {}
            for ev in stream_run(get_nodes(), hours, True):      # 리더 앱은 항상 dry_run
                if ev["node"] == "__end__":
                    state, seconds = ev["state"], ev["seconds"]
                    break
                yield _sse(ev)
            state["run_id"] = run_id
            save_run(STORE_DIR, LOCAL, run_id, state)
            append_metrics(summarize(state, run_id, seconds), metrics_path(STORE_DIR, LOCAL))
            yield _sse({"node": "__end__", "state": state})
        except Exception as e:                                    # noqa: BLE001
            yield _sse({"node": "__error__", "error": repr(e)})
        finally:
            with _lock:
                _pending.pop(run_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- 발송 ----------
@app.post("/api/issues/{run_id}/send")
def send_issue(run_id: str):
    origin = next((o for o in ORIGINS if (runs_dir(STORE_DIR, o) / f"{run_id}.json").exists()), None)
    if origin is None:
        raise HTTPException(404, "그 호가 없습니다")
    state = load_run(STORE_DIR, run_id)
    if state.get("sent_at"):
        raise HTTPException(409, f"이미 보냈습니다 ({state['sent_at']})")
    drafts = state.get("verified", [])
    if not drafts:
        raise HTTPException(400, "보낼 기사가 없습니다")
    s = st.load(SETTINGS_PATH)
    if not s.discord_webhook_url:
        raise HTTPException(400, "Discord 웹훅을 설정하세요")
    try:
        n = send_discord(drafts, s.discord_webhook_url, post=post_fn)
    except Exception as e:                                        # noqa: BLE001
        raise HTTPException(502, f"Discord 발송 실패: {e!r}")
    state["sent_at"] = datetime.now(timezone.utc).isoformat()
    save_run(STORE_DIR, origin, run_id, state)
    return {"sent": n, "sent_at": state["sent_at"]}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
```
주의: `_settings_path` 헬퍼는 불필요하니 넣지 말 것(위 코드에서 제거). `SETTINGS_PATH`를 직접 쓴다. `web/app.py`처럼 `run_events`의 예외를 다시 `raise`하지 않는 이유는 리더 앱에서는 SSE `__error__`가 유일한 보고 경로이기 때문이다.

임시 `index.html`(Task 4에서 교체): `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AI 뉴스레터</title></head><body><h1>AI 뉴스레터 리더</h1></body></html>`

- [ ] **Step 4: 테스트 통과** — `uv run pytest -q` → 전부 통과.

- [ ] **Step 5: Commit** — `git add app tests/test_app_api.py && git commit -m "feat: 리더 앱 서버 — 설정·호 목록·실행·Discord 발송 API"`

---

### Task 4: 리더 앱 화면

**Files:**
- Create/Replace: `app/static/index.html`, `app/static/app.js`, `app/static/style.css`

**Interfaces:** Task 3의 API만 사용. 테스트는 `node --check app/static/app.js`와 `test_index_served`(제목에 "뉴스레터" 포함).

- [ ] **Step 1: index.html**

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 뉴스레터</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="topbar">
  <div class="brand">◎ AI 뉴스레터</div>
  <div class="actions">
    <label class="hours">시간 창
      <select id="hours"><option value="24">24시간</option><option value="48">48시간</option><option value="72">72시간</option></select>
    </label>
    <button id="make" class="primary">▶ 오늘 치 만들기</button>
    <button id="open-settings" class="ghost" title="설정">설정 ⚙</button>
  </div>
</header>

<div class="layout">
  <aside class="sidebar">
    <h2>발행 목록</h2>
    <ul id="issue-list"></ul>
  </aside>

  <main class="content">
    <div id="empty" class="empty">아직 만든 뉴스레터가 없습니다. 위의 <b>오늘 치 만들기</b>를 눌러 보세요.</div>
    <article id="issue" hidden>
      <header class="issue-head">
        <h1 id="issue-date"></h1>
        <div id="issue-meta" class="meta"></div>
      </header>
      <nav class="tabs">
        <button data-tab="published" class="tab active">발행본 <span id="n-published"></span></button>
        <button data-tab="rejected" class="tab">검수 탈락 <span id="n-rejected"></span></button>
        <button data-tab="collected" class="tab">수집 전체 <span id="n-collected"></span></button>
      </nav>
      <section id="tab-published" class="tab-pane"></section>
      <section id="tab-rejected" class="tab-pane" hidden></section>
      <section id="tab-collected" class="tab-pane" hidden>
        <input id="search" type="search" placeholder="제목·출처 검색">
        <table id="collected-table"></table>
      </section>
      <footer class="issue-foot">
        <button id="send" class="primary">Discord로 보내기</button>
        <span id="send-status" class="meta"></span>
      </footer>
    </article>
  </main>
</div>

<div id="overlay" class="overlay" hidden>
  <div class="dialog">
    <h2 id="overlay-title">오늘 치 뉴스레터 만드는 중</h2>
    <ol id="steps" class="steps">
      <li data-step="collect"><span class="dot"></span>수집 <em></em></li>
      <li data-step="select"><span class="dot"></span>선별 <em></em></li>
      <li data-step="report"><span class="dot"></span>취재 <em></em></li>
      <li data-step="verify"><span class="dot"></span>검수 <em></em></li>
      <li data-step="publish"><span class="dot"></span>정리 <em></em></li>
    </ol>
    <details id="log-details"><summary>상세 로그 보기</summary><pre id="run-log"></pre></details>
    <div id="overlay-error" class="error" hidden></div>
    <div class="dialog-foot"><span class="meta">취소할 수 없습니다 · 약 1분</span><button id="overlay-close" class="ghost" hidden>닫기</button></div>
  </div>
</div>

<aside id="settings" class="drawer" hidden>
  <div class="drawer-head"><h2>설정</h2><button id="close-settings" class="ghost">✕</button></div>
  <form id="settings-form">
    <label>OpenAI API 키 <span id="key-status" class="meta"></span>
      <input id="f-key" type="password" autocomplete="off" placeholder="새 키 입력 (비우면 유지)">
    </label>
    <label>모델
      <select id="f-model"><option>gpt-4o-mini</option><option>gpt-4o</option><option>gpt-4.1-mini</option><option>gpt-4.1</option></select>
    </label>
    <label>Discord 웹훅 URL <span id="hook-status" class="meta"></span>
      <input id="f-hook" type="password" autocomplete="off" placeholder="https://discord.com/api/webhooks/… (비우면 유지)">
      <button type="button" id="clear-hook" class="link">등록 해제</button>
    </label>
    <label>기본 수집 시간 창 <input id="f-hours" type="number" min="1" max="168"> 시간</label>
    <p class="meta">저장 위치: store/local/settings.json · 이 컴퓨터에만 저장되고 Git에 올라가지 않습니다.</p>
    <div id="settings-error" class="error" hidden></div>
    <button type="submit" class="primary">저장</button>
  </form>
</aside>
<div id="backdrop" class="backdrop" hidden></div>

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: app.js**

```javascript
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safeHref = (u) => /^https?:\/\//i.test(u || "") ? esc(u) : null;
const fmtTime = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }); };
const fmtDate = (ymd) => { const [y, m, d] = ymd.split("-").map(Number); const dt = new Date(y, m - 1, d); return `${y}년 ${m}월 ${d}일 (${"일월화수목금토"[dt.getDay()]})`; };

const state = { issues: [], current: null, tab: "published", settings: null };

// ---------- 데이터 ----------
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
}

async function loadIssues(selectId) {
  state.issues = await api("/api/issues");
  renderSidebar();
  const id = selectId || (state.current && state.current.run_id) || (state.issues[0] && state.issues[0].run_id);
  if (id) await openIssue(id); else renderIssue();
}

async function openIssue(runId) {
  state.current = await api(`/api/issues/${runId}`);
  state.current.run_id = runId;
  renderSidebar();
  renderIssue();
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  renderSettingsForm();
  $("#make").disabled = !state.settings.openai_key_tail;
  $("#hours").value = String(state.settings.hours);
  if (!state.settings.openai_key_tail) openSettings();
}

// ---------- 렌더 ----------
function renderSidebar() {
  const today = new Date().toISOString().slice(0, 10);
  $("#issue-list").innerHTML = state.issues.map(i => {
    const active = state.current && state.current.run_id === i.run_id ? "active" : "";
    const badge = i.origin === "github" ? `<span class="badge">GitHub</span>` : "";
    const dot = i.date === today ? `<span class="today">●</span>` : "";
    return `<li class="${active}" data-id="${esc(i.run_id)}">
      <div class="row1">${esc(i.date.slice(5).replace("-", "월 "))}일 ${dot}${badge}</div>
      <div class="row2 meta">발행 ${i.published} · 수집 ${i.collected}${i.sent_at ? " · 발송됨" : ""}</div></li>`;
  }).join("") || `<li class="meta">아직 없음</li>`;
  $$("#issue-list li[data-id]").forEach(li => li.addEventListener("click", () => openIssue(li.dataset.id)));
}

function rejectionReasons(s) {
  const map = {};
  (s.log || []).forEach(l => { const m = l.match(/✗ 탈락 · (.+?) · (.+?) · (.+)$/); if (m) map[`${m[1]}::${m[2]}`] = m[3]; });
  return map;
}

function card(d, reason) {
  const href = safeHref(d.url);
  const title = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(d.headline)}</a>` : esc(d.headline);
  return `<article class="card ${reason ? "rejected" : ""}">
    <div class="meta">${esc(d.source)} · ${esc(fmtTime(d.at))}</div>
    <h3>${title}</h3>
    <p class="summary">${esc(d.summary)}</p>
    <p class="why">➜ 왜 중요한가 · ${esc(d.why)}</p>
    ${reason ? `<p class="reason">검수 탈락 · ${esc(reason)}</p>` : ""}
    ${href ? `<a class="more" href="${href}" target="_blank" rel="noopener">원문 보기 ↗</a>` : ""}
  </article>`;
}

function renderIssue() {
  const s = state.current;
  $("#empty").hidden = !!s; $("#issue").hidden = !s;
  if (!s) return;
  const verifiedUrls = new Set((s.verified || []).map(d => d.url));
  const rejected = (s.drafted || []).filter(d => !verifiedUrls.has(d.url));
  const reasons = rejectionReasons(s);
  const rid = s.run_id;
  $("#issue-date").textContent = fmtDate(`${rid.slice(0,4)}-${rid.slice(4,6)}-${rid.slice(6,8)}`);
  $("#issue-meta").textContent = `발행 ${(s.verified||[]).length}건 · 검수 탈락 ${rejected.length}건 · 수집 ${(s.collected||[]).length}건`;
  $("#n-published").textContent = (s.verified||[]).length;
  $("#n-rejected").textContent = rejected.length;
  $("#n-collected").textContent = (s.collected||[]).length;
  $("#tab-published").innerHTML = (s.verified||[]).map(d => card(d, null)).join("") || `<p class="meta">검수를 통과한 기사가 없습니다.</p>`;
  $("#tab-rejected").innerHTML = rejected.map(d => card(d, reasons[`${d.source}::${d.headline.slice(0,30)}`] || "사유 로그 참조")).join("") || `<p class="meta">탈락한 기사가 없습니다.</p>`;
  renderCollected();
  showTab(state.tab);
  const canSend = (s.verified||[]).length > 0 && state.settings && state.settings.webhook_registered && !s.sent_at;
  $("#send").disabled = !canSend;
  $("#send-status").textContent = s.sent_at ? `${fmtTime(s.sent_at)} 발송됨`
    : !(s.verified||[]).length ? "보낼 기사가 없습니다"
    : !(state.settings && state.settings.webhook_registered) ? "설정에서 Discord 웹훅을 등록하세요"
    : "보낸 적 없음";
}

function renderCollected() {
  const s = state.current; if (!s) return;
  const q = ($("#search").value || "").toLowerCase();
  const picked = new Set((s.picked||[]).map(p => p.url));
  const rows = (s.collected||[]).filter(a => !q || (a.title||"").toLowerCase().includes(q) || (a.source||"").toLowerCase().includes(q));
  $("#collected-table").innerHTML = `<tr><th>출처</th><th>시각</th><th>제목</th></tr>` + rows.map(a => {
    const href = safeHref(a.url);
    const t = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(a.title)}</a>` : esc(a.title);
    return `<tr><td>${esc(a.source)}</td><td class="meta">${esc(fmtTime(a.at))}</td><td>${t}${picked.has(a.url) ? ' <span class="badge pick">선별</span>' : ""}</td></tr>`;
  }).join("");
}

function showTab(name) {
  state.tab = name;
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-pane").forEach(p => p.hidden = p.id !== `tab-${name}`);
}

// ---------- 만들기 ----------
async function makeIssue() {
  const ov = $("#overlay"); ov.hidden = false;
  $("#overlay-error").hidden = true; $("#overlay-close").hidden = true; $("#run-log").textContent = "";
  $$("#steps li").forEach(li => { li.className = ""; li.querySelector("em").textContent = ""; });
  $("#make").disabled = true;
  let runId;
  try { ({ run_id: runId } = await api("/api/run", { method: "POST", body: JSON.stringify({ hours: Number($("#hours").value) }) })); }
  catch (e) { showRunError(e.message); return; }
  let reportDone = 0, reportTotal = 0;
  const setStep = (name, cls, note) => { const li = $(`#steps li[data-step="${name}"]`); li.className = cls; if (note !== undefined) li.querySelector("em").textContent = note; };
  setStep("collect", "active");
  const es = new EventSource(`/api/run/${runId}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    (e.update && e.update.log || []).forEach(l => $("#run-log").textContent += l + "\n");
    if (e.node === "collect") { setStep("collect", "done", `${(e.update.collected||[]).length}건`); setStep("select", "active"); }
    if (e.node === "select") { reportTotal = (e.update.picked||[]).length; setStep("select", "done", `${reportTotal}건`); setStep(reportTotal ? "report" : "verify", "active"); }
    if (e.node === "report") { reportDone += 1; setStep("report", reportDone >= reportTotal ? "done" : "active", `${reportDone} / ${reportTotal}`); if (reportDone >= reportTotal) setStep("verify", "active"); }
    if (e.node === "verify") { setStep("verify", "done", `${(e.update.verified||[]).length}건 통과`); setStep("publish", "active"); }
    if (e.node === "publish") { setStep("publish", "done"); }
    if (e.node === "__end__") { es.close(); ov.hidden = true; $("#make").disabled = false; loadIssues(runId); }
    if (e.node === "__error__") { es.close(); showRunError(e.error); }
  };
  es.onerror = () => { es.close(); showRunError("연결이 끊겼습니다"); };
}

function showRunError(msg) {
  $("#overlay-error").textContent = "오류: " + msg; $("#overlay-error").hidden = false;
  $("#log-details").open = true; $("#overlay-close").hidden = false; $("#make").disabled = false;
}

// ---------- 발송 ----------
async function sendIssue() {
  const s = state.current; if (!s) return;
  if (!confirm(`${(s.verified||[]).length}건을 Discord로 보낼까요? 보낸 뒤에는 되돌릴 수 없습니다.`)) return;
  $("#send").disabled = true; $("#send-status").textContent = "보내는 중…";
  try { await api(`/api/issues/${s.run_id}/send`, { method: "POST" }); await loadIssues(s.run_id); }
  catch (e) { $("#send-status").textContent = "발송 실패: " + e.message; $("#send").disabled = false; }
}

// ---------- 설정 ----------
function openSettings() { $("#settings").hidden = false; $("#backdrop").hidden = false; }
function closeSettings() { $("#settings").hidden = true; $("#backdrop").hidden = true; }
function renderSettingsForm() {
  const s = state.settings; if (!s) return;
  $("#key-status").textContent = s.openai_key_tail ? `등록됨 · ${s.openai_key_tail}` : "미등록";
  $("#hook-status").textContent = s.webhook_registered ? "등록됨" : "미등록";
  $("#clear-hook").hidden = !s.webhook_registered;
  $("#f-model").value = s.openai_model; $("#f-hours").value = s.hours;
  $("#f-key").value = ""; $("#f-hook").value = "";
}
async function saveSettings(ev) {
  ev.preventDefault();
  const body = { openai_model: $("#f-model").value, hours: Number($("#f-hours").value) };
  if ($("#f-key").value) body.openai_api_key = $("#f-key").value.trim();
  if ($("#f-hook").value) body.discord_webhook_url = $("#f-hook").value.trim();
  if ($("#f-hook").dataset.clear === "1") body.discord_webhook_url = "";
  $("#settings-error").hidden = true;
  try {
    state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    delete $("#f-hook").dataset.clear;
    renderSettingsForm(); closeSettings();
    $("#make").disabled = !state.settings.openai_key_tail; $("#hours").value = String(state.settings.hours);
    renderIssue();
  } catch (e) { $("#settings-error").textContent = e.message; $("#settings-error").hidden = false; }
}

// ---------- 이벤트 ----------
$("#make").addEventListener("click", makeIssue);
$("#send").addEventListener("click", sendIssue);
$("#open-settings").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", closeSettings);
$("#backdrop").addEventListener("click", closeSettings);
$("#settings-form").addEventListener("submit", saveSettings);
$("#clear-hook").addEventListener("click", () => { $("#f-hook").dataset.clear = "1"; $("#hook-status").textContent = "저장하면 해제됨"; });
$("#overlay-close").addEventListener("click", () => { $("#overlay").hidden = true; });
$("#search").addEventListener("input", renderCollected);
$$(".tab").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));

(async () => { await loadSettings(); await loadIssues(); })();
```

- [ ] **Step 3: style.css**

```css
:root { --bg:#f7f6f3; --paper:#fff; --ink:#1c1c1e; --muted:#6e6e73; --accent:#1e2a78; --line:#e6e4df; --danger:#b42318; --ok:#1f7a4d; }
* { box-sizing:border-box; }
html, body { margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",Pretendard,sans-serif; font-size:16px; line-height:1.65; }
button { font:inherit; cursor:pointer; border-radius:8px; padding:8px 14px; border:1px solid var(--line); background:var(--paper); color:var(--ink); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button.ghost { background:transparent; }
button.link { background:none; border:0; color:var(--accent); padding:0; font-size:13px; }
button:disabled { opacity:.45; cursor:default; }
input, select { font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:#fff; width:100%; }
.meta { color:var(--muted); font-size:13px; }
.error { color:var(--danger); background:#fdecea; padding:10px 12px; border-radius:8px; margin:10px 0; font-size:14px; }

.topbar { display:flex; justify-content:space-between; align-items:center; padding:14px 28px; background:var(--paper); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; }
.brand { font-weight:700; font-size:18px; letter-spacing:-.2px; }
.actions { display:flex; gap:10px; align-items:center; }
.actions .hours { display:flex; gap:6px; align-items:center; font-size:13px; color:var(--muted); }
.actions select { width:auto; padding:6px 8px; }

.layout { display:grid; grid-template-columns:240px 1fr; min-height:calc(100vh - 61px); }
.sidebar { border-right:1px solid var(--line); padding:20px 14px; background:var(--paper); }
.sidebar h2 { font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin:0 0 10px 6px; }
.sidebar ul { list-style:none; margin:0; padding:0; }
.sidebar li { padding:10px 10px; border-radius:8px; cursor:pointer; }
.sidebar li:hover { background:var(--bg); }
.sidebar li.active { background:#eceef8; }
.sidebar .row1 { font-weight:600; display:flex; gap:6px; align-items:center; }
.today { color:var(--accent); font-size:10px; }
.badge { font-size:11px; padding:1px 6px; border-radius:4px; background:#eceef8; color:var(--accent); }
.badge.pick { background:#e7f5ec; color:var(--ok); }

.content { padding:28px 40px; max-width:860px; }
.empty { color:var(--muted); padding:80px 0; text-align:center; }
.issue-head h1 { font-size:26px; margin:0 0 4px; letter-spacing:-.3px; }
.tabs { display:flex; gap:4px; margin:18px 0 22px; border-bottom:1px solid var(--line); }
.tab { border:0; background:none; padding:8px 12px; color:var(--muted); border-bottom:2px solid transparent; border-radius:0; }
.tab.active { color:var(--ink); border-bottom-color:var(--accent); font-weight:600; }
.tab span { font-size:12px; margin-left:4px; }

.card { background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:20px 22px; margin-bottom:16px; }
.card h3 { font-size:19px; margin:4px 0 8px; line-height:1.4; }
.card h3 a { color:inherit; text-decoration:none; }
.card h3 a:hover { text-decoration:underline; }
.card .summary { font-size:17px; margin:0 0 10px; }
.card .why { color:var(--accent); margin:0; font-size:15px; }
.card .reason { color:var(--danger); font-size:14px; margin:10px 0 0; }
.card .more { display:inline-block; margin-top:10px; font-size:13px; color:var(--muted); }
.card.rejected { opacity:.8; border-left:3px solid var(--danger); }

#search { margin-bottom:12px; }
#collected-table { width:100%; border-collapse:collapse; font-size:14px; background:var(--paper); }
#collected-table th, #collected-table td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
#collected-table a { color:inherit; }

.issue-foot { display:flex; gap:14px; align-items:center; margin-top:28px; padding-top:18px; border-top:1px solid var(--line); }

.overlay { position:fixed; inset:0; background:rgba(28,28,30,.45); display:flex; align-items:center; justify-content:center; z-index:20; }
.dialog { background:var(--paper); border-radius:14px; padding:26px 30px; width:min(520px, 92vw); }
.dialog h2 { margin:0 0 16px; font-size:18px; }
.steps { list-style:none; margin:0; padding:0; }
.steps li { display:flex; align-items:center; gap:10px; padding:7px 0; color:var(--muted); }
.steps li em { font-style:normal; margin-left:auto; font-size:13px; }
.steps .dot { width:12px; height:12px; border-radius:50%; border:2px solid var(--line); }
.steps li.active { color:var(--ink); }
.steps li.active .dot { border-color:var(--accent); border-top-color:transparent; animation:spin .8s linear infinite; }
.steps li.done { color:var(--ink); }
.steps li.done .dot { background:var(--ok); border-color:var(--ok); }
@keyframes spin { to { transform:rotate(360deg); } }
#log-details { margin-top:14px; font-size:13px; }
#run-log { white-space:pre-wrap; max-height:200px; overflow:auto; background:var(--bg); padding:10px; border-radius:8px; }
.dialog-foot { display:flex; justify-content:space-between; align-items:center; margin-top:14px; }

.drawer { position:fixed; top:0; right:0; height:100vh; width:min(420px, 94vw); background:var(--paper); border-left:1px solid var(--line); padding:22px 24px; z-index:30; overflow:auto; }
.drawer-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.drawer h2 { margin:0; font-size:18px; }
.drawer label { display:block; margin:14px 0 6px; font-weight:600; font-size:14px; }
.drawer label input, .drawer label select { margin-top:6px; font-weight:400; }
.drawer label .meta { font-weight:400; margin-left:6px; }
.backdrop { position:fixed; inset:0; background:rgba(28,28,30,.25); z-index:25; }

@media (max-width:900px) {
  .layout { grid-template-columns:1fr; }
  .sidebar { border-right:0; border-bottom:1px solid var(--line); padding:12px; }
  .sidebar ul { display:flex; gap:8px; overflow-x:auto; }
  .sidebar li { flex:0 0 auto; }
  .content { padding:20px 16px; }
  .topbar { padding:10px 16px; flex-wrap:wrap; gap:8px; }
}
```

- [ ] **Step 4: 검사** — `node --check app/static/app.js`; `uv run pytest -q`; 서버를 띄워(`uv run uvicorn app.server:app --port 8100`) `curl`로 `/`, `/api/settings`, `/api/issues`가 200인지 확인 후 종료.

- [ ] **Step 5: Commit** — `git add app/static && git commit -m "feat: 리더 앱 화면 — 3열 리더, 실행 오버레이, 설정 패널"`

---

### Task 5: Actions 스케줄 끄기 + README

**Files:**
- Modify: `.github/workflows/daily.yml`, `README.md`

- [ ] **Step 1:** `daily.yml`에서 `schedule:` 블록(두 줄)을 삭제. `workflow_dispatch`는 유지. YAML 파싱 확인.
- [ ] **Step 2:** README 상단 "사용법"에 **0. 리더 앱(권장)** 절을 추가:
  ```markdown
  ### 0. 리더 앱 — 버튼으로 만들고 잡지처럼 읽기 (권장)
  ```bash
  uv run uvicorn app.server:app --port 8100     # http://127.0.0.1:8100
  ```
  - 처음 열면 설정 패널이 뜹니다. OpenAI 키(필수)와 Discord 웹훅(선택)을 넣으면 `store/local/settings.json`에 저장됩니다. `.env`는 필요 없습니다.
  - **▶ 오늘 치 만들기** → 수집·선별·취재·검수가 차례로 진행되고 끝나면 왼쪽 목록에 새 호가 생깁니다. Discord로는 보내지 않습니다.
  - 본문의 **발행본 / 검수 탈락 / 수집 전체** 탭으로 그날 결과를 읽습니다.
  - 마음에 들면 **Discord로 보내기**를 누릅니다. 한 호는 한 번만 보낼 수 있습니다.
  - 기존 대시보드(`web/`, 포트 8000)는 운영 지표용으로 그대로 남아 있습니다.
  ```
  "3. 매일 아침 자동 실행" 절을 "3. GitHub Actions 수동 실행"으로 바꾸고, 스케줄이 꺼져 있으며 Actions 탭에서 수동으로만 돌릴 수 있다고 적는다.
- [ ] **Step 3:** `uv run pytest -q` 전부 통과. Commit — `git commit -m "chore: Actions 자동 스케줄 끄기, README에 리더 앱 안내"`

---

## Self-Review

- 스펙 §2 화면 3열·탭 3개·발송 버튼·오버레이·설정 패널 → Task 4. §3 API 7개 → Task 3. §4 Actions → Task 5. §5 폴더 → Task 1~4. §6 에러 처리(키 없음 400, 실행 오류 오버레이, 발송 실패 502·재시도, 0건 400, 키 검증 실패 400) → Task 3·4. §7 테스트 항목 → Task 1~3. ✓
- 타입 일관성: `stream_run` 이벤트 모양을 `web/app.py`와 `app/server.py`가 동일하게 소비. `send_discord(drafts, webhook_url, title=None, post=)` 시그니처가 Task 2 테스트·Task 3 서버에서 일치. `masked()` 키 이름이 Task 2 테스트·Task 3 테스트·app.js(`openai_key_tail`, `webhook_registered`, `hours`, `openai_model`)에서 일치. ✓
- 플레이스홀더 없음. Task 3 코드의 `_settings_path` 헬퍼는 삭제하라고 명시. ✓
