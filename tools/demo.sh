#!/usr/bin/env bash
# One command to bring up the 3D demo for a defense run.
#
#   bash tools/demo.sh
#
# Opens the viewer on :5173 and streams the sim on :8766. Two terminals are
# unavoidable on macOS: ops.py drives netstat/taskkill and is Windows-only.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v gh >/dev/null || { echo "first run: brew install gh && gh auth login"; }
[ -s assets/vendor/jgb37-520/37mm_mounting_bracket.step ] || bash tools/fetch_vendor.sh
[ -d web/node_modules ] || (cd web && npm install)

echo "starting viewer on http://localhost:5173 ..."
(cd web && npm run dev) &
sleep 4
echo "starting sim stream on ws://127.0.0.1:8766 ..."
uv run python -m race --task 1 --serve
echo
echo "open: http://localhost:5173/?ws=ws://127.0.0.1:8766"
