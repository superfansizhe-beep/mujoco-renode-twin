"""LQR gains for the balance stub, derived from the twin itself.

Numerically linearizes ONE coupling period (5 x 1 ms steps, symmetric
torque) around the hover-trim keyframe, on the planar WIP state

    z = [y, ydot, theta - theta_trim, thetadot]

(5th candidate phi_wheel was dropped: with the no-slip contact y and
phi are kinematically locked, an uncontrollable mode that made the
DARE fail) and solves a discrete LQR. The gains live in
BalanceController.K_LQR; recompute with ``python -m bot.lqr`` after
any mass-table edit.

The point is not elegance -- it is that a hand-tuned PD on a wheeled
inverted pendulum has no stationary equilibrium (constant lean ->
constant torque -> constant acceleration; the bot drifts forever),
and every empirical drift we chased traced back to exactly that.
"""
import numpy as np

import mujoco
from scipy.linalg import solve_discrete_are

from . import mjcf
from .loop import COUPLING_S, SUBSTEPS

DT = COUPLING_S
N = 4


def _trim_state(model, data):
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)


def _z(model, data, base_y):
    q = data.qpos
    pitch = 2.0 * np.arctan2(q[4], q[3])
    return np.array([q[1] - base_y, data.qvel[1],
                     pitch - mjcf.hover_trim_rad(), data.qvel[3]])


def _roll(model, data, tau):
    data.ctrl[0] = data.ctrl[1] = tau
    for _ in range(SUBSTEPS):
        mujoco.mj_step(model, data)


def linearize():
    model = mjcf.load_model()
    data = mujoco.MjData(model)
    _trim_state(model, data)
    base_y = data.qpos[1]

    def step(z0, tau):
        _trim_state(model, data)
        q = data.qpos
        pitch0 = 2.0 * np.arctan2(q[4], q[3])
        p = pitch0 + z0[2]
        q[1] = base_y + z0[0]
        q[3], q[4] = np.cos(p / 2), np.sin(p / 2)
        data.qvel[1] = z0[1]
        data.qvel[3] = z0[3]
        mujoco.mj_forward(model, data)
        _roll(model, data, tau)
        return _z(model, data, base_y)

    z_eq = step(np.zeros(N), 0.0)
    A = np.zeros((N, N))
    for j in range(N):
        e = np.zeros(N)
        e[j] = 1e-4
        A[:, j] = (step(e, 0.0) - step(-e, 0.0)) / 2e-4
    B = (step(np.zeros(N), 0.05) - step(np.zeros(N), -0.05)) / 0.1
    return A, B, z_eq


def lqr_gains(q_diag=(40.0, 1.0, 200.0, 2.0), r=8.0):
    A, B, z_eq = linearize()
    Q = np.diag(q_diag)
    R = np.array([[r]])
    P = solve_discrete_are(A, B[:, None], Q, R)
    K = np.linalg.solve(R + B[:, None].T @ P @ B[:, None],
                        B[:, None].T @ P @ A)
    return K.flatten(), A, B, z_eq


if __name__ == "__main__":
    K, A, B, z_eq = lqr_gains()
    print("residual |z_eq| =", np.abs(z_eq).max())
    print("A =\n", np.round(A, 4))
    print("B =", np.round(B, 4))
    print("K =", np.round(K, 3))
    eig = np.linalg.eigvals(A - B[:, None] @ K[None, :])
    print("closed-loop |eig| =", np.round(np.abs(eig), 4))

