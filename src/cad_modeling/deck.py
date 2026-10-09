"""Two identical recessed deck discs and the mounted electronics.

All dimensions are millimeters. The through profile is laser/CNC cut;
the two MPU6050 head counterbores require secondary top-face machining.
Both discs have dedicated mounting holes, wheel/bracket recesses, four
battery strap slots, a side loom slot and an M3 grid with disjoint cuts.
Bought sonar and line-bar geometry lives in sensors.py.
"""
import math

from build123d import Axis, Box, Color, Cylinder, GridLocations, Part, Pos, Rot

from .fits import M2_5_MEDIUM, M3_MEDIUM
from .layout import (
    BATTERY_CENTER_Y, BATTERY_PAD_T, BRACKET_BASE_BOLTS_R, BRACKET_RELIEF_HALF_Y,
    BRACKET_RELIEF_X, CABLE_SLOT_L, CABLE_SLOT_W, CABLE_SLOT_XY, DISC_R, DISC_T,
    DISC_Z, DISC2_Z, LINE_POST_XY, SONAR_TAB_XY, STRAP_SLOT_L, STRAP_SLOT_W,
    STRAP_SLOT_X, STRAP_SLOT_XY, STRAP_SLOT_Y, STANDOFF_HALF_X, STANDOFF_HALF_Y, IMU_BOTTOM_Z,
    IMU_MOUNT_XY, IMU_SPACER_D, IMU_SPACER_L, PCB_SPACER_L,
    IMU_COUNTERBORE_D, IMU_COUNTERBORE_DEPTH, IMU_SCREW_HEAD_D,
    IMU_SCREW_HEAD_H, IMU_UPPER_SCREW_L, IMU_LOWER_SCREW_L,
    WHEEL_RECESS_X, WHEEL_RECESS_HALF_Y, WHEEL_RECESS_FILLET,
)
from .sensors import GY521_MOUNT_HOLES, GY521_PCB_T, GY521_SIZE

# Mounted extents: the 106 mm pack length runs along Y, between bracket
# bases and their screw heads. A small forward bias balances rear modules.
BATTERY = (34.0, 106.0, 22.0)
BATTERY_XYZ = (0.0, BATTERY_CENTER_Y, BATTERY_PAD_T + BATTERY[2] / 2)
DRIVER_XYZ = (0.0, -66.0, PCB_SPACER_L + 1.5)
MCU_XYZ = (0.0, 0.0, PCB_SPACER_L + 1.5)
IMU_XYZ = (*IMU_MOUNT_XY, IMU_BOTTOM_Z + GY521_SIZE[2] / 2 - (DISC_Z + DISC_T / 2))

# Provisional mounting patterns for the two placeholder PCBs. Verify the
# purchased boards; the GY-521 pattern below is measured from its STEP.
PCB_MOUNT_HOLES = {
    "motor_driver": [(DRIVER_XYZ[0] + sx * 8, DRIVER_XYZ[1] + sy * 5)
                     for sx in (-1, 1) for sy in (-1, 1)],
    "mcu": [(MCU_XYZ[0] + sx * 15, MCU_XYZ[1] + sy * 10)
            for sx in (-1, 1) for sy in (-1, 1)],
}

# centered on the disc mid-plane, so every cutter overshoots both faces
_CUTTER_H = 2 * DISC_T + 2

# ---------------- M3 mounting grid ----------------
GRID_PITCH = 15.0
GRID_CLEAR = 1.0         # material kept between a grid hole and any feature

_M3_HOLES = (
    BRACKET_BASE_BOLTS_R + [(-x, y) for x, y in BRACKET_BASE_BOLTS_R]
    + [(sx * STANDOFF_HALF_X, sy * STANDOFF_HALF_Y)
       for sx in (+1, -1) for sy in (+1, -1)]
    + [(sx * SONAR_TAB_XY[0], SONAR_TAB_XY[1]) for sx in (+1, -1)]
    + [(sx * LINE_POST_XY[0], -LINE_POST_XY[1]) for sx in (+1, -1)]
)
_M2_5_HOLES = (
    [(IMU_MOUNT_XY[0] + x, IMU_MOUNT_XY[1] + y) for x, y in GY521_MOUNT_HOLES]
    + PCB_MOUNT_HOLES["motor_driver"] + PCB_MOUNT_HOLES["mcu"]
)
_FEATURE_HOLES = _M3_HOLES + _M2_5_HOLES


