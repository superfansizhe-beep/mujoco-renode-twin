"""Full two-wheeled self-balancing bot assembly.

Coordinate system: X = vehicle width, Y = forward, Z = up.

Two assembly modes, same placement math:

- ``collision``: motors, wheels and brackets are conservative primitive
  envelopes built from the constants sheet; the regression tests
  run on this and are independently checked against placed vendor BREPs.
- ``visual``: motors and brackets are the vendor STEPs (re-based);
  everything else identical; this is what the STEP/GLB export uses.

Our fabricated part: the deck disc (cut x2, identical tiers). Everything
else -- including the sonar bracket and line bar -- is bought.
"""
import os

from build123d import Axis, Circle, Color, Compound, Cylinder, Pos, Rot, Unit, export_gltf, export_step
from build123d.exporters import ExportDXF

from .bracket import build_bracket_envelope, load_bracket_visual
from .deck import (
    DISC_T, build_battery_retention, build_disc, build_electronics, build_module_mounts,
)
from .jgb37_520 import build_motor_envelope, load_motor_visual
from .layout import (
    AXLE_Z, DISC2_Z, DISC_Z, FLANGE_X, LINE_BAR_Y, LINE_POST_L,
    LINE_POST_XY, SONAR_FACE_Y, STANDOFF_D, STANDOFF_HALF_X,
    STANDOFF_HALF_Y,
    IMU_COUNTERBORE_D, IMU_MOUNT_XY,
)
from .sensors import (
    GY521_MOUNT_HOLES, SONAR_CAN_AXIS_Z, build_line_bar_envelope, build_sonar_bracket_envelope,
    build_sonar_envelope,
)
from .wheel import build_wheel_envelope


def build_our_parts() -> list:
    """The part WE fabricate: two placed deck discs (same file, x2)."""
    disc = build_disc()
    lower = Pos(0, 0, DISC_Z) * disc
    lower.label = "deck_lower"
    upper = Pos(0, 0, DISC2_Z) * disc
    upper.label = "deck_upper"
    return [lower, upper]


def build_standoffs() -> Compound:
    """Four brass M3 columns clamping the two discs together."""
    z0 = DISC_Z + DISC_T / 2
    height = DISC2_Z - DISC_T / 2 - z0
    columns = [
        Pos(sx * STANDOFF_HALF_X, sy * STANDOFF_HALF_Y, z0 + height / 2)
        * Cylinder(STANDOFF_D / 2, height)
        for sx in (+1, -1) for sy in (+1, -1)
    ]
    col = columns[0] + columns[1] + columns[2] + columns[3]
    col.color = Color(0.85, 0.7, 0.2)
    col.label = "standoffs"
    return col


def build_line_posts() -> Compound:
    """Two long brass posts hanging the line bar under the lower disc."""
    z0 = DISC_Z - DISC_T / 2 - LINE_POST_L
    posts = [
        Pos(sx * LINE_POST_XY[0], -LINE_POST_XY[1], z0 + LINE_POST_L / 2)
        * Cylinder(STANDOFF_D / 2, LINE_POST_L)
        for sx in (+1, -1)
    ]
    both = posts[0] + posts[1]
    both.color = Color(0.85, 0.7, 0.2)
    both.label = "line_posts"
    return both


def _placed(left_mirror: bool, part, flip: str = "z"):
    """Place a shaft-datum module at the axle, preserving eccentricity.

    Both sides use a Z half-turn: shaft height and bracket base stay up.
    The optional Y turn is retained for callers with truly symmetric parts.
    """
    if left_mirror:
        rot = Rot(0, 180, 0) if flip == "y" else Rot(0, 0, 180)
        return Pos(-FLANGE_X, 0, AXLE_Z) * rot * part
    return Pos(FLANGE_X, 0, AXLE_Z) * part


