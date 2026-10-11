"""Geometric regression tests (two-tier disc chassis, 2026-09-27).

Every past assembly bug was a boolean operation failing silently: holes cut
into air, a trim box halving a wheel, a free-floating tire, a clamp that
could not clamp. The gates:

- connectivity: every part WE fabricate must be ONE solid;
- interface: the flange constants are SETTLED (6x M3 on a D31 bolt circle,
  3.5 deep taps) and the bracket's axle offset must set the disc height;
- cuts: probe cylinders must find holes empty and material beside them;
- alignment: the disc's bracket-bolt holes must line up with the vendor
  bracket's own holes, the sonar bracket's tab holes with the lower disc;
- grid: the M3 mounting grid must be real holes on real discs, with the
  exact hole count the construction math predicts;
- sensors: the line bar rides at working height off the floor, the sonar
  hangs its cans exactly on the bracket's face holes;
- interference: no two placed things share volume, checked against both
  the primitive envelopes and the supplied vendor BREPs;
- vendor files: the shipped STEPs must still be the variants we measured.

Runs standalone (``python -m tests.test_assembly``) and is
pytest-collectable without any extra dependency.
"""
import math
import os

from build123d import Compound, Cylinder, GeomType, Pos, Rot
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

from cad_modeling.balance_bot import (
    _placed, build_assembly, build_our_parts, build_standoffs,
)
from cad_modeling.bracket import (
    AXLE_OFFSET, BASE_T, PLATE_T, _VENDOR_STEP, build_bracket_envelope, load_bracket_visual,
)
from cad_modeling.deck import (
    DISC_R, DISC_T, build_disc, build_disc_blank, feature_holes, grid_holes,
)
from cad_modeling.fits import M3_MEDIUM, M3_TAP_DRILL
from cad_modeling.jgb37_520 import (
    FLANGE_BC, FLANGE_SCREW_ENGAGEMENT, FLANGE_TAP_DEPTH,
    FLANGE_TAP_D, FLANGE_TAP_N, FLANGE_THROUGH_N, _VENDOR_STEP as MOTOR_STEP,
    OUTPUT_SHAFT_OFFSET, build_motor_envelope, load_motor_visual,
)
from cad_modeling.layout import (
    BRACKET_BASE_BOLTS_R, CABLE_SLOT_L, CABLE_SLOT_W, DISC2_Z, DISC_Z,
    FLANGE_X, LINE_BAR_Y, LINE_FACE_Z, LINE_POST_L, LINE_POST_XY,
    MOTOR_REACH, SONAR_FACE_Y, SONAR_TAB_XY, STRAP_SLOT_L, STRAP_SLOT_W,
    STRAP_SLOT_XY, STRAP_SLOT_Y, STANDOFF_HALF_X, STANDOFF_HALF_Y, WIRING_CORRIDOR,
    AXLE_Z, IMU_BOTTOM_Z, WHEEL_INNER_X, WHEEL_RECESS_CLEARANCE,
    IMU_COUNTERBORE_D, IMU_COUNTERBORE_DEPTH, IMU_SCREW_HEAD_H,
    IMU_UPPER_SCREW_L, IMU_LOWER_SCREW_L,
)
from cad_modeling.sensors import (
    GY521_MOUNT_HOLES, SONAR_CAN_AXIS_Z, SONAR_CAN_PITCH, _GY521_STEP,
)
from cad_modeling.wheel import WHEEL_SEAT_X, WHEEL_W, build_wheel_envelope

MOTOR_STEP_PATH = os.path.normpath(MOTOR_STEP)
BRACKET_STEP_PATH = os.path.normpath(_VENDOR_STEP)

# The vendor STEPs are fetched, not redistributed (assets/vendor/README.md);
# every geometry gate below runs on OUR envelopes either way. Each gate declares
# ONLY the models it actually touches, so a missing file skips the tests that need
# it instead of every gate at once.
import pytest

