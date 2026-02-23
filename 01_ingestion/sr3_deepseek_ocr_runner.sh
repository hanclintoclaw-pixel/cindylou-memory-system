#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

: "${RAW_ROOT:=/Volumes/carbonite/GDrive/cindylou}"
: "${HELPER:=}"

ROOT="${RAW_ROOT}/Shadowrun_3e_Rules_Library/organized_3e"
if [[ -z "$HELPER" ]]; then
  HELPER="$REPO_ROOT/01_ingestion/helper_scripts"
fi
PY="$HELPER/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi
TASK="$HELPER/run_remote_deepseek_batch.py"
STATE_DIR="$ROOT/_ocr_remote/deepseek/_runner"
LOG_DIR="$STATE_DIR/logs"
PID_FILE="$STATE_DIR/runner.pid"
LOCK_DIR="$STATE_DIR/runner.lock"
HEARTBEAT_FILE="$STATE_DIR/last_heartbeat.txt"
ALERT_FILE="$STATE_DIR/last_alert.txt"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "DeepSeek runner already active (pid=$old_pid)"
    exit 0
  fi
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Runner lock exists; another instance may be active: $LOCK_DIR"
  exit 1
fi

cleanup() {
  rm -rf "$LOCK_DIR"
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

echo $$ > "$PID_FILE"

[[ -x "$PY" ]] || { echo "Missing python at $PY"; exit 1; }
[[ -f "$TASK" ]] || { echo "Missing task script at $TASK"; exit 1; }

backoff=60
while true; do
  ts="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  run_log="$LOG_DIR/run_$(date '+%Y%m%d_%H%M%S').log"
  echo "[$ts] starting DeepSeek OCR batch" | tee -a "$run_log"

  set +e
  "$PY" "$TASK" 2>&1 | tee -a "$run_log"
  code=${PIPESTATUS[0]}
  set -e

  now="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "$now exit_code=$code log=$run_log" > "$HEARTBEAT_FILE"

  if [[ $code -eq 0 ]]; then
    if rg -qi "timed out|curl: \(28\)|connection refused|empty response body" "$run_log"; then
      echo "[$now] warning: timeout/server errors seen in $run_log" | tee -a "$ALERT_FILE"
    fi
    echo "[$now] batch completed; sleeping 10m before next pass" | tee -a "$run_log"
    backoff=60
    sleep 600
  else
    echo "[$now] batch failed code=$code; retrying in ${backoff}s" | tee -a "$run_log"
    sleep "$backoff"
    if [[ $backoff -lt 900 ]]; then
      backoff=$((backoff * 2))
      [[ $backoff -gt 900 ]] && backoff=900
    fi
  fi
done
