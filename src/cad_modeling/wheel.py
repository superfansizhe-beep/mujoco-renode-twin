"""Bought wheel -- placeholder envelope only (shaft-hub type).

The wheel is NOT fabricated by us (ownership decision 2026-09-27, revised
the same day to the L-bracket architecture): with the motor hanging in a
catalog L bracket, the wheel rides the D6 output shaft -- hub against the
D12x5 shoulder, setscrews onto the D-flat. D80 rubber wheels with a metal
hub for 6 mm shafts are catalog parts; that kills the self-made-drivetrain
risk class (the old printed tire was a free-floating solid -- git history).

Until the bought wheel is calipered these are GUESS placeholders driving
an envelope for collision tests and visuals. New caliper items with this
mount: hub bore/width, D-flat depth, setscrew size.
"""
from build123d import Cylinder, Part, Pos, Rot

from .jgb37_520 import SHAFT_D, SHAFT_SHOULDER_L

WHEEL_D = 80.0   # GUESS -- caliper the bought wheel
WHEEL_W = 25.0   # GUESS -- axial wheel envelope, independent of shaft length
WHEEL_SEAT_X = SHAFT_SHOULDER_L
WHEEL_BORE_D = SHAFT_D + 0.2   # clearance envelope, actual hub fit pending

# --- Hub/shaft joint: the ONLY torque bottleneck left in this architecture ---
# Stall demand 0.57 N*m. A bare M3 setscrew on the ROUND shaft holds only
# ~0.5 N*m by friction -- coin flip. Three assembly requirements are part
# of the design, not optional:
#   1. setscrew must seat on the D-flat (rotate hub to find it, mark it);
#   2. thread the setscrew with Loctite 242 (torque reversals back screws
#      out -- the classic balance-car failure);
#   3. hub face butted hard against the D12x5 shoulder (kills axial play).
# When buying: metal hub, TWO setscrews at 90 deg, width >= 10 mm -- or a
# split-clamp hub (~2-3x the holding torque). No FDM here, ever: layer
# adhesion + creep cannot carry torque (this is why the shaft carried
# nothing in the old design).
HUB_SETSCREW_TORQUE = 0.5   # N*m, assembly spec
HUB_HOLD_ESTIMATE = 1.0     # N*m, setscrew seated on the flat + Loctite; ESTIMATE


def build_wheel_envelope() -> Part:
    """D80 x 25 wheel seated on the shoulder, with a real shaft bore."""
    center_x = WHEEL_SEAT_X + WHEEL_W / 2
    env = Pos(center_x, 0, 0) * Rot(Y=90) * Cylinder(WHEEL_D / 2, WHEEL_W)
    bore = Pos(center_x, 0, 0) * Rot(Y=90) * Cylinder(WHEEL_BORE_D / 2, WHEEL_W + 2)
    env = env - bore
    env.label = "wheel_envelope_bought"
    return env
