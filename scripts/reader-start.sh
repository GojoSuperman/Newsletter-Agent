#!/usr/bin/env bash
# 리더 앱을 백그라운드로 켠다. 이미 켜져 있으면 그대로 둔다. (Windows 바로가기가 호출)
set -e
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
PORT=8100
PIDFILE=store/local/reader.pid
if curl -sf --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/api/settings"; then
  echo "이미 실행 중: http://127.0.0.1:$PORT"
  exit 0
fi
mkdir -p store/local
# setsid: 새 세션으로 띄워 호출한 창이 닫혀도 살아남게. stdin/stdout 분리: 호출자가 기다리지 않게.
setsid nohup uv run uvicorn app.server:app --host 127.0.0.1 --port "$PORT" > store/local/reader.log 2>&1 < /dev/null &
echo $! > "$PIDFILE"
for _ in $(seq 1 40); do
  sleep 0.5
  if curl -sf --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/api/settings"; then echo "시작됨: http://127.0.0.1:$PORT"; exit 0; fi
done
echo "시작 실패 — store/local/reader.log 확인" >&2
exit 1
