"""Ground-truth acceptance of the faster C profile with actuator delay.

The controller sees raw sensor frames only. The grader checks completion,
real body motion during the stopped hold, and exactly one C cycle per sample.
"""
import unittest

from bot.hostc import find_host_gcc
from race.controller import STOP_V
from race.speed_probe import probe


class _DelayedMission:
    def check_delayed_mission(self, backend):
        self.performance_evidence = probe(
            task=4, backend=backend, battery_v=10.5, friction=1.0,
            actuator_delay=True, nudge_at=10.0, cap_s=115.0,
            progress=lambda row: print(f"{backend} delayed mission: {row}", flush=True))
        result = self.performance_evidence
        verdict = result["verdict"]
        self.assertTrue(verdict["pass"], verdict)
        self.assertEqual(verdict["nodes"], ["C", "B", "D", "A"] * 4)
        self.assertEqual(result["heartbeat"], result["couplings"])
        self.assertEqual(result["heartbeat_gaps"], 0)
        self.assertLess(result["max_tilt_deg"], 45.0)
        # This is simulated world time: machine/host CPU speed cannot pass it.
        self.assertLess(result["world_total_s"], 110.0)
        # Filtering encoder bins must not label continuing body travel stopped.
        self.assertLessEqual(result["stop_hold_body_speed_peak_mps"], STOP_V + 0.001)
        self.assertTrue(all(span < 0.005 for span in result["stop_hold_xy_span_m"]))


@unittest.skipIf(find_host_gcc() is None, "host gcc required for C acceptance")
class RaceTuning(_DelayedMission, unittest.TestCase):
    def test_fast_c_profile_tracks_and_stops_with_full_period_delay(self):
        self.check_delayed_mission("hostc")


class RenodeRaceTuning(_DelayedMission, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_race_firmware import _renode_ready
        ready, reason = _renode_ready()
        if not ready:
            raise unittest.SkipTest(reason)

    def test_fast_profile_survives_delay_through_real_peripherals(self):
        self.check_delayed_mission("renode")


if __name__ == "__main__":
    unittest.main(verbosity=2)
