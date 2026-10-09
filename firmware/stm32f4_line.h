/* 8-channel IR line bar (YB-MX04-2.0 class) on the 8xIO interface:
 * PF0-PF7 digital inputs, bit i = bar sensor i ON TAPE, i growing with
 * +x -- the bar frame race/main.c::lateral_error consumes.
 *
 * Module polarity: most IR boards pull the output LOW on detection, so
 * the read inverts; if the purchased board differs, flip
 * LINE_SENSORS_ACTIVE_LOW (one place). The 5 V module's output high
 * lands on F4 FT pins -- the level/series-resistor check is the
 * arrival-day procedure in firmware/race_status.md.
 */
#ifndef STM32F4_LINE_H
#define STM32F4_LINE_H

#include <stdint.h>
#include "line_config.h"

#define LINE_SENSORS LINE_CFG_COUNT
#define LINE_SENSORS_ACTIVE_LOW LINE_CFG_ACTIVE_LOW

void line_bar_init(void);
uint16_t line_bar_read(void);        /* bit i = sensor i on-tape */

#endif /* STM32F4_LINE_H */
