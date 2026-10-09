"""Closed-loop arc-entry and line-recovery disturbances.

Fixtures change forces or digital inputs, never feed ground truth into the
controller. Each case must finish and pass the same mission grader.
"""
from dataclasses import replace
import os
import unittest

from bot.line_sensor import observe
from race.loop import RaceLoop
from race import tasks


class DisturbedRaceLoop(RaceLoop):
    def __init__(self, case, controller=None):
        self.case = case
        super().__init__(task=2, controller=controller)

    def reset(self, task=None):
        super().reset(task)
        self.injection_started = False
        self.injected_cycles = 0
        self._clean = 0
        self._arc_since = None
        self.max_error_step_mm = 0.0
        self._previous_error = 0.0
        self.invalid_fresh_measurements = 0
        self.consumed_mismatches = 0
        self.fresh_sensor_cycles = 0
        self._last_injected_time = None
        self.reacquire_delay_s = None

    def read_sensors(self):
        frame = super().read_sensors()
        info = self.controller.info()
        if info['seg_i'] == 1 and info['phase'] == 'run':
            if self._arc_since is None: self._arc_since = self.data.time
            self._clean = self._clean + 1 if observe(frame.line_bits).valid else 0
            if self.case == 'late_dropout' and not self.injection_started:
                seg = tasks.task_route(2)[1]
                progress, _, _ = seg.project(*info['odo'])
                if progress >= 0.82 * seg.length:
                    self.injection_started = True
            if (self.case in ('dropout', 'long_dropout', 'split', 'wide') and not self.injection_started
                    and self._clean >= 50 and self.data.time - self._arc_since > 3):
                self.injection_started = True
            duration = {'dropout': 50, 'long_dropout': 360, 'split': 30,
                        'wide': 30, 'late_dropout': 50}.get(self.case, 0)
            if self.injection_started and self.injected_cycles < duration:
                self.injected_cycles += 1
                self._last_injected_time = self.data.time
                mask = {'split': 0x81, 'wide': 0xFF}.get(self.case, 0)
                return replace(frame, line_bits=mask)
        return frame

    def step_coupling(self):
        info = self.controller.info()
        if self.case.startswith('entry') and info['seg_i'] == 1 and info['phase'] == 'run':
            self.injection_started = True
            if self.injected_cycles < 24:
                self.data.xfrc_applied[1, 5] = 0.025 if self.case == 'entry_left' else -0.025
                self.injected_cycles += 1
            else:
                self.data.xfrc_applied[1, 5] = 0
        frame = super().step_coupling()
        info = self.controller.info()
        error = info['e_lat_mm']
        self.max_error_step_mm = max(self.max_error_step_mm, abs(error - self._previous_error))
        self._previous_error = error
        bits = info.get('line_bits')
        if info['line_source'] == 'sensor':
            self.fresh_sensor_cycles += 1
        if bits is not None and info['line_source'] == 'sensor' and not observe(bits).valid:
            self.invalid_fresh_measurements += 1
        if bits is not None and bits != frame.line_bits:
            self.consumed_mismatches += 1
        if (self._last_injected_time is not None and self.reacquire_delay_s is None
                and info['seg_i'] == 1 and info['line_source'] == 'sensor'
                and observe(frame.line_bits).valid):
            self.reacquire_delay_s = round(self.data.time - self._last_injected_time, 4)
        return frame


def run_case(case, firmware=False):
    backend = None
    if firmware:
        print(f'line tracking: firmware {case}', flush=True)
        from bot.renode import DEFAULT_PORTABLE
        os.environ.setdefault('PYRENODE_PATH', DEFAULT_PORTABLE)
        from race.renode_backend import RacePeriphBackend
        backend = RacePeriphBackend(task=2, elf_path=os.environ.get('LINE_RACE_ELF'))
    loop = DisturbedRaceLoop(case, backend)
    try:
        verdict = loop.run_until_done(45, progress_hz=0.1 if firmware else 0)
        state = loop.state()       # finished telemetry must remain viewable
        if state['mission']['phase'] != 'done':
            verdict['pass'] = False
        return {**verdict, 'case': case, 'backend': 'firmware' if firmware else 'python',
                'injected_cycles': loop.injected_cycles,
                'max_error_step_mm': round(loop.max_error_step_mm, 3),
                'invalid_fresh_measurements': loop.invalid_fresh_measurements,
                'fresh_sensor_cycles': loop.fresh_sensor_cycles,
                'reacquire_delay_s': loop.reacquire_delay_s,
                'consumed_mismatches': loop.consumed_mismatches}
    finally:
        if backend is not None: backend._ch.emu.clear()


