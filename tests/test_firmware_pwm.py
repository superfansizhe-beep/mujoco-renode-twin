"""The PWM bring-up gate: firmware/pwm_bringup.elf takes signed duties
from the harness command block, runs them through the real motor PWM
driver (firmware/stm32f4_pwm.c -- TIM1 + TB6612 direction pins), and
the harness measures the resulting pin waveform's average duty.

Sim limits this suite works WITH (probed 2026-09-29): the OC's
intra-period phase is not faithful, so the waveform gate measures
averages over many periods; BDTR/MOE is STORED (firmware/
timer1_model.cs) and the plant decode gates on every drive-chain
enable (see the gate test), but the pin waveform itself still ignores
MOE -- the scope/electrical layer stays on the BOARD label in
firmware/pwm_status.md.
"""
import os
import re
import unittest

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
PWM_ELF = os.path.join(FW, "pwm_bringup.elf")

TIM1 = 0x40010000
GPIOE = 0x40021000
RES = 0x2001EC00
CMD = RES + 0x40

RESULT_MAGIC = 0x524D5750          # "PWMR"
CMD_MAGIC = 0x434D5750             # "PWMC"
PWM_ARR = 799                      # 20 kHz @ 16 MHz


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
    if not os.path.isfile(PWM_ELF):
        return None, f"{PWM_ELF} missing -- bash firmware/build_pwm.sh"
    return True, ""


class TestPwmLayout(unittest.TestCase):

    def test_results_block_sits_in_the_ld_carve(self):
        header = open(os.path.join(FW, "pwm_bringup.h")).read()
        base = int(re.search(r"#define\s+PWM_RESULT_BASE\s+(0x[0-9A-Fa-f]+)",
                             header).group(1), 16)
        ld = open(os.path.join(FW, "stm32f407.ld")).read()
        ram = re.search(r"RAM   \(rwx\) : ORIGIN = 0x20000000, LENGTH = (\S+)",
                        ld).group(1)
        ram_end = 0x20000000 + int(ram, 16)
        self.assertLessEqual(ram_end, base,
                             "usable RAM must end at the pwm block "
                             "(ld header carve map)")
        self.assertEqual(base, RES)
        self.assertLess(base + 0x80, 0x2001EE00,
                        "the pwm block must stay below the enc block")


