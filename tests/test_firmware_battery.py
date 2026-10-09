"""The battery bring-up gate: firmware/battery_bringup.elf reads the
3S battery sense through the real ADC driver (firmware/stm32f4_adc.c)
against the runtime-compiled ADC1 model (firmware/adc_model.cs), which
applies the board's VBAT divider before the 12-bit quantization.

Bench millivolts quantize against VREF and saturate at the rail, like
the real converter; the divider resistor values themselves are
board-labeled (firmware/battery_status.md).
"""
import os
import re
import unittest

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
BAT_ELF = os.path.join(FW, "battery_bringup.elf")

BENCH = 0xF0000000
BENCH_BATTERY_MV = BENCH + 0x28
RES = 0x2001EA00
RESULT_MAGIC = 0x52544142          # "BATR"

ADC1 = 0x40012000
GPIOC = 0x40020800


def _renode_ready():
    from bot.renode import DEFAULT_PORTABLE
    os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
    try:
        import pyrenode3  # noqa: F401
    except Exception as exc:
        return None, f"pyrenode3 not importable ({exc.__class__.__name__}: {exc})"
    if not DEFAULT_PORTABLE or not os.path.isdir(DEFAULT_PORTABLE):
        return None, ("Renode portable not configured "
                      f"(set RENODE_PORTABLE): {DEFAULT_PORTABLE}")
    if not os.path.isfile(BAT_ELF):
        return None, f"{BAT_ELF} missing -- bash firmware/build_battery.sh"
    return True, ""


class TestBatteryLayout(unittest.TestCase):
    """Static: the divider contract and the bench-region overlap."""

    def test_model_divider_matches_the_firmware_constant(self):
        model = open(os.path.join(FW, "adc_model.cs")).read()
        m = re.search(r"DefaultBatteryDivider = (\d+)", model)
        drv = open(os.path.join(FW, "stm32f4_adc.h")).read()
        d = re.search(r"#define\s+VBAT_DIVIDER\s+(\d+)u?", drv)
        self.assertEqual(int(m.group(1)), int(d.group(1)),
                         "the modeled divider must equal VBAT_DIVIDER")

    def test_bench_words_do_not_overlap(self):
        imu = open(os.path.join(FW, "imu_bringup.h")).read()
        fi = int(re.search(r"#define\s+IMU_BENCH_FI\s+(0x[0-9A-Fa-f]+)u?",
                           imu).group(1), 16)
        model = open(os.path.join(FW, "adc_model.cs")).read()
        bat = int(re.search(r"BenchBatteryMv = (0x[0-9A-Fa-f]+)",
                            model).group(1), 16)
        cur = int(re.search(r"BenchCurrentMa = (0x[0-9A-Fa-f]+)",
                            model).group(1), 16)
        self.assertLess(fi, bat, "imu words must stay below the adc words")
        self.assertLess(bat, cur)
        self.assertLess(cur, 0x400, "bench region is one page")

    def test_results_block_sits_in_the_ld_carve(self):
        ld = open(os.path.join(FW, "stm32f407.ld")).read()
        ram = re.search(r"RAM   \(rwx\) : ORIGIN = 0x20000000, LENGTH = (\S+)",
                        ld).group(1)
        ram_end = 0x20000000 + int(ram, 16)
        self.assertLessEqual(ram_end, RES,
                             "usable RAM must end at the battery block")
        self.assertLess(RES + 0x80, 0x2001EC00,
                        "the battery block must stay below the pwm block")


