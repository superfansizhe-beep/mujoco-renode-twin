"""Bought 37 mm bracket, referenced to the motor OUTPUT shaft.

The STEP has a 1.5 mm plate, six D3.2 flange holes, a vertical D13
shaft/boss slot and four D3.4 base holes. Its D40 edge is the outer
outline, not a bore. The plate sits outboard of the motor flange; the
lower disc sits under the base. Caliper the purchased variant.
"""
import math
import os

from build123d import Box, Cylinder, Part, Pos, Rot

from .fits import M3_MEDIUM
from .jgb37_520 import FLANGE_BC, OUTPUT_SHAFT_OFFSET, SHAFT_SHOULDER_D

# --- constants from the vendor STEP (caliper the real bracket) ---
BORE_D = 13.0            # boss-slot width; D40 was the OUTER outline
GEARBOX_BASE_OFFSET = 28.0
AXLE_OFFSET = GEARBOX_BASE_OFFSET - OUTPUT_SHAFT_OFFSET
PLATE_T = 1.5            # STEP: plate x -1.5..0 before rebasing
PLATE_W = 40.0           # model z -20..20
PLATE_H = 48.0           # model y -28..20
BASE_L = 41.0            # model x 0..41, extends inboard from the plate
BASE_T = 1.5             # STEP: base z 26.5..28 before shaft rebasing
BEND_ENVELOPE = 2.262    # STEP bend radius, envelope extends into the inner corner
SLOT_HALF_SPAN = 7.0
BASE_BOLT_X_REL = (9.0, 33.0)   # from the plate face, inboard
BASE_BOLT_Y = 15.0              # fore/aft of the axle line

assert BORE_D >= SHAFT_SHOULDER_D + 0.8

_VENDOR_STEP = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "vendor", "jgb37-520",
    "37mm_mounting_bracket.step")


def build_bracket_envelope() -> Part:
    """Plate/base envelope with real shaft and mounting-hole openings."""
    center_x = PLATE_T / 2
    plate = Pos(center_x, 0, 4.0 - OUTPUT_SHAFT_OFFSET) * Box(PLATE_T, PLATE_W, PLATE_H)
    slot_center_z = -OUTPUT_SHAFT_OFFSET
    slot = Pos(center_x, 0, slot_center_z) * Box(PLATE_T + 2, BORE_D, 2 * SLOT_HALF_SPAN)
    for sz in (-1, 1):
        slot += (Pos(center_x, 0, slot_center_z + sz * SLOT_HALF_SPAN)
                 * Rot(Y=90) * Cylinder(BORE_D / 2, PLATE_T + 2))
    flange_holes = [
        Pos(center_x, FLANGE_BC / 2 * math.cos(math.radians(deg)),
            -OUTPUT_SHAFT_OFFSET + FLANGE_BC / 2 * math.sin(math.radians(deg)))
        * Rot(Y=90) * Cylinder(1.6, PLATE_T + 2)
        for deg in range(0, 360, 60)
    ]
    plate = plate - slot - flange_holes
    base_z = AXLE_OFFSET - BASE_T / 2
    base = Pos(PLATE_T - BASE_L / 2, 0, base_z) * Box(
        BASE_L, PLATE_W, BASE_T)
    base_holes = [
        Pos(PLATE_T - dx, sy * BASE_BOLT_Y, base_z) * Cylinder(M3_MEDIUM / 2, BASE_T + 2)
        for dx in BASE_BOLT_X_REL for sy in (-1, 1)
    ]
    bend = Pos(PLATE_T - BEND_ENVELOPE / 2, 0,
               AXLE_OFFSET - BEND_ENVELOPE / 2) * Box(
                   BEND_ENVELOPE, PLATE_W, BEND_ENVELOPE)
    env = plate + (base - base_holes) + bend
    env.label = "bracket_envelope"
    return env


def load_bracket_visual() -> Part:
    """Vendor part with motor mating face x=0 and output shaft z=0."""
    from build123d import import_step, Rot

    part = import_step(_VENDOR_STEP)
    part = Pos(PLATE_T, 0, -OUTPUT_SHAFT_OFFSET) * Rot(0, 0, 180) * Rot(-90, 0, 0) * part
    bb = part.bounding_box()
    assert abs(bb.min.X - (PLATE_T - BASE_L)) < 0.1 and abs(bb.max.X - PLATE_T) < 0.1, (
        f"bracket re-base X off: [{bb.min.X:.1f},{bb.max.X:.1f}]")
    assert abs(bb.min.Z - (-20.0 - OUTPUT_SHAFT_OFFSET)) < 0.1 and abs(bb.max.Z - AXLE_OFFSET) < 0.1, (
        f"bracket re-base Z off: [{bb.min.Z:.1f},{bb.max.Z:.1f}] "
        "(base must be up, axle offset 28)")
    part.label = "bracket_visual"
    return part


if __name__ == "__main__":
    env = build_bracket_envelope()
    bb = env.bounding_box()
    print(f"envelope: X[{bb.min.X:.1f},{bb.max.X:.1f}] "
          f"Y[{bb.min.Y:.1f},{bb.max.Y:.1f}] Z[{bb.min.Z:.1f},{bb.max.Z:.1f}]")
    vis = load_bracket_visual()
    bb = vis.bounding_box()
    print(f"visual:   X[{bb.min.X:.1f},{bb.max.X:.1f}] "
          f"Y[{bb.min.Y:.1f},{bb.max.Y:.1f}] Z[{bb.min.Z:.1f},{bb.max.Z:.1f}]")
