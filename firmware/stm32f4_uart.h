/* USART2 polled driver -- the Bluetooth-module link.
 *
 * Pin contract (our allocation):
 *   BT_TX (module TX -> MCU RX) = PA3, AF7, pull-up (idles high when the
 *                                 module is unplugged)
 *   BT_RX (module RX <- MCU TX) = PA2, AF7, push-pull
 * (the module itself is unselected hardware: its wiring and its OWN
 * default baud/AT config are board labels, firmware/uart_status.md)
 *
 * 115200 8N1 at the 16 MHz HSI reset tree: PCLK1 16 MHz / (16 x 115200)
 * = 8.68 -> BRR mantissa 8, fraction 11 = 139 (0x8B), -0.08% baud error.
 * A future clock-tree change must move this together with the .repl
 * timer frequencies (same rule as the clock-init note there).
 *
 * Renode model note: usart2 is UARTWireSim (firmware/uart_model.cs,
 * 2026-09-30) -- the stock register model plus baud-paced frames
 * (~87 us each here), TXE/TC hold-off while a frame is queued, and ORE
 * on a byte completing over an unread RXNE. Gates and the remaining
 * board labels (bit-level framing, the ~180 us stock RXNE deferral):
 * firmware/uart_status.md. The per-byte deadline below is what the
 * driver can actually rely on, in sim and on the board alike.
 */
#ifndef STM32F4_UART_H
#define STM32F4_UART_H

#include <stdint.h>

#define UART2_BAUDRATE 115200u
#define UART2_BRR      139u    /* 16 MHz / (16 x 115200) rounded */

void uart2_init(void);
/* Status separate from the data, like the ADC contract: 0 ok, -1 the
 * flag did not arrive within the deadline (per BYTE, not per burst). */
int uart2_putc(char c, uint32_t timeout_us);
int uart2_write(const char *buf, uint32_t len, uint32_t timeout_us);
/* timeout_us 0 = single nonblocking poll (bring-up line assembly). */
int uart2_getc(char *out, uint32_t timeout_us);
/* wait for TC: the last byte fully left the shifter (before sleep or a
 * disabled peripheral -- DR-empty alone does not mean the wire is quiet) */
int uart2_flush(uint32_t timeout_us);

#endif /* STM32F4_UART_H */
