/* uart_bringup: prove the Bluetooth-link serial path through the real
 * USART2 driver (firmware/stm32f4_uart.c). Line protocol, \n-terminated:
 *
 *   firmware -> world   "UART-UP 115200 8N1" banner, then a "tick <n>"
 *                      telemetry line every 100 ms the input stays idle
 *   world -> firmware  "ping" -> "pong", "stat" -> "tx=.. rx=.. cmds=..
 *                      ticks=..", anything else -> "err"
 *
 * The Renode gate drives this through a TerminalTester (CI) or a TCP
 * terminal (the hands-on "wireless other end"); the results block
 * mirrors the counters so sysbus reads can cross-check both ports.
 */
#include <stdint.h>

#include "uart_bringup.h"
#include "stm32f4_uart.h"
#include "uart_proto.h"
#include "timer_monotonic.h"

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RES_MAGIC   REG32(UART_RESULT_BASE + 0x00)
#define RES_TX      REG32(UART_RESULT_BASE + 0x04)
#define RES_RX      REG32(UART_RESULT_BASE + 0x08)
#define RES_CMDS    REG32(UART_RESULT_BASE + 0x0C)
#define RES_TICKS   REG32(UART_RESULT_BASE + 0x10)
#define RES_LAST    REG32(UART_RESULT_BASE + 0x14)

#define RESULT_MAGIC 0x54524155u        /* "UART" little-endian */
#define TELEM_PERIOD_US 100000u
#define TX_TIMEOUT_US 1000u             /* a byte is ~87 us at 115200 */
#define LINE_MAX 31u

/* freestanding build: no libc string functions, tiny local ones */
static uint32_t slen(const char *s)
{
    uint32_t n = 0;
    while (s[n])
        n++;
    return n;
}

/* "key=value" piece; returns the new end */
static char *put_kv(char *p, const char *key, uint32_t v)
{
    while (*key)
        *p++ = *key++;
    p += up_fmt_u32(p, v);
    return p;
}

/* first <=4 chars packed little-endian, the gate's "last command" tag */
static uint32_t pack_tag(const char *s, uint32_t len)
{
    uint32_t tag = 0;
    for (uint32_t i = 0; i < len && i < 4; i++)
        tag |= (uint32_t)(uint8_t)s[i] << (8 * i);
    return tag;
}

static void emit(const char *s)
{
    uint32_t n = slen(s);
    RES_TX += n;
    uart2_write(s, n, TX_TIMEOUT_US);
}

int main(void)
{
    timer_monotonic_start();
    RES_MAGIC = RESULT_MAGIC;
    RES_TX = 0;
    RES_RX = 0;
    RES_CMDS = 0;
    RES_TICKS = 0;
    RES_LAST = 0;

    uart2_init();
    emit("UART-UP 115200 8N1\n");

    char line[LINE_MAX + 1];
    uint32_t len = 0;
    uint32_t mark = timer_ticks();

    for (;;) {
        char c;
        if (uart2_getc(&c, 0) == 0) {
            RES_RX++;
            if (c == '\n' || c == '\r') {
                line[len] = '\0';
                if (len > 0) {
                    RES_LAST = pack_tag(line, len);
                    RES_CMDS++;
                    if (up_seq_eq(line, "ping")) {
                        emit("pong\n");
                    } else if (up_seq_eq(line, "stat")) {
                        char buf[80], *p = buf;
                        p = put_kv(p, "tx=", RES_TX);
                        *p++ = ' ';
                        p = put_kv(p, "rx=", RES_RX);
                        *p++ = ' ';
                        p = put_kv(p, "cmds=", RES_CMDS);
                        *p++ = ' ';
                        p = put_kv(p, "ticks=", RES_TICKS);
                        *p++ = '\n';
                        *p = '\0';
                        emit(buf);
                    } else {
                        emit("err\n");
                    }
                }
                len = 0;
            } else if (len < LINE_MAX) {
                line[len++] = c;
            } else {
                len = 0;              /* overflowed: drop the line */
            }
            mark = timer_ticks();       /* traffic defers telemetry */
            continue;
        }
        if (timer_elapsed_us(mark) >= TELEM_PERIOD_US) {
            mark += TIMER_US_TO_TICKS(TELEM_PERIOD_US);
            RES_TICKS++;
            char buf[16];
            int n = up_fmt_u32(buf, RES_TICKS);
            buf[n++] = '\n';
            buf[n] = '\0';
            emit("tick ");
            emit(buf);
        }
    }
}
