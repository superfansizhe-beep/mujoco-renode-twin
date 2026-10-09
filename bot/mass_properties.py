"""Mass properties for the bot -- every constant carries its provenance.

Geometry comes from the CAD modules (mm, single source; the bot converts
to SI), masses are provenance-tagged constants: CITE (web-checked) /
CALC (CAD volume x density) / WEIGH (pending scales) / GUESS
(placeholder). The chassis is LUMPED: each part becomes one
primitive geom with an explicit mass, and MuJoCo sums the inertias
(inertiafromgeom "auto" with explicit geom masses).
"""
import math

from build123d import CenterOf

from cad_modeling import layout
from cad_modeling.bracket import BASE_L, PLATE_W, load_bracket_visual
from cad_modeling.deck import (
    BATTERY, BATTERY_XYZ, DRIVER_XYZ, IMU_XYZ, MCU_XYZ, build_disc,
)
from cad_modeling.jgb37_520 import FLANGE_D, GEARBOX_L, OUTPUT_SHAFT_OFFSET, REAR_D, REAR_L
from cad_modeling.sensors import GY521_SIZE, SONAR_CAN_AXIS_Z, SONAR_FACE, build_sonar_bracket_envelope

MM = 1e-3   # CAD mm -> SI m

# ---------------- provenance-tagged masses (CITE/CALC/WEIGH/GUESS) ----------------
MOTOR_MASS = 0.160        # kg, CITE: retail cluster 152-169 g, midpoint
WHEEL_MASS = 0.100        # kg, GUESS: unweighed (wheel not selected); envelope 125.66 cm3 reference
_BRACKET_PART = load_bracket_visual()
_DISC_PART = build_disc()
_BRACKET_CENTER = tuple(_BRACKET_PART.center(CenterOf.MASS))
_DISC_CENTER = tuple(_DISC_PART.center(CenterOf.MASS))
BRACKET_MASS = _BRACKET_PART.volume * 7.85e-6 # CALC: STEP volume, steel assumed
DISC_MASS = _DISC_PART.volume * 1.18e-6      # CALC: cut CAD volume, PMMA assumed
STANDOFF_MASS = 0.0085 * layout.TIER_STANDOFF_L / 38.0 # CALC: length-scaled brass
LINE_POST_MASS = 0.010 * layout.LINE_POST_L / 45.0
LINE_BAR_MASS = 0.020     # kg, WEIGH pending: listing 15-25 g band midpoint
SONAR_MASS = 0.0095       # kg, CITE: HC-SR04 9-10 g
SONAR_BRACKET_MASS = build_sonar_bracket_envelope().volume * 7.85e-6 # CALC, steel assumed
BATTERY_MASS = 0.172      # kg, CITE: 2200 mAh 3S LiPo pack, 166-182 g band
DRIVER_MASS = 0.0035      # kg, CITE: TB6612 breakout 2-5 g
MCU_MASS = 0.010          # kg, CITE order-of-magnitude
IMU_MASS = 0.003          # kg, CITE: GY-521 ~3 g with headers
HARDWARE_PER_DISC = 0.010  # kg, est: screws/nuts/straps lump, half per tier


def _motor_mass_split() -> tuple[float, float]:
    """Gearbox / rear cylinder split, proportional to envelope volumes (CALC)."""
    v_gb = GEARBOX_L * math.pi * (FLANGE_D / 2) ** 2
    v_rear = REAR_L * math.pi * (REAR_D / 2) ** 2
    share = v_gb / (v_gb + v_rear)
    return MOTOR_MASS * share, MOTOR_MASS * (1 - share)


