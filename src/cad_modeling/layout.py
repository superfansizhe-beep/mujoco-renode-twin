"""Vehicle-level layout: the single source for every cross-part dimension.

Part-intrinsic dimensions stay with their part modules (jgb37_520, wheel,
bracket, sensors). Fits and clearances come from the fits module.

X stack, right side, +X outboard:
  lower disc under L-bracket base | motor flange | bracket plate |
  shaft shoulder | bought shaft-hub wheel
FLANGE_X is driven from inboard -- the two motor tails reach toward the
center and bound the track (user call 2026-09-27: compact chassis); the
disc rim then clears the wheel inner faces.

Lowered stack (2026-09-29): two identical recessed discs on four 28 mm
standoffs. The battery lies lengthwise between the motor bracket bases;
driver and sonar occupy the rear and front of the lower tier. The MCU is
the highest module, on the upper tier. The MPU6050 mounts centrally under
the lower disc; the line bar hangs farther aft on two posts.
"""
import math

from .bracket import AXLE_OFFSET, BASE_BOLT_X_REL, BASE_BOLT_Y, BASE_T, PLATE_T, PLATE_W
from .jgb37_520 import FLANGE_D, motor_body_length
from .sensors import (
    GY521_PCB_T, LINE_BAR_H, LINE_BAR_HOLE_DX, LINE_BAR_Y_HALF,
    SONAR_TAB_DX, SONAR_TAB_DY,
)
from .wheel import WHEEL_D, WHEEL_SEAT_X, WHEEL_W

# --- Running gear ---
WHEEL_R = WHEEL_D / 2
AXLE_Z = WHEEL_R   # wheels rest on z = 0

# --- Wiring corridor: motor tails reach inboard from the flange face ---
MOTOR_REACH = motor_body_length()           # 67.7, drawing-derived
WIRING_CORRIDOR = 15.0
FLANGE_X = MOTOR_REACH + WIRING_CORRIDOR
WHEEL_INNER_X = FLANGE_X + WHEEL_SEAT_X
TRACK_HALF = WHEEL_INNER_X + WHEEL_W / 2

# --- Lower housing: disc hangs under the bracket base, with wheel recesses ---
DISC_T = 3.0
DISC_Z = AXLE_Z + AXLE_OFFSET - BASE_T - DISC_T / 2
DISC_R = 95.0                             # D190 outer housing before recesses
WHEEL_RECESS_CLEARANCE = 3.0
WHEEL_RECESS_X = WHEEL_INNER_X - WHEEL_RECESS_CLEARANCE
WHEEL_RECESS_HALF_Y = WHEEL_R + WHEEL_RECESS_CLEARANCE
WHEEL_RECESS_FILLET = 2.0
BRACKET_RELIEF_X = FLANGE_X - 1.0           # clear vertical plate through lower disc
BRACKET_RELIEF_HALF_Y = PLATE_W / 2 + 1.0
assert abs(DISC_Z + DISC_T / 2 - (AXLE_Z + AXLE_OFFSET - BASE_T)) < 1e-9

TIER_STANDOFF_L = 28.0   # 4 mm above the retained battery and its strap
DISC2_Z = DISC_Z + DISC_T + TIER_STANDOFF_L  # upper disc mid-plane
STANDOFF_HALF_X = 60.0   # quarter-pattern; holes at all 4 sign combos
STANDOFF_HALF_Y = 45.0
STANDOFF_D = 5.5         # hex brass column envelope

# --- Bracket base bolts through the lower disc (per side, mirrored) ---
BRACKET_BASE_BOLTS_R = [(FLANGE_X + PLATE_T - dx, sy) for dx in BASE_BOLT_X_REL
                        for sy in (BASE_BOLT_Y, -BASE_BOLT_Y)]
assert max(math.hypot(x, y) for x, y in BRACKET_BASE_BOLTS_R) <= DISC_R - 2.0, (
    "bracket base bolts run off the disc rim")

# --- Wiring / strap features (cut into the discs) ---
CABLE_SLOT_L = 22.0
CABLE_SLOT_W = 8.0
CABLE_SLOT_XY = (-40.0, 32.0)  # loom passage beside the pack, clear of straps
STRAP_SLOT_L = 22.0
STRAP_SLOT_W = 3.0
BATTERY_CENTER_Y = 1.0
STRAP_SLOT_X = 21.0     # pack sides x = +/-17; slots leave 2.5 mm clearance
STRAP_SLOT_Y = (-27.0, 29.0)  # two transverse straps, 56 mm apart
STRAP_SLOT_XY = [(sx * STRAP_SLOT_X, y)
                 for y in STRAP_SLOT_Y for sx in (-1, 1)]
BATTERY_PAD_T = 1.0

# MPU6050: underside of lower disc, centered between the encoder tails.
# Keep chip +Z upward; use right-angle headers exiting toward -Y.
IMU_MOUNT_XY = (0.0, 0.0)
IMU_SPACER_L = 5.0      # double-female M2.5, separate screws at each end
IMU_SPACER_D = 4.0
IMU_BOTTOM_Z = DISC_Z - DISC_T / 2 - IMU_SPACER_L - GY521_PCB_T
IMU_COUNTERBORE_D = 5.0
IMU_COUNTERBORE_DEPTH = 1.8  # recessed heads leave 1.2 mm of plate
IMU_SCREW_HEAD_D = 4.7      # Accu SSB-M2.5 button-head specification
IMU_SCREW_HEAD_H = 1.5      # verify selected supplier; recess leaves 0.3 mm
IMU_UPPER_SCREW_L = 4.0
IMU_LOWER_SCREW_L = 3.0
PCB_SPACER_L = 3.0

# --- Sonar: lower-disc front; MCU alone occupies the top equipment tier ---
SONAR_FACE_Y = 67.0   # bracket face mid-plane; +Y = forward
SONAR_TAB_XY = (SONAR_TAB_DX, SONAR_FACE_Y - SONAR_TAB_DY)   # tab bolts
assert SONAR_FACE_Y + 1.0 < DISC_R, "sonar bracket stands off the rim"

# --- Line bar: hangs under the lower disc tail (-Y), posts up into the disc
LINE_BAR_Y = -42.0       # close to axle to retain pitch clearance at the floor
# posts bolt through the OUTER hole pair of the module (21.025 off the
# centerline) -- the old +-40 posts reached past every hole and could
# never have bolted up (2026-09-27 listing-drawing fix)
LINE_POST_XY = (LINE_BAR_HOLE_DX[1], -LINE_BAR_Y)
LINE_POST_L = 28.0
# sensor face height off the floor: listing detect window is 5-60 mm;
# ~10 mm is the rule of thumb for digital IR (higher misreads, lower drags)
LINE_FACE_Z = DISC_Z - DISC_T / 2 - LINE_POST_L - LINE_BAR_H
assert 5.0 <= LINE_FACE_Z <= 15.0, f"line face at {LINE_FACE_Z:.1f} mm"
assert abs(LINE_BAR_Y) - LINE_BAR_Y_HALF >= max(PLATE_W / 2, FLANGE_D / 2) + 3.0, (
    "line bar fouls the motor/bracket envelope")
assert max(math.hypot(x, -LINE_POST_XY[1]) for x in (-LINE_POST_XY[0], LINE_POST_XY[0])) \
    <= DISC_R - 2.0, "line posts run off the disc rim"
