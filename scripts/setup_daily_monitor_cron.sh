#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${SKILL_DIR}/output/scheduler_logs"
mkdir -p "${LOG_DIR}"
cat <<EOF
# Collection-only cron example for non-Windows hosts.
# GitHub Pages publishing is implemented by deployment/windows and is Windows-oriented.
0 10 * * 1-5 cd "${SKILL_DIR}" && python run.py && python rebuild_dashboard_history.py --incremental >> "${LOG_DIR}/daily.log" 2>&1
EOF