def chassis_lumps() -> list[dict]:
    """Chassis lumped parts: name / center (SI, world) / mass / primitive.

    Centers mirror the CAD assembly exactly (same constants, mm/1000).
    Boxes are full extents (m); the MJCF builder halves them.
    """
    m_gb, m_rear = _motor_mass_split()
    lower_top = layout.DISC_T / 2                       # above DISC_Z
    upper_top = layout.DISC2_Z + layout.DISC_T / 2
    standoff_mid = (layout.DISC_Z + layout.DISC2_Z) / 2

    def motor_geoms(side: int) -> list[dict]:
        fx = side * layout.FLANGE_X
        return [
            dict(name=f"motor_gb_{side}", kind="cyl_x",
                 pos=(fx - side * GEARBOX_L / 2, 0, layout.AXLE_Z - OUTPUT_SHAFT_OFFSET),
                 d=FLANGE_D, l=GEARBOX_L, mass=m_gb),
            dict(name=f"motor_rear_{side}", kind="cyl_x",
                 pos=(fx - side * (GEARBOX_L + REAR_L / 2), 0, layout.AXLE_Z - OUTPUT_SHAFT_OFFSET),
                 d=REAR_D, l=REAR_L, mass=m_rear),
            dict(name=f"bracket_{side}", kind="box",
                 pos=(fx + side * _BRACKET_CENTER[0], side * _BRACKET_CENTER[1],
                      layout.AXLE_Z + _BRACKET_CENTER[2]),
                 size=(BASE_L, PLATE_W, 48.0), mass=BRACKET_MASS),
        ]

    lumps = [
        dict(name="disc_lower", kind="cyl_z",
             pos=(_DISC_CENTER[0], _DISC_CENTER[1], layout.DISC_Z), d=2 * layout.DISC_R, l=layout.DISC_T,
             mass=DISC_MASS + HARDWARE_PER_DISC),
        dict(name="disc_upper", kind="cyl_z",
             pos=(_DISC_CENTER[0], _DISC_CENTER[1], layout.DISC2_Z), d=2 * layout.DISC_R, l=layout.DISC_T,
             mass=DISC_MASS + HARDWARE_PER_DISC),
    ]
    for sx in (+1, -1):
        for sy in (+1, -1):
            lumps.append(dict(
                name="standoff", kind="cyl_z",
                pos=(sx * layout.STANDOFF_HALF_X, sy * layout.STANDOFF_HALF_Y,
                     standoff_mid),
                d=layout.STANDOFF_D, l=layout.TIER_STANDOFF_L,
                mass=STANDOFF_MASS))
    lumps += [
        dict(name="battery", kind="box",
             pos=(BATTERY_XYZ[0], BATTERY_XYZ[1],
                  layout.DISC_Z + lower_top + BATTERY_XYZ[2]),
             size=BATTERY, mass=BATTERY_MASS),
        dict(name="driver", kind="box",
             pos=(DRIVER_XYZ[0], DRIVER_XYZ[1],
                  layout.DISC_Z + lower_top + DRIVER_XYZ[2]),
             size=(21, 16, 3), mass=DRIVER_MASS),
        dict(name="mcu", kind="box",
             pos=(MCU_XYZ[0], MCU_XYZ[1], upper_top + MCU_XYZ[2]),
             size=(36, 27, 3), mass=MCU_MASS),
        dict(name="imu", kind="box",
             pos=(IMU_XYZ[0], IMU_XYZ[1],
                  layout.DISC_Z + lower_top + IMU_XYZ[2]),
             size=GY521_SIZE, mass=IMU_MASS),
        # sonar + its bent bracket, one lump at the bracket face
        dict(name="sonar_lump", kind="box",
             pos=(0, layout.SONAR_FACE_Y, layout.DISC_Z + lower_top + SONAR_CAN_AXIS_Z),
             size=(46, 8, SONAR_FACE[2]), mass=SONAR_MASS + SONAR_BRACKET_MASS),
        dict(name="line_bar", kind="box",
             pos=(0, layout.LINE_BAR_Y,
                  layout.DISC_Z - lower_top - layout.LINE_POST_L - 13.5 / 2),
             size=(91.11, 36.5, 13.5), mass=LINE_BAR_MASS),
    ]
    for sx in (+1, -1):
        lumps.append(dict(
            name="line_post", kind="cyl_z",
            pos=(sx * layout.LINE_POST_XY[0], -layout.LINE_POST_XY[1],
                 layout.DISC_Z - lower_top - layout.LINE_POST_L / 2),
            d=layout.STANDOFF_D, l=layout.LINE_POST_L, mass=LINE_POST_MASS))
    lumps += motor_geoms(+1) + motor_geoms(-1)
    for lump in lumps:
        lump["pos"] = tuple(v * MM for v in lump["pos"])
        if lump["kind"] == "box":
            lump["size"] = tuple(v * MM for v in lump["size"])
        else:
            lump["d"], lump["l"] = lump["d"] * MM, lump["l"] * MM
    return lumps


def imu_site_pos() -> tuple[float, float, float]:
    """GY-521 center on its dedicated underside mounting pair, SI."""
    return (IMU_XYZ[0] * MM, IMU_XYZ[1] * MM,
            (layout.IMU_BOTTOM_Z + GY521_SIZE[2] / 2) * MM)


def wheel_pos(side: int) -> tuple[float, float, float]:
    """Wheel body center, with hub seated on the output-shaft shoulder."""
    return (side * layout.TRACK_HALF * MM, 0.0, layout.AXLE_Z * MM)


def total_mass() -> float:
    return sum(l["mass"] for l in chassis_lumps()) + 2 * WHEEL_MASS


def center_of_mass() -> tuple[float, float, float]:
    """Whole vehicle CoM in upright CAD coordinates (meters, estimated masses)."""
    lumps = chassis_lumps()
    weights = [(p["mass"], p["pos"]) for p in lumps]
    weights += [(WHEEL_MASS, wheel_pos(side)) for side in (-1, 1)]
    mass = sum(m for m, _ in weights)
    return tuple(sum(m * p[i] for m, p in weights) / mass for i in range(3))


if __name__ == "__main__":
    for lump in chassis_lumps():
        print(f"{lump['name']:14s} {lump['mass'] * 1e3:7.1f} g  "
              f"at ({lump['pos'][0]:+.3f}, {lump['pos'][1]:+.3f}, "
              f"{lump['pos'][2]:+.3f}) m")
    print(f"total {total_mass():.3f} kg (expected: 1.0-1.15 kg)")
