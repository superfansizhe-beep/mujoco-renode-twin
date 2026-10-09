/* Line-protocol helpers shared by the USART2 shells (twin, race, and
 * the bring-up ELF): freestanding integer formatting and the newline
 * RX assembler with the drop-on-overflow rule. Command DISPATCH stays
 * in each shell -- bring-up answers unknown lines with "err", the
 * production shells ignore them silently.
 */
#ifndef UART_PROTO_H
#define UART_PROTO_H

#include <stdint.h>

#define UP_LINE_MAX 31u

int up_seq_eq(const char *a, const char *b);
int up_fmt_u32(char *out, uint32_t v);   /* decimal, returns length */
int up_fmt_i32(char *out, int32_t v);    /* decimal with sign, returns length */
/* Feed one RX byte into the line buffer (sized UP_LINE_MAX + 1).
 * Returns 1 when a complete line sits in buf, NUL-terminated; *len is
 * then reset. An overflowed line is dropped byte by byte the same way. */
int up_feed(char *buf, uint32_t *len, char c);

#endif /* UART_PROTO_H */
