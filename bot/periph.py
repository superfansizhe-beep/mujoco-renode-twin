"""The shared peripheral bench -- the hardware map both app backends drive.

twin and race each boot the same STM32F407 machine through bot.renode;
what differs is the mission, not the bench. This module owns the pieces
both RenodePeriphBackend/RacePeriphBackend inject through:

  - the IMU bench words the MPU6050 model latches from (SIM ONLY),
  - the encoder timer counters (edges injected, never a direct CNT
    write -- that would fake a driver-visible counter),
  - the TIM1/RCC/GPIOE truth the duty decode reads (what the motor
    bridge actually receives, not what was commanded).

Edge discipline: 20 us RunFor spacing so the event-driven models see
each transition; counters preset to 0x8000 as the origin convention;
every batch checked modulo 65536 -- a lost edge is loud.
"""

# IMU bench (SIM ONLY -- the Renode MPU6050 model latches from here)
BENCH = 0xF0000000
BENCH_MAGIC = 0x494D4231          # "IMB1"
BENCH_SEQ = BENCH + 0x04
BENCH_AX = BENCH + 0x08           # ax ay az gx gy gz temp, then FI, batt
BENCH_FI = BENCH + 0x24
BENCH_BATT = BENCH + 0x28

# encoder counters (edges only -- a direct CNT write would fake a
# driver-visible counter) and the PWM truth the plant torque reads
TIM3_CNT = 0x40000424
TIM4_CNT = 0x40000824
TIM1_CR1 = 0x40010000
TIM1_CCER = 0x40010020
TIM1_CCR1 = 0x40010034
TIM1_CCR2 = 0x40010038
TIM1_BDTR = 0x40010044
GPIOE_ODR = 0x40021014
RCC_AHB1ENR = 0x40023830
RCC_APB2ENR = 0x40023844
PWM_ARR = 799                     # 20 kHz at the 16 MHz tree


def decode_duty_pair(read_word) -> tuple:
    """What the motor bridge receives (RM0090 + TB6612 sheet): the whole
    drive chain must be on -- APB2ENR.TIM1EN, AHB1ENR.GPIOEEN, CR1.CEN,
    CCER.CCxE, BDTR.MOE (the repl's TIM1Sim stores it) and the STBY pin.
    Any gate off -> 0. On silicon a cleared CEN or timer clock freezes
    the counter at an unknowable level instead of forcing the pins low;
    the model takes the conservative side, which is also exactly what a
    never-enabled peripheral looks like -- the bug class this gate
    exists to catch."""
    dirword = read_word(GPIOE_ODR)
    if not (read_word(RCC_APB2ENR) & 0x1
            and read_word(RCC_AHB1ENR) & 0x10
            and read_word(TIM1_CR1) & 0x1
            and read_word(TIM1_BDTR) & 0x8000
            and dirword & 0x10):
        return 0, 0
    ccer = read_word(TIM1_CCER)
    duties = []
    for ccr, cce, in1, in2 in ((read_word(TIM1_CCR1), 0, 0, 1),
                               (read_word(TIM1_CCR2), 4, 2, 3)):
        a, b = (dirword >> in1) & 1, (dirword >> in2) & 1
        if not (ccer >> cce) & 1 or ccer == 0 or a == b:
            duties.append(0)          # output disabled / coast / brake
        else:
            mag = round(ccr * 1000 / PWM_ARR)
            duties.append(mag if a else -mag)
    return duties[0], duties[1]


QUAD = ((0, 0), (1, 0), (1, 1), (0, 1))   # forward cycle, +1 count/step
EDGE_TICK_S = 0.00002            # RunFor spacing so the event-driven
                                 # model sees each transition
# encoder pins: A/B ride the port pins in AF2 (PC6/7 -> TIM3,
# PD12/13 -> TIM4); gpio_model.cs gates them on MODER/AFRL, so the
# injection enters through the same pin map the firmware configures
ENC_PORTS = (("gpioPortC", 6, 7), ("gpioPortD", 12, 13))


def write_bench(ch, s) -> None:
    """Push one raw sensor frame through the IMU/ADC bench; BENCH_SEQ
    LAST -- its write is the data-ready latch."""
    w = ch.write_word
    w(BENCH, BENCH_MAGIC)
    for off, v in zip((0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20),
                      (*s.accel, *s.gyro, s.temp_raw)):
        w(BENCH + off, v & 0xFFFFFFFF)
    w(BENCH_FI, 0)
    w(BENCH_BATT, s.battery_mv & 0xFFFFFFFF)
    w(BENCH_SEQ, s.seq & 0xFFFFFFFF)   # LAST: the data-ready latch


def inject_encoder(ch, encoder_inputs, idx, injected,
                   wheel: int, target: int) -> None:
    """Move the firmware-visible count to `target` by quadrature edges
    on the encoder PORT pins (wheel 0 = PC6/PC7 -> TIM3). idx/injected
    are the caller's per-wheel state lists, mutated in place."""
    port, pin_a, pin_b = ENC_PORTS[wheel]
    receiver = encoder_inputs[wheel]
    delta = target - injected[wheel]
    if delta == 0:
        return
    step = 1 if delta > 0 else -1
    i = idx[wheel]
    for _ in range(abs(delta)):
        nxt = (i + step) % 4
        (a, b), (pa, pb) = QUAD[nxt], QUAD[i]
        if a != pa:
            receiver.OnGPIO(pin_a, bool(a))
        if b != pb:
            receiver.OnGPIO(pin_b, bool(b))
        ch.run(EDGE_TICK_S)
        i = nxt
    idx[wheel] = i
    injected[wheel] = target
    want = (0x8000 + target) & 0xFFFF
    cnt = ch.read_word(TIM3_CNT if wheel == 0 else TIM4_CNT) & 0xFFFF
    if cnt != want:
        raise RuntimeError(
            f"encoder edge loss on {port}: counter {cnt}, want "
            f"{want} -- the modeled path dropped a transition")


def send_line(ch, text: str) -> None:
    """Inject a command line at a pace the polled driver supports.

    The wire model (firmware/uart_model.cs) paces RX frames; a whole
    line injected back-to-back overruns the single data register
    exactly like a bursting module on the board (the uart_status.md
    BOARD labels), so bytes go out one coupling period apart."""
    from Antmicro.Renode.Peripherals.UART import IUART
    uart = IUART(ch.mach.sysbus.get_child("usart2").internal)
    for b in (text + "\n").encode():
        uart.WriteChar(b)
        ch.run_period()
