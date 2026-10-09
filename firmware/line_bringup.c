/* GPIO line-driver + production observation/recovery-law bring-up.
 * The harness drives the eight physical input receivers. No motor init. */
#include <stdint.h>
#include "line_bringup.h"
#include "stm32f4_line.h"
#include "timer_monotonic.h"
#include "core/line.h"

#define WORD(a) (*(volatile uint32_t *)(a))
#define FLOAT(a) (*(volatile float *)(a))
#define RES(i) WORD(LINE_RESULT_BASE + 4u * (i))

int main(void)
{
    timer_monotonic_start();
    line_bar_init();
    line_tracker_t tracker = {0};
    line_endpoint_t endpoint = {0};
    uint32_t previous = 0;
    for (unsigned i = 0; i < 12; ++i) RES(i) = 0;
    RES(0) = LINE_RESULT_MAGIC;
    for (;;) {
        uint32_t seq = WORD(LINE_COMMAND_BASE);
        if (seq == previous) continue;
        uint32_t flags = WORD(LINE_COMMAND_BASE + 4);
        if (flags & 1u) {
            tracker = (line_tracker_t){0};
            endpoint = (line_endpoint_t){0};
        }
        uint16_t bits = line_bar_read();
        line_observation_t o = line_observe(bits);
        float error = line_track(&tracker, o, FLOAT(LINE_COMMAND_BASE + 8),
                                 0.005f, (flags & 2u) != 0);
        RES(2) = bits;
        RES(3) = o.status;
        RES(4) = o.count | ((uint32_t)o.groups << 8) | ((uint32_t)o.centered << 16);
        FLOAT(LINE_RESULT_BASE + 20) = o.error;
        FLOAT(LINE_RESULT_BASE + 24) = error;
        RES(7) = tracker.source;
        RES(8) = WORD(0x40021410u) & 0xFFu;
        FLOAT(LINE_RESULT_BASE + 36) = tracker.age;
        RES(10) = line_endpoint_update(&endpoint, o, (flags & 4u) != 0,
                                      (flags & 8u) != 0, 0.005f);
        RES(11) = endpoint.white_cycles;
        previous = seq;
        RES(1) = seq;                 /* publish coherent results last */
    }
}