class TestBatteryBringup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(BAT_ELF, 0.005)
        self.sb = self._ch.sysbus
        self.sb.WriteDoubleWord(BENCH, 0x494D4231)   # bench magic

    def tearDown(self):
        self._ch.emu.clear()

    def _res(self, i):
        return self.sb.ReadDoubleWord(RES + 4 * i)

    def _run_at(self, battery_mv, seconds=0.03):
        self.sb.WriteDoubleWord(BENCH_BATTERY_MV, battery_mv)
        self._ch.run(seconds)

    # ---- the gates ----
    def test_adc_config_contract_is_written_at_runtime(self):
        self._run_at(11100)
        moder = self.sb.ReadDoubleWord(GPIOC)
        self.assertEqual(moder & 0x3, 0x3, "PC0 analog mode (11)")
        self.assertEqual(moder & 0xC, 0xC, "PC1 analog mode (11)")
        pupdr = self.sb.ReadDoubleWord(GPIOC + 0x0C)
        self.assertEqual(pupdr & 0x0F, 0, "PC0/PC1: no pulls")
        rcc = 0x40023800
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x30) & 0x4, 0x4,
                         "AHB1ENR.GPIOCEN (was missing -- review 6)")
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x44) & 0x100, 0x100,
                         "APB2ENR.ADC1EN (the repl RCC stores enables)")
        self.assertEqual(self.sb.ReadDoubleWord(ADC1 + 0x08) & 0x1, 0x1,
                         "CR2.ADON")
        self.assertEqual(self.sb.ReadDoubleWord(ADC1 + 0x34) & 0x1F, 10,
                         "SQR3: channel 10 (VBAT sense)")
        smpr1 = self.sb.ReadDoubleWord(ADC1 + 0x0C)
        self.assertEqual(smpr1 & 0x3F, 0x3F,
                         "SMPR1: 480-cycle sampling on ch10/ch11")
        # ADCPRE in the common block is not modeled -- battery_status.md

    def test_3s_nominal_reads_back_within_quantization(self):
        self._run_at(11100)
        self.assertEqual(self._res(0), RESULT_MAGIC, "BATR magic")
        self.assertGreater(self._res(1), 0, "the 10 ms sampling loop runs")
        self.assertLessEqual(abs(self._res(2) - 11100), 10,
                             "battery mV echo within quantization")
        self.assertEqual(self._res(3), 2774, "pin mV = battery / 4")
        self.assertEqual(self._res(4), 3443, "12-bit raw vs VREF 3300")
        self.assertEqual(self._res(5), 0, "no EOC timeouts")

    def test_full_and_empty_spans_of_the_3s_battery(self):
        self._run_at(12600)          # 4.2 V/cell
        self.assertLessEqual(abs(self._res(2) - 12600), 10)
        self._run_at(9900)           # 3.3 V/cell, effectively empty
        self.assertLessEqual(abs(self._res(2) - 9900), 10)
        self._run_at(1000)           # deep under: quantizes toward zero
        self.assertLessEqual(abs(self._res(2) - 1000), 10)

    def test_over_range_saturates_at_the_vref_rail(self):
        self._run_at(20000)          # impossible for 3S; pin would be 5 V
        self.assertEqual(self._res(4), 4095, "raw saturates at full scale")
        self.assertEqual(self._res(3), 3300, "pin clamps to VREF")
        self.assertEqual(self._res(2), 13200,
                         "echo = rail x divider (over-range marker)")

    def test_valid_zero_voltage_publishes_zero_then_recovers(self):
        """A conversion that reads 0 is VALID (sense at ground): it must
        publish and count no timeout -- the old code kept the stale
        nominal value and added false timeouts (review finding 7)."""
        self._run_at(11100)
        self.assertGreater(self._res(2), 0, "nominal first")
        self._run_at(0)              # a real 0 V at the sense pin
        self.assertEqual(self._res(4), 0, "raw 0 published")
        self.assertEqual(self._res(2), 0, "battery mV publishes the zero")
        self.assertEqual(self._res(5), 0, "no false EOC timeouts")
        self._run_at(11100)          # and back
        self.assertGreater(self._res(2), 0, "recovers to nominal")

    def test_deadline_clock_survives_the_32_bit_wrap(self):
        """Renode's LimitTimer throws on edge-injected crossings of the
        16-bit encoder counters, but the FREE-RUNNING 32-bit TIM2 wraps
        without model error (probe:
        output/battery-milestone/tim2-wrap-probe.log) -- so the ~268 s
        wrap of the shared deadline clock is an EXECUTED sim gate, not
        a board label (review finding 5, confirmed runnable by the
        review round's re-probe)."""
        # park TIM2 one microsecond under the wrap BEFORE the firmware
        # boots: the first pacing mark sits at the boundary, the wrap
        # crosses ~1 us into the run, and the raw-tick modular delta
        # must read it as a small forward step -- pre-2026-09-29 this
        # arithmetically exploded into hundreds of catch-up samples.
        self._ch.preset_counter("timer2", 0xFFFFFFF0)
        # 50 ms: the boot pushes the first pacing mark ~3 ms past the
        # boundary, so the first sample lands ~13 ms in (same as the
        # review round's probe observed) -- 0.03 s would only see two.
        self._run_at(11100, seconds=0.05)
        self.assertLess(self.sb.ReadDoubleWord(0x40000024), 0x100000,
                        "TIM2 must have wrapped during the run")
        self.assertGreaterEqual(self._res(1), 3, "the 10 ms pacing "
                                "survives the wrap")
        self.assertLessEqual(abs(self._res(2) - 11100), 10, "mv intact")
        self.assertEqual(self._res(5), 0, "no false EOC timeouts")


