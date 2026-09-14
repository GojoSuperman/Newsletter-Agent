# 뉴스레터 에이전트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수업(모두의연구소 「뉴스레터 에이전트」)의 5단계 LangGraph 파이프라인을 그대로 구현하고, 브라우저 대시보드에서 실행·관찰할 수 있게 하며, GitHub Actions로 매일 아침 Discord에 발행한다.

**Architecture:** `newsletter/`는 교재 코드(State, 노드 5개, 그래프, 지표, 설정)이며 화면을 모른다. `web/`은 FastAPI가 그래프를 `stream()`으로 돌리며 SSE로 로그를 흘리는 한 페이지 대시보드다. `run.py`는 화면 없이 그래프를 한 번 돌리는 CLI로, GitHub Actions가 이것만 부른다. 구현 순서는 수업대로 "빈 노드 뼈대 → 하나씩 채우기"이며, 매 태스크 끝에 전체가 돈다.

**Tech Stack:** Python 3.14, uv, langgraph, openai(구조화 출력), pydantic, feedparser, requests, trafilatura, PyYAML, FastAPI + uvicorn, pytest, 순수 HTML/JS/CSS.

**Spec:** `docs/superpowers/specs/2026-09-14-newsletter-agent-design.md`

## Global Constraints

- Python 3.14, 패키지 관리는 `uv` (`uv run pytest`, `uv run python run.py`). pip는 없다.
- 테스트는 실제 네트워크·OpenAI·Discord를 절대 호출하지 않는다. 전부 monkeypatch/가짜 객체.
- State 리듀서는 `drafted`·`log`에만 붙인다. `collected`·`picked`·`verified`는 덮어쓰기.
- 노드는 자기가 바꾼 키만 반환한다.
- 발행(publish) 노드에는 LLM을 넣지 않는다. `dry_run=True`면 HTTP 호출이 없어야 한다.
- 조용한 실패 금지: 결과물을 바꾸는 건너뜀(소스 실패, 본문 추출 실패, 검수 탈락)은 반드시 `log` 또는 지표에 남긴다.
- 코드·식별자는 영어, 주석·로그·UI 텍스트는 한국어.
- 시크릿은 `.env`(gitignore)에만. `.env.example`에는 키 이름만.
- 커밋 메시지 끝에 다음 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017h4uY6imjmtQj5NonVo8TY
  ```
- LLM 모델은 환경 변수 `OPENAI_MODEL`(기본 `gpt-4o-mini`)로 정한다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `pyproject.toml` | 의존성·pytest 설정 (uv) |
| `.env.example` | `OPENAI_API_KEY`, `OPENAI_MODEL`, `DISCORD_WEBHOOK_URL` 이름만 |
| `audience.yaml` | 독자·기준·토픽·톤·소스 목록·발행 건수 |
| `newsletter/state.py` | `Article`, `Pick`, `Draft`, `Verdict` TypedDict와 `Brief` State |
| `newsletter/config.py` | `load_config(path) -> Config` (YAML 로드 + 필수 키 검증) |
| `newsletter/llm.py` | `get_client()`, `ask_structured(system, user, schema)` OpenAI 헬퍼 |
| `newsletter/metrics.py` | `append_metrics(row, path)`, `read_metrics(path)` |
| `newsletter/nodes/collect.py` | ① 수집: `collect(state, sources) -> dict` + 순수 함수들 |
| `newsletter/nodes/select.py` | ② 선별: 예선→본선 `select(state, cfg, ask) -> dict` |
| `newsletter/nodes/report.py` | ③ 요약: `extract_body(url)`, `draft(pick, cfg, ask)`, `fan_report(state)`, `report(state) -> dict` |
| `newsletter/nodes/verify.py` | ④ 검수: `check(draft, ask) -> Verdict`, `verify(state) -> dict` |
| `newsletter/nodes/publish.py` | ⑤ 발행: `render_discord(drafts)`, `publish(state, post) -> dict` |
| `newsletter/graph.py` | `build(cfg, deps)`, `initial_state(hours, dry_run)`, `run(...)` |
| `newsletter/sources_check.py` | 관문 G1·G2·G3 검사 스크립트 (수동 실행) |
| `run.py` | CLI: 그래프 한 번 실행 + 지표 append + 결과 저장 |
| `web/app.py` | FastAPI: `/api/run`, `/api/run/{id}/events`, `/api/runs`, `/api/run/{id}`, `/api/config`, 정적 파일 |
| `web/static/index.html`, `app.js`, `style.css` | 대시보드 |
| `.github/workflows/daily.yml` | 매일 07:30 KST 실행 |
| `tests/*.py` | 태스크별 테스트 |

노드 함수는 의존성(소스 목록, LLM 호출 함수, HTTP post 함수)을 **인자로 받는 순수 함수**로 만들고, `graph.py`가 `functools.partial`로 묶어 LangGraph에 등록한다. 테스트에서 가짜를 꽂기 쉽게 하기 위한 유일한 구조적 선택이다.

---

### Task 0: 프로젝트 초기화

**Files:**
- Create: `pyproject.toml`, `.env.example`, `newsletter/__init__.py`, `newsletter/nodes/__init__.py`, `tests/__init__.py`, `store/.gitkeep`, `README.md`

**Interfaces:**
- Produces: `uv run pytest`가 동작하는 환경

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "newsletter-agent"
version = "0.1.0"
description = "AI 뉴스레터 에이전트 — 수집부터 발행까지"
requires-python = ">=3.14"
dependencies = [
    "langgraph>=0.4",
    "openai>=1.60",
    "pydantic>=2.7",
    "feedparser>=6.0",
    "requests>=2.32",
    "trafilatura>=2.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]

[dependency-groups]
dev = ["pytest>=8", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["newsletter", "web"]
```

- [ ] **Step 2: .env.example 작성**

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
DISCORD_WEBHOOK_URL=
```

- [ ] **Step 3: 빈 패키지 파일과 store 생성**

```bash
mkdir -p newsletter/nodes tests store web/static
touch newsletter/__init__.py newsletter/nodes/__init__.py tests/__init__.py store/.gitkeep
```

`.gitignore`에 이미 `store/`가 있다. `.gitkeep`만 추적되도록 `.gitignore`의 `store/` 줄을 다음 두 줄로 바꾼다:
```
store/*
!store/.gitkeep
```

- [ ] **Step 4: README.md 작성**

```markdown
# 뉴스레터 에이전트

AI 뉴스를 매일 아침 수집 → 선별 → 요약 → 검수 → Discord 발행하는 LangGraph 파이프라인과 대시보드.

## 실행
```bash
cp .env.example .env   # 키 입력
uv sync
uv run python run.py --hours 24 --dry-run      # 터미널 한 번 실행
uv run uvicorn web.app:app --reload            # 대시보드 http://127.0.0.1:8000
uv run pytest
```
```

- [ ] **Step 5: 의존성 설치 및 pytest 동작 확인**

Run: `uv sync && uv run pytest`
Expected: `no tests ran` (에러 없음)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .env.example .gitignore README.md newsletter tests store
git commit -m "chore: 프로젝트 초기화 (uv, 의존성, 패키지 뼈대)"
```

---

### Task 1: State와 빈 노드 뼈대 (수업 섹션 2)

**Files:**
- Create: `newsletter/state.py`, `newsletter/graph.py`, `run.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Produces:
  - `Brief` TypedDict: `hours:int, dry_run:bool, collected:list, picked:list, drafted:Annotated[list, operator.add], verified:list, log:Annotated[list, operator.add]`
  - `Article` TypedDict: `title:str, url:str, source:str, tier:int, at:str(ISO), summary:str`
  - `Pick` TypedDict: `Article` + `reason:str`
  - `Draft` TypedDict: `Pick` + `headline:str, summary:str, why:str, body:str`
  - `Verdict` TypedDict: `url:str, ok:bool, reason:str`
  - `graph.build(nodes: dict[str, Callable]) -> StateGraph` — 이름→함수 매핑을 받아 5개를 순서대로 연결
  - `graph.initial_state(hours:int, dry_run:bool) -> Brief`
  - `graph.stub_nodes() -> dict[str, Callable]` — 빈 노드 5개
  - `graph.run(nodes, hours, dry_run) -> Brief`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_graph.py`:
```python
from newsletter.graph import build, initial_state, run, stub_nodes


def test_stub_pipeline_runs_five_nodes_in_order():
    result = run(stub_nodes(), hours=24, dry_run=True)
    assert len(result["log"]) == 5
    assert [line[0] for line in result["log"]] == ["①", "②", "③", "④", "⑤"]
    assert result["collected"] == [] and result["picked"] == []


def test_initial_state_has_all_keys():
    s = initial_state(24, True)
    assert set(s) == {"hours", "dry_run", "collected", "picked", "drafted", "verified", "log"}


def test_build_accepts_replaced_node():
    nodes = stub_nodes()
    nodes["collect"] = lambda s: {"collected": [{"title": "x"}], "log": ["① 가짜 1건"]}
    out = build(nodes).compile().invoke(initial_state(24, True))
    assert out["collected"] == [{"title": "x"}]
    assert out["log"][1].startswith("② 선별    1 → 0건")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.graph`

- [ ] **Step 3: state.py 작성**

`newsletter/state.py`:
```python
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
```

- [ ] **Step 4: graph.py 작성 (빈 노드 + build/run)**

`newsletter/graph.py`:
```python
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from newsletter.state import Brief

NODE_ORDER = ("collect", "select", "report", "verify", "publish")


def stub_nodes() -> dict[str, Callable]:
    """섹션 2의 빈 노드 다섯 개. 로그 한 줄만 남기고 빈 값을 돌려준다."""
    return {
        "collect": lambda s: {"collected": [], "log": [f"① 수집    {s['hours']}시간 창 · 0건 (빈 노드)"]},
        "select": lambda s: {"picked": [], "log": [f"② 선별    {len(s['collected'])} → 0건 (빈 노드)"]},
        "report": lambda s: {"drafted": [], "log": [f"③ 취재    {len(s['picked'])}건 (빈 노드)"]},
        "verify": lambda s: {"verified": [], "log": [f"④ 검수    {len(s['drafted'])}건 (빈 노드)"]},
        "publish": lambda s: {"log": [f"⑤ 발행    {len(s['verified'])}건 (빈 노드)"]},
    }


def build(nodes: dict[str, Callable]) -> StateGraph:
    """이름→함수 매핑을 받아 다섯 노드를 순서대로 잇는다. 노드를 갈아 끼워도 이 함수는 안 바뀐다."""
    g = StateGraph(Brief)
    for name in NODE_ORDER:
        g.add_node(name, nodes[name])
    g.add_edge(START, "collect")
    g.add_edge("collect", "select")
    g.add_edge("select", "report")
    g.add_edge("report", "verify")
    g.add_edge("verify", "publish")
    g.add_edge("publish", END)
    return g


def initial_state(hours: int, dry_run: bool) -> Brief:
    return {"hours": hours, "dry_run": dry_run,
            "collected": [], "picked": [], "drafted": [], "verified": [], "log": []}


def run(nodes: dict[str, Callable], hours: int = 24, dry_run: bool = True) -> Brief:
    return build(nodes).compile().invoke(initial_state(hours, dry_run))
```

- [ ] **Step 5: run.py 작성 (빈 노드로 한 바퀴)**

`run.py`:
```python
"""그래프를 한 번 돌린다. 터미널과 GitHub Actions가 쓴다."""
import argparse

from newsletter.graph import run, stub_nodes


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    result = run(stub_nodes(), hours=a.hours, dry_run=a.dry_run)
    for line in result["log"]:
        print(line)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 테스트 통과 및 CLI 확인**

Run: `uv run pytest tests/test_graph.py -v && uv run python run.py --dry-run`
Expected: 3 passed. CLI는 ①~⑤ 다섯 줄, 전부 0건.

- [ ] **Step 7: Commit**

```bash
git add newsletter/state.py newsletter/graph.py run.py tests/test_graph.py
git commit -m "feat: State와 빈 노드 5개 뼈대 (섹션 2)"
```

---

### Task 2: 대시보드 뼈대 — 실행 버튼과 SSE 로그

**Files:**
- Create: `web/__init__.py`, `web/app.py`, `web/static/index.html`, `web/static/app.js`, `web/static/style.css`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `graph.build`, `graph.initial_state`, `graph.stub_nodes`
- Produces:
  - `web.app.app` (FastAPI)
  - `web.app.get_nodes() -> dict[str, Callable]` — 이후 태스크에서 진짜 노드로 교체하는 유일한 지점
  - `POST /api/run {hours, dry_run} -> {run_id}`
  - `GET /api/run/{run_id}/events` SSE. 이벤트 `data:` JSON: `{"node": str, "update": dict}` 노드마다 하나, 끝에 `{"node":"__end__","state": Brief}`
  - `GET /api/run/{run_id}` → 저장된 최종 State
  - `web.app.STORE_DIR` (기본 `store/`), 실행 결과는 `store/runs/<run_id>.json`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api.py`:
```python
import json

from fastapi.testclient import TestClient

import web.app as webapp


def test_run_streams_five_node_events(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    client = TestClient(webapp.app)
    run_id = client.post("/api/run", json={"hours": 24, "dry_run": True}).json()["run_id"]
    with client.stream("GET", f"/api/run/{run_id}/events") as r:
        events = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
    nodes = [e["node"] for e in events]
    assert nodes == ["collect", "select", "report", "verify", "publish", "__end__"]
    assert len(events[-1]["state"]["log"]) == 5
    saved = json.loads((tmp_path / "runs" / f"{run_id}.json").read_text())
    assert saved["log"] == events[-1]["state"]["log"]


def test_get_run_returns_saved_state(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "abc.json").write_text(json.dumps({"log": ["x"]}))
    assert TestClient(webapp.app).get("/api/run/abc").json() == {"log": ["x"]}


def test_index_served():
    r = TestClient(webapp.app).get("/")
    assert r.status_code == 200 and "뉴스레터" in r.text
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: web.app`

- [ ] **Step 3: app.py 작성**

`web/app.py`:
```python
"""대시보드 서버. 그래프를 stream()으로 돌리며 노드마다 SSE 이벤트를 흘린다."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from newsletter.graph import build, initial_state, stub_nodes

STORE_DIR = Path("store")
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="뉴스레터 에이전트")

_pending: dict[str, dict] = {}       # run_id -> {"hours", "dry_run"} (아직 시작 안 함)
_lock = threading.Lock()


def get_nodes():
    """실행에 쓸 노드 매핑. 이후 태스크에서 진짜 노드로 바꾼다."""
    return stub_nodes()


class RunRequest(BaseModel):
    hours: int = 24
    dry_run: bool = True


@app.post("/api/run")
def start_run(req: RunRequest):
    with _lock:
        if any(v.get("running") for v in _pending.values()):
            raise HTTPException(409, "이미 실행 중입니다")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        _pending[run_id] = {"hours": req.hours, "dry_run": req.dry_run, "running": False}
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
            cfg = _pending[run_id]
            state = initial_state(cfg["hours"], cfg["dry_run"])
            graph = build(get_nodes()).compile()
            for update in graph.stream(state, stream_mode="updates"):
                for node, delta in update.items():
                    yield _sse({"node": node, "update": delta})
                    state = _merge(state, delta)
            state["run_id"] = run_id
            _save(run_id, state)
            yield _sse({"node": "__end__", "state": state})
        except Exception as e:                      # 화면에 에러를 보여야 한다
            yield _sse({"node": "__error__", "error": repr(e)})
            raise
        finally:
            _pending.pop(run_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _merge(state: dict, delta: dict) -> dict:
    out = dict(state)
    for k, v in delta.items():
        out[k] = out.get(k, []) + v if k in ("drafted", "log") else v
    return out


def _save(run_id: str, state: dict) -> None:
    d = STORE_DIR / "runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}.json").write_text(json.dumps(state, ensure_ascii=False, default=str, indent=1))


@app.get("/api/run/{run_id}")
def get_run(run_id: str):
    f = STORE_DIR / "runs" / f"{run_id}.json"
    if not f.exists():
        raise HTTPException(404, "저장된 실행이 없습니다")
    return json.loads(f.read_text())


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
```

`web/__init__.py`는 빈 파일.

- [ ] **Step 4: index.html / app.js / style.css 작성**

`web/static/index.html`:
```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 뉴스레터 에이전트</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header>
  <h1>AI 뉴스레터 에이전트</h1>
  <div class="controls">
    <label>시간 창 <input id="hours" type="number" value="24" min="1" max="168"></label>
    <label><input id="dry" type="checkbox" checked> dry_run</label>
    <button id="run">▶ 실행</button>
  </div>
</header>
<main>
  <section id="funnel" class="panel">
    <h2>깔때기</h2>
    <ul>
      <li><span>수집</span><b data-k="collected">–</b></li>
      <li><span>선별</span><b data-k="picked">–</b></li>
      <li><span>취재</span><b data-k="drafted">–</b></li>
      <li><span>검수</span><b data-k="verified">–</b></li>
      <li><span>발행</span><b data-k="published">–</b></li>
    </ul>
  </section>
  <section class="panel">
    <h2>실시간 로그</h2>
    <pre id="log"></pre>
  </section>
  <section id="cards" class="panel wide"><h2>발행 카드</h2><div id="cardlist"></div></section>
  <section id="history" class="panel wide"><h2>과거 실행</h2><table id="runs"></table></section>
</main>
<script src="/static/app.js"></script>
</body>
</html>
```

`web/static/app.js`:
```javascript
const $ = (s) => document.querySelector(s);
const logEl = $("#log");

function setFunnel(k, v) { const el = document.querySelector(`[data-k="${k}"]`); if (el) el.textContent = v; }

function resetView() {
  logEl.textContent = "";
  ["collected","picked","drafted","verified","published"].forEach(k => setFunnel(k, "–"));
  $("#cardlist").innerHTML = "";
}

function onUpdate(node, u) {
  (u.log || []).forEach(l => logEl.textContent += l + "\n");
  if (u.collected) setFunnel("collected", u.collected.length);
  if (u.picked) setFunnel("picked", u.picked.length);
  if (u.drafted) setFunnel("drafted", Number($("[data-k=drafted]").textContent) || 0 + u.drafted.length);
  if (u.verified) setFunnel("verified", u.verified.length);
  if (node === "publish") setFunnel("published", u.published_count ?? "–");
}

async function startRun() {
  $("#run").disabled = true;
  resetView();
  const body = { hours: Number($("#hours").value), dry_run: $("#dry").checked };
  const r = await fetch("/api/run", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
  if (!r.ok) { logEl.textContent = "실행 실패: " + (await r.text()); $("#run").disabled = false; return; }
  const { run_id } = await r.json();
  const es = new EventSource(`/api/run/${run_id}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.node === "__end__") { es.close(); $("#run").disabled = false; renderCards(e.state); loadHistory(); return; }
    if (e.node === "__error__") { logEl.textContent += "⚠ 오류: " + e.error + "\n"; es.close(); $("#run").disabled = false; return; }
    onUpdate(e.node, e.update);
  };
  es.onerror = () => { es.close(); $("#run").disabled = false; };
}

function renderCards(state) { /* Task 9에서 채운다 */ }
async function loadHistory() { /* Task 10에서 채운다 */ }

