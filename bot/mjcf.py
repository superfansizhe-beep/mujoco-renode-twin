"""MJCF generation -- the physics twin of the CAD assembly, same frame.

Model frame = CAD frame (X width, Y forward, Z up; MuJoCo's default
gravity is -Z, so the twin and the CAD agree without any rotation, and
the web frontend can consume poses verbatim). Chassis body frame sits
at (0, 0, DISC_Z); every lump from mass_properties.chassis_lumps() is
one primitive geom with an explicit mass; wheels hinge about +X at the
flange-derived track positions. The CAD's 8-way line bar rides as eight
numbered massless sample sites (line_0..line_7) under the chassis tail
-- sites carry no mass/contact, so the dynamics are untouched.

Approximations, deliberate and documented (see README twin section):
- inertia = primitive-lumped (MuJoCo sums geom inertias); a CAD-exact
  inertia export is a later upgrade, not a secret;
- wheel CONTACT geom = sphere of tire radius (the standard sim-balancer
  practice): the contact point stays directly under the wheel center
  for every lean. A rigid cylinder/ellipsoid contacts at its rim as
  soon as the body leans, jumping the support line sideways by
  curvature-radius * lean (128 mm * 1 deg here vs ~3 mm for real
  rounded tires) and faking a wide support base -- that artifact is
  what parked the drive demo on a wheel-pole + tail-skid tripod;
- motor torque enters as a dumb torque actuator -- the torque-speed
  line lives in bot.motors (tested Python), not in the XML.
"""
import math

import mujoco

from cad_modeling import layout
from cad_modeling.wheel import WHEEL_D, WHEEL_W

from . import mass_properties as mp
from . import motors
from .sensors import LINE_PITCH, N_LINE_SENSORS

TIMESTEP = 0.001               # physics substep; 5 per coupling period
CTRL_LIMIT = motors.STALL_NM   # derating happens in the motor model

# Reflected rotor inertia of the 1:30 gearmotor: rotor ~3 g*cm^2 x 30^2
# = 2.7e-4 kg*m^2, ~3x the bare 100 g wheel. Without it the dumb torque
# actuator spins the wheel up at >4000 rad/s^2 and breaks traction --
# the classic missing half of a geared-drive twin.
WHEEL_ARMATURE = 2.7e-4

# 8-way line-bar sample sites (vehicle hardware, the CAD's LINE_BAR_*):
# pitch/count from bot.sensors, hang geometry derived from the layout.
BAR_Y = layout.LINE_BAR_Y * mp.MM     # bar centerline, chassis frame
BAR_Z = layout.LINE_FACE_Z * mp.MM    # bar face height above the floor
SENSOR_XS = tuple((i - (N_LINE_SENSORS - 1) / 2.0) * LINE_PITCH
                  for i in range(N_LINE_SENSORS))

# Contact/solver tuning -- the model's only free physics knobs (the
# sphere-wheel contact rationale is in the module docstring):
CONTACT_FRICTION = "1.0 0.005 0.0001"   # default for every chassis geom
FLOOR_FRICTION = "1.2 0.005 0.0001"     # the floor runs grippier than geoms
SOLREF = "0.005 1"                      # 5 ms contact time constant
SOLIMP = "0.9 0.95 0.001"               # impedance / width / margin
JOINT_DAMPING = 0.001                   # wheel hinge viscous damping


def line_site_ids(model: mujoco.MjModel) -> list[int]:
    """The 8 line-bar sampler site ids, bar order (line_0..line_7)."""
    return [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, f"line_{i}")
            for i in range(N_LINE_SENSORS)]


def _fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _geom_xml(idx: int, lump: dict) -> str:
    name, pos = f"{lump['name']}_{idx}", lump["pos"]
    p = " ".join(_fmt(v) for v in pos)
    m = _fmt(lump["mass"])
    if lump["kind"] == "box":
        size = " ".join(_fmt(v / 2) for v in lump["size"])
        return (f'        <geom name="{name}" type="box" pos="{p}" '
                f'size="{size}" mass="{m}" rgba="0.8 0.85 0.9 0.4"/>')
    d, l = lump["d"], lump["l"]
    if lump["kind"] == "cyl_z":
        return (f'        <geom name="{name}" type="cylinder" pos="{p}" '
                f'size="{_fmt(d / 2)} {_fmt(l / 2)}" mass="{m}" '
                f'rgba="0.8 0.85 0.9 0.4"/>')
    return (f'        <geom name="{name}" type="cylinder" pos="{p}" '
            f'size="{_fmt(d / 2)} {_fmt(l / 2)}" mass="{m}" '
            f'euler="0 {_fmt(math.pi / 2)} 0" rgba="0.55 0.55 0.58 0.4"/>')


def hover_trim_rad() -> float:
    """The lean that parks the CoM over the WHEEL CONTACT line, from the
    twin's own mass table. The pivot of a rolling WIP is the AXLE, not
    the ground point: the contact follows the axle, so the lever is
    com_z - AXLE_Z (~17 mm), not com_z (~57 mm) -- using the ground
    point underestimates the trim 3x (-3.7 deg vs the true -12.3 deg)
    and every closed loop quietly settled at the wrong lean.

    The keyframe starts here (like a hand holding the bot near balance
    before let-go); BalanceController targets the same angle."""
    import math as _math
    axle_z = WHEEL_D / 2 / 1000.0      # AXLE_Z = WHEEL_R, mm -> m
    lumps = mp.chassis_lumps()
    m_tot = sum(l["mass"] for l in lumps) + 2 * mp.WHEEL_MASS
    com_y = sum(l["mass"] * l["pos"][1] for l in lumps) / m_tot
    com_z = (sum(l["mass"] * l["pos"][2] for l in lumps)
             + 2 * mp.WHEEL_MASS * axle_z) / m_tot
    return _math.atan2(com_y, com_z - axle_z)