class TestAdcLatency(unittest.TestCase):
    """Conversion-time gates (RM0090 ch. 13): TCONV = sampling + 12
    ADCCLK cycles, sampling from SMPR1 (channels 10-18), ADCCLK = PCLK2 / ADCPRE -- a
    wrong sample time or a wrong prescaler must stretch the conversion,
    not pass as instant luck. CPU self-branches; TIM2 (1 MHz) measures."""

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        from bot.renode import RenodeChannel
        cls.ch = RenodeChannel(BAT_ELF, .005)

    @classmethod
    def tearDownClass(cls):
        cls.ch.emu.clear()

    def setUp(self):
        self.ch.mach.internal.Reset()
        self.ch.write_word(0x20010000, 0xE7FEE7FE)
        self.ch.mon.execute('cpu PC 0x20010000')
        self.ch.write_word(0x40023844, 1 << 8)               # APB2.ADC1EN
        self.ch.write_word(0x40023840, 1 << 0)               # APB1.TIM2EN
        self.ch.write_word(0x40000028, 15)                    # TIM2 1 MHz
        self.ch.write_word(0x40000000, 1)                     # TIM2 CEN
        self.ch.write_word(0x40012034, 10)                    # SQR3: ch10
        self.ch.write_word(0xF0000028, 11100)                 # 3S pack
        self.ch.write_word(ADC1 + 0x0C, 0)                    # SMPR1 reset

    def _convert_us(self, smp, adcpre):
        """One SWSTART conversion at the given SMPR2 ch10 sampling value
        and CR2 ADCPRE code; returns (virtual us to EOC, DR)."""
        self.ch.write_word(ADC1 + 0x0C, smp & 0x7)   # SMPR1 ch10
        self.ch.write_word(ADC1 + 0x08, (adcpre << 16) | 1)   # ADON
        t0 = self.ch.read_word(0x40000024)
        self.ch.write_word(ADC1 + 0x08, (1 << 30) | (adcpre << 16) | 1)
        for _ in range(2000):                    # 2 us steps, 4 ms cap
            self.ch.run(.000002)
            if self.ch.read_word(ADC1) & 2:
                t1 = self.ch.read_word(0x40000024)
                return t1 - t0, self.ch.read_word(ADC1 + 0x4C)
        return None, None

    def test_conversion_pays_its_sample_time(self):
        fast, fast_dr = self._convert_us(0, 0)     # 3 cyc, /2: ~1.9 us
        slow, slow_dr = self._convert_us(7, 0)     # 480 cyc, /2: ~61.5 us
        self.assertIsNotNone(fast, "reset sampling must convert")
        self.assertIsNotNone(slow, "480-cycle sampling must convert")
        self.assertLessEqual(fast, 10, "15 cycles at 8 MHz is ~1.9 us")
        self.assertGreaterEqual(slow, 50, "492 cycles at 8 MHz is ~61.5 us")
        self.assertGreater(slow, 5 * fast,
                           "the sampling time must dominate TCONV")
        self.assertGreater(fast_dr, 3000, "11.1 V / 4 -> ~3.4 k raw")
        self.assertEqual(fast_dr, slow_dr, "latency must not change the value")

    def test_wrong_adcpre_stretches_the_conversion(self):
        div2, _ = self._convert_us(0, 0)           # ADCCLK 8 MHz: ~1.9 us
        div8, _ = self._convert_us(0, 3)           # ADCCLK 2 MHz: ~7.5 us
        self.assertIsNotNone(div2)
        self.assertIsNotNone(div8)
        self.assertGreaterEqual(div8, 6, "15 cycles at 2 MHz is ~7.5 us")
        self.assertGreater(div8, 3 * div2,
                           "ADCPRE must scale the conversion time")

    def test_swstart_during_a_conversion_is_ignored(self):
        self.ch.write_word(ADC1 + 0x0C, 7)         # the long sampling
        self.ch.write_word(ADC1 + 0x08, 1)         # ADON
        self.ch.write_word(ADC1 + 0x08, (1 << 30) | 1)
        self.ch.run(.00002)
        self.assertEqual(self.ch.read_word(ADC1) & 2, 0,
                         "61.5 us conversion must still be in flight")
        self.ch.write_word(ADC1 + 0x08, (1 << 30) | 1)  # an early restart
        self.ch.run(.0001)
        self.ch.read_word(ADC1 + 0x4C)             # drain, clear EOC
        self.assertEqual(self.ch.read_word(ADC1) & 2, 0,
                         "one conversion completed, not two")


if __name__ == "__main__":
    unittest.main()
