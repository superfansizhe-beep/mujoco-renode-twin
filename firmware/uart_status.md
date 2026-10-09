# UART bring-up status -- SIM vs BOARD

One driver (firmware/stm32f4_uart.c), one bring-up ELF
(firmware/uart_bringup.c). Pin contract: the Bluetooth module rides
**USART2 = PA2 (MCU TX) / PA3 (MCU RX), AF7**, 115200 8N1 (BRR 139 at
the 16 MHz HSI tree, -0.08% error), PA3 pulled up so an unplugged
module idles high. The module itself is unselected hardware: its
wiring, its logic levels and its OWN AT-configured baud are board
labels below.

The sim's serial-link story, with what THIS Renode actually supports:

| facility | textbook command | reality in Renode 1.17.0 portable |
| --- | --- | --- |
| UART model | `UART.STM32_UART` | USART2 uses `UARTWireSim` ([uart_model.cs](uart_model.cs)): the stock register model plus baud-paced frames, TXE/TC hold-off and ORE; two private repl timers (uartTxBaud/uartRxBaud, 16 MHz) time the wire; other UARTs remain stock |
| wireless far end | `sysbus.uart CreateTcpServerTerminal 4545` | **does not exist** -- the UART exposes no terminal command at all (probed; usart2-introspect.log) |
| debugger | `machine EnableGDB 3333` | named `machine StartGdbServer`; the in-process pyrenode3 monitor has NO extension commands (even `help` shows none), but the .NET method is callable directly |
| CI "far end" | -- | pyrenode3 `TerminalTester`: `WriteLine` injects RX (the only tester path that reaches RXNE; its per-byte `WriteChar` feeds only the tester's own matcher), `NextLine` consumes TX |
| hands-on far end | -- | [twin/uart_session.py](../twin/uart_session.py): TCP server bridged to the UART's `CharReceived` event (TX; fires on the CPU thread, so the delegate only queues) + `tt.WriteLine` (RX); `--gdb N` starts the GDB server |

Probing trail (output/uart-milestone/, untracked evidence): probe 1
mis-wrote the CR1 pattern as 0x200A and "concluded" the model drops the
RE bit; the runtime gate's exact 0x200C readback corrected that -- the
model stores UE|TE|RE fine. Two structural findings stand: no terminal
command anywhere (full renode.exe monitor introspected too), and
TerminalTester.WriteChar being matcher-only. A TX-delegate that calls
send() directly kills the emulation when the socket dies -- the
exception propagates out of the CPU thread -- hence the queue-then-drain
bridge.

## SIM -- verified (tests/test_firmware_uart.py, Renode 1.17.0)

| gate | test |
| --- | --- |
| config contract (APB1ENR.USART2EN, AHB1ENR.GPIOAEN, PA2/PA3 AF+speed+pull nibbles, AFRL=AF7, BRR=139, CR1=UE\|TE\|RE exact readback) at runtime | `test_config_contract_is_written_at_runtime` |
| banner "UART-UP 115200 8N1" then "tick N" telemetry at the 100 ms idle cadence, byte-counted | `test_banner_then_periodic_telemetry` |
| ping -> pong round trip through the driver, rx/tx byte deltas and the "ping" command tag exact | `test_ping_pong_round_trip_through_the_driver` |
| `stat` line cross-checks against the result words (tx grows by exactly the stat line's own bytes) | `test_stat_cross_checks_the_result_words` |
| unknown command answers `err`, still dispatched | `test_unknown_command_answers_err` |
| a round trip pays both directions' wire frames (~87 us each at 115200 8N1) | `test_round_trip_pays_the_wire_time` (TestUARTWire) |
| the frame duration follows the fixed-point BRR (139 -> ~87 us, 1667 -> ~1.04 ms; a wrong BRR changes the wire) | `test_wrong_brr_stretches_the_wire` (TestUARTOverrun) |
| a byte completing over an unread RXNE is lost, ORE latches, SR-then-DR clears it, reception resumes | `test_overrun_drops_the_byte_and_latches_ore` (TestUARTOverrun) |
| missing GPIOA/USART2 enable discards configuration; clock-disabled wire input is dropped and recovers | [rcc_status.md](rcc_status.md), `tests.test_firmware_rcc` |
| results block clears the imu trace end and the fault words; BRR derives from the documented baud; driver keeps writing RE | `TestUARTLayout` |
| GDB server opens + accepts a connection in-process (`Machine.StartGdbServer`) | `test_gdb_server_opens_the_st_link_equivalent_port` |
| the hands-on session end to end: TCP accept, banner, ping->pong, real arm-none-eabi-gdb handshake with a breakpoint hit at `uart2_getc` | output/uart-milestone/interactive-probe.log (ALL PASS) |

## BOARD -- pending hardware (procedure for the on-arrival day)

| gate | procedure |
| --- | --- |
| module wiring | PA2 -> module RX, PA3 <- module TX, common ground; confirm the module board is 3.3 V logic (most HC-05/JDY carriers are; if a 5 V board, level-shift PA2) |
| module baud | the module's AT default is usually 9600 -- configure it to 115200 8N1, or change `UART2_BAUDRATE`/`UART2_BRR` together (the layout test pins the pair) |
| wire pacing | [uart_model.cs](uart_model.cs) now paces the wire in SIM (gates above); on the board scope a frame at 115200 8N1 (~87 us) and confirm the 1 ms per-byte TXE deadline holds with interrupts disabled for a full line. SIM caveat: RXNE surfaces ~180 us AFTER the frame completes (a stock-model deferral inside `WriteChar`, conservative -- never faster than silicon) |
| frame fidelity | scope PA2 for 115200 8N1 start/stop framing if garbage arrives; the model times whole frames, it does not check bit-level framing |
| interactive session | same firmware, real module instead of the TCP bridge: `python -m twin.uart_session` proves the protocol; on the board just wire the module and the bring-up lines appear on the phone/PC side |

Follow-on (not this milestone): ~~wire telemetry TX / command RX into
firmware/twin/main.c~~ -- landed same day, see below.
~~The full-scenario integration round (race through the peripheral
backend)~~ -- landed the same evening: race v3 carries the link through
the shared core firmware/uart_proto.{c,h} (integer formatting + the RX
line assembler, extracted from the twin shell; bring-up adopted the
identical helpers), gates and labels in [race_status.md](race_status.md).

## Production ELF integration (firmware/twin/main.c v3, 2026-09-29)

The balance shell now carries the link through the same driver. Line
protocol, \n-terminated:

| line | meaning |
| --- | --- |
| `UP` | boot complete (after all inits, right before the loop) |
| `T <seq> <duty> <batt_mv> <ang_mdeg>` | telemetry at 10 Hz (every 20th 200 Hz cycle) and as the `stat` answer; seq = the mailbox heartbeat, duty = permille the PWM holds, ang = filtered tilt vs VERTICAL (at rest it reads the trim, ~-16700 mdeg -- NOT the error-vs-reference) |
| `starved` / `resume` | supervision transitions: no fresh IMU sample for 150 ms / first fresh sample after |
| `pong` | the `ping` answer; unknown lines are IGNORED silently |

The outer loop no longer blocks inside one 150 ms `mpu6050_read`:
data-ready is polled in 2 ms slices so `uart_pump()` runs between
samples (RX polled every slice; commands answer within ~2-7 ms). The
starvation rule MOVED TO THE SHELL -- same 150 ms window from the last
fresh sample, same zero-duty / heartbeat-freeze / resume semantics; the
e2e (kick, A/B vs the stub, heartbeat exactly 200/200) passes unchanged
on the restructured ELF (25/25 in tests/test_twin.py).

| gate | test |
| --- | --- |
| telemetry + commands + starved/resume on the live balance loop (through fw.uart_log, the backend's pre-boot TX tap) | `test_production_elf_talks_on_the_serial_link` (tests/test_twin.py) |
| the hands-on session against the production ELF (`--bench-imu` feeds the AT-TRIM rest frame): UP, 10 Hz telemetry with duty 0 at trim, ping->pong | output/uart-milestone/session-balance-probe.log (ALL PASS) |

Renode quirks this cost (both in output/uart-milestone/ probes): a UART
receiver attached AFTER the machine has executed crashes Renode's bus
(ObjectDisposedException; every later sysbus read dies) -- the backend
attaches its tap inside reset(), pre-first-execution; and the
TerminalTester's waiting reads (NextLine/IsIdle) hang forever on an
empty buffer (virtual-time timeout, nobody advancing virtual time) --
assert against the raw tap instead, the tester is write-only.

## BOARD labels specific to the production shell (on-arrival day)

- polled single-byte RX: bytes must arrive spaced >= ~2 ms -- human /
  typed pacing and one-line commands are fine; a module that bursts a
  whole line back-to-back at 115200 WILL lose bytes -- the sim now
  reproduces this (the wire model's single data register overruns, so
  the harness injects commands one byte per coupling period:
  `backend.send_line`). The IRQ-RX follow-up (vector slot exists in
  startup.c) is the fix, decide after measuring the real module's
  pacing
- each telemetry line is ~24 bytes = ~2.1 ms of TXE-blocking wire time
  at 115200, once per 100 ms -- the sim pays this too now (a
  misconfigured slow BRR does not merely slow the link: the firmware's
  own tick transmission blocks RX past the single data register and
  interactive commands are lost -- wrong config fails in sim, the
  wrong way the board would fail); starvation (150 ms) is far away