HAS_MOTOR = os.path.exists(MOTOR_STEP_PATH)
HAS_BRACKET = os.path.exists(BRACKET_STEP_PATH)
HAS_GY521 = os.path.exists(os.path.normpath(_GY521_STEP))
VENDOR_READY = HAS_MOTOR and HAS_BRACKET and HAS_GY521

_WHERE = "see assets/vendor/README.md"
_ABSENT = {
    "motor": f"GrabCAD LR24 motor STEP absent ({_WHERE})",
    "bracket": f"37 mm mounting bracket STEP absent ({_WHERE})",
    "gy521": f"GY-521 STEP absent ({_WHERE})",
}


def _gate(*keys):
    """skipif over an explicit list of needed models."""
    return pytest.mark.skipif(
        not all({"motor": HAS_MOTOR, "bracket": HAS_BRACKET,
                 "gy521": HAS_GY521}[k] for k in keys),
        reason="; ".join(_ABSENT[k] for k in keys
                         if not {"motor": HAS_MOTOR, "bracket": HAS_BRACKET,
                                 "gy521": HAS_GY521}[k]) or "vendor STEPs not fetched",
    )


requires_motor = _gate("motor")
requires_bracket = _gate("bracket")
requires_gy521 = _gate("gy521")
requires_motor_bracket = _gate("motor", "bracket")
# mode="visual" swaps every envelope for the real model, so it needs the full set.
requires_visual_vendor = _gate("motor", "bracket", "gy521")
requires_vendor = requires_visual_vendor  # legacy alias: the all-three gate


# ---------------- interface: settled facts ----------------
def test_flange_interface_settled():
    assert FLANGE_BC == 31.0 and FLANGE_TAP_N == 6
    assert FLANGE_TAP_DEPTH == 3.5
    assert FLANGE_SCREW_ENGAGEMENT <= FLANGE_TAP_DEPTH - 0.3
    assert FLANGE_TAP_D == M3_TAP_DRILL
    assert FLANGE_THROUGH_N == 3


def test_wiring_corridor():
    gap = FLANGE_X - MOTOR_REACH
    assert gap >= WIRING_CORRIDOR, (
        f"{gap:.1f} mm between the encoder tails leaves no cable exit")


def test_hub_holding_margin_over_stall():
    from cad_modeling.jgb37_520 import STALL_TORQUE
    from cad_modeling.wheel import HUB_HOLD_ESTIMATE
    assert HUB_HOLD_ESTIMATE > STALL_TORQUE, (
        "hub/shaft joint is the last torque bottleneck: holding estimate "
        "must stay above stall (assembly: D-flat seat + Loctite 242)")


# ---------------- connectivity gate ----------------
def test_fabricated_parts_are_single_solids():
    parts = build_our_parts()
    labels = sorted(p.label for p in parts)
    assert labels == ["deck_lower", "deck_upper"], labels
    for part in parts:
        n = len(part.solids())
        assert n == 1, f"{part.label}: {n} solids (disconnected geometry)"


def test_discs_are_identical():
    lower, upper = build_our_parts()
    assert abs(lower.volume - upper.volume) < 1e-6 * lower.volume, (
        "the two tiers are supposed to be the same cut, x2")


# ---------------- bracket sets the disc height ----------------
def test_bracket_offset_sets_disc_height():
    assert DISC_Z == AXLE_Z_OFFSET_PLUS_DISC(), (
        "disc underside must equal axle + bracket offset")
    placed = _placed(False, build_bracket_envelope())
    bb = placed.bounding_box()
    disc_top = DISC_Z + DISC_T / 2
    assert abs((bb.max.Z - BASE_T) - disc_top) < 1e-6, (
        "lower disc must seat UNDER the bracket base")
    assert abs(bb.max.X - (FLANGE_X + PLATE_T)) < 1e-6


def AXLE_Z_OFFSET_PLUS_DISC() -> float:
    from cad_modeling.layout import AXLE_Z
    return AXLE_Z + AXLE_OFFSET - BASE_T - DISC_T / 2


