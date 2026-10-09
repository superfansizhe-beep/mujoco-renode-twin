"""Race spawn poses -- where the car enters the field, per task.

The physics model is bot.mjcf's output UNTOUCHED (same masses, same
sphere-contact wheels, same trim keyframe): the exam car IS the balance
bot, which natively carries the CAD's 8-way IR bar as massless sample
sites (bot/mjcf line_0..line_7 -- the harness evaluates the tape mask
under each). What is left here is only the START POSE composition.

Driving orientation: the bar hangs at chassis y = LINE_BAR_Y = -66 mm,
i.e. BEHIND the axle -- the bot runs the course BAR-FIRST, travel
direction = chassis -Y (the sonar face trails). spawn_qpos() composes
the keyframe trim quaternion with the world yaw for a given travel
heading, so the lean physics of the keyframe carries over unchanged.
"""
import math

import mujoco
import numpy as np

from . import tasks


def spawn_qpos(model: mujoco.MjModel, x: float, y: float,
               yaw_travel: float) -> np.ndarray:
    """Keyframe pose re-rooted so the AXLE sits at (x, y) with the bar on
    the tape ahead: travel heading = yaw_travel, chassis yaw = that + pi.
    Trim lean, z compensation and zero wheel angles all carry over from
    the twin keyframe."""
    qpos = model.key_qpos[0].copy()
    qpos[0], qpos[1] = x, y
    # chassis -Y points along travel: body yaw = travel + 90 deg (with
    # x_b = R(yaw) x_hat, y_b = R(yaw) y_hat this makes -y_b = travel
    # and +x_b = travel-LEFT -- the derivation the controller signs use)
    yaw = yaw_travel + math.pi / 2.0
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    qw = (cy, 0.0, 0.0, sy)             # world yaw, w-first
    qt = tuple(qpos[3:7])               # keyframe trim (pitch about +X)
    # Hamilton product q_yaw * q_trim (yaw applied in the world frame)
    qpos[3] = qw[0] * qt[0] - qw[1] * qt[1] - qw[2] * qt[2] - qw[3] * qt[3]
    qpos[4] = qw[0] * qt[1] + qw[1] * qt[0] + qw[2] * qt[3] - qw[3] * qt[2]
    qpos[5] = qw[0] * qt[2] - qw[1] * qt[3] + qw[2] * qt[0] + qw[3] * qt[1]
    qpos[6] = qw[0] * qt[3] + qw[1] * qt[2] - qw[2] * qt[1] + qw[3] * qt[0]
    return qpos


def spawn_for_task(model: mujoco.MjModel, task: int):
    """(qpos, travel pose) for a task's start: the AXLE sits on node A
    (the car "is at" A in the exam's terms), travel = the first leg's
    tangent. Every task opens on an untaped straight, so the bar (one
    bar-lead ahead of A) starts over open white -- the run opens with
    dead reckoning, exactly as the sheet intends."""
    seg = tasks.task_route(task)[0]
    psi = seg.heading_at(0.0)                    # travel heading there
    axle = seg.point(0.0)
    # freejoint qpos[0:2] IS the world position of the body origin (the
    # axle line), so it takes the track coordinates verbatim
    qpos = spawn_qpos(model, axle[0], axle[1], psi)
    return qpos, dict(x=axle[0], y=axle[1], psi=psi, bar=axle)
