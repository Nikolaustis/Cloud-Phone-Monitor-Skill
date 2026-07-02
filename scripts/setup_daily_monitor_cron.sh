#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${SKILL_DIR}/output/scheduler_logs"

mkdir -p "${LOG_DIR}"

cat <<EOF
# Cloud Phone Monitor weekday cron example
# Review the command first, then add it with: crontab -e
#
# Runs every Monday-Friday at 10:00 local machine time.
0 10 * * 1-5 cd "${SKILL_DIR}" && python run.py >> "${LOG_DIR}/daily.log" 2>&1

# Optional status file after you enable the cron entry:
cat > "${LOG_DIR}/schedule_status.json" <<'JSON'
{
  "scheduler_enabled": true,
  "scheduler_type": "cron",
  "schedule_time_local": "10:00",
  "logs_path": "output/scheduler_logs",
  "last_run_status": "unknown",
  "stale_after_hours": 30
}
JSON
EOF
