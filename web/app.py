"""대시보드 서버. 그래프를 stream()으로 돌리며 노드마다 SSE 이벤트를 흘린다."""
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(find_dotenv(usecwd=True))   # real_nodes()가 os.environ을 읽기 전에 .env를 먼저 반영한다

from newsletter.config import load_config  # noqa: E402
from newsletter.graph import build, initial_state, merge_delta, real_nodes  # noqa: E402
from newsletter.metrics import append_metrics, read_metrics, summarize  # noqa: E402

STORE_DIR = Path("store")
STALE_SECONDS = 60
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="뉴스레터 에이전트")

_pending: dict[str, dict] = {}       # run_id -> {"hours", "dry_run"} (아직 시작 안 함)
_lock = threading.Lock()


def get_nodes():
    """실행에 쓸 노드 매핑. 채워진 노드는 진짜, 나머지는 stub."""
    return real_nodes(load_config())


class RunRequest(BaseModel):
    hours: int = 24
    dry_run: bool = True


@app.post("/api/run")
def start_run(req: RunRequest):
    with _lock:
        now = time.monotonic()
        for rid in [k for k, v in _pending.items()
                    if not v["running"] and now - v["created_at"] > STALE_SECONDS]:
            _pending.pop(rid, None)                  # 버려진 run(스트림을 안 연 채 방치) 정리
        if _pending:
            raise HTTPException(409, "이미 실행 중입니다")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        _pending[run_id] = {"hours": req.hours, "dry_run": req.dry_run, "running": False, "created_at": now}
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
            seconds: dict[str, float] = {}
            t = time.perf_counter()
            for update in graph.stream(state, stream_mode="updates"):
                for node, delta in update.items():
                    now = time.perf_counter()
                    seconds[node] = seconds.get(node, 0.0) + (now - t)
                    t = now
                    yield _sse({"node": node, "update": delta})
                    state = merge_delta(state, delta)
            state["run_id"] = run_id
            _save(run_id, state)
            append_metrics(summarize(state, run_id, seconds), STORE_DIR / "metrics.jsonl")
            yield _sse({"node": "__end__", "state": state})
        except Exception as e:                      # 화면에 에러를 보여야 한다
            yield _sse({"node": "__error__", "error": repr(e)})
            raise
        finally:
            with _lock:
                _pending.pop(run_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


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


@app.get("/api/runs")
def list_runs():
    return read_metrics(STORE_DIR / "metrics.jsonl")


@app.get("/api/config")
def get_config():
    return asdict(load_config())


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
