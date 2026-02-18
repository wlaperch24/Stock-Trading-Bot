#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/williamlaperch/Documents/GitHub/Stock-Trading-Bot"
cd "$REPO_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv in $REPO_DIR"
  exit 1
fi

mkdir -p logs
RUN_ID="$(date -u +kalshi_6h_%Y%m%dT%H%M%SZ)"
LOG_PATH="$REPO_DIR/logs/${RUN_ID}.log"
STATUS_PATH="$REPO_DIR/logs/${RUN_ID}.status"
META_PATH="$REPO_DIR/logs/${RUN_ID}.meta"

cat > "$META_PATH" <<EOF
run_id=$RUN_ID
start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log=$LOG_PATH
status=$STATUS_PATH
launcher=caffeinate -dimsu
EOF

echo "$RUN_ID" > "$REPO_DIR/logs/active_run_id.txt"

# Keep the machine awake so 10-minute cadence is not interrupted by clamshell/idle sleep.
source .venv/bin/activate
caffeinate -dimsu env \
  KALSHI_CONTINUOUS=1 \
  KALSHI_MAX_RUNTIME_SECONDS=21600 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=src \
  python3 -u src/trading_bot/main.py > "$LOG_PATH" 2>&1
EXIT_CODE=$?
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$EXIT_CODE" > "$STATUS_PATH"
echo "Run complete: $RUN_ID (exit_code=$EXIT_CODE)"
