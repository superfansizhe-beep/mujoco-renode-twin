#!/usr/bin/env bash
# Fetch the vendor reference STEP models this twin needs.
#
# They are gitignored on purpose (third-party terms), so a fresh clone -- or
# a machine that lost ~/.cache -- starts without them and every `import bot`
# dies in src/cad_modeling/bracket.py. Run this once before `uv run python -m race`.
#
#   bash tools/fetch_vendor.sh
#
# GrabCAD items need a logged-in session and are NOT fetched here; they are
# visual cross-check references only. See assets/vendor/README.md.
set -euo pipefail

cd "$(dirname "$0")/.."
V=assets/vendor
mkdir -p "$V/jgb37-520" "$V/mpu6050-gy521" "$V/ams1117"

command -v gh >/dev/null || { echo "needs gh: brew install gh && gh auth login"; exit 1; }

fetch() { # repo, path-in-repo, dest
  local dest="$3"
  [ -s "$dest" ] && { printf '  skip  %-28s (already there)\n' "$(basename "$dest")"; return 0; }
  gh api "repos/$1/contents/$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$2")" \
    --jq '.content' 2>/dev/null | tr -d '\n' | base64 -d > "$dest"
  [ -s "$dest" ] || { rm -f "$dest"; echo "  FAIL  $dest"; return 1; }
  printf '  ok    %-28s %s bytes\n' "$(basename "$dest")" "$(wc -c < "$dest" | tr -d ' ')"
}

echo "JGB37-520 (github.com/hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot.)"
M="repos/hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot./contents"
JGB="New folder/37-mm-dc-geared-motor-mounting-bracket-1.snapshot.11/37 mm DC Geared Motor Mounting Bracket.STEP"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "DC MOTOR- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/dc_motor.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "GEARED BODY- MOTOR- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/geared_body.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "MOTOR SHAFT- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/motor_shaft.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "PLASTIC COVER- DC MOTOR- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/plastic_cover.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "SHAFT COUPLER- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/shaft_coupler.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "COUPLING BRACKET- GEARED BODY TO DC MOTOR- JGB37-520-1_Default_sldprt.STEP" "$V/jgb37-520/coupling_bracket.step"
fetch hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. \
  "$JGB" "$V/jgb37-520/37mm_mounting_bracket.step"

echo "GY-521 (github.com/adam-kabbara/RSX-CANSAT-2026)"
fetch adam-kabbara/RSX-CANSAT-2026 \
  "electrical/DO_NOT_EDIT__KICAD_LIBRARIES/Custom_3D_Models.3dshapes/GY-521_(MPU-6050).step" \
  "$V/mpu6050-gy521/gy521_module.step"

echo "AMS1117 (github.com/xhivo97/esp-garage-hardware)"
fetch xhivo97/esp-garage-hardware "models/AMS1117-3.3.step" \
  "$V/ams1117/ams1117_chip_sot223_only.step"

echo
echo "done. verify with:  uv run python -m race --task 1"