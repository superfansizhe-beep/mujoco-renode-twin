"""Bought sensor envelopes. All dimensions in mm.

The GY-521 has a supplied STEP. The sonar, its bracket and the line bar
use measured or provisional primitives; caliper the purchased variants.

- HC-SR04: drawing-standard dims (45x20 board, D16x12 cans on a 25 mm
  pitch) -- the same sensor the radar twin already uses; caliper when it
  arrives. Rides the bent-steel sonar bracket: board back face ~1 mm off
  the bracket face, cans fully forward of it. The face holes only matter
  for the classic back-mount variant (board behind, cans through); pick
  the mounting side once the real bracket is calipered.
- Sonar bracket: generic bent-steel HC-SR04 bracket -- vertical face,
  two feet tabs bolted flat to the lower disc (nuts under the disc).
  Every constant GUESS until the catalog part is calipered.
- 8-way IR line bar (Taobao listing drawing, 2026-09-27, user-supplied):
  91.11 x 36.50 x 13.50 overall, 1.60 PCB, D3 mounting holes at 16.11 /
  42.05 spans (symmetric-on-centerline assumption -> +-8.055 / +-21.025 --
  caliper the real part before cutting). Interface specs match the Yahboom
  YB-MX04-2.0 (5V/85mA, 8 IO + I2C + USART, detect height 5-60 mm); the
  listing's "800g" weight field is category junk. Mounts hanging under
  the lower disc on two long posts, sensors looking down at the floor.
"""
import os

from build123d import Box, Color, Cylinder, Part, Pos, Rot

# --- HC-SR04 (drawing; SETTLED-ish, caliper to confirm) ---
SONAR_BOARD = (45.0, 1.6, 20.0)   # X, Y, Z in the mounted orientation
SONAR_CAN_D = 16.0
SONAR_CAN_L = 12.0
SONAR_CAN_PITCH = 25.0            # can center spacing
SONAR_HOLE_D = SONAR_CAN_D + 0.2  # clearance in the bracket face

# --- bent-steel sonar bracket (catalog part; GUESS until calipered) ---
SONAR_FACE = (50.0, 2.0, 25.0)    # compact bracket required by lowered tier gap
SONAR_TAB_DX = 20.0               # tab bolt half-pattern (tab width 10)
SONAR_TAB_DY = 3.0                # face back face -> tab hole center
SONAR_TAB_HOLE_D = 3.4
SONAR_CAN_AXIS_Z = SONAR_FACE[2] / 2   # can axis above the disc top

# --- 8-way line bar (listing drawing 2026-09-27; CITE, caliper to confirm) ---
LINE_BAR_X = 91.11                # overall length
LINE_BAR_Y_HALF = 18.25           # 36.50 width / 2
LINE_BAR_PCB_T = 1.6              # drawing "1.60"
LINE_BAR_SKIRT = 11.9             # 13.50 total height - PCB, all below (worst case)
LINE_BAR_H = LINE_BAR_PCB_T + LINE_BAR_SKIRT
LINE_BAR_HOLE_D = 3.0             # mounting holes take M2.5/M3
LINE_BAR_HOLE_DX = (8.055, 21.025)   # hole centers off the centerline: the
#                                    16.11/42.05 hole spans / 2, symmetry assumed

# --- GY-521 (MPU6050) IMU: open board STEP (vendor), cross-checked size ---
_GY521_STEP = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "vendor",
    "mpu6050-gy521", "gy521_module.step")

GY521_SIZE = (20.35, 15.65, 2.50)   # supplied STEP, no headers
GY521_PCB_T = 1.0                  # STEP mounting-hole walls span z 0..1
GY521_MOUNT_HOLES = ((-8.175, 5.825), (8.175, 5.825))
GY521_MOUNT_HOLE_D = 3.0


def build_gy521_envelope() -> Part:
    """PCB plus component envelope, with clear mounting pads above the PCB.

    The supplied STEP has no components in the D4.5 mounting-pad regions;
    spacers bear on the 1 mm PCB rather than intersecting a full-height box.
    """
    board = Pos(0, 0, GY521_PCB_T / 2) * Box(*GY521_SIZE[:2], GY521_PCB_T)
    holes = [Pos(x, y, GY521_SIZE[2] / 2)
             * Cylinder(GY521_MOUNT_HOLE_D / 2, GY521_SIZE[2] + 2)
             for x, y in GY521_MOUNT_HOLES]
    board = board - holes
    component_h = GY521_SIZE[2] - GY521_PCB_T
    components = Pos(0, 0, GY521_PCB_T + component_h / 2) * Box(*GY521_SIZE[:2], component_h)
    components = components - [
        Pos(x, y, GY521_PCB_T + component_h / 2) * Cylinder(2.25, component_h + 0.02)
        for x, y in GY521_MOUNT_HOLES
    ]
    board = board + components
    board.label = "imu_envelope"
    return board