class TestLineTracking(unittest.TestCase):
    def test_arc_entry_and_line_loss_in_python(self):
        for case in ('entry_left', 'entry_right', 'dropout', 'split', 'wide', 'late_dropout'):
            with self.subTest(case=case):
                result = run_case(case)
                print(result, flush=True)
                self.assertTrue(result['pass'], result)
                expected_cycles = (24 if case.startswith('entry') else
                                   30 if case in ('split', 'wide') else 50)
                self.assertEqual(result['injected_cycles'], expected_cycles, result)
                self.assertGreater(result['fresh_sensor_cycles'], 50, result)
                self.assertLessEqual(result['max_error_step_mm'], 2.001, result)
                self.assertEqual(result['invalid_fresh_measurements'], 0, result)
                self.assertEqual(result['consumed_mismatches'], 0, result)

    def test_inspection_pause_freezes_physics_and_controller(self):
        import numpy as np
        loop = RaceLoop(task=2)
        loop.run(0.5)
        time, seq = loop.data.time, loop.controller.seq
        pose = loop.data.qpos.copy()
        loop.paused = True
        for _ in range(30): loop.step_coupling()
        self.assertEqual(loop.data.time, time)
        self.assertEqual(loop.controller.seq, seq)
        np.testing.assert_array_equal(loop.data.qpos, pose)
        loop.paused = False
        loop.step_coupling()
        self.assertGreater(loop.data.time, time)
        self.assertEqual(loop.controller.seq, seq + 1)
        loop.reset()
        loop.paused = True
        reset_frame = loop.step_coupling()
        self.assertEqual(reset_frame.seq, 0)
        self.assertEqual(loop.controller.seq, 0)
        self.assertEqual(loop.state()['duty'], [0, 0])


class TestLineTrackingFirmware(unittest.TestCase):
    def test_arc_entry_and_line_loss_through_real_gpio(self):
        from tests.test_race_firmware import _renode_ready
        ready, why = _renode_ready()
        if not ready: self.skipTest(why)
        for case in ('entry_left', 'entry_right', 'dropout', 'split', 'wide', 'late_dropout'):
            with self.subTest(case=case):
                result = run_case(case, firmware=True)
                print(result, flush=True)
                self.assertTrue(result['pass'], result)
                expected_cycles = (24 if case.startswith('entry') else
                                   30 if case in ('split', 'wide') else 50)
                self.assertEqual(result['injected_cycles'], expected_cycles, result)
                self.assertGreater(result['fresh_sensor_cycles'], 50, result)
                self.assertLessEqual(result['max_error_step_mm'], 2.001, result)
                self.assertEqual(result['invalid_fresh_measurements'], 0, result)
                self.assertEqual(result['consumed_mismatches'], 0, result)


class TestLongLineRecovery(unittest.TestCase):
    def check_result(self, firmware):
        result = run_case('long_dropout', firmware=firmware)
        print(result, flush=True)
        self.assertTrue(result['pass'], result)
        self.assertEqual(result['injected_cycles'], 360, result)
        self.assertIsNotNone(result['reacquire_delay_s'], result)
        self.assertLessEqual(result['reacquire_delay_s'], 1.0, result)
        self.assertLessEqual(result['max_error_step_mm'], 2.001, result)
        self.assertEqual(result['invalid_fresh_measurements'], 0, result)
        self.assertEqual(result['consumed_mismatches'], 0, result)

    def test_python_recovers_after_slowdown_and_search_activate(self):
        self.check_result(False)

    def test_firmware_recovers_after_slowdown_and_search_activate(self):
        from tests.test_race_firmware import _renode_ready
        ready, why = _renode_ready()
        if not ready: self.skipTest(why)
        self.check_result(True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