def feature_holes() -> list[tuple[float, float, float]]:
    """Dedicated mounting holes as x/y/diameter, common to both discs."""
    return [(*p, M3_MEDIUM) for p in _M3_HOLES] + [(*p, M2_5_MEDIUM) for p in _M2_5_HOLES]


def _recess_distance(x: float, y: float, start_x: float, half_y: float) -> float:
    return math.hypot(max(start_x - abs(x), 0.0), max(abs(y) - half_y, 0.0))


def _recess(start_x: float, half_y: float, corner_r: float) -> Part:
    """Right-side edge recess; outer end overshoots the circular blank."""
    end_x = DISC_R + 10
    cutter = Box(end_x - start_x, 2 * half_y, _CUTTER_H)
    cutter = cutter.fillet(corner_r, cutter.edges().filter_by(Axis.Z))
    return Pos((start_x + end_x) / 2, 0, 0) * cutter


def build_disc_blank() -> Part:
    """Circular blank with symmetric wheel pockets and bracket neck relief."""
    from build123d import Rot
    cutters = [
        _recess(WHEEL_RECESS_X, WHEEL_RECESS_HALF_Y, WHEEL_RECESS_FILLET),
        _recess(BRACKET_RELIEF_X, BRACKET_RELIEF_HALF_Y, 1.0),
    ]
    cutters += [Rot(Z=180) * c for c in cutters[:]]
    return Cylinder(DISC_R, DISC_T) - cutters


def _slot_distance(x: float, y: float, cx: float, cy: float,
                   half_l: float, half_w: float) -> float:
    return math.hypot(max(abs(x - cx) - half_l, 0.0),
                      max(abs(y - cy) - half_w, 0.0))


def grid_holes() -> list[tuple[float, float]]:
    """M3 grid centers on one disc. Single source for the builder AND the
    volume/alignment tests."""
    r_max = DISC_R - M3_MEDIUM / 2 - GRID_CLEAR
    holes = []
    n = int(r_max / GRID_PITCH)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = i * GRID_PITCH, j * GRID_PITCH
            if math.hypot(x, y) > r_max:
                continue
            if any(math.hypot(x - fx, y - fy) < (M3_MEDIUM + d) / 2 + GRID_CLEAR
                   for fx, fy, d in feature_holes()):
                continue
            if _slot_distance(x, y, *CABLE_SLOT_XY, CABLE_SLOT_L / 2, CABLE_SLOT_W / 2) \
                    < M3_MEDIUM / 2 + GRID_CLEAR:
                continue
            if (_recess_distance(x, y, WHEEL_RECESS_X, WHEEL_RECESS_HALF_Y) < M3_MEDIUM / 2 + GRID_CLEAR
                    or _recess_distance(x, y, BRACKET_RELIEF_X, BRACKET_RELIEF_HALF_Y) < M3_MEDIUM / 2 + GRID_CLEAR):
                continue
            if any(_slot_distance(x, y, sx, sy, STRAP_SLOT_W / 2, STRAP_SLOT_L / 2)
                   < M3_MEDIUM / 2 + GRID_CLEAR for sx, sy in STRAP_SLOT_XY):
                continue
            holes.append((x, y))
    return holes


def _obround(length: float, width: float, thickness: float) -> Part:
    """Obround prism centered on the origin, long axis along X."""
    ends = [
        loc * Cylinder(width / 2, thickness)
        for loc in GridLocations(length - width, width, 2, 1)
    ]
    return Box(length - width, width, thickness) + ends


