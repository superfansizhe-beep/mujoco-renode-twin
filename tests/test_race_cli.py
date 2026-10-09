"""The public firmware launch must select the production peripheral path."""
from argparse import Namespace
import unittest
from unittest.mock import Mock, patch

from bot import motors
from bot.loop import COUPLING_S
from race.__main__ import _firmware_backend, run_task


class TestFastDefaults(unittest.TestCase):
    def test_reference_controller_defaults_to_fast_for_every_task(self):
        from race.controller import RaceController

        for task in (1, 2, 3, 4):
            with self.subTest(task=task):
                controller = RaceController(task, COUPLING_S,
                                             motors.BATTERY_NOMINAL["3s"])
                self.assertTrue(controller.turbo)

    def test_slow_override_is_explicit_and_task4_stays_fast(self):
        from race.controller import RaceController

        self.assertFalse(RaceController(2, COUPLING_S,
                                         motors.BATTERY_NOMINAL["3s"],
                                         turbo=False).turbo)
        self.assertTrue(RaceController(4, COUPLING_S,
                                       motors.BATTERY_NOMINAL["3s"],
                                       turbo=False).turbo)


class TestFirmwareLaunch(unittest.TestCase):
    def test_cli_passes_configuration_to_the_peripheral_backend(self):
        args = Namespace(battery="2s", turbo=True)
        with patch("race.renode_backend.RacePeriphBackend") as peripheral, \
                patch("race.renode_backend.RaceFirmwareBackend") as legacy:
            backend = _firmware_backend(args, 3)
        self.assertIs(backend, peripheral.return_value)
        peripheral.assert_called_once_with(
            task=3, dt=COUPLING_S,
            v_batt=motors.BATTERY_NOMINAL["2s"], turbo=True)
        legacy.assert_not_called()

    def test_all_task_runner_passes_the_selected_battery_to_the_world(self):
        loop = Mock()
        loop.run_until_done.return_value = {"pass": True}
        backend = object()
        with patch("race.__main__.RaceLoop", return_value=loop) as race_loop:
            result = run_task(2, turbo=True, timeout=3.0, verbose=True,
                              backend=backend, event_log="events.jsonl",
                              battery="2s")
        self.assertEqual(result, {"pass": True})
        race_loop.assert_called_once_with(
            task=2, battery="2s", turbo=True, controller=backend,
            event_log="events.jsonl")
        loop.run_until_done.assert_called_once_with(3.0, progress_hz=1.0)


class TestFirmwareLaunchRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_race_firmware import _renode_ready
        ready, reason = _renode_ready()
        if not ready:
            raise unittest.SkipTest(reason)

    def test_public_factory_runs_real_gpio_sensor_cycles(self):
        from race.loop import RaceLoop
        from race.renode_backend import RacePeriphBackend
        fw = _firmware_backend(Namespace(battery="3s", turbo=None), 2)
        self.assertIsInstance(fw, RacePeriphBackend)
        self.assertTrue(fw.turbo,
                        "the normal Renode firmware launch must select fast mode")
        loop = RaceLoop(task=2, controller=fw)
        self.addCleanup(fw._ch.emu.clear)
        seq = fw.fw_seq
        # BotLoop starts at seq=0; boot's seq=1 is the initialization prior.
        for i, bits in enumerate((0x18, 0x81, 0x00, 0xE0)):
            frame = loop.read_sensors()
            frame.seq = i
            frame.line_bits = bits
            fw.step(frame)
            self.assertEqual(fw._consumed_line_bits, bits,
                             "CLI-selected firmware must read the driven GPIO mask")
            self.assertEqual(fw.fw_seq - seq, i + 1,
                             "one firmware cycle per sensor strobe")

    def test_native_encoder_input_matches_monitor_and_keeps_pin_guards(self):
        from race.renode_backend import RacePeriphBackend
        from bot.periph import EDGE_TICK_S
        fw = RacePeriphBackend(task=2)
        self.addCleanup(fw._ch.emu.clear)

        def trace(native):
            ch = fw._ch
            receiver = fw._encoder_inputs[0]
            counter, gpio = 0x40000424, 0x40020800
            ch.write_word(counter, 0xFFFC)
            rows = []

            def edges(sequence):
                for pin, value in sequence:
                    if native:
                        receiver.OnGPIO(pin, value)
                    else:
                        ch.mon.execute(f"gpioPortC OnGPIO {pin} {str(value).lower()}")
                    ch.run(EDGE_TICK_S)
                    rows.append(ch.read_word(counter))

            forward = ((6, True), (7, True), (6, False), (7, False))
            reverse = ((7, True), (6, True), (7, False), (6, False))
            edges(forward * 2)          # cross the real 16-bit boundary
            self.assertEqual(rows[-1], 4)
            edges(((7, False),) * 4)    # repeated levels have no extra edge
            self.assertEqual(rows[-1], 4)
            edges(reverse * 2)
            self.assertEqual(rows[-1], 0xFFFC)

            for address, mask, bad in ((gpio, 0xF << 12, 0),
                                        (gpio + 0x20, 0xFF << 24, 0x33 << 24),
                                        (0x40000400, 1, 0)):
                correct = ch.read_word(address)
                ch.write_word(address, (correct & ~mask) | bad)
                edges(forward)
                self.assertEqual(rows[-1], 0xFFFC, 'bad AF/mode/enable must stop counting')
                ch.write_word(address, correct)
            edges(forward)
            self.assertEqual(rows[-1], 0)
            return rows

        monitor_rows = trace(False)
        fw.reset()                     # cached receivers must follow the new machine
        self.assertEqual(trace(True), monitor_rows)


if __name__ == "__main__":
    unittest.main()