def load_gy521_visual() -> Part:
    """Vendor GY-521 board STEP re-based: centered in XY, board bottom on
    z=0 (assembly supplies mounting height), long axis along X. Cross-checked size
    20.35 x 15.65 x 2.50, board only, no headers (assets/vendor/README.md)."""
    from build123d import import_step

    part = import_step(_GY521_STEP)
    bb = part.bounding_box()
    if (bb.max.X - bb.min.X) < (bb.max.Y - bb.min.Y):
        part = Rot(0, 0, 90) * part
        bb = part.bounding_box()
    part = Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2,
               -bb.min.Z) * part
    bb = part.bounding_box()
    assert abs((bb.max.X - bb.min.X) - 20.35) < 0.5, (
        f"GY-521 board X {bb.max.X - bb.min.X:.2f}: wrong variant or re-base")
    assert abs((bb.max.Y - bb.min.Y) - 15.65) < 0.5, (
        f"GY-521 board Y {bb.max.Y - bb.min.Y:.2f}")
    assert abs((bb.max.Z - bb.min.Z) - 2.50) < 0.3, (
        f"GY-521 board Z {bb.max.Z - bb.min.Z:.2f}")
    assert abs(bb.min.Z) < 1e-6, "board must sit on z=0 after re-base"
    part.label = "imu_visual"
    part.color = Color(0.12, 0.22, 0.5)
    return part


def build_sonar_bracket_envelope() -> Part:
    """Local frame: feet on z=0 (lower disc top), face mid-plane y=0,
    cans forward +Y. Two feet tabs with bolt holes extend back (-Y)."""
    face = Pos(0, 0, SONAR_FACE[2] / 2) * Box(*SONAR_FACE)
    can_holes = [
        Pos(sx * SONAR_CAN_PITCH / 2, 0, SONAR_CAN_AXIS_Z)
        * Rot(X=90) * Cylinder(SONAR_HOLE_D / 2, SONAR_FACE[1] + 2)
        for sx in (+1, -1)
    ]
    face = face - can_holes
    tabs = [
        (Pos(sx * SONAR_TAB_DX, -SONAR_TAB_DY, 1.0)
         * Box(10.0, 2 * SONAR_TAB_DY, 2.0))
        - Pos(sx * SONAR_TAB_DX, -SONAR_TAB_DY, 1.0)
        * Cylinder(SONAR_TAB_HOLE_D / 2, 6)
        for sx in (-1, +1)
    ]
    env = face + tabs[0] + tabs[1]
    env.label = "sonar_bracket_envelope_bought"
    return env


def build_sonar_envelope() -> Part:
    """Local frame: board back face on y=0 (against the bracket face),
    cans toward +Y, can axes at z=0. Place with the bracket."""
    board = Pos(0, SONAR_BOARD[1] / 2, 0) * Box(*SONAR_BOARD)
    cans = [
        Pos(sx * SONAR_CAN_PITCH / 2,
            SONAR_BOARD[1] + SONAR_CAN_L / 2, 0)
        * Rot(X=90) * Cylinder(SONAR_CAN_D / 2, SONAR_CAN_L)
        for sx in (+1, -1)
    ]
    env = board + cans[0] + cans[1]
    env.label = "sonar_envelope_bought"
    return env


def build_line_bar_envelope() -> Part:
    """Local frame: PCB top face at z=0, body hanging down (-z), long axis
    along X, sensors looking at the floor."""
    pcb = Pos(0, 0, -LINE_BAR_PCB_T / 2) * Box(
        LINE_BAR_X, 2 * LINE_BAR_Y_HALF, LINE_BAR_PCB_T)
    skirt = Pos(0, 0, -LINE_BAR_PCB_T - LINE_BAR_SKIRT / 2) * Box(
        LINE_BAR_X - 10, 2 * LINE_BAR_Y_HALF - 6, LINE_BAR_SKIRT)
    env = pcb + skirt
    holes = [Pos(sx * dx, 0, -LINE_BAR_H / 2)
             * Cylinder(LINE_BAR_HOLE_D / 2, LINE_BAR_H + 2)
             for dx in LINE_BAR_HOLE_DX for sx in (-1, 1)]
    env = env - holes
    env.label = "line_bar_envelope_bought"
    return env
