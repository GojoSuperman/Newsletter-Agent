#!/usr/bin/env bash
# 리더 앱을 끈다. (Windows 바로가기가 호출) — 시작 스크립트가 남긴 PID의 프로세스 그룹을 종료하고 포트가 닫힐 때까지 기다린다.
cd "$(dirname "$0")/.."
PORT=8100
PIDFILE=store/local/reader.pid
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill -- -"$(cat "$PIDFILE")" 2>/dev/null || kill "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
  for _ in $(seq 1 20); do
    curl -sf --max-time 1 -o /dev/null "http://127.0.0.1:$PORT/api/settings" || { echo "리더 앱을 종료했습니다."; exit 0; }
    sleep 0.5
  done
  echo "종료 신호를 보냈지만 아직 응답 중입니다."
else
  rm -f "$PIDFILE"
  echo "실행 중인 리더 앱이 없습니다."
fi