# ---------------- bracket envelope vs motor ----------------
def test_bracket_bore_clears_the_motor():
    env = build_bracket_envelope()
    motor = build_motor_envelope()
    assert _intersect_volume(env, motor) < 1.0, (
        "motor envelope must nest inside the bracket bore without touching")
    # the bore is actually open: probe down the axis through the plate
    probe = Pos(PLATE_T / 2, 0, 0) * Rot(Y=90) * Cylinder(6, PLATE_T)
    assert _intersect_volume(env, probe) < 1.0, "bore not open"


# ---------------- disc ----------------
def test_disc_rim_clears_the_wheels():
    # the disc plane passes through the wheel's z-band; only the radial
    # gap to the wheel inner faces keeps them apart
    lower, upper = build_our_parts()
    assert DISC_R > WHEEL_INNER_X, "disc must engage the wheel band with real recesses"
    for side in (-1, 1):
        wheel = _placed(side < 0, build_wheel_envelope())
        for disc in (lower, upper):
            assert disc.distance_to(wheel) >= WHEEL_RECESS_CLEARANCE - 1e-6


def test_bracket_bolts_sit_on_the_disc():
    far = max(math.hypot(x, y) for x, y in BRACKET_BASE_BOLTS_R)
    assert far <= DISC_R - 2.0, f"bolt at r={far:.1f} runs off the disc rim"


def _slot_area(length: float, width: float) -> float:
    return (length - width) * width + math.pi * (width / 2) ** 2


def test_disc_volume_matches_construction():
    # two-sided exact pin: the grid keep-out rules guarantee the cutters
    # never merge, so the construction budget must match to OCC tolerance
    hole_vol = math.pi * (M3_MEDIUM / 2) ** 2 * DISC_T
    solid = build_disc_blank().volume
    feature_vol = sum(math.pi * (d / 2) ** 2 * DISC_T for _, _, d in feature_holes())
    cable = _slot_area(CABLE_SLOT_L, CABLE_SLOT_W) * DISC_T
    strap = len(STRAP_SLOT_XY) * _slot_area(STRAP_SLOT_L, STRAP_SLOT_W) * DISC_T
    from cad_modeling.fits import M2_5_MEDIUM
    counterbores = 2 * math.pi * ((IMU_COUNTERBORE_D / 2) ** 2 - (M2_5_MEDIUM / 2) ** 2) * IMU_COUNTERBORE_DEPTH
    expected = solid - len(grid_holes()) * hole_vol - feature_vol \
        - cable - strap - counterbores

    disc = build_disc()
    assert abs(disc.volume - expected) < 0.005 * expected, (
        f"disc volume {disc.volume:.0f}, construction expects {expected:.0f}")