class TestPwmBringup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(PWM_ELF, 0.005)
        self.sb = self._ch.sysbus

    def tearDown(self):
        self._ch.emu.clear()

    # ---- helpers ----
    def _res(self, i):
        return self.sb.ReadDoubleWord(RES + 4 * i)

    def _command(self, duty_l, duty_r):
        self.sb.WriteDoubleWord(CMD + 0x04, duty_l & 0xFFFFFFFF)
        self.sb.WriteDoubleWord(CMD + 0x08, duty_r & 0xFFFFFFFF)
        self.sb.WriteDoubleWord(CMD, CMD_MAGIC)

    def _idr(self):
        return self.sb.ReadDoubleWord(GPIOE + 0x10)

    def _avg_duty(self, bit, samples=1000):
        hi = 0
        for _ in range(samples):
            hi += (self._idr() >> bit) & 1
            self._ch.run(0.000001)     # 1 us: 1000 us ~ 20 PWM periods
        return hi / samples

    # ---- the gates ----
    def test_pwm_config_contract_is_written_at_runtime(self):
        self._ch.run(0.02)
        self.assertEqual(self.sb.ReadDoubleWord(TIM1 + 0x28), 0, "PSC=0")
        self.assertEqual(self.sb.ReadDoubleWord(TIM1 + 0x2C), PWM_ARR,
                         "ARR=799 -> 20 kHz at the 16 MHz tree")
        ccmr1 = self.sb.ReadDoubleWord(TIM1 + 0x18)
        self.assertEqual(ccmr1 & 0x6060, 0x6060,
                         "CCMR1: OC1M/OC2M=110 PWM mode")
        # OCxPE (preload-enable) reads back 0 -- Renode does not store
        # those fields (probed 2026-09-29); harmless here, the duty gate
        # measures the pins
        self.assertEqual(self.sb.ReadDoubleWord(TIM1 + 0x20) & 0x11, 0x11,
                         "CCER: CC1E + CC2E")
        self.assertEqual(self.sb.ReadDoubleWord(TIM1) & 0x81, 0x81,
                         "CR1: CEN + ARPE")
        moder = self.sb.ReadDoubleWord(GPIOE)
        self.assertEqual(moder & ((3 << 18) | (3 << 22)),
                         (2 << 18) | (2 << 22), "PE9/PE11 AF mode")
        self.assertEqual(moder & 0x3FF, 0x155, "PE0-PE4 outputs")
        afrh = self.sb.ReadDoubleWord(GPIOE + 0x24)
        self.assertEqual(afrh & ((0xF << 4) | (0xF << 12)),
                         (1 << 4) | (1 << 12), "PE9/PE11 AF1")
        rcc = 0x40023800
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x44) & 0x1, 0x1,
                         "APB2ENR.TIM1EN")
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x30) & 0x10, 0x10,
                         "AHB1ENR.GPIOE (the repl RCC stores enables)")
        self.assertEqual(self._res(0), RESULT_MAGIC, "results magic")
        self.assertEqual(self._res(6) & 0x1F, 0x10,
                         "boot state: STBY on, all phases coast")
        self.assertEqual(self.sb.ReadDoubleWord(TIM1 + 0x44) & 0x8000,
                         0x8000, "BDTR.MOE reads back (timer1_model.cs)")

    def test_command_echoes_through_ccr_and_direction(self):
        self._command(500, -250)
        self._ch.run(0.01)
        self.assertEqual(self._res(2), 500, "duty echo left")
        self.assertEqual(self._res(3) - (1 << 32), -250, "duty echo right")
        self.assertEqual(self._res(4), 400, "CCR1 = 500 permille of 799")
        self.assertEqual(self._res(5), 200, "CCR2 = 250 permille of 799")
        self.assertEqual(self._res(6) & 0x1F, 0x19,
                         "AIN1 | BIN2 | STBY: left forward, right reverse")

    def test_waveform_average_duty_matches_the_command(self):
        self._command(500, -250)
        self._ch.run(0.01)
        d1 = self._avg_duty(9)
        self.assertAlmostEqual(d1, 0.50, delta=0.05,
                               msg=f"CH1 duty {d1:.2f} ~ 500 permille")
        d2 = self._avg_duty(11)
        self.assertAlmostEqual(d2, 0.25, delta=0.05,
                               msg=f"CH2 duty {d2:.2f} ~ 250 permille")

    def test_duty_zero_coasts_and_clamps_at_the_rail(self):
        self._command(0, 0)
        self._ch.run(0.01)
        self.assertEqual(self._res(6) & 0x1F, 0x10,
                         "zero duty: coast on both phases, STBY held")
        self.assertEqual(self._res(4), 0, "CCR1 = 0")
        self._command(2000, -2000)
        self._ch.run(0.01)
        self.assertEqual(self._res(4), PWM_ARR, "left clamped to ARR")
        self.assertEqual(self._res(5), PWM_ARR, "right clamped to ARR")
        self.assertEqual(self._res(6) & 0x1F, 0x19,
                         "AIN1 | BIN2 | STBY (left fwd, right rev)")

    def test_every_drive_chain_gate_kills_the_decoded_output(self):
        """The plant decode must honor every enable between the core and
        the motor (RM0090 + TB6612 sheet): a firmware that forgets any of
        them drives motors in sim that would be dead on the board -- the
        decode is the harness's truth, so IT carries the gating."""
        from bot.periph import decode_duty_pair
        self._command(500, -250)
        self._ch.run(0.01)
        rw = self.sb.ReadDoubleWord
        ww = self.sb.WriteDoubleWord
        # the CCR round-trip is lossy by construction: 500 permille -> 400
        # of 799 counts -> 400*1000/799 = 500.6 rounds to 501
        self.assertEqual(decode_duty_pair(rw), (501, -250),
                         "chain fully on: the commanded drive decodes")

        def poke(addr, mask, on):
            v = rw(addr)
            ww(addr, (v | mask) if on else (v & ~mask))

        for addr, mask, name, want in (
                (TIM1 + 0x44, 1 << 15, "BDTR.MOE", (0, 0)),
                (TIM1 + 0x20, 1 << 0, "CCER.CC1E", (0, -250)),
                (TIM1 + 0x20, 1 << 4, "CCER.CC2E", (501, 0)),
                (TIM1 + 0x00, 1 << 0, "CR1.CEN", (0, 0)),
                (0x40023844, 1 << 0, "APB2ENR.TIM1EN", (0, 0)),
                (0x40023830, 1 << 4, "AHB1ENR.GPIOEEN", (0, 0)),
        ):
            with self.subTest(gate=name):
                poke(addr, mask, False)
                try:
                    self.assertEqual(decode_duty_pair(rw), want)
                finally:
                    poke(addr, mask, True)
                self.assertEqual(decode_duty_pair(rw), (501, -250))

        with self.subTest(gate="TB6612 STBY pin"):
            odr = rw(GPIOE + 0x14)
            ww(GPIOE + 0x14, odr & ~(1 << 4))
            self.assertEqual(decode_duty_pair(rw), (0, 0))
            ww(GPIOE + 0x14, odr)


if __name__ == "__main__":
    unittest.main()
