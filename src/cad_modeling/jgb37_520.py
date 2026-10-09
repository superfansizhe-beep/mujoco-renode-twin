"""JGB37-520 gearmotor -- interface constants + envelope + vendor visual.

Ownership structure (2026-09-27 decision): the motor is BOUGHT. We do not
model its internals. This module carries:

1. the interface constants that OUR fabricated parts are driven by,
   each tagged with its provenance:
   - SETTLED  : three independent sources agree (vendor drawing shipped in
                assets/vendor/jgb37-520/grabcad_encoder/JGB37-520_size.png,
                the GrabCAD LR24 STEP measured hole-by-hole, and the GitHub
                geared_body/bracket pair) -- caliper still wins on conflict,
                but these are no longer guesses;
   - SHEET    : from that dimensioned drawing, not yet calipered;
   - STEP     : measured off the shipped LR24 STEP;
   - GUESS    : placeholder, must be calipered before fabrication.
2. build_motor_envelope(): conservative collision primitive stack;
3. load_motor_visual(): the vendor STEP, re-based to our convention
   (axis +X outboard, flange face plane at x=0, shaft tip toward +X).

Local datum: output shaft axis = X at y=z=0, flange mating plane x=0.
The gearbox axis is below the output shaft: the supplied LR24 STEP has
7 mm eccentricity (the separate family drawing says 5.5 mm; measure the
purchased variant before fabrication). Both modules rotate about Z when
placed, preserving the same shaft and gearbox heights on both sides.
"""
import math
import os

from build123d import Compound, Cylinder, Part, Pos, Rot

from .fits import M3_TAP_DRILL

# --- Flange: SETTLED (drawing == GrabCAD STEP == GitHub pair) ---
FLANGE_D = 37.0
FLANGE_T = 3.0            # SHEET (drawing); STEP models ~3.5 incl. chamfer
FLANGE_BC = 31.0          # bolt circle diameter (R15.5)
FLANGE_TAP_N = 6          # 6x M3, 60 deg apart, angles 0,60,...,300
FLANGE_TAP_D = M3_TAP_DRILL   # modeled at tap drill
FLANGE_TAP_DEPTH = 3.5    # drawing "profondeur 3.5MM"; STEP: 3.1 + 0.4 chamfer
# Usable thread engagement cap for OUR screw stack (0.3 reserved).
FLANGE_SCREW_ENGAGEMENT = 3.0
FLANGE_THROUGH_N = 3      # 3x D4 through at 30/150/270 deg (not used by us)
FLANGE_THROUGH_D = 4.0

assert FLANGE_SCREW_ENGAGEMENT <= FLANGE_TAP_DEPTH - 0.3

# --- Gearbox: STEP (LR24 file shipped in this repo) ---
GEARBOX_L = 24.2          # flange face -> barrel rear, LR24 tier (1:30, probable)
assert abs(GEARBOX_L - 24.0) < 0.5

# Output interface measured from the supplied LR24 STEP, not the real unit.
OUTPUT_SHAFT_OFFSET = 7.0
SHAFT_D = 6.0
SHAFT_SHOULDER_D = 12.0
SHAFT_SHOULDER_L = 5.0
SHAFT_TIP_X = 20.8

# --- Rear section (can + encoder): SHEET vs STEP CONFLICT, documented ---
# Drawing total 70.2+-0.4 for the L=26.5 tier -> LR24 body ~= 67.7 -> rear ~= 43.5.
# The GrabCAD model's rear is ~32.6 (simplified encoder); we take the drawing.
REAR_L = 43.5             # SHEET-derived, caliper before final build
REAR_D = 33.2             # encoder collar dia (drawing) -- conservative envelope

# --- vendor STEP file ---
_VENDOR_STEP = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "vendor", "jgb37-520",
    "grabcad_encoder", "jgb37-520_LR24.step")

# Stall torque of the 1:30 tier (Hiwonder table): 5.8 kg*cm
STALL_TORQUE = 0.57       # N*m, SHEET


def motor_body_length() -> float:
    """Flange face to encoder tail (no shaft)."""
    return GEARBOX_L + REAR_L


def build_motor_envelope() -> Part:
    """Conservative collision stack, flange face at x=0, body toward -X.

    Gearbox/rear cylinders retain their eccentricity. The shoulder and
    shaft are included, so wheel-bore alignment is a real interface.
    """
    gb = Pos(-GEARBOX_L / 2, 0, -OUTPUT_SHAFT_OFFSET) * Rot(Y=90) * Cylinder(FLANGE_D / 2, GEARBOX_L)
    rear = Pos(-(GEARBOX_L + REAR_L / 2), 0, -OUTPUT_SHAFT_OFFSET) * Rot(Y=90) * Cylinder(REAR_D / 2, REAR_L)
    shoulder = Pos(SHAFT_SHOULDER_L / 2, 0, 0) * Rot(Y=90) * Cylinder(SHAFT_SHOULDER_D / 2, SHAFT_SHOULDER_L)
    shaft_l = SHAFT_TIP_X - SHAFT_SHOULDER_L
    shaft = Pos(SHAFT_SHOULDER_L + shaft_l / 2, 0, 0) * Rot(Y=90) * Cylinder(SHAFT_D / 2, shaft_l)
    env = gb + rear + shoulder + shaft
    env.label = "motor_envelope"
    return env


def load_motor_visual() -> Part:
    """Vendor LR24 STEP re-based: model axis +Y -> our -X (body), shaft -> +X.

    Model coords: flange face y=0, gearbox +y, shaft -y, radial = X/Z.
    Rotation Z+90 maps (x,y,z)->(-y,x,z); shifting Z by the measured
    eccentricity puts the output shaft at y=z=0.
    """
    from build123d import import_step

    part = import_step(_VENDOR_STEP)
    part = Pos(0, 0, -OUTPUT_SHAFT_OFFSET) * Rot(0, 0, 90) * part
    # Bake the vendor's nested locations into the rebased solids.
    # Distributing booleans over nested assembly children otherwise
    # misplaces its M2 screws in build123d 0.13.
    part = Compound(children=list(part.solids()))
    bb = part.bounding_box()
    assert bb.max.X - bb.min.X > 70, "vendor motor: axis length wrong after re-base"
    assert abs(bb.max.X - 20.8) < 1.5 and abs(bb.min.X + 56.8) < 1.5, (
        f"vendor motor re-base off: X span [{bb.min.X:.1f}, {bb.max.X:.1f}]")
    part.label = "motor_visual"
    return part


if __name__ == "__main__":
    env = build_motor_envelope()
    bb = env.bounding_box()
    print(f"envelope: X[{bb.min.X:.1f},{bb.max.X:.1f}] "
          f"Y[{bb.min.Y:.1f},{bb.max.Y:.1f}] Z[{bb.min.Z:.1f},{bb.max.Z:.1f}]")
    vis = load_motor_visual()
    bb = vis.bounding_box()
    print(f"visual:   X[{bb.min.X:.1f},{bb.max.X:.1f}] "
          f"Y[{bb.min.Y:.1f},{bb.max.Y:.1f}] Z[{bb.min.Z:.1f},{bb.max.Z:.1f}]")