def test_grid_holes_are_real_holes():
    """Probes through grid centers must find air; a probe between the grid
    knots must find material."""
    disc = Pos(0, 0, DISC_Z) * build_disc()
    holes = sorted(grid_holes(), key=lambda p: math.hypot(*p))
    sample = holes[:: max(1, len(holes) // 6)][:6]
    for x, y in sample:
        probe = Pos(x, y, DISC_Z) * Cylinder(1.4, DISC_T + 2)
        vol = _intersect_volume(disc, probe)
        assert vol < 1.0, f"grid hole ({x},{y}) is not open ({vol:.1f} mm^3)"
    between = Pos(7.5, 30.0, DISC_Z) * Cylinder(1.4, DISC_T + 2)
    assert _intersect_volume(disc, between) > 10.0, (
        "material between grid knots is missing -- cuts merged")


@requires_bracket
def test_bracket_bolts_align_bracket_and_disc():
    """Disc holes (our constants) vs bracket holes (vendor STEP, re-based):
    a bolt-axis probe must pass through BOTH without hitting material."""
    disc = Pos(0, 0, DISC_Z) * build_disc()
    bracket = _placed(False, load_bracket_visual(), flip="z")
    bracket_l = _placed(True, load_bracket_visual(), flip="z")
    holes = BRACKET_BASE_BOLTS_R + [(-x, y) for x, y in BRACKET_BASE_BOLTS_R]
    for x, y in holes:
        probe = Pos(x, y, DISC_Z - DISC_T / 2 - 2) * Cylinder(1.5, 12)
        vol = _intersect_volume(bracket, probe)
        vol += _intersect_volume(disc, probe)
        assert vol < 1.0, f"base bolt ({x},{y}): bracket+disc {vol:.1f} mm^3"
        vol = _intersect_volume(bracket_l, probe)
        assert vol < 1.0, f"left base bolt ({x},{y}): {vol:.1f} mm^3"


# ---------------- sonar bracket ----------------
def test_sonar_tab_bolts_align_bracket_and_lower_disc():
    """Tab holes (our constants) vs the placed bracket + lower disc: a
    bolt-axis probe must pass through BOTH without hitting material."""
    lower, _ = build_our_parts()[:2]
    children = {c.label: c for c in build_assembly().children}
    bracket = children["sonar_bracket"]
    for sx in (+1, -1):
        x, y = sx * SONAR_TAB_XY[0], SONAR_TAB_XY[1]
        probe = Pos(x, y, DISC_Z + 2) * Cylinder(1.5, 12)
        vol = _intersect_volume(lower, probe)
        vol += _intersect_volume(bracket, probe)
        assert vol < 1.0, f"sonar tab bolt ({x},{y}): {vol:.1f} mm^3"


def test_sonar_cans_land_on_the_bracket_face_holes():
    """The can-axis line through the placed sonar must pass through the
    bracket face's big holes without touching bracket material."""
    children = {c.label: c for c in build_assembly().children}
    bracket, sonar = children["sonar_bracket"], children["sonar"]
    can_z = DISC_Z + DISC_T / 2 + SONAR_CAN_AXIS_Z
    for sx in (+1, -1):
        probe = (Pos(sx * SONAR_CAN_PITCH / 2, SONAR_FACE_Y, can_z)
                 * Rot(X=90) * Cylinder(6, 20))
        vol = _intersect_volume(bracket, probe)
        assert vol < 1.0, (
            f"can axis x={sx * SONAR_CAN_PITCH / 2} hits the bracket "
            f"({vol:.1f} mm^3)")
    # and the sonar really sits against the bracket face, cans forward
    sb = sonar.bounding_box()
    assert sb.min.Y > SONAR_FACE_Y, "sonar is not in front of the bracket"


# ---------------- line bar ----------------
def test_line_bar_rides_at_working_height():
    children = {c.label: c for c in build_assembly().children}
    bar = children["line_sensor"].bounding_box()
    assert abs(bar.min.Z - LINE_FACE_Z) < 1e-6
    assert 5.0 <= bar.min.Z <= 15.0, (
        f"line face at {bar.min.Z:.1f} mm: digital IR wants ~10 mm")
    assert bar.max.Y <= -23.0, "line bar must clear the bracket by 3 mm"


def test_line_posts_span_disc_to_bar():
    from cad_modeling.balance_bot import build_line_posts
    posts = build_line_posts()
    bb = posts.bounding_box()
    assert abs(bb.max.Z - (DISC_Z - DISC_T / 2)) < 1e-6, (
        "posts must start at the disc underside")
    assert abs(bb.min.Z - (DISC_Z - DISC_T / 2 - LINE_POST_L)) < 1e-6


def test_line_posts_land_on_the_module_holes():
    """Posts must bolt through the bar's own D3 holes: X on a hole axis
    (outer pair), Y on the bar centerline. The 2026-09-27 listing drawing
    puts the holes at +-8.055/+-21.025 -- the pre-fix +-40 posts reached
    past every hole (assembly-impossible, caught before cutting)."""
    from cad_modeling.sensors import LINE_BAR_HOLE_DX
    assert LINE_POST_XY[0] in LINE_BAR_HOLE_DX, (
        f"post x = +-{LINE_POST_XY[0]} is not on a module hole axis")
    assert -LINE_POST_XY[1] == LINE_BAR_Y, (
        "post y must land on the bar centerline hole row")


def test_line_posts_stand_on_disc_holes():
    """Same probe gate as the standoffs: the post columns must stand on
    real disc holes. The volume budget proves 16 feature holes exist,
    not where they are."""
    disc = Pos(0, 0, DISC_Z) * build_disc()
    for sx in (+1, -1):
        probe = (Pos(sx * LINE_POST_XY[0], -LINE_POST_XY[1], DISC_Z)
                 * Cylinder(1.4, DISC_T + 2))
        assert _intersect_volume(disc, probe) < 1.0, (
            "line post column not on a disc hole")


# ---------------- standoffs ----------------
def test_standoffs_span_the_tiers():
    col = build_standoffs()
    bb = col.bounding_box()
    assert abs(bb.min.Z - (DISC_Z + DISC_T / 2)) < 1e-6
    assert abs(bb.max.Z - (DISC2_Z - DISC_T / 2)) < 1e-6
    # the columns stand exactly on the disc's standoff holes
    disc = Pos(0, 0, DISC_Z) * build_disc()
    for sx in (+1, -1):
        for sy in (+1, -1):
            probe = (Pos(sx * STANDOFF_HALF_X, sy * STANDOFF_HALF_Y, DISC_Z)
                     * Cylinder(1.4, DISC_T + 2))
            assert _intersect_volume(disc, probe) < 1.0, (
                "standoff column not on a disc hole")


# ---------------- assembly ----------------
def test_assembly_collision_has_no_solid_interference():
    children = build_assembly(mode="collision").children
    assert len(children) == 22, (
        "2 discs + standoffs + sonar bracket + 4 electronics + module mounts + battery retention + sonar + line posts "
        "+ line bar + 2x (wheel, bracket, motor)")
    bad = []
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            bi, bj = children[i].bounding_box(), children[j].bounding_box()
            if not (bi.min.X <= bj.max.X and bj.min.X <= bi.max.X
                    and bi.min.Y <= bj.max.Y and bj.min.Y <= bi.max.Y
                    and bi.min.Z <= bj.max.Z and bj.min.Z <= bi.max.Z):
                continue
            volume = _intersect_volume(children[i], children[j])
            if volume > 1.0:
                bad.append((children[i].label, children[j].label, round(volume, 1)))
    assert not bad, f"interfering pairs: {bad}"


def test_wheels_sit_outboard_of_the_flange():
    for sy in (+1, -1):
        bb = _placed(sy < 0, build_wheel_envelope()).bounding_box()
        inner = bb.min.X if sy > 0 else bb.max.X
        assert abs(abs(inner) - (FLANGE_X + WHEEL_SEAT_X)) < 1e-6
        # tolerance, not ==: bbox arithmetic on a rotated+mirrored placement
        # lands on 25.000000000000004, which is the same width.
        assert abs((bb.max.X - bb.min.X) - WHEEL_W) < 1e-9


# ---------------- vendor file gates ----------------
@requires_motor
def test_vendor_motor_step_is_still_LR24():
    assert os.path.exists(MOTOR_STEP_PATH), f"missing: {MOTOR_STEP_PATH}"
    part = load_motor_visual()
    bb = part.bounding_box()
    axis_len = bb.max.X - bb.min.X
    assert 74.0 <= axis_len <= 80.0, f"axis length {axis_len:.1f}: wrong variant?"
    assert abs(bb.max.X - 20.8) < 1.5, "shaft tip moved: re-base broken"
    taps = 0
    for f in part.faces().filter_by(GeomType.CYLINDER):
        ad = BRepAdaptor_Surface(f.wrapped)
        try:
            cyl = ad.Cylinder()
        except Exception:
            continue
        r = cyl.Radius()
        d = cyl.Axis().Direction()
        if not (1.0 <= r <= 1.5 and abs(d.X()) > 0.9):
            continue
        loc = cyl.Axis().Location()
        if abs(math.hypot(loc.Y(), loc.Z() + OUTPUT_SHAFT_OFFSET) - FLANGE_BC / 2) < 1.0:
            taps += 1
    assert taps >= 6, (
        f"expected 6 flange taps on the D31 circle, found {taps}: "
        "the vendor file is not the variant we settled the interface on")


@requires_bracket
def test_vendor_bracket_step_still_fits():
    assert os.path.exists(BRACKET_STEP_PATH), f"missing: {BRACKET_STEP_PATH}"
    part = load_bracket_visual()
    assert len(part.solids()) == 1, "bracket STEP should import as one solid"
    # axle offset fact: base outer face sits AXLE_OFFSET above the bore axis
    bb = part.bounding_box()
    assert abs(bb.max.Z - AXLE_OFFSET) < 1.5, (
        f"bracket axle offset moved: base top {bb.max.Z:.1f} vs {AXLE_OFFSET}")


@requires_gy521
def test_vendor_gy521_step_still_fits():
    from cad_modeling.sensors import _GY521_STEP, load_gy521_visual
    path = os.path.normpath(_GY521_STEP)
    assert os.path.exists(path), f"missing: {path}"
    part = load_gy521_visual()
    assert len(part.solids()) == 1, "GY-521 STEP should import as one solid"
    bb = part.bounding_box()
    assert abs((bb.max.X - bb.min.X) - 20.35) < 0.5, "wrong board variant?"
    assert abs((bb.max.Y - bb.min.Y) - 15.65) < 0.5, "wrong board variant?"
    assert abs(bb.min.Z) < 1e-6, "re-base must put the board bottom on z=0"


# ---------------- electronics ----------------
# mode="visual" needs the full vendor set, incl. the GrabCAD LR24 motor that
# needs a logged-in session -- stricter than the single-model gates above.
@requires_visual_vendor
def test_visual_assembly_swaps_imu_for_vendor_board():
    children = {c.label: c for c in build_assembly(mode="visual").children}
    assert len(children) == 22, "the IMU swap must stay 1:1"
    bb = children["imu"].bounding_box()
    assert abs((bb.max.X - bb.min.X) - 20.35) < 0.5
    assert abs(bb.min.Z - IMU_BOTTOM_Z) < 0.01, (
        "GY-521 must use its dedicated underside mounting height")


def test_strap_slots_flank_the_battery():
    """Zip ties route through the slots and over the pack: both slots must
    sit fully clear of the battery footprint (the pre-LiPo placeholder sat
    ON both slots -- ties could never route through)."""
    from cad_modeling.deck import BATTERY, BATTERY_XYZ
    x_lo = BATTERY_XYZ[0] - BATTERY[0] / 2
    x_hi = BATTERY_XYZ[0] + BATTERY[0] / 2
    disc = Pos(0, 0, DISC_Z) * build_disc()
    for x, y in STRAP_SLOT_XY:
        clear = x + STRAP_SLOT_W / 2 < x_lo or x - STRAP_SLOT_W / 2 > x_hi
        assert clear, f"strap slot at ({x},{y}) runs under the battery"
        probe = Pos(x, y, DISC_Z) * Cylinder(1.0, DISC_T + 2)
        assert _intersect_volume(disc, probe) < 0.01
    assert len(STRAP_SLOT_XY) == 4 and len(STRAP_SLOT_Y) == 2


# ---------------- helpers ----------------
def test_recesses_remove_wheel_and_bracket_material_only():
    """Independent probes distinguish real wheel pockets from a round disc."""
    lower, _ = build_our_parts()
    for side in (-1, 1):
        pocket = Pos(side * (WHEEL_INNER_X - 1), 25, DISC_Z) * Cylinder(0.5, DISC_T + 2)
        assert _intersect_volume(lower, pocket) < 0.01
        supported = Pos(side * 75, 25, DISC_Z) * Cylinder(1.4, DISC_T + 2)
        assert _intersect_volume(lower, supported) > 10


@requires_motor
def test_vendor_shafts_are_coaxial_with_both_wheel_bores():
    """Measure actual D6 cylindrical axes, independent of bounding boxes."""
    for left in (False, True):
        motor = _placed(left, load_motor_visual())
        shafts = []
        for face in motor.faces().filter_by(GeomType.CYLINDER):
            c = BRepAdaptor_Surface(face.wrapped).Cylinder()
            if abs(c.Radius() - 3.0) < 0.01 and abs(c.Axis().Direction().X()) > 0.99:
                shafts.append(c.Axis().Location())
        assert shafts, "no output shaft found"
        assert all(abs(p.Y()) < 1e-6 and abs(p.Z() - AXLE_Z) < 1e-6 for p in shafts)
        wheel = _placed(left, build_wheel_envelope())
        assert _intersect_volume(motor, wheel) < 0.01


@requires_motor_bracket
def test_motor_flange_holes_have_matching_bracket_support():
    """Each screw axis is open AND its head has surrounding plate material."""
    for left in (False, True):
        bracket = _placed(left, load_bracket_visual())
        motor = _placed(left, load_motor_visual())
        # The vendor's three M2 screw heads have 12 tiny lobes protruding
        # 0.0669 mm beyond the flange (0.0506 mm^3 total). Record a small
        # reference-model allowance; it must not hide a housing overlap.
        assert _intersect_volume(bracket, motor) < 0.1
        for deg in range(0, 360, 60):
            y = FLANGE_BC / 2 * math.cos(math.radians(deg))
            z = -OUTPUT_SHAFT_OFFSET + FLANGE_BC / 2 * math.sin(math.radians(deg))
            axis = _placed(left, Pos((PLATE_T - FLANGE_SCREW_ENGAGEMENT) / 2, y, z)
                           * Rot(Y=90) * Cylinder(1.2, PLATE_T + FLANGE_SCREW_ENGAGEMENT))
            bearing = _placed(left, Pos(PLATE_T / 2, y, z) * Rot(Y=90) * Cylinder(3, PLATE_T))
            assert _intersect_volume(bracket, axis) < 0.01
            assert _intersect_volume(motor, axis) < 0.01
            assert _intersect_volume(bracket, bearing) > 20


@requires_visual_vendor
def test_mpu6050_mount_matches_real_board_and_disc_holes():
    children = {c.label: c for c in build_assembly("visual").children}
    imu, mount, disc = children["imu"], children["imu_mount"], children["deck_lower"]
    bb = imu.bounding_box()
    assert abs((bb.min.X + bb.max.X) / 2) < 1e-6
    assert abs((bb.min.Y + bb.max.Y) / 2) < 1e-6
    assert bb.max.Z < disc.bounding_box().min.Z
    for x, y in GY521_MOUNT_HOLES:
        probe = Pos(x, y, DISC_Z - 3) * Cylinder(1.2, 12)
        for part in (imu, mount, disc):
            assert _intersect_volume(part, probe) < 0.01
        bearing = Pos(x, y, DISC_Z - DISC_T / 2 - 1.5) * Cylinder(2, 3)
        assert _intersect_volume(mount, bearing) > 10


def test_battery_mounting_and_top_controller_clearance():
    children = {c.label: c for c in build_assembly().children}
    battery, pad, strap = (children[n] for n in ("battery", "battery_pad", "battery_strap"))
    assert abs(battery.bounding_box().min.Z - pad.bounding_box().max.Z) < 1e-6
    assert strap.bounding_box().max.Z <= children["deck_upper"].bounding_box().min.Z - 3.9
    assert children["mcu"].bounding_box().min.Z > children["deck_upper"].bounding_box().max.Z
    assert children["mcu"].bounding_box().max.Z == max(c.bounding_box().max.Z for c in children.values())


def test_imu_recessed_heads_and_standoff_engagement():
    """Real fastener envelopes fit below the pack and leave separated tips."""
    from cad_modeling.sensors import GY521_PCB_T
    children = {c.label: c for c in build_assembly().children}
    screws = children["imu_fasteners"]
    disc = children["deck_lower"]
    head_floor = DISC_Z + DISC_T / 2 - IMU_COUNTERBORE_DEPTH
    assert screws.bounding_box().max.Z < children["battery_pad"].bounding_box().min.Z
    assert DISC_T - IMU_COUNTERBORE_DEPTH >= 1.2 - 1e-9
    upper_tip = head_floor - IMU_UPPER_SCREW_L
    lower_tip = IMU_BOTTOM_Z + IMU_LOWER_SCREW_L
    assert upper_tip - lower_tip >= 0.19
    assert lower_tip - (IMU_BOTTOM_Z + GY521_PCB_T) >= 2.0
    assert disc.bounding_box().min.Z - upper_tip >= 2.5
    for name in ("deck_lower", "imu", "imu_mount", "battery_pad", "battery"):
        assert _intersect_volume(screws, children[name]) < 0.01, name
    for x, y in GY521_MOUNT_HOLES:
        pocket = Pos(x, y, head_floor + IMU_SCREW_HEAD_H / 2) * Cylinder(2.35, IMU_SCREW_HEAD_H)
        assert _intersect_volume(disc, pocket) < 0.01
        floor = Pos(x + 2.0, y, disc.bounding_box().min.Z + 0.5) * Cylinder(0.1, 1.0)
        assert _intersect_volume(disc, floor) > 0.025


def test_chassis_keeps_floor_clearance_through_twelve_degree_pitch():
    """Rotate actual shapes about the axle, independent of sensor-height math."""
    chassis = [p for p in build_assembly().children if not p.label.startswith("wheel_")]
    for degrees in (-12, 12):
        tilt = Pos(0, 0, AXLE_Z) * Rot(X=degrees) * Pos(0, 0, -AXLE_Z)
        for p in chassis:
            assert (tilt * p).bounding_box().min.Z >= 3.0, (degrees, p.label)


def test_lowered_structure_and_estimated_center_of_gravity():
    from bot import mass_properties as mp
    assert DISC_Z == 58.0 and DISC2_Z == 89.0
    com = mp.center_of_mass()
    assert abs(com[0]) < 1e-4 and abs(com[1]) < 1e-3
    assert AXLE_Z / 1000 < com[2] < 0.05368  # >5 mm below the old 58.68 mm estimate
    assert abs(mp.imu_site_pos()[2] - (IMU_BOTTOM_Z + 1.25) / 1000) < 1e-9


@requires_visual_vendor
def test_visual_assembly_has_no_solid_interference():
    children = build_assembly("visual").children
    bad = []
    for i, p in enumerate(children):
        for q in children[i + 1:]:
            a, b = p.bounding_box(), q.bounding_box()
            if not (a.min.X <= b.max.X and b.min.X <= a.max.X
                    and a.min.Y <= b.max.Y and b.min.Y <= a.max.Y
                    and a.min.Z <= b.max.Z and b.min.Z <= a.max.Z):
                continue
            volume = _intersect_volume(p, q)
            if volume > 1.0:
                bad.append((p.label, q.label, round(volume, 3)))
    assert not bad, bad


def _intersect_volume(part, probe) -> float:
    # Check the placed OCCT shapes directly. Compound.intersect in 0.13
    # can reapply imported child transforms while distributing a boolean.
    common = BRepAlgoAPI_Common(part.wrapped, probe.wrapped)
    common.Build()
    assert common.IsDone(), "geometry intersection did not complete"
    return Compound(common.Shape()).volume


def main() -> int:
    import traceback

    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
