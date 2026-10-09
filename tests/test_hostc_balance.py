"""Host-C balance core gates: build, mailbox-domain duty parity vs the
Python stub on identical frames, and closed-loop trajectory parity on
the same kick scenario that pins stub vs ELF (tests/test_twin.py,
<1.0 deg / 3 cm). The ELF itself stays gated on the Renode path --
these gates pin the ALGORITHM port, not the driver layer.

Renode is not needed: the host DLL is the only external dependency
(skipped with a reason when no host gcc exists).
"""
import math
import os
import unittest

import numpy as np

from bot.hostc import DLL, HostBalanceController, find_host_gcc
from bot.loop import COUPLING_S
from bot.mailbox import SensorFrame
from bot.mjcf import hover_trim_rad
from bot.backend import BalanceController
from twin.loop import TwinLoop

TRIM = hover_trim_rad()


def _hostc_ready():
    gcc = find_host_gcc()
    if gcc is None:
        return False, ("no host gcc (HOSTCC env, PATH gcc, or MSYS2 "
                       "mingw64 default)")
    return True, gcc


def _kick_scenario(loop):
    """Settle 1 s, kick, ride it out 3 s; return (peak, 0.5 s samples).
    Same shape as tests.test_twin._kick_scenario -- the scenario the
    stub-vs-ELF gate runs, so all three controllers compare like for
    like."""
    samples = []

    def snap():
        samples.append((loop.data.time, loop.tilt_deg(),
                        float(loop.data.qpos[1])))

    snap()
    loop.run(1.0)
    snap()
    loop.nudge(tx=3.5)
    peak = 0.0
    for i in range(600):
        loop.step_coupling()
        peak = max(peak, abs(loop.tilt_deg() - np.degrees(TRIM)))
        if (i + 1) % 100 == 0:
            snap()
    loop.run(2.0)
    snap()
    return peak, samples


class HostCBalance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _hostc_ready()
        if not ready:
            raise unittest.SkipTest(why)
        cls.hostc = HostBalanceController()

    def test_core_builds_and_steps(self):
        self.assertTrue(os.path.isfile(DLL))
        m = self.hostc.step(SensorFrame(
            seq=1, accel=(0, int(math.sin(TRIM) * 16384),
                          int(math.cos(TRIM) * 16384)),
            gyro=(0, 0, 0), battery_mv=11100, enc_l=0, enc_r=0))
        self.assertEqual(m.duty_l, m.duty_r)
        self.assertTrue(-450 <= m.duty_l <= 450)
        self.assertEqual(self.hostc.fw_seq, 1)

    def test_duty_series_matches_stub_on_identical_frames(self):
        """Replay one recorded sensor trajectory through both
        controllers: same frames in, duty series out. The stub computes
        float64, the core float32 -- the bound covers filter drift and
        libm ulps, not structure."""
        record = []

        class _Tap:
            name = "balance"

            def __init__(self, inner):
                self.inner = inner

            def reset(self):
                self.inner.reset()

            def step(self, s):
                record.append(s)
                return self.inner.step(s)

        host = TwinLoop(controller=_Tap(BalanceController(
            dt=COUPLING_S, v_batt=11.1)))
        host.run(2.0)
        host.nudge(tx=3.5)
        for _ in range(400):
            host.step_coupling()

        stub = BalanceController(dt=COUPLING_S, v_batt=11.1)
        core = HostBalanceController()
        worst = 0.0
        for s in record:
            a = stub.step(s).duty_l
            b = core.step(s).duty_l
            worst = max(worst, abs(a - b))
        self.assertLessEqual(worst, 3,
                             f"stub vs host-C duty divergence {worst} permille")

    def test_closed_loop_matches_stub_on_kick_scenario(self):
        host = TwinLoop(controller=HostBalanceController())
        peak_h, samples_h = _kick_scenario(host)
        st = host.state()
        self.assertFalse(st["fallen"], f"kick peak {peak_h:.1f} deg -> fell")
        self.assertGreater(peak_h, 8.0)
        self.assertLess(abs(st["tilt_deg"] - math.degrees(TRIM)), 5.0)
        self.assertTrue(st["fw_seq"])          # heartbeat mirror live

        stub = TwinLoop(mode="balance")
        peak_s, samples_s = _kick_scenario(stub)
        max_dtilt = max(abs(a[1] - b[1])
                        for a, b in zip(samples_h, samples_s))
        max_dy = max(abs(a[2] - b[2])
                     for a, b in zip(samples_h, samples_s))
        self.assertLess(max_dtilt, 1.0,
                        f"stub vs host-C tilt divergence {max_dtilt:.2f} deg")
        self.assertLess(max_dy, 0.03,
                        f"stub vs host-C position divergence {max_dy*100:.1f} cm")


if __name__ == "__main__":
    unittest.main()
