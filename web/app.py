"""대시보드 서버. 그래프를 stream()으로 돌리며 노드마다 SSE 이벤트를 흘린다."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from newsletter.config import load_config
from newsletter.graph import build, initial_state, real_nodes

STORE_DIR = Path("store")
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
        if _pending:
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
            with _lock:
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