def build_disc() -> Part:
    """One deck disc, FLAT (mid-plane z=0). Cut two -- the tiers are the
    same part: bracket/standoff/sensor/PCB holes, side loom passage,
    four strap slots and the mounting grid. Machine the two MPU6050
    counterbores from the TOP face after cutting the through profile."""
    cutters = [
        Pos(x, y, 0) * Cylinder(d / 2, _CUTTER_H)
        for x, y, d in feature_holes()
    ]
    cutters += [
        Pos(x, y, 0) * Cylinder(M3_MEDIUM / 2, _CUTTER_H)
        for x, y in grid_holes()
    ]
    cutters.append(Pos(*CABLE_SLOT_XY, 0) * _obround(CABLE_SLOT_L, CABLE_SLOT_W, _CUTTER_H))
    cutters += [
        Pos(sx, sy, 0) * Rot(Z=90)
        * _obround(STRAP_SLOT_L, STRAP_SLOT_W, _CUTTER_H)
        for sx, sy in STRAP_SLOT_XY
    ]
    cutters += [
        Pos(IMU_MOUNT_XY[0] + x, IMU_MOUNT_XY[1] + y,
            DISC_T / 2 - IMU_COUNTERBORE_DEPTH / 2)
        * Cylinder(IMU_COUNTERBORE_D / 2, IMU_COUNTERBORE_DEPTH)
        for x, y in GY521_MOUNT_HOLES
    ]
    disc = build_disc_blank() - cutters
    disc.color = Color(0.55, 0.75, 0.95, 0.55)
    disc.label = "deck_disc"
    return disc


# ---------------- Electronics (bought; placeholder blocks) ----------------
# Block centers as placed on the tiers; the twin's mass table reads these
# so the CAD placement and the simulated masses cannot drift apart.
# real pack: white-label 2200 mAh 3S LiPo (2026-09-27), 106 x 34 x 22 with
# R2.5 vertical corners; same-class measured range, caliper the arrival


def _rounded_box(x: float, y: float, z: float, r: float) -> Part:
    if r <= 0:
        return Box(x, y, z)
    b = Box(x, y, z)
    return b.fillet(r, b.edges().filter_by(Axis.Z))


def _block(x: float, y: float, z: float, sx: float, sy: float, sz: float,
           color: Color, r: float = 1.0) -> Part:
    b = Pos(x, y, z) * _rounded_box(sx, sy, sz, r)
    b.color = color
    return b


def build_electronics(mode: str = "collision") -> list[Part]:
    """Bought; placeholder blocks -- visual mode swaps the IMU block for
    the vendor GY-521 board STEP (label stays "imu": the web registry keys
    on it). Lower tier: lengthwise battery, rear driver and front sonar.
    MPU6050: dedicated underside pair near the axle. Upper tier: MCU."""
    if mode not in ("collision", "visual"):
        raise ValueError(f"unknown mode {mode!r}")
    lower_top = DISC_Z + DISC_T / 2
    upper_top = DISC2_Z + DISC_T / 2
    parts = []
    battery = _block(*BATTERY_XYZ[:2], lower_top + BATTERY_XYZ[2],
                     *BATTERY, Color(0.9, 0.3, 0.2), r=2.5)
    battery.label = "battery"
    parts.append(battery)
    driver = _block(DRIVER_XYZ[0], DRIVER_XYZ[1], lower_top + DRIVER_XYZ[2],
                     21, 16, 3, Color(0.2, 0.7, 0.3))
    driver = driver - [Pos(x, y, lower_top + DRIVER_XYZ[2]) * Cylinder(1.5, 5)
                       for x, y in PCB_MOUNT_HOLES["motor_driver"]]
    driver.label = "motor_driver"
    parts.append(driver)
    mcu = _block(MCU_XYZ[0], MCU_XYZ[1], upper_top + MCU_XYZ[2],
                  36, 27, 3, Color(0.2, 0.5, 0.9))
    mcu = mcu - [Pos(x, y, upper_top + MCU_XYZ[2]) * Cylinder(1.5, 5)
                 for x, y in PCB_MOUNT_HOLES["mcu"]]
    mcu.label = "mcu"
    parts.append(mcu)
    if mode == "visual":
        from .sensors import load_gy521_visual
        imu = Pos(*IMU_MOUNT_XY, IMU_BOTTOM_Z) * load_gy521_visual()
    else:
        from .sensors import build_gy521_envelope
        imu = Pos(*IMU_MOUNT_XY, IMU_BOTTOM_Z) * build_gy521_envelope()
        imu.color = Color(0.95, 0.85, 0.2)
    imu.label = "imu"
    parts.append(imu)
    return parts


