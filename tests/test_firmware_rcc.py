"""RCC enable failures through Renode's bus, clocks and encoder pins.

RM0090 sections 7.3.10, 7.3.13 and 7.3.14 (STM32F405/407):
AHB1ENR/APB1ENR/APB2ENR gate peripheral clocks, independently of CEN.
CPU executes a self-branch so production init cannot repair the injected
missing enable. IMU bring-up ELF supplies the normal platform/linker.
"""
import unittest

from tests.test_firmware_imu import IMU_ELF, _renode_ready

AHB1 = 0x40023830
APB1 = 0x40023840
APB2 = 0x40023844
TIM2 = 0x40000000
TIM3 = 0x40000400
GPIOC = 0x40020800


class TestRccGating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)
        from bot.renode import RenodeChannel
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        cls.ch = RenodeChannel(IMU_ELF, .005)

    @classmethod
    def tearDownClass(cls):
        cls.ch.emu.clear()

    def setUp(self):
        self.ch.mach.internal.Reset()
        self.ch.write_word(0x20010000, 0xE7FEE7FE)
        self.ch.mon.execute('cpu PC 0x20010000')

    def _timer(self):
        self.ch.write_word(TIM2 + 0x28, 15)
        self.ch.write_word(TIM2 + 0x14, 1)
        self.ch.write_word(TIM2, 1)

    def test_disabled_register_writes_do_not_configure_peripherals(self):
        for enr, bit, reg, val in (
            (AHB1, 0, 0x40020000, 0xA0),
            (AHB1, 1, 0x40020400, 0xA000),
            (AHB1, 2, GPIOC, 0xA000),
            (AHB1, 3, 0x40020C00, 0xA000000),
            (AHB1, 4, 0x40021000, 0x55),
            (AHB1, 5, 0x4002140C, 0x5555),
            (APB1, 0, TIM2 + 0x28, 15),
            (APB1, 1, TIM3 + 0x18, 0x101),
            (APB1, 2, 0x40000818, 0x101),
            (APB1, 17, 0x40004408, 139),
            (APB1, 21, 0x40005404, 16),
            (APB2, 0, 0x4001002C, 799),
            (APB2, 8, 0x40012034, 10),
        ):
            with self.subTest(register=hex(reg)):
                self.ch.write_word(enr, 0)
                self.ch.write_word(reg, val)
                self.ch.write_word(enr, 1 << bit)
                self.assertNotEqual(self.ch.read_word(reg), val,
                                    'a disabled clock must discard configuration')
                self.ch.write_word(reg, val)
                self.assertEqual(self.ch.read_word(reg), val)
                self.ch.write_word(enr, 0)

    def test_tim2_clock_stops_preserves_and_resumes_counter(self):
        self._timer()  # CEN before RCC is ineffective
        self.ch.run(.001)
        self.ch.write_word(APB1, 1)
        self.assertEqual(self.ch.read_word(TIM2 + 0x24), 0)
        self._timer()
        self.ch.run(.001)
        count = self.ch.read_word(TIM2 + 0x24)
        self.assertAlmostEqual(count, 1000, delta=2)
        self.ch.write_word(APB1, 0)
        self.ch.run(.003)
        self.ch.write_word(APB1, 1)
        self.assertEqual(self.ch.read_word(TIM2 + 0x24), count)
        self.ch.run(.001)
        self.assertAlmostEqual(self.ch.read_word(TIM2 + 0x24) - count,
                               1000, delta=2)

    def test_encoder_clock_blocks_edges_and_recovers(self):
        self.ch.write_word(AHB1, 1 << 2)
        self.ch.write_word(APB1, 1 << 1)
        self.ch.write_word(GPIOC, 0xA000)
        self.ch.write_word(GPIOC + 0x20, 0x22000000)
        for off, val in ((0x08, 3), (0x18, 0x101), (0x2C, 0xFFFF), (0, 1)):
            self.ch.write_word(TIM3 + off, val)

        def cycle():
            for pin, value in ((6, True), (7, True), (6, False), (7, False)):
                self.ch.mon.execute(f'gpioPortC OnGPIO {pin} {str(value).lower()}')

        cycle()
        self.assertEqual(self.ch.read_word(TIM3 + 0x24), 4)
        self.ch.write_word(APB1, 0)
        cycle()
        self.ch.write_word(APB1, 1 << 1)
        self.assertEqual(self.ch.read_word(TIM3 + 0x24), 4)
        cycle()
        self.assertEqual(self.ch.read_word(TIM3 + 0x24), 8)

    def test_adc_cannot_convert_with_its_clock_disabled(self):
        self.ch.write_word(0xF0000028, 11100)
        self.ch.write_word(APB2, 1 << 8)
        self.ch.write_word(0x40012034, 10)
        self.ch.write_word(0x40012008, 1)
        self.ch.write_word(APB2, 0)
        self.ch.write_word(0x40012008, 0x40000001)
        self.ch.write_word(APB2, 1 << 8)
        self.assertEqual(self.ch.read_word(0x40012000) & 2, 0)
        self.ch.write_word(0x40012008, 0x40000001)
        self.ch.run(.00002)    # TCONV: the result is no longer instant
        self.assertEqual(self.ch.read_word(0x40012000) & 2, 2)
        self.assertGreater(self.ch.read_word(0x4001204C), 3000)

    def test_reset_does_not_resume_previous_timer_state(self):
        self.ch.write_word(APB1, 1)
        self._timer()
        self.ch.run(.001)
        self.ch.write_word(APB1, 0)
        self.setUp()
        self.ch.write_word(APB1, 1)
        self.ch.run(.001)
        self.assertEqual(self.ch.read_word(TIM2 + 0x24), 0)

    def test_usart_clock_discards_wire_input_and_recovers(self):
        from Antmicro.Renode.Peripherals.UART import IUART
        uart = IUART(self.ch.mach.sysbus.get_child('usart2').internal)
        self.ch.write_word(APB1, 1 << 17)
        self.ch.write_word(0x40004408, 139)    # BRR: frame ~87 us
        self.ch.write_word(0x4000440C, 0x200C)  # UE, TE, RE
        self.ch.write_word(APB1, 0)
        uart.WriteChar(65)
        self.ch.write_word(APB1, 1 << 17)
        self.assertEqual(self.ch.read_word(0x40004400) & 0x20, 0)
        uart.WriteChar(66)
        self.ch.run(.001)                      # let the frame land (RM0090 30)
        self.assertEqual(self.ch.read_word(0x40004400) & 0x20, 0x20)
        self.assertEqual(self.ch.read_word(0x40004404), 66)

    def test_tim1_pwm_clock_entries_pause_and_resume(self):
        self.ch.write_word(APB2, 1)
        for off, val in ((0x28, 0), (0x2C, 799), (0x18, 0x6060),
                         (0x20, 0x11), (0x34, 400), (0x38, 200), (0, 1)):
            self.ch.write_word(0x40010000 + off, val)
        self.ch.run(.00001)
        count = self.ch.read_word(0x40010024)
        self.ch.write_word(APB2, 0)
        self.ch.run(.00002)
        self.ch.write_word(APB2, 1)
        self.assertEqual(self.ch.read_word(0x40010024), count)
        self.ch.run(.00001)
        self.assertNotEqual(self.ch.read_word(0x40010024), count)


if __name__ == '__main__':
    unittest.main()
