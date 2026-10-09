"""Line-array optical tests and real ARM GPIO / observation-law parity.
No physical-board correlation is implied by the assumed optical profile.
"""
import math
import os
from pathlib import Path
import struct
import unittest

from bot import line_sensor as line

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = (1, 0, 0, 0, 1, 0, 0, 0, 1)
RES, CMD = 0x2001ED00, 0x2001ED80


def flat_sample(model, black):
    return model.sample([(x, 0, 0.020) for x in line.SENSOR_XS],
                        [IDENTITY] * 8, black)


class TestLineOptics(unittest.TestCase):
    def test_white_leds_on_black_leds_off_with_continuous_illumination(self):
        model = line.LineArray()
        white = flat_sample(model, lambda x, y: False)
        self.assertEqual((white.black_bits, white.indicator_bits, white.gpio_bits), (0, 255, 255))
        center = flat_sample(model, lambda x, y: abs(x) <= 0.009)
        self.assertEqual((center.black_bits, center.indicator_bits, center.gpio_bits), (0x18, 0xE7, 0xE7))
        self.assertTrue(center.payload()["illumination_on"])
        white_again = flat_sample(model, lambda x, y: False)
        self.assertEqual(white_again.indicator_bits, 255)

    def test_optical_axis_hits_floor_instead_of_using_body_xy(self):
        angle = math.radians(25)
        rotation = (math.cos(angle), 0, -math.sin(angle), 0, 1, 0,
                    math.sin(angle), 0, math.cos(angle))
        projected = 0.020 * math.tan(angle)
        model = line.LineArray()
        sample = model.sample([(0, 0, 0.020)] * 8, [rotation] * 8,
                              lambda x, y: abs(x - projected) < 0.002)
        self.assertEqual(sample.black_bits, 255)
        self.assertAlmostEqual(sample.spots[0][0], projected)
        self.assertFalse(abs(projected) < 0.002, "old body-XY sampler would miss this line")

    def test_hysteresis_preserves_both_previous_states_near_threshold(self):
        model = line.LineArray()
        positions = [(0, 0, 0.020)] * 8
        jitter = lambda x, y: x + 0.41 * y < 0
        model.sample(positions, [IDENTITY] * 8, lambda x, y: True)
        middle = model.sample(positions, [IDENTITY] * 8, jitter)
        self.assertGreater(middle.coverage[0], line.BLACK_OFF)
        self.assertLess(middle.coverage[0], line.BLACK_ON)
        self.assertEqual(middle.black_bits, 255)
        model.sample(positions, [IDENTITY] * 8, lambda x, y: False)
        self.assertEqual(model.sample(positions, [IDENTITY] * 8, jitter).black_bits, 0)

    def test_out_of_range_is_visible_and_never_claims_centering(self):
        model = line.LineArray()
        sample = model.sample([(x, 0, 0.100) for x in line.SENSOR_XS],
                              [IDENTITY] * 8, lambda x, y: True)
        self.assertEqual(sample.valid_bits, 0)
        self.assertEqual(sample.black_bits, 0)
        self.assertTrue(all(p is None for p in sample.spots))
        self.assertFalse(line.observe(sample.black_bits).bar_centered)


class TestLineObservation(unittest.TestCase):
    def test_opposite_edge_detections_are_not_a_centered_line(self):
        for bits in (0x81, 0x42, 0x24, 0x99):
            obs = line.observe(bits)
            self.assertEqual(obs.status, "split")
            self.assertIsNone(obs.error_m)
            self.assertFalse(obs.bar_centered)

    def test_no_line_and_full_black_never_report_a_centered_vehicle(self):
        for bits, status in ((0, "lost"), (255, "wide")):
            obs = line.observe(bits)
            self.assertEqual(obs.status, status)
            self.assertFalse(obs.valid)
            self.assertFalse(obs.bar_centered)
        self.assertTrue(line.observe(0x18).bar_centered)
        self.assertEqual(line.observe(0x18).error_m, 0)

    def test_every_pattern_has_mirror_symmetry_and_only_one_cluster_is_valid(self):
        for bits in range(256):
            obs = line.observe(bits)
            mirror = line.observe(int(f"{bits:08b}"[::-1], 2))
            self.assertEqual((obs.status, obs.count, obs.groups, obs.bar_centered),
                             (mirror.status, mirror.count, mirror.groups, mirror.bar_centered))
            if obs.valid:
                self.assertEqual(obs.groups, 1)
                self.assertLessEqual(obs.count, 4)
                self.assertAlmostEqual(obs.error_m, -mirror.error_m)
            else:
                self.assertIsNone(obs.error_m)

    def test_recovery_handover_has_one_sign_convention_and_bounded_steps(self):
        tracker = line.LineTracker()
        sequence = [(0x80, -0.06, True)] * 40 + [(0, -0.06, True)] * 50 \
            + [(0x01, -0.06, True)] * 40 + [(0x81, 0.06, True)] * 50
        previous = 0
        sources = set()
        for bits, recovery, hold in sequence:
            value = tracker.update(bits, recovery, 0.005, hold)
            self.assertLessEqual(abs(value - previous), line.ERROR_SLEW_M_S * 0.005 + 1e-12)
            sources.add(tracker.source)
            previous = value
        self.assertEqual(sources, {"sensor", "hold", "odometry"})
        self.assertGreater(tracker.error_m, 0)

    def test_planned_white_leg_does_not_hold_an_old_arc_reading(self):
        tracker = line.LineTracker()
        for _ in range(40): tracker.update(0x80, 0, 0.005)
        tracker.update(0, -0.02, 0.005, allow_hold=False)
        self.assertEqual(tracker.source, "odometry")


