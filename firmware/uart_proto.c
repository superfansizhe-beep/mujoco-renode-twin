#include "uart_proto.h"

int up_seq_eq(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

int up_fmt_u32(char *out, uint32_t v)
{
    char tmp[10];
    int n = 0;
    do {
        tmp[n++] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v);
    for (int i = 0; i < n; i++)
        out[i] = tmp[n - 1 - i];
    return n;
}

int up_fmt_i32(char *out, int32_t v)
{
    if (v < 0) {
        out[0] = '-';
        return 1 + up_fmt_u32(out + 1, (uint32_t)-v);
    }
    return up_fmt_u32(out, (uint32_t)v);
}

int up_feed(char *buf, uint32_t *len, char c)
{
    if (c == '\n' || c == '\r') {
        buf[*len] = '\0';
        *len = 0;
        return 1;
    }
    if (*len < UP_LINE_MAX) {
        buf[(*len)++] = c;
    } else {
        *len = 0;               /* overflowed: drop the line */
    }
    return 0;
}
