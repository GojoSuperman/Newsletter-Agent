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
from pydantic import BaseModel, Field

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


def _load_settings() -> st.Settings:
    """settings.json이 깨져 있으면(수동 편집 등) 500으로 명확히 알린다 — 파일을 고치거나 지우면 된다."""
    try:
        return st.load(SETTINGS_PATH)
    except ValueError as e:
        raise HTTPException(500, f"설정 파일을 읽을 수 없습니다: {e}")


# ---------- 설정 ----------
class SettingsIn(BaseModel):
    openai_api_key: str | None = None
    openai_model: str | None = None
    discord_webhook_url: str | None = None
    hours: int | None = None


@app.get("/api/settings")
def get_settings():
    return st.masked(_load_settings())


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
    hours: int | None = Field(default=None, ge=1, le=168)


@app.post("/api/run")
def start_run(body: RunIn):
    s = _load_settings()
    if not s.openai_api_key:
        raise HTTPException(400, "OpenAI 키를 설정하세요")
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
        try:
            pending = _pending.get(run_id)
            if pending is None:
                yield _sse({"node": "__error__", "error": "실행 정보가 사라졌습니다"})
                return
            pending["running"] = True
            hours = pending["hours"]
            st.apply_env(_load_settings())    # 설정은 실행 시점의 것을 쓴다
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
            # 여기서 다시 raise하지 않는다: SSE 스트림은 이미 응답이 시작된 뒤라
            # 예외를 올려도 클라이언트에 전달되지 않고, __error__ 이벤트가
            # 리더 앱에서 실패를 알리는 유일한 통로이기 때문이다.
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
    if state.get("dry_run") is False:
        raise HTTPException(409, "이미 발행된 호입니다")
    drafts = state.get("verified", [])
    if not drafts:
        raise HTTPException(400, "보낼 기사가 없습니다")
    s = _load_settings()
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