$("#run").addEventListener("click", startRun);
loadHistory();
```

`web/static/style.css`:
```css
:root { --bg:#f6f7fb; --panel:#fff; --ink:#1f2333; --muted:#6b7280; --accent:#4f46e5; --line:#e5e7eb; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif; }
header { display:flex; justify-content:space-between; align-items:center; padding:16px 24px; background:var(--panel); border-bottom:1px solid var(--line); }
h1 { font-size:20px; margin:0; } h2 { font-size:15px; margin:0 0 10px; color:var(--muted); }
.controls { display:flex; gap:16px; align-items:center; }
.controls input[type=number] { width:64px; }
button { background:var(--accent); color:#fff; border:0; padding:8px 16px; border-radius:6px; cursor:pointer; }
button:disabled { opacity:.5; cursor:default; }
main { display:grid; grid-template-columns:260px 1fr; gap:16px; padding:16px 24px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; }
.wide { grid-column:1 / -1; }
#funnel ul { list-style:none; margin:0; padding:0; }
#funnel li { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--line); }
#log { margin:0; min-height:160px; white-space:pre-wrap; font-size:13px; }
.card { border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:10px; }
.card.rejected { opacity:.55; }
.card h3 { margin:0 0 6px; font-size:15px; }
.card .why { color:var(--accent); }
.card .meta { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }
@media (max-width:720px) { main { grid-template-columns:1fr; } }
```

- [ ] **Step 5: 테스트 통과 및 브라우저 확인**

Run: `uv run pytest tests/test_api.py -v`
Expected: 3 passed.

Run (백그라운드): `uv run uvicorn web.app:app --port 8000` 후 브라우저에서 http://127.0.0.1:8000 → [실행] 클릭 → 로그 5줄(전부 0건)이 흐르는지 확인.

- [ ] **Step 6: Commit**

```bash
git add web tests/test_api.py
git commit -m "feat: 대시보드 뼈대 — 실행 버튼과 SSE 로그"
```

---

### Task 3: 설정 파일과 로더 (수업 섹션 13 앞당김 — 소스 목록이 여기 산다)

**Files:**
- Create: `audience.yaml`, `newsletter/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Source` dataclass: `name:str, url:str, tier:int, kind:str` (`kind` ∈ `"rss"`, `"hn"`)
  - `Config` dataclass: `audience:str, question:str, topics:list[str], pick_count:int, tone:str, min_body:int, shortlist_batch:int, tier1_max:int, sources:list[Source]`
  - `load_config(path: str | Path = "audience.yaml") -> Config` — 필수 키 누락·타입 오류 시 `ConfigError`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.config`

- [ ] **Step 3: audience.yaml 작성**

```yaml
# 분야마다 달라지는 것은 전부 여기. 코드에는 AI 뉴스가 박혀 있지 않다.
audience: 국내 AI 개발팀
question: 이번 주 우리가 일하는 방식이 바뀔 만한가
topics: [모델·API, 인프라·비용, 규제·정책, 오픈소스, 제품·서비스]
pick_count: 5
tone: 간결한 존댓말. 과장 없이.
min_body: 600          # 요약을 쓰려면 원문이 최소 이만큼은 있어야 한다 (G1 관문)
shortlist_batch: 40    # 예선 한 묶음 크기
tier1_max: 2           # 당사자 발표(tier 1) 경쟁 면제 상한

sources:
  - {name: OpenAI,      url: https://openai.com/blog/rss.xml,                                          tier: 1, kind: rss}
  - {name: DeepMind,    url: https://deepmind.google/blog/rss.xml,                                     tier: 1, kind: rss}
  - {name: HuggingFace, url: https://huggingface.co/blog/feed.xml,                                     tier: 1, kind: rss}
  - {name: TechCrunch,  url: https://techcrunch.com/category/artificial-intelligence/feed/,            tier: 2, kind: rss}
  - {name: The Verge,   url: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml,        tier: 2, kind: rss}
  - {name: MIT TR,      url: https://www.technologyreview.com/feed/,                                   tier: 2, kind: rss}
  - {name: AI타임스,     url: https://www.aitimes.com/rss/allArticle.xml,                               tier: 2, kind: rss}
  - {name: Hacker News, url: "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI",      tier: 2, kind: hn}
```

- [ ] **Step 4: config.py 작성**

`newsletter/config.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add audience.yaml newsletter/config.py tests/test_config.py
git commit -m "feat: audience.yaml과 검증 로더 (섹션 13)"
```

---

### Task 4: ① 수집 노드 (수업 섹션 3~5)

**Files:**
- Create: `newsletter/nodes/collect.py`
- Modify: `newsletter/graph.py` (`real_nodes()` 추가), `run.py`, `web/app.py:get_nodes`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `Config`, `Source`, `Article`
- Produces:
  - `collect.parse_rss(name, tier, content: bytes) -> list[Article]`
  - `collect.parse_hn(name, tier, payload: dict) -> list[Article]`
  - `collect.fetch(source: Source, http_get) -> list[Article]` — `http_get(url) -> requests.Response` 형태
  - `collect.dedupe_key(url) -> str`
  - `collect.collect(state, sources: list[Source], http_get=requests.get, now=None) -> dict` — `{"collected", "log"}` 반환. 로그에 건수와 죽은 소스 이름
  - `graph.real_nodes(cfg: Config) -> dict[str, Callable]` — 채워진 노드는 진짜, 나머지는 stub

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_collect.py`:
```python
from datetime import datetime, timedelta, timezone

from newsletter.config import Source
from newsletter.nodes.collect import collect, dedupe_key, parse_hn, parse_rss

NOW = datetime(2026, 9, 14, 7, 30, tzinfo=timezone.utc)


def rss(items: list[tuple[str, str, datetime]]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        f"<pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
        f"<description>&lt;p&gt;요약 {t}&lt;/p&gt;</description></item>"
        for t, u, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class FakeResp:
    def __init__(self, content=b"", payload=None, status=200):
        self.content, self._payload, self.status_code = content, payload, status
    def json(self): return self._payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def test_parse_rss_strips_tags_and_isoformats_date():
    a = parse_rss("TC", 2, rss([("제목", "https://x/a", NOW)]))[0]
    assert a == {"title": "제목", "url": "https://x/a", "source": "TC", "tier": 2,
                 "at": "2026-09-14T07:30:00+00:00", "summary": "요약 제목"}


def test_parse_hn_uses_points_in_summary():
    payload = {"hits": [{"title": "HN글", "url": "https://y/b", "created_at": "2026-09-14T06:00:00Z",
                         "points": 120, "num_comments": 30}]}
    a = parse_hn("HN", 2, payload)[0]
    assert a["url"] == "https://y/b" and "120" in a["summary"]


def test_dedupe_key_drops_query_and_slash():
    assert dedupe_key("https://x/a/?utm_source=t") == dedupe_key("https://x/a")


def test_collect_filters_window_dedupes_and_isolates_dead_source():
    fresh, old = NOW - timedelta(hours=2), NOW - timedelta(hours=30)
    feeds = {
        "https://s1": FakeResp(rss([("a", "https://x/a", fresh), ("a2", "https://x/a?utm=1", fresh), ("old", "https://x/o", old)])),
    }
    def http_get(url, **kw):
        if url == "https://dead": raise ConnectionError("boom")
        return feeds[url]
    sources = [Source("S1", "https://s1", 2, "rss"), Source("Dead", "https://dead", 2, "rss")]
    out = collect({"hours": 24}, sources, http_get=http_get, now=NOW)
    assert [a["title"] for a in out["collected"]] == ["a"]
    assert "1건" in out["log"][0] and "Dead" in out["log"][0]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_collect.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.nodes.collect`

- [ ] **Step 3: collect.py 작성**

`newsletter/nodes/collect.py`:
```python
"""① 자료 수집. RSS(2칸)와 Hacker News 공개 API(1칸)에서 시간 창 안의 글을 모은다."""
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from newsletter.config import Source
from newsletter.state import Article

UA = {"User-Agent": "Mozilla/5.0 (newsletter-agent)"}
TIMEOUT = 20


def strip_tags(s: str | None) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def dedupe_key(url: str) -> str:
    """추적용 꼬리표(?utm=...)와 끝 슬래시를 떼고 비교한다."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def parse_rss(name: str, tier: int, content: bytes) -> list[Article]:
    out: list[Article] = []
    for e in feedparser.parse(content).entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t or not e.get("link"):
            continue                                  # 날짜·링크 없는 항목은 결과를 바꾸지 않으므로 조용히 버린다
        at = datetime(*t[:6], tzinfo=timezone.utc)
        body = e.get("content", [{}])[0].get("value") if e.get("content") else e.get("summary", "")
        out.append({"title": strip_tags(e.get("title")), "url": e.link, "source": name, "tier": tier,
                    "at": at.isoformat(), "summary": strip_tags(body)[:300]})
    return out


def parse_hn(name: str, tier: int, payload: dict) -> list[Article]:
    out: list[Article] = []
    for h in payload.get("hits", []):
        if not h.get("url"):
            continue
        at = datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
        out.append({"title": h.get("title", ""), "url": h["url"], "source": name, "tier": tier,
                    "at": at.isoformat(),
                    "summary": f"HN 추천 {h.get('points', 0)} · 댓글 {h.get('num_comments', 0)}"})
    return out


def fetch(source: Source, http_get=requests.get) -> list[Article]:
    r = http_get(source.url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    if source.kind == "hn":
        return parse_hn(source.name, source.tier, r.json())
    return parse_rss(source.name, source.tier, r.content)


def collect(state: dict, sources: list[Source], http_get=requests.get, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=state["hours"])
    items: list[Article] = []
    dead: list[str] = []
    seen: set[str] = set()
    for src in sources:
        try:
            fetched = fetch(src, http_get)
        except Exception:
            dead.append(src.name)                     # 한 곳이 죽어도 나머지는 계속. 죽은 곳은 반드시 남긴다
            continue
        for a in fetched:
            if datetime.fromisoformat(a["at"]) < cutoff:
                continue
            key = dedupe_key(a["url"])
            if key in seen:
                continue
            seen.add(key)
            items.append(a)
    items.sort(key=lambda a: a["at"], reverse=True)
    dead_note = f" · 실패 {', '.join(dead)}" if dead else ""
    return {"collected": items,
            "log": [f"① 수집    {state['hours']}시간 창 · {len(items)}건 · 소스 {len(sources) - len(dead)}/{len(sources)}{dead_note}"]}
```

- [ ] **Step 4: graph.py에 real_nodes 추가, run.py·web/app.py 연결**

`newsletter/graph.py` 끝에 추가:
```python
from functools import partial

from newsletter.config import Config
from newsletter.nodes.collect import collect


def real_nodes(cfg: Config) -> dict[str, Callable]:
    """채워진 노드는 진짜, 아직 안 채운 노드는 stub. 섹션마다 한 줄씩 늘어난다."""
    nodes = stub_nodes()
    nodes["collect"] = partial(collect, sources=cfg.sources)
    return nodes
```

`run.py` 수정: `stub_nodes` 대신
```python
from dotenv import load_dotenv
from newsletter.config import load_config
from newsletter.graph import real_nodes, run
...
    load_dotenv()
    result = run(real_nodes(load_config()), hours=a.hours, dry_run=a.dry_run)
```

`web/app.py`의 `get_nodes` 수정:
```python
from newsletter.config import load_config
from newsletter.graph import build, initial_state, real_nodes

def get_nodes():
    return real_nodes(load_config())
```
`tests/test_api.py`의 첫 테스트는 실제 네트워크를 타면 안 되므로 `monkeypatch.setattr(webapp, "get_nodes", stub_nodes)`를 추가한다 (`from newsletter.graph import stub_nodes`).

- [ ] **Step 5: 테스트 통과 및 실제 수집 확인**

Run: `uv run pytest -v`
Expected: 전부 passed.

Run: `uv run python run.py --dry-run`
Expected: `① 수집    24시간 창 · N건 · 소스 8/8` (N > 0). 나머지 네 줄은 0건.

- [ ] **Step 6: Commit**

```bash
git add newsletter/nodes/collect.py newsletter/graph.py run.py web/app.py tests
git commit -m "feat: ① 수집 노드 — RSS·HN, 시간 창, 중복 제거, 소스 실패 격리 (섹션 5)"
```

---

### Task 5: 관문 검사 스크립트 (수업 섹션 4)

**Files:**
- Create: `newsletter/sources_check.py`
- Test: `tests/test_sources_check.py`

**Interfaces:**
- Consumes: `collect.fetch`, `Config`
- Produces:
  - `sources_check.gate_body(articles, extract, min_body, sample=3) -> tuple[int,int]` (통과/검사)
  - `sources_check.gate_alive(articles, now, days=14) -> int` (최근 N일 건수)
  - `sources_check.gate_access(url) -> bool` (robots.txt 허용 여부)
  - CLI: `uv run python -m newsletter.sources_check` → 소스별 G1/G2/G3 표

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sources_check.py`:
```python
from datetime import datetime, timedelta, timezone

from newsletter.sources_check import gate_alive, gate_body

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def art(url, days_ago):
    return {"title": url, "url": url, "source": "s", "tier": 2, "summary": "",
            "at": (NOW - timedelta(days=days_ago)).isoformat()}


def test_gate_body_counts_extractions_over_threshold():
    arts = [art("a", 0), art("b", 0), art("c", 0)]
    extract = lambda u: "x" * 700 if u != "b" else "short"
    assert gate_body(arts, extract, min_body=600) == (2, 3)


def test_gate_alive_counts_recent_only():
    assert gate_alive([art("a", 1), art("b", 20)], NOW, days=14) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_sources_check.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: sources_check.py 작성**

```python
"""관문 G1(본문)·G2(생존)·G3(접근) 검사. 매일 돌리지 않고 소스를 채택할 때 한 번 돌린다."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import trafilatura

from newsletter.config import load_config
from newsletter.nodes.collect import UA, fetch


def extract_text(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    return (trafilatura.extract(downloaded) if downloaded else "") or ""


def gate_body(articles: list[dict], extract: Callable[[str], str], min_body: int, sample: int = 3) -> tuple[int, int]:
    picked = articles[:sample]
    ok = sum(1 for a in picked if len(extract(a["url"])) > min_body)
    return ok, len(picked)


def gate_alive(articles: list[dict], now: datetime, days: int = 14) -> int:
    cutoff = now - timedelta(days=days)
    return sum(1 for a in articles if datetime.fromisoformat(a["at"]) >= cutoff)


def gate_access(url: str) -> bool:
    p = urlparse(url)
    rp = RobotFileParser()
    try:
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA["User-Agent"], url)
    except Exception:
        return True                                  # robots.txt가 없으면 허용으로 본다


def main() -> None:
    cfg = load_config()
    now = datetime.now(timezone.utc)
    print(f"{'소스':<12}{'건수':>5}{'G1 본문':>9}{'G2 14일':>9}{'G3 접근':>9}")
    print("-" * 44)
    for src in cfg.sources:
        try:
            arts = fetch(src)
        except Exception as e:
            print(f"{src.name:<12}  실패: {e!r}")
            continue
        ok, n = gate_body(arts, extract_text, cfg.min_body)
        alive = gate_alive(arts, now)
        access = "허용" if gate_access(src.url) else "금지"
        print(f"{src.name:<12}{len(arts):>5}{f'{ok}/{n}':>9}{alive:>9}{access:>9}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 및 실제 검사 1회**

Run: `uv run pytest tests/test_sources_check.py -v` → 2 passed.
Run: `uv run python -m newsletter.sources_check` (1~2분) → 표가 출력됨. G1이 0/3인 소스가 있으면 `audience.yaml`에서 뺀다.

- [ ] **Step 5: Commit**

```bash
git add newsletter/sources_check.py tests/test_sources_check.py audience.yaml
git commit -m "feat: 소스 관문 검사 G1·G2·G3 (섹션 4)"
```

---

### Task 6: LLM 헬퍼와 ② 선별 노드 (수업 섹션 6~7)

**Files:**
- Create: `newsletter/llm.py`, `newsletter/nodes/select.py`
- Modify: `newsletter/graph.py:real_nodes`
- Test: `tests/test_select.py`

**Interfaces:**
- Produces:
  - `llm.ask_structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel` — OpenAI 구조화 출력. 실패 시 1회 재시도 후 예외
  - `select.Shortlist(BaseModel)`: `urls: list[str]`
  - `select.Final(BaseModel)`: `picks: list[FinalPick]`, `FinalPick`: `url:str, reason:str`
  - `select.select(state, cfg: Config, ask=llm.ask_structured) -> dict` — `{"picked", "log"}`
  - 규칙: tier 1은 최대 `cfg.tier1_max`건 경쟁 면제(최신순). 나머지를 `shortlist_batch`씩 예선 → 각 묶음에서 `pick_count`건 → 본선에서 남은 자리만큼. 코드로 정확히 `pick_count`건 강제(초과분 자르고, LLM이 모르는 URL 주면 무시)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_select.py`:
```python
from newsletter.config import Config
from newsletter.nodes.select import Final, FinalPick, Shortlist, select

CFG = Config(audience="a", question="q", topics=["t"], pick_count=3, tone="", min_body=600,
             shortlist_batch=4, tier1_max=1, sources=[])


def art(i, tier=2):
    return {"title": f"t{i}", "url": f"https://x/{i}", "source": "s", "tier": tier,
            "at": f"2026-09-14T0{i % 10}:00:00+00:00", "summary": f"s{i}"}


def fake_ask_factory(calls):
    def ask(system, user, schema):
        calls.append(schema.__name__)
        urls = [l.split()[0] for l in user.splitlines() if l.startswith("https://")]
        if schema is Shortlist:
            return Shortlist(urls=urls[:3] + ["https://unknown"])
        return Final(picks=[FinalPick(url=u, reason="이유") for u in urls[:5]])   # 일부러 초과 반환
    return ask


def test_select_prelim_batches_then_final_and_enforces_count():
    calls = []
    state = {"collected": [art(i) for i in range(9)]}
    out = select(state, CFG, ask=fake_ask_factory(calls))
    assert calls == ["Shortlist", "Shortlist", "Shortlist", "Final"]    # 9건 / 4 = 예선 3묶음
    assert len(out["picked"]) == 3
    assert all(p["reason"] == "이유" for p in out["picked"])
    assert "9 → 3건" in out["log"][0]


def test_tier1_bypasses_competition_with_cap():
    calls = []
    state = {"collected": [art(1, tier=1), art(2, tier=1), art(3), art(4)]}
    out = select(state, CFG, ask=fake_ask_factory(calls))
    tier1 = [p for p in out["picked"] if p["tier"] == 1]
    assert len(tier1) == 1 and tier1[0]["reason"] == "당사자 발표"
    assert len(out["picked"]) == 3


def test_small_input_skips_prelim():
    calls = []
    out = select({"collected": [art(1), art(2)]}, CFG, ask=fake_ask_factory(calls))
    assert calls == ["Final"] and len(out["picked"]) == 2
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_select.py -v` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: llm.py 작성**

```python
"""OpenAI 구조화 출력 헬퍼. 노드는 이 함수 하나만 안다."""
import os
from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel


@lru_cache
def get_client() -> OpenAI:
    return OpenAI()                                   # OPENAI_API_KEY 환경 변수 사용


def model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def ask_structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    last: Exception | None = None
    for _ in range(2):                                # 1회 재시도
        try:
            r = get_client().chat.completions.parse(
                model=model_name(),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format=schema,
            )
            parsed = r.choices[0].message.parsed
            if parsed is None:
                raise RuntimeError("모델이 스키마에 맞는 응답을 주지 않았습니다")
            return parsed
        except Exception as e:                        # noqa: BLE001
            last = e
    raise RuntimeError(f"LLM 호출 실패: {last!r}")
```

- [ ] **Step 4: select.py 작성**

```python
"""② 중요도 선별. 2단 상대평가 — 묶음 예선 → 본선. 건수는 코드가 강제한다."""
from pydantic import BaseModel

from newsletter import llm
from newsletter.config import Config
from newsletter.state import Article, Pick


class Shortlist(BaseModel):
    urls: list[str]


class FinalPick(BaseModel):
    url: str
    reason: str


class Final(BaseModel):
    picks: list[FinalPick]


def _lines(arts: list[Article]) -> str:
    return "\n".join(f"{a['url']} | {a['source']} | {a['title']} | {a['summary'][:120]}" for a in arts)


def _system(cfg: Config) -> str:
    return (f"당신은 '{cfg.audience}'을 위한 뉴스레터 편집자입니다. "
            f"기준: {cfg.question}. 관심 토픽: {', '.join(cfg.topics)}. "
            "같은 사건을 다룬 기사는 하나만 남깁니다. 홍보성 글은 제외합니다.")


def prelim(batch: list[Article], cfg: Config, ask) -> list[Article]:
    r = ask(_system(cfg),
            f"아래 기사 중 기준에 가장 맞는 {cfg.pick_count}건의 URL만 고르세요. 한 줄에 'URL | 출처 | 제목 | 요약'.\n\n{_lines(batch)}",
            Shortlist)
    by_url = {a["url"]: a for a in batch}
    return [by_url[u] for u in r.urls if u in by_url][:cfg.pick_count]


def final(cands: list[Article], n: int, cfg: Config, ask) -> list[Pick]:
    if n <= 0 or not cands:
        return []
    r = ask(_system(cfg),
            f"아래 후보를 서로 견주어 가장 중요한 순서로 정확히 {n}건을 고르고 각각 한 문장 이유를 쓰세요.\n\n{_lines(cands)}",
            Final)
    by_url = {a["url"]: a for a in cands}
    out: list[Pick] = []
    for p in r.picks:
        if p.url in by_url and all(o["url"] != p.url for o in out):
            out.append({**by_url[p.url], "reason": p.reason})
    return out[:n]                                    # 부탁은 지켜지지 않을 수 있다. 자르는 건 코드가 한다


def select(state: dict, cfg: Config, ask=llm.ask_structured) -> dict:
    collected: list[Article] = state["collected"]
    tier1 = sorted([a for a in collected if a["tier"] == 1], key=lambda a: a["at"], reverse=True)
    exempt: list[Pick] = [{**a, "reason": "당사자 발표"} for a in tier1[:cfg.tier1_max]]
    rest = [a for a in collected if a["url"] not in {e["url"] for e in exempt}]
    slots = cfg.pick_count - len(exempt)

    if len(rest) > cfg.shortlist_batch:
        batches = [rest[i:i + cfg.shortlist_batch] for i in range(0, len(rest), cfg.shortlist_batch)]
        cands = [a for b in batches for a in prelim(b, cfg, ask)]
        stage = f"예선 {len(batches)}묶음 → {len(cands)}건 → 본선"
    else:
        cands, stage = rest, "본선만"
    picked = exempt + final(cands, slots, cfg, ask)
    return {"picked": picked,
            "log": [f"② 선별    {len(collected)} → {len(picked)}건 · {stage} · 면제 {len(exempt)}"]}
```

- [ ] **Step 5: real_nodes에 연결**

`newsletter/graph.py`의 `real_nodes`:
```python
from newsletter.nodes.select import select
...
    nodes["select"] = partial(select, cfg=cfg)
```

- [ ] **Step 6: 테스트 통과 및 실제 실행**

Run: `uv run pytest -v` → 전부 passed.
Run: `uv run python run.py --dry-run` (OPENAI_API_KEY 필요) → `② 선별    N → 5건 · 예선 ...`. 화면에서도 선별 숫자가 5로 바뀌는지 확인.

- [ ] **Step 7: Commit**

```bash
git add newsletter/llm.py newsletter/nodes/select.py newsletter/graph.py tests/test_select.py
git commit -m "feat: ② 선별 노드 — 예선→본선 2단 상대평가, 건수 강제 (섹션 7)"
```

---

### Task 7: ③ 취재(요약) 노드 — 본문 추출, 팬아웃, 3칸 (수업 섹션 8)

**Files:**
- Create: `newsletter/nodes/report.py`
- Modify: `newsletter/graph.py` (`build`에 팬아웃 엣지, `real_nodes`)
- Test: `tests/test_report.py`, `tests/test_graph.py`

**Interfaces:**
- Produces:
  - `report.DraftOut(BaseModel)`: `headline:str, summary:str, why:str`
  - `report.extract_body(url) -> str`
  - `report.draft(pick: Pick, cfg, ask, extract) -> Draft | None` — 본문 `< cfg.min_body`면 None
  - `report.report_worker(state: dict, cfg, ask, extract) -> dict` — 입력 `{"pick": Pick}`(Send 페이로드). 반환 `{"drafted": [Draft] | [], "log": [...]}`
  - `report.fan_report(state) -> list[Send]` — picked 하나당 `Send("report", {"pick": p})`. 0건이면 `[Send("report_none", {})]` 대신 빈 리스트 반환하지 않고 `verify`로 곧장 가도록 `graph.build`에서 처리
  - `graph.build`: `select --(conditional: fan_report)--> report ×N --> verify`. picked가 비면 `select → verify`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_report.py`:
```python
from newsletter.config import Config
from newsletter.nodes.report import DraftOut, draft, report_worker

CFG = Config(audience="a", question="q", topics=[], pick_count=5, tone="존댓말", min_body=600,
             shortlist_batch=40, tier1_max=2, sources=[])
PICK = {"title": "t", "url": "https://x/1", "source": "s", "tier": 2, "at": "2026-09-14T00:00:00+00:00",
        "summary": "s", "reason": "r"}


def fake_ask(system, user, schema):
    assert "존댓말" in system
    return DraftOut(headline="H", summary="S1. S2. S3.", why="W")


def test_draft_returns_three_fields_and_body():
    d = draft(PICK, CFG, ask=fake_ask, extract=lambda u: "본문" * 400)
    assert d["headline"] == "H" and d["why"] == "W" and len(d["body"]) >= 600 and d["reason"] == "r"


def test_draft_returns_none_when_body_too_short():
    assert draft(PICK, CFG, ask=fake_ask, extract=lambda u: "짧음") is None


def test_worker_logs_extraction_failure_instead_of_silently_dropping():
    out = report_worker({"pick": PICK}, CFG, ask=fake_ask, extract=lambda u: "")
    assert out["drafted"] == [] and "본문 부족" in out["log"][0]
```

`tests/test_graph.py`에 추가:
```python
def test_report_fans_out_per_pick():
    nodes = stub_nodes()
    nodes["select"] = lambda s: {"picked": [{"url": "a"}, {"url": "b"}], "log": ["② 2건"]}
    nodes["report"] = lambda s: {"drafted": [{"url": s["pick"]["url"]}], "log": [f"③ {s['pick']['url']}"]}
    out = build(nodes).compile().invoke(initial_state(24, True))
    assert sorted(d["url"] for d in out["drafted"]) == ["a", "b"]


def test_no_picks_goes_straight_to_verify():
    out = run(stub_nodes(), hours=24, dry_run=True)
    assert [l[0] for l in out["log"]] == ["①", "②", "④", "⑤"]
```
(첫 테스트 `test_stub_pipeline_runs_five_nodes_in_order`는 picked가 0건이면 ③이 안 돌므로 기대값을 `["①","②","④","⑤"]`로 고친다.)

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_report.py tests/test_graph.py -v` → FAIL

- [ ] **Step 3: report.py 작성**

```python
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
```

- [ ] **Step 4: graph.py 수정 — 팬아웃 엣지와 real_nodes**

`build` 함수 교체:
```python
from newsletter.nodes.report import fan_report, report_worker


def build(nodes: dict[str, Callable]) -> StateGraph:
    g = StateGraph(Brief)
    for name in NODE_ORDER:
        g.add_node(name, nodes[name])
    g.add_edge(START, "collect")
    g.add_edge("collect", "select")
    g.add_conditional_edges("select", fan_report, ["report", "verify"])   # 기사 수만큼 펼친다
    g.add_edge("report", "verify")
    g.add_edge("verify", "publish")
    g.add_edge("publish", END)
    return g
```
`stub_nodes`의 `report`를 Send 페이로드를 받는 모양으로 바꾼다:
```python
"report": lambda s: {"drafted": [], "log": [f"③ 취재    {s['pick']['title']} (빈 노드)"]},
```
`real_nodes`에 추가:
```python
    nodes["report"] = partial(report_worker, cfg=cfg)
```

- [ ] **Step 5: 테스트 통과 및 실제 실행**

Run: `uv run pytest -v` → 전부 passed.
Run: `uv run python run.py --dry-run` → `③ 취재    완료 · ...` 줄이 기사 수만큼. 화면에서 취재 숫자 확인.

- [ ] **Step 6: Commit**

```bash
git add newsletter/nodes/report.py newsletter/graph.py tests
git commit -m "feat: ③ 취재 노드 — 본문 추출, 기사별 팬아웃, 3칸 출력 (섹션 8)"
```

---

### Task 8: ④ 검수 노드 — LLM 대조 (수업 섹션 9)

**Files:**
- Create: `newsletter/nodes/verify.py`
- Modify: `newsletter/graph.py:real_nodes`
- Test: `tests/test_verify.py`

**Interfaces:**
- Produces:
  - `verify.VerdictOut(BaseModel)`: `grounded: bool, reason: str`
  - `verify.check(draft: Draft, ask) -> Verdict` — headline·summary만 원문과 대조. why는 넣지 않음
  - `verify.verify(state, ask) -> dict` — `{"verified": [통과분], "rejected": [Verdict...], "log"}`. `rejected`는 State에 없으므로 `verified`에 포함 안 되고 로그로만 남긴다. (State 키 추가는 하지 않는다 — 대신 로그에 탈락 사유를 한 줄씩)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_verify.py`:
```python
from newsletter.nodes.verify import VerdictOut, check, verify

D = {"title": "t", "url": "https://x/1", "source": "s", "tier": 2, "at": "", "summary": "3개월 전 6000만 달러",
     "reason": "r", "headline": "H", "why": "이건 해석", "body": "three months after raised $60 million"}


def test_check_sends_headline_and_summary_but_not_why():
    seen = {}
    def ask(system, user, schema):
        seen["user"] = user
        return VerdictOut(grounded=True, reason="번역·단위 환산일 뿐")
    v = check(D, ask)
    assert v == {"url": "https://x/1", "ok": True, "reason": "번역·단위 환산일 뿐"}
    assert "3개월 전" in seen["user"] and "이건 해석" not in seen["user"]


def test_verify_keeps_only_grounded_and_logs_rejections():
    bad = {**D, "url": "https://x/2", "summary": "업계 최초"}
    def ask(system, user, schema):
        return VerdictOut(grounded="업계 최초" not in user, reason="근거 없음")
    out = verify({"drafted": [D, bad]}, ask)
    assert [d["url"] for d in out["verified"]] == ["https://x/1"]
    assert "1/2 통과" in out["log"][0] and any("근거 없음" in l for l in out["log"])


def test_verify_zero_drafts():
    out = verify({"drafted": []}, ask=lambda *a: None)
    assert out["verified"] == [] and "0/0" in out["log"][0]
```

- [ ] **Step 2: 실패 확인** → `uv run pytest tests/test_verify.py -v` FAIL

- [ ] **Step 3: verify.py 작성**

```python
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
```

- [ ] **Step 4: real_nodes 연결**

```python
from newsletter.nodes.verify import verify
...
    nodes["verify"] = verify
```

- [ ] **Step 5: 테스트 통과 및 실제 실행** → `uv run pytest -v`, `uv run python run.py --dry-run` → `④ 검수    N/M 통과`

- [ ] **Step 6: Commit**

```bash
git add newsletter/nodes/verify.py newsletter/graph.py tests/test_verify.py
git commit -m "feat: ④ 검수 노드 — LLM 원문 대조, why 제외 (섹션 9)"
```

---

### Task 9: ⑤ 발행 노드 — dry_run과 Discord, 대시보드 카드 (수업 섹션 10)

**Files:**
- Create: `newsletter/nodes/publish.py`
- Modify: `newsletter/graph.py:real_nodes`, `web/static/app.js:renderCards`, `web/app.py`(published_count 전달 없음 — 로그로 판단)
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces:
  - `publish.render_discord(drafts: list[Draft], title: str) -> dict` — Discord 웹훅 payload (`content` + `embeds`)
  - `publish.render_text(drafts) -> str` — dry_run 미리보기
  - `publish.publish(state, post, webhook_url: str | None) -> dict` — `{"log"}`. dry_run이면 `post` 호출 없음. 0건이면 보내지 않음. 웹훅 실패는 예외로 올림 (조용히 넘기지 않음)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_publish.py`:
```python
import pytest

from newsletter.nodes.publish import publish, render_discord

D = {"title": "t", "url": "https://x/1", "source": "TechCrunch", "tier": 2, "at": "", "summary": "S",
     "reason": "r", "headline": "H", "why": "W", "body": "b"}


def test_render_discord_has_embed_per_draft():
    p = render_discord([D, {**D, "url": "https://x/2"}], "오늘의 AI 뉴스")
    assert p["content"].startswith("**오늘의 AI 뉴스") and len(p["embeds"]) == 2
    assert p["embeds"][0]["url"] == "https://x/1" and "W" in p["embeds"][0]["description"]


def test_dry_run_never_posts():
    calls = []
    out = publish({"dry_run": True, "verified": [D]}, post=lambda *a, **k: calls.append(1), webhook_url="https://hook")
    assert calls == [] and "dry_run" in out["log"][0] and "1건" in out["log"][0]


def test_real_run_posts_once():
    calls = []
    class R:
        def raise_for_status(self): pass
    publish({"dry_run": False, "verified": [D]}, post=lambda url, json, timeout: calls.append(url) or R(), webhook_url="https://hook")
    assert calls == ["https://hook"]


def test_zero_verified_does_not_post():
    calls = []
    out = publish({"dry_run": False, "verified": []}, post=lambda *a, **k: calls.append(1), webhook_url="https://hook")
    assert calls == [] and "0건" in out["log"][0]


def test_missing_webhook_raises_when_not_dry_run():
    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        publish({"dry_run": False, "verified": [D]}, post=lambda *a, **k: None, webhook_url=None)
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: publish.py 작성**

```python
"""⑤ 발행. 되돌릴 수 없는 단계라 LLM이 없고, dry_run이 먼저다."""
from datetime import datetime

import requests

from newsletter.state import Draft


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


def publish(state: dict, post=requests.post, webhook_url: str | None = None) -> dict:
    drafts: list[Draft] = state["verified"]
    n = len(drafts)
    if n == 0:
        return {"log": ["⑤ 발행    0건 · 보낼 것이 없어 건너뜀"]}
    if state["dry_run"]:
        return {"log": [f"⑤ 발행    dry_run · {n}건 (보내지 않음)", *render_text(drafts).splitlines()]}
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL이 없습니다")
    title = f"AI 뉴스레터 {datetime.now().strftime('%Y-%m-%d')}"
    r = post(webhook_url, json=render_discord(drafts, title), timeout=20)
    r.raise_for_status()                              # 실패를 조용히 넘기지 않는다
    return {"log": [f"⑤ 발행    Discord · {n}건"]}
```

- [ ] **Step 4: real_nodes 연결**

```python
import os
from newsletter.nodes.publish import publish
...
    nodes["publish"] = partial(publish, webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"))
```

- [ ] **Step 5: 대시보드 카드 렌더**

`web/static/app.js`의 `renderCards`와 `onUpdate`의 publish 부분 교체:
```javascript
function renderCards(state) {
  const okUrls = new Set((state.verified || []).map(d => d.url));
  const rejectedReason = {};
  (state.log || []).forEach(l => { const m = l.match(/✗ 탈락 · (.+?) · (.+?) · (.+)$/); if (m) rejectedReason[m[2]] = m[3]; });
  $("#cardlist").innerHTML = (state.drafted || []).map(d => {
    const ok = okUrls.has(d.url);
    const reason = ok ? "" : `<div class="meta">검수 탈락: ${rejectedReason[d.headline.slice(0,30)] || "사유 로그 참조"}</div>`;
    return `<article class="card ${ok ? "" : "rejected"}">
      <h3><a href="${d.url}" target="_blank" rel="noopener">${d.headline}</a></h3>
      <p>${d.summary}</p><p class="why">왜 중요한가 · ${d.why}</p>
      <div class="meta">${d.source} · ${d.at.slice(0,16).replace("T"," ")}</div>${reason}</article>`;
  }).join("") || "<p class='meta'>발행 카드가 없습니다.</p>";
  setFunnel("published", state.dry_run ? `${(state.verified||[]).length} (dry)` : (state.verified||[]).length);
}
```
`onUpdate`에서 `if (node === "publish") ...` 줄은 삭제한다 (`__end__`에서 처리).

- [ ] **Step 6: 테스트 통과 및 실제 실행**

Run: `uv run pytest -v` → 전부 passed.
Run: `uv run python run.py --dry-run` → 다섯 줄이 전부 0이 아닌 숫자. 대시보드에서 카드가 뜨는지 확인.
Run (Discord 웹훅 설정 후 1회): `uv run python run.py` → Discord 채널에 임베드 도착 확인.

- [ ] **Step 7: Commit**

```bash
git add newsletter/nodes/publish.py newsletter/graph.py web/static/app.js tests/test_publish.py
git commit -m "feat: ⑤ 발행 노드 — dry_run, Discord 웹훅, 대시보드 카드 (섹션 10)"
```

---

### Task 10: 지표 남기기와 과거 실행 화면 (수업 섹션 12)

**Files:**
- Create: `newsletter/metrics.py`
- Modify: `run.py`, `web/app.py` (`/api/runs`, `/api/config`, 실행 끝에 지표 append), `web/static/app.js:loadHistory`
- Test: `tests/test_metrics.py`, `tests/test_api.py`

**Interfaces:**
- Produces:
  - `metrics.summarize(state: Brief, run_id: str, seconds: dict[str, float]) -> dict` — 스펙의 JSON 한 줄 모양
  - `metrics.append_metrics(row: dict, path: Path) -> None`
  - `metrics.read_metrics(path: Path) -> list[dict]`
  - `graph.run_timed(nodes, hours, dry_run) -> tuple[Brief, dict[str, float]]` — 노드별 소요 초
  - `GET /api/runs` → `read_metrics(STORE_DIR/"metrics.jsonl")`
  - `GET /api/config` → audience.yaml dataclass를 dict로

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_metrics.py`:
```python
import json

from newsletter.metrics import append_metrics, read_metrics, summarize

STATE = {"hours": 24, "dry_run": True,
         "collected": [{"source": "A", "url": "1"}, {"source": "B", "url": "2"}, {"source": "A", "url": "3"}],
         "picked": [{"source": "A", "url": "1"}, {"source": "B", "url": "2"}],
         "drafted": [{"source": "A", "url": "1"}],
         "verified": [{"source": "A", "url": "1"}],
         "log": ["① 수집    24시간 창 · 3건 · 소스 1/2 · 실패 Dead", "③ 취재    본문 부족 → 제외 · B · x"]}


def test_summarize_builds_funnel_row():
    row = summarize(STATE, "r1", {"collect": 1.5, "report": 3.0})
    assert row["run_id"] == "r1" and row["collected"] == 3 and row["picked"] == 2
    assert row["drafted"] == 1 and row["verified"] == 1 and row["published"] == 1
    assert row["extract_ok"] == 1 and row["dead_sources"] == ["Dead"]
    assert row["by_source"] == {"A": 1} and row["seconds"]["report"] == 3.0 and row["dry_run"] is True


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "m.jsonl"
    append_metrics({"run_id": "a", "collected": 1}, p)
    append_metrics({"run_id": "b", "collected": 2}, p)
    assert [r["run_id"] for r in read_metrics(p)] == ["a", "b"]
    assert len(p.read_text().strip().splitlines()) == 2


def test_read_missing_file_is_empty(tmp_path):
    assert read_metrics(tmp_path / "none.jsonl") == []
```

`tests/test_api.py`에 추가:
```python
def test_runs_and_config_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "STORE_DIR", tmp_path)
    (tmp_path / "metrics.jsonl").write_text('{"run_id":"a","collected":3}\n')
    c = TestClient(webapp.app)
    assert c.get("/api/runs").json() == [{"run_id": "a", "collected": 3}]
    cfg = c.get("/api/config").json()
    assert cfg["pick_count"] == 5 and isinstance(cfg["sources"], list)
```
그리고 첫 테스트 `test_run_streams_five_node_events`에 `assert (tmp_path / "metrics.jsonl").exists()`를 추가한다.

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: metrics.py 작성**

```python
"""실행마다 JSON 한 줄. DB도 대시보드 도구도 없이 파일 append."""
import json
import re
from collections import Counter
from pathlib import Path


def summarize(state: dict, run_id: str, seconds: dict[str, float]) -> dict:
    dead: list[str] = []
    for line in state.get("log", []):
        m = re.search(r"실패 (.+)$", line) if line.startswith("① 수집") else None
        if m:
            dead = [s.strip() for s in m.group(1).split(",")]
    published = 0 if state.get("dry_run") else len(state.get("verified", []))
    return {
        "run_id": run_id,
        "hours": state.get("hours"),
        "collected": len(state.get("collected", [])),
        "picked": len(state.get("picked", [])),
        "drafted": len(state.get("drafted", [])),
        "extract_ok": len(state.get("drafted", [])),          # drafted에 남은 것 = 본문 추출 성공
        "verified": len(state.get("verified", [])),
        "published": len(state.get("verified", [])) if state.get("dry_run") else published,
        "dead_sources": dead,
        "by_source": dict(Counter(d["source"] for d in state.get("verified", []))),
        "seconds": {k: round(v, 2) for k, v in seconds.items()},
        "dry_run": bool(state.get("dry_run")),
    }


def append_metrics(row: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_metrics(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
```

- [ ] **Step 4: graph.run_timed 추가, run.py·web/app.py에서 지표 저장**

`newsletter/graph.py`에 추가:
```python
import time


def run_timed(nodes: dict[str, Callable], hours: int = 24, dry_run: bool = True) -> tuple[Brief, dict[str, float]]:
    """노드별 소요 시간을 함께 돌려준다. 대시보드는 stream을 직접 쓰므로 CLI 전용."""
    state = initial_state(hours, dry_run)
    seconds: dict[str, float] = {}
    t = time.perf_counter()
    for update in build(nodes).compile().stream(state, stream_mode="updates"):
        for node, delta in update.items():
            now = time.perf_counter()
            seconds[node] = seconds.get(node, 0.0) + (now - t)
            t = now
            for k, v in delta.items():
                state[k] = state.get(k, []) + v if k in ("drafted", "log") else v
    return state, seconds
```

`run.py` 본문:
```python
from datetime import datetime, timezone
from pathlib import Path

from newsletter.metrics import append_metrics, summarize
from newsletter.graph import real_nodes, run_timed
...
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    state, seconds = run_timed(real_nodes(load_config()), hours=a.hours, dry_run=a.dry_run)
    for line in state["log"]:
        print(line)
    append_metrics(summarize(state, run_id, seconds), Path("store") / "metrics.jsonl")
```

`web/app.py`: `run_events`의 `gen()` 안에서 노드별 시간을 재고 `_save` 다음에 지표를 append:
```python
import time
from dataclasses import asdict
from newsletter.metrics import append_metrics, read_metrics, summarize
...
            seconds: dict[str, float] = {}
            t = time.perf_counter()
            for update in graph.stream(state, stream_mode="updates"):
                for node, delta in update.items():
                    now = time.perf_counter(); seconds[node] = seconds.get(node, 0.0) + (now - t); t = now
                    yield _sse({"node": node, "update": delta})
                    state = _merge(state, delta)
            state["run_id"] = run_id
            _save(run_id, state)
            append_metrics(summarize(state, run_id, seconds), STORE_DIR / "metrics.jsonl")
```
엔드포인트 추가:
```python
@app.get("/api/runs")
def list_runs():
    return read_metrics(STORE_DIR / "metrics.jsonl")


@app.get("/api/config")
def get_config():
    return asdict(load_config())
```

- [ ] **Step 5: app.js loadHistory 구현**

```javascript
async function loadHistory() {
  const rows = await (await fetch("/api/runs")).json();
  const head = "<tr><th>실행</th><th>수집</th><th>선별</th><th>취재</th><th>검수</th><th>발행</th><th>실패 소스</th><th>초</th></tr>";
  $("#runs").innerHTML = head + rows.slice(-30).reverse().map(r => {
    const secs = Object.values(r.seconds || {}).reduce((a, b) => a + b, 0).toFixed(1);
    const id = `<a href="#" data-run="${r.run_id}">${r.run_id}</a>${r.dry_run ? " (dry)" : ""}`;
    return `<tr><td>${id}</td><td>${r.collected}</td><td>${r.picked}</td><td>${r.drafted}</td><td>${r.verified}</td><td>${r.published}</td><td>${(r.dead_sources||[]).join(", ")}</td><td>${secs}</td></tr>`;
  }).join("");
  $("#runs").querySelectorAll("a[data-run]").forEach(a => a.addEventListener("click", async (ev) => {
    ev.preventDefault();
    const s = await (await fetch(`/api/run/${a.dataset.run}`)).json();
    logEl.textContent = (s.log || []).join("\n");
    ["collected","picked","drafted","verified"].forEach(k => setFunnel(k, (s[k]||[]).length));
    renderCards(s);
  }));
}
```

- [ ] **Step 6: 테스트 통과 및 확인**

Run: `uv run pytest -v` → 전부 passed.
Run: `uv run python run.py --dry-run && tail -1 store/metrics.jsonl` → JSON 한 줄. 대시보드 "과거 실행" 표에 행이 보이고 클릭하면 그 실행이 다시 그려진다.

- [ ] **Step 7: Commit**

```bash
git add newsletter/metrics.py newsletter/graph.py run.py web tests
git commit -m "feat: metrics.jsonl 지표와 과거 실행 화면 (섹션 12)"
```

---

### Task 11: GitHub Actions 매일 실행 (수업 섹션 11)

**Files:**
- Create: `.github/workflows/daily.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `run.py`, Secrets `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`

- [ ] **Step 1: 워크플로 작성**

`.github/workflows/daily.yml`:
```yaml
name: daily-newsletter
on:
  schedule:
    - cron: "30 22 * * *"        # 07:30 KST
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Discord로 보내지 않고 로그만"
        type: boolean
        default: false

permissions:
  contents: write                 # metrics.jsonl 커밋용

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --no-dev
      - name: 파이프라인 실행
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: |
          if [ "${{ inputs.dry_run }}" = "true" ]; then uv run python run.py --hours 24 --dry-run; else uv run python run.py --hours 24; fi
      - name: 실행 기록 커밋
        run: |
          git config user.name "newsletter-bot"
          git config user.email "bot@users.noreply.github.com"
          git add -f store/metrics.jsonl
          git diff --cached --quiet || git commit -m "chore: 실행 기록 $(date -u +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: README에 셋업 절차 추가**

```markdown
## 매일 아침 자동 실행
1. GitHub 저장소 → Settings → Secrets and variables → Actions
   - Secrets: `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`
   - Variables(선택): `OPENAI_MODEL`
2. Actions 탭 → daily-newsletter → Run workflow (dry_run 체크) 로 수동 1회 검증
3. 이후 매일 07:30 KST 자동 실행. 실행 기록은 `store/metrics.jsonl`에 커밋됨
```

- [ ] **Step 3: 로컬 검증**

Run: `uv run pytest -v` → 전부 passed (워크플로는 테스트 대상 아님).
`git remote -v`로 원격이 있는지 확인. 없으면 사용자에게 GitHub 저장소 생성과 Secrets 등록을 요청하고, push 후 Actions 탭에서 `workflow_dispatch`(dry_run) 1회 실행해 초록 체크를 확인한다.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/daily.yml README.md
git commit -m "ci: 매일 07:30 KST 자동 실행 워크플로 (섹션 11)"
```

---

## Self-Review

**Spec coverage**
- §1 범위: 섹션 2~13 코드 → Task 1,3~10. 대시보드 → Task 2,9,10. Actions → Task 11. ✓
- §2 폴더 구조: 스펙의 `sources.py`는 Task 3(`config.py`에 소스 목록)과 Task 5(`sources_check.py`)로 나뉨. 파일명 차이는 스펙보다 책임 분리가 명확해서 채택. ✓
- §3 State·리듀서·노드 규칙·팬아웃·metrics 모양·audience.yaml 검증 → Task 1,4,6,7,8,9,10,3. ✓
- §4 화면·API 5개·SSE → Task 2,9,10. ✓
- §5 Actions cron·Secrets·기록 커밋 → Task 11. ✓
- §6 에러 처리: 소스 격리(T4), 추출 실패 로그(T7), LLM 1회 재시도(T6 llm.py), 검수 0건 시 미발행(T9), 웹훅 실패 예외(T9), SSE `__error__` 이벤트(T2). ✓
- §7 테스트 목록 전부 대응. ✓
- §8 순서: 스펙의 "10 audience.yaml 분리"를 Task 3으로 앞당김 — 소스 목록이 collect의 입력이라 먼저 있어야 한다. 스펙 의도(설정과 코드 분리)는 그대로. ✓

**Placeholder scan**: Task 2 app.js의 `renderCards`/`loadHistory`는 "Task 7/9에서 채운다" 주석 — 실제로는 Task 9·10에서 채워지므로 주석을 `Task 9`, `Task 10`으로 읽는다. 코드 본문은 해당 태스크에 전부 있음. ✓

**Type consistency**: `Article.at`은 ISO 문자열(collect가 `isoformat()`), metrics·sources_check·select 전부 `fromisoformat`/문자열 정렬로 일관. `report_worker`는 Send 페이로드 `{"pick": Pick}`을 받고, stub의 report도 같은 모양. `verify` 반환 키는 `verified`·`log`뿐(스펙의 `rejected` 키는 State에 넣지 않고 로그로). `publish`는 `post(url, json=, timeout=)` 시그니처로 테스트와 일치. ✓
