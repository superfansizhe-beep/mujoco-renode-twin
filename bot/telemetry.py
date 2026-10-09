"""State-frame schema -- the single constructor both backends emit from.

Layers (a backend's state() = pose_fields(...) + its identity field):
  base (BASE_FIELDS)  pose + telemetry every backend must carry; the
      names, frames, rounding and sign conventions live HERE and
      nowhere else (the loops used to hand-write twin dicts and drift)
  backend identity    twin adds "mode"; race adds "mission"

Conventions pinned here:
  - pos = qpos[0:3] in the CAD frame (X width, Y forward, Z up);
    quat_xyzw reorders MuJoCo's wxyz because the viewer takes xyzw
  - speed_mps = signed speed along the bot's TRAVEL axis, positive
    when advancing nose-first. The same chassis leads OPPOSITE ends
    in the two apps: the twin drives CAD-forward (chassis +Y, mjcf
    "Y forward"), the race car runs bar-first (chassis -Y, see
    race/spawn.py) -- so the caller passes travel_y (+1 twin, -1
    race) and the projection qvel[0:2] . chassis_+Y_axis carries it.
    At yaw 0 this equals the old world-Y sensor readout bit for bit.
  - tilt_deg = pitch about +X from the quaternion; fallen: |tilt| > 45
  - fw_seq is base, not identity: any backend with a firmware/
    heartbeat slot reports it (null on stubs) -- it says what DRIVES
    the bot, not which app this is
"""
import math

BASE_FIELDS = ("type", "t", "pos", "quat_xyzw", "wheel_deg", "tilt_deg",
               "speed_mps", "duty", "enc", "batt_v", "fw_seq",
               "paused", "fallen")


def tilt_deg(d) -> float:
    w, x, y, z = d.qpos[3:7]
    return math.degrees(math.atan2(2.0 * (w * x + y * z),
                                   1.0 - 2.0 * (x * x + y * y)))


def pose_fields(d, *, duty, enc, batt_v, paused,
                travel_y: float = 1.0, fw_seq=None) -> dict:
    """Base-layer state fields from an MjData plus the loop-owned bits."""
    quat = d.qpos[3:7]     # MuJoCo w x y z
    w, x, y, z = quat
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    yb = (-math.sin(yaw), math.cos(yaw))          # chassis +Y axis, world
    speed = travel_y * (d.qvel[0] * yb[0] + d.qvel[1] * yb[1])
    tilt = tilt_deg(d)
    return {
        "type": "state",
        "t": round(d.time, 4),
        "pos": [round(v, 5) for v in d.qpos[0:3]],
        "quat_xyzw": [round(quat[1], 6), round(quat[2], 6),
                      round(quat[3], 6), round(quat[0], 6)],
        "wheel_deg": [round(math.degrees(d.qpos[7]), 2),
                      round(math.degrees(d.qpos[8]), 2)],
        "tilt_deg": round(tilt, 2),
        "speed_mps": round(float(speed), 4),
        "duty": duty,
        "enc": enc,
        "batt_v": batt_v,
        "fw_seq": fw_seq,
        "paused": paused,
        # the chassis body frame rides the axle line by construction,
        # so "fallen" is an IMU-observable call, not a height call
        "fallen": bool(abs(tilt) > 45.0),
    }
