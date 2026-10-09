"""The backend probe must count real control cycles and retain a usable profile."""
from pathlib import Path
import pstats
import tempfile
import unittest

from bot.hostc import find_host_gcc
from race.perf_probe import probe


@unittest.skipIf(find_host_gcc() is None, "host gcc required")
class PerformanceProbe(unittest.TestCase):
    def test_native_probe_retains_real_cycles_and_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "controller.prof"
            result = probe("hostc", task=2, seconds=.1, blocks=2,
                           warmup_s=.01, profile_path=profile)
            self.assertEqual(result["heartbeat"], 62)
            self.assertEqual(result["couplings"], 62)
            self.assertEqual(result["heartbeat_gaps"], 0)
            self.assertEqual([row["heartbeat_delta"] for row in result["blocks"]], [20, 20])
            for row in result["blocks"]:
                self.assertAlmostEqual(row["world_delta_s"], .1)
                self.assertGreater(row["wall_s"], 0)
                self.assertGreaterEqual(row["host_cpu_s"], 0)
            self.assertEqual(len(result["artifact"]["sha256"]), 64)
            self.assertGreater(pstats.Stats(str(profile)).total_calls, 0)