def build_assembly(mode: str = "collision") -> Compound:
    if mode not in ("collision", "visual"):
        raise ValueError(f"unknown mode {mode!r}")
    children = list(build_our_parts())
    children.append(build_standoffs())
    children.extend(build_electronics(mode))
    children.extend(build_module_mounts())
    children.extend(build_battery_retention())

    # sensors: the sonar rides its compact bracket on the lower disc's front
    # edge; the line bar hangs under the tail on its posts
    sonar_bracket = (Pos(0, SONAR_FACE_Y, DISC_Z + DISC_T / 2)
                     * build_sonar_bracket_envelope())
    sonar_bracket.label = "sonar_bracket"
    sonar_bracket.color = Color(0.2, 0.2, 0.22)
    children.append(sonar_bracket)
    sonar = (Pos(0, SONAR_FACE_Y + 1.0, DISC_Z + DISC_T / 2 + SONAR_CAN_AXIS_Z)
             * build_sonar_envelope())
    sonar.label = "sonar"
    sonar.color = Color(0.3, 0.55, 0.75)
    children.append(sonar)
    children.append(build_line_posts())
    line_bar = (Pos(0, LINE_BAR_Y, DISC_Z - DISC_T / 2 - LINE_POST_L)
                * build_line_bar_envelope())
    line_bar.label = "line_sensor"
    line_bar.color = Color(0.35, 0.2, 0.5)
    children.append(line_bar)

    for sy in (+1, -1):
        left = sy < 0
        wheel = _placed(left, build_wheel_envelope())
        wheel.label = "wheel_l_placeholder" if left else "wheel_r_placeholder"
        wheel.color = Color(0.15, 0.15, 0.15)
        children.append(wheel)

        bracket = _placed(left, load_bracket_visual() if mode == "visual"
                          else build_bracket_envelope(), flip="z")
        bracket.label = ("bracket_l" if left else "bracket_r") + (
            "_visual" if mode == "visual" else "_envelope")
        bracket.color = Color(0.2, 0.2, 0.22)
        children.append(bracket)

        motor = _placed(left, load_motor_visual() if mode == "visual"
                        else build_motor_envelope(), flip="z")
        motor.label = ("motor_l" if left else "motor_r") + (
            "_visual" if mode == "visual" else "_envelope")
        motor.color = Color(0.55, 0.55, 0.58)
        children.append(motor)

    return Compound(children=children)


def build_fabricated_parts() -> Compound:
    """Export target for the laser cutter: ONE disc (cut 2x)."""
    return Compound(children=[build_disc()])


def export_disc_profiles(out_dir: str) -> None:
    """Separate through-cut DXF from the secondary top-face counterbores."""
    disc = build_disc()
    bottom_face = disc.faces().filter_by(Axis.Z).sort_by(Axis.Z)[0]
    through = Pos(0, 0, DISC_T / 2) * bottom_face
    cut = ExportDXF(unit=Unit.MM)
    cut.add_shape(through)
    cut.write(os.path.join(out_dir, "deck_disc_cut.dxf"))
    counterbores = ExportDXF(unit=Unit.MM)
    counterbores.add_shape([
        Pos(IMU_MOUNT_XY[0] + x, IMU_MOUNT_XY[1] + y) * Circle(IMU_COUNTERBORE_D / 2)
        for x, y in GY521_MOUNT_HOLES
    ])
    counterbores.write(os.path.join(out_dir, "deck_disc_top_counterbores.dxf"))


def _vendor_models_present() -> bool:
    from . import bracket, jgb37_520, sensors
    return all(os.path.isfile(p) for p in
               (jgb37_520._VENDOR_STEP, bracket._VENDOR_STEP,
                sensors._GY521_STEP))


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output")
    os.makedirs(out_dir, exist_ok=True)

    mode = "visual" if _vendor_models_present() else "collision"
    if mode == "collision":
        print("vendor STEPs not fetched (assets/vendor/README.md) -- "
              "exporting the envelope assembly instead")
    a = build_assembly(mode=mode)
    bb = a.bounding_box()
    print(f"assembly: X={bb.max.X - bb.min.X:.1f}  Y={bb.max.Y - bb.min.Y:.1f}  "
          f"Z={bb.max.Z - bb.min.Z:.1f} mm")
    print(f"min Z = {bb.min.Z:.2f}")

    export_step(a, os.path.join(out_dir, "balance_bot.step"))
    export_gltf(a, os.path.join(out_dir, "balance_bot.glb"), binary=True,
                linear_deflection=0.05, angular_deflection=0.15)
    print("wrote balance_bot.step / .glb")

    export_step(build_fabricated_parts(),
                os.path.join(out_dir, "fabricated_parts.step"))
    print("wrote fabricated_parts.step (deck disc, cut x2)")
    export_disc_profiles(out_dir)
    print("wrote deck_disc_cut.dxf / deck_disc_top_counterbores.dxf (top depth 1.8 mm)")

    web_models = os.path.join(os.path.dirname(__file__), "..", "..", "web", "public", "models")
    os.makedirs(web_models, exist_ok=True)
    export_gltf(a, os.path.join(web_models, "balance_bot.gltf"),
                linear_deflection=0.05, angular_deflection=0.15)
    print("refreshed web/public/models/balance_bot.gltf / .bin")