def build_mjcf() -> str:
    wheel_r = WHEEL_D / 2 * mp.MM
    half_w = WHEEL_W / 2 * mp.MM
    lumps = mp.chassis_lumps()
    geoms = "\n".join(_geom_xml(i, l) for i, l in enumerate(lumps))
    # chassis body frame at the WORLD origin: lump/wheel/site coordinates
    # from mass_properties are world-frame SI already, so they double as
    # body coordinates verbatim (the first draft hung the body at DISC_Z
    # and double-offset every lump -- caught by the CoM probe in tests).
    imu_p = " ".join(_fmt(v) for v in mp.imu_site_pos())
    wl_p = " ".join(_fmt(v) for v in mp.wheel_pos(-1))
    wr_p = " ".join(_fmt(v) for v in mp.wheel_pos(+1))
    line_sites = "\n".join(
        f'      <site name="line_{i}" pos="{x:.6f} {BAR_Y:.6f} {BAR_Z:.6f}"'
        f' size="0.003" rgba="0.95 0.6 0.1 1"/>'
        for i, x in enumerate(SENSOR_XS))
    # keyframe = trim lean with wheels placed EXACTLY on the floor: the
    # body-frame pitch rotates the wheel centers down by R*(1-cos), and
    # even 0.1 mm of penetration resolves as a contact impulse offset
    # forward of the axle -- a systematic nose-up kick that made every
    # run start by toppling onto the tail skid.
    trim = hover_trim_rad()
    z_lift = wheel_r * (1.0 - math.cos(trim))
    ctrl = _fmt(CTRL_LIMIT)
    return f"""<mujoco model="balance_bot_twin">
  <compiler angle="radian"/>
  <option timestep="{TIMESTEP}" gravity="0 0 -9.81" integrator="implicitfast"/>
  <default>
    <geom friction="{CONTACT_FRICTION}" solref="{SOLREF}" solimp="{SOLIMP}"/>
    <joint damping="{JOINT_DAMPING}"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="3 3 0.1"
          friction="{FLOOR_FRICTION}" rgba="0.25 0.27 0.3 1"/>
    <body name="chassis" pos="0 0 0">
      <freejoint name="root"/>
{geoms}
{line_sites}
      <site name="imu_site" pos="{imu_p}" size="0.004" rgba="0.95 0.2 0.2 1"/>
      <body name="wheel_l" pos="{wl_p}">
        <joint name="wheel_l" type="hinge" axis="-1 0 0" armature="{_fmt(WHEEL_ARMATURE)}"/>
        <geom name="wheel_l" type="sphere" size="{_fmt(wheel_r)}"
              mass="{_fmt(mp.WHEEL_MASS)}" rgba="0.15 0.15 0.15 1"/>
      </body>
      <body name="wheel_r" pos="{wr_p}">
        <joint name="wheel_r" type="hinge" axis="-1 0 0" armature="{_fmt(WHEEL_ARMATURE)}"/>
        <geom name="wheel_r" type="sphere" size="{_fmt(wheel_r)}"
              mass="{_fmt(mp.WHEEL_MASS)}" rgba="0.15 0.15 0.15 1"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="torque_l" joint="wheel_l" gear="1"
           ctrlrange="-{ctrl} {ctrl}" ctrllimited="true"/>
    <motor name="torque_r" joint="wheel_r" gear="1"
           ctrlrange="-{ctrl} {ctrl}" ctrllimited="true"/>
  </actuator>
  <sensor>
    <accelerometer name="imu_accel" site="imu_site"/>
    <gyro name="imu_gyro" site="imu_site"/>
    <framequat name="chassis_quat" objtype="body" objname="chassis"/>
    <framelinvel name="chassis_vel" objtype="body" objname="chassis"/>
    <jointvel name="wheel_l_vel" joint="wheel_l"/>
    <jointvel name="wheel_r_vel" joint="wheel_r"/>
  </sensor>
  <keyframe>
    <key name="upright" qpos="0 0 {_fmt(z_lift)} {_fmt(math.cos(trim / 2))} {_fmt(math.sin(trim / 2))} 0 0 0 0"/>
  </keyframe>
</mujoco>
"""


def load_model() -> mujoco.MjModel:
    """Compile the generated XML (raises with MuJoCo's own diagnostics)."""
    return mujoco.MjModel.from_xml_string(build_mjcf())


def write_xml(path: str) -> None:
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_mjcf())


if __name__ == "__main__":
    import sys
    model = load_model()
    print(f"compiled: nq={model.nq} nu={model.nu} nsensor={model.nsensor} "
          f"nbody={model.nbody} total_mass={model.body_mass.sum():.3f} kg")
    out = sys.argv[1] if len(sys.argv) > 1 else "output/twin/balance_bot.xml"
    write_xml(out)
    print(f"wrote {out}")
