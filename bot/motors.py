"""PWM duty -> wheel torque: the twin's motor peripheral.

Model (JGB37-520, Hiwonder 1:30 tier, dual-source spec):

    tau(omega) = (STALL / V_NOM) * (V_batt * duty - (V_NOM / OMEGA_FREE) * omega)

a straight line pinned by the two most reliable sheet points -- stall
torque 0.57 N*m and no-load speed 320 rpm at 12 V. The current points
(3.2 A stall / 0.36 A rated) are deliberately NOT used: Kt from stall
current and Ke from no-load speed disagree by ~2x, an internal sheet
inconsistency; the two-point line is the standard DC-motor fit and
sidesteps it. Voltage derating falls out of the same line (7.4 V ->
~0.35 N*m stall, ~197 rpm), matching the sheet's derating table.

The line is not clamped at zero: when the wheel spins against the
command (plug braking / back-driving) torque legitimately exceeds the
stall point. Battery sag and driver current limits are future work.
"""
import math

from cad_modeling.jgb37_520 import STALL_TORQUE

STALL_NM = STALL_TORQUE          # 0.57 N*m at the shaft, SHEET
V_NOM = 12.0                     # V, sheet rating
NO_LOAD_RPM = 320.0              # rpm at 12 V, sheet
OMEGA_FREE = NO_LOAD_RPM * 2.0 * math.pi / 60.0   # 33.51 rad/s

# Nominal pack voltages (3S LiPo settled; full-charge values in comments)
BATTERY_NOMINAL = {"2s": 7.4, "3s": 11.1}   # full: 8.4 / 12.6

DUTY_MAX = 1000                  # duty unit is permille


def torque_nm(duty_permille: int, wheel_omega: float, v_batt: float) -> float:
    """Torque at the wheel for a duty command [-1000, 1000] (+ = forward).

    wheel_omega is the hinge rate in rad/s; positive hinge spin drives the
    bot toward +Y (forward), same sign convention for both wheels.
    """
    duty = max(-DUTY_MAX, min(DUTY_MAX, duty_permille)) / DUTY_MAX
    return (STALL_NM / V_NOM) * (v_batt * duty - (V_NOM / OMEGA_FREE) * wheel_omega)


def max_torque_nm(v_batt: float) -> float:
    """Stall torque available at this pack voltage (duty = +-100%)."""
    return STALL_NM * v_batt / V_NOM


def torque_to_duty(tau: float, v_batt: float) -> int:
    """Inverse map at zero speed -- what the stub controller uses to turn a
    desired torque into the permille command the firmware will emit."""
    return int(round(DUTY_MAX * tau / max_torque_nm(v_batt)))