class TestLineFirmware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from bot.renode import DEFAULT_PORTABLE
        if DEFAULT_PORTABLE:  # None until RENODE_PORTABLE/PYRENODE_PATH is set
            os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
        cls.elf = ROOT / "firmware" / "line_bringup.elf"
        if (not cls.elf.is_file() or not DEFAULT_PORTABLE
                or not Path(DEFAULT_PORTABLE).is_dir()):
            raise unittest.SkipTest("build firmware/build_line.sh and install portable Renode")

    def setUp(self):
        from bot.renode import RenodeChannel
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        self.ch = RenodeChannel(str(self.elf), 0.005)
        self.addCleanup(self.ch.emu.clear)
        self.ch.run(0.002)
        self.seq = 0
        self.assertEqual(self.ch.read_word(RES), 0x314E494C)

    def command(self, bits, recovery=0.0, reset=False, hold=True, taped=False, late=False):
        pin_bits = (~bits) & 255 if line.ACTIVE_LOW else bits & 255
        for i in range(8):
            self.ch.mon.execute(f"gpioPortF OnGPIO {i} {'true' if pin_bits >> i & 1 else 'false'}")
        self.seq += 1
        self.ch.write_word(CMD + 4, int(reset) | (int(hold) << 1)
                           | (int(taped) << 2) | (int(late) << 3))
        self.ch.write_word(CMD + 8, struct.unpack('<I', struct.pack('<f', recovery))[0])
        self.ch.write_word(CMD, self.seq)
        self.ch.run(0.0005)
        words = [self.ch.read_word(RES + 4 * i) for i in range(10)]
        self.assertEqual(words[1], self.seq)
        self.assertEqual(words[2], bits & 255)
        self.assertEqual(words[8], pin_bits)
        floats = [struct.unpack('<f', struct.pack('<I', words[i]))[0] for i in (5, 6, 9)]
        self.assertEqual(self.ch.read_word(0x2001FFB8), 0)
        return words, floats

    def test_all_256_gpio_patterns_match_the_python_observation(self):
        status = {"lost": 0, "track": 1, "wide": 2, "split": 3}
        for bits in range(256):
            obs = line.observe(bits)
            words, floats = self.command(bits, reset=True)
            self.assertEqual(words[3], status[obs.status], f"mask {bits:08b}")
            self.assertEqual(words[4] & 255, obs.count)
            self.assertEqual((words[4] >> 8) & 255, obs.groups)
            self.assertEqual(bool(words[4] >> 16), obs.bar_centered)
            if obs.valid: self.assertAlmostEqual(floats[0], obs.error_m, places=7)

    def test_loss_split_and_reacquisition_match_production_c_filter(self):
        tracker = line.LineTracker()
        sequence = [(0x80, -0.06, True)] * 30 + [(0, -0.06, True)] * 35 \
            + [(0x81, 0.06, True)] * 20 + [(0x18, 0.02, True)] * 30 \
            + [(0, -0.02, False)] * 20
        sources = {"odometry": 0, "sensor": 1, "hold": 2}
        for i, (bits, recovery, hold) in enumerate(sequence):
            value = tracker.update(bits, recovery, 0.005, allow_hold=hold)
            words, floats = self.command(bits, recovery, reset=i == 0, hold=hold)
            self.assertEqual(words[7], sources[tracker.source], f"cycle {i}")
            self.assertAlmostEqual(floats[1], value, places=6)

    def test_input_mode_pullups_and_gpio_clock_enable(self):
        self.assertEqual(self.ch.read_word(0x40021400) & 0xFFFF, 0)
        self.assertEqual(self.ch.read_word(0x4002140C) & 0xFFFF, 0x5555)
        self.assertTrue(self.ch.read_word(0x40023830) & (1 << 5))

    def test_endpoint_confirmation_matches_python_and_rejects_short_losses(self):
        endpoint = line.LineEndpoint()
        sequence = [(0x18, True, True)] + [(0, True, True)] * 50 \
            + [(0x18, True, True)] + [(0, True, True)] * 65 \
            + [(0x81, True, True)] + [(0, True, True)] * 65 \
            + [(0xFF, True, True)] + [(0, True, True)] * 65 \
            + [(0x18, True, True)] + [(0, True, False)] * 10 \
            + [(0, True, True)] * 65 + [(0x18, False, True)] \
            + [(0, False, True)] * 65
        detections = []
        for i, (bits, taped, late) in enumerate(sequence):
            detected = endpoint.update(line.observe(bits), taped, late, 0.005)
            self.command(bits, reset=i == 0, taped=taped, late=late)
            self.assertEqual(bool(self.ch.read_word(RES + 40)), detected, f'cycle {i}')
            self.assertEqual(self.ch.read_word(RES + 44), endpoint.white_cycles)
            detections.append(detected)
        self.assertFalse(any(detections[:111]), '250 ms loss must not advance a leg')
        self.assertTrue(detections[111], '300 ms confirmed endpoint must fire')
        self.assertFalse(any(detections[117:]), 'ambiguous and untaped inputs cannot seed an endpoint')


if __name__ == '__main__':
    unittest.main(verbosity=2)