def build_module_mounts() -> list[Part]:
    """PCB spacers plus the dedicated underside MPU6050 mounting pair."""
    from build123d import Compound
    lower_top, upper_top = DISC_Z + DISC_T / 2, DISC2_Z + DISC_T / 2

    def spacer(x, y, bottom, height):
        outer = Pos(x, y, bottom + height / 2) * Cylinder(IMU_SPACER_D / 2, height)
        bore = Pos(x, y, bottom + height / 2) * Cylinder(1.25, height + 2)
        return outer - bore

    pcb = Compound(children=[spacer(x, y, surface, PCB_SPACER_L)
                             for label, surface in (("motor_driver", lower_top), ("mcu", upper_top))
                             for x, y in PCB_MOUNT_HOLES[label]])
    pcb.label, pcb.color = "pcb_spacers", Color(0.8, 0.8, 0.85)
    imu = Compound(children=[spacer(IMU_MOUNT_XY[0] + x, IMU_MOUNT_XY[1] + y,
                                           IMU_BOTTOM_Z + GY521_PCB_T, IMU_SPACER_L)
                             for x, y in GY521_MOUNT_HOLES])
    imu.label, imu.color = "imu_mount", Color(0.8, 0.8, 0.85)
    screws = []
    for x, y in GY521_MOUNT_HOLES:
        x, y = IMU_MOUNT_XY[0] + x, IMU_MOUNT_XY[1] + y
        upper_head_bottom = lower_top - IMU_COUNTERBORE_DEPTH
        for head_bottom, shaft_start, shaft_len in (
            (upper_head_bottom, upper_head_bottom - IMU_UPPER_SCREW_L, IMU_UPPER_SCREW_L),
            (IMU_BOTTOM_Z - IMU_SCREW_HEAD_H, IMU_BOTTOM_Z, IMU_LOWER_SCREW_L),
        ):
            head = Pos(x, y, head_bottom + IMU_SCREW_HEAD_H / 2) * Cylinder(
                IMU_SCREW_HEAD_D / 2, IMU_SCREW_HEAD_H)
            shaft = Pos(x, y, shaft_start + shaft_len / 2) * Cylinder(1.25, shaft_len)
            screws.append(head + shaft)
    fasteners = Compound(children=screws)
    fasteners.label, fasteners.color = "imu_fasteners", Color(0.55, 0.55, 0.6)
    return [pcb, imu, fasteners]


def build_battery_retention() -> list[Part]:
    """Anti-slip pad and two 10 mm straps across the pack's short axis."""
    from build123d import Compound
    top, bottom = DISC_Z + DISC_T / 2, DISC_Z - DISC_T / 2
    pad = Pos(BATTERY_XYZ[0], BATTERY_XYZ[1], top + BATTERY_PAD_T / 2) * _rounded_box(
        BATTERY[0], BATTERY[1], BATTERY_PAD_T, 2.5)
    pad.label, pad.color = "battery_pad", Color(0.15, 0.15, 0.16)
    pack_top = top + BATTERY_XYZ[2] + BATTERY[2] / 2
    strap_t, strap_w = 1.0, 10.0
    span = 2 * STRAP_SLOT_X + strap_t
    loops = []
    for y in STRAP_SLOT_Y:
        upper = Pos(0, y, pack_top + strap_t / 2) * Box(span, strap_w, strap_t)
        lower = Pos(0, y, bottom - strap_t / 2) * Box(span, strap_w, strap_t)
        legs = [Pos(x, y, (pack_top + bottom) / 2) * Box(strap_t, strap_w, pack_top - bottom)
                for x in (-STRAP_SLOT_X, STRAP_SLOT_X)]
        loops.append(upper + lower + legs[0] + legs[1])
    strap = Compound(children=loops)
    strap.label, strap.color = "battery_strap", Color(0.12, 0.12, 0.14)
    return [pad, strap]
