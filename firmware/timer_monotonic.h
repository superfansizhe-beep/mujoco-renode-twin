/* Free-running microsecond clock on TIM2, shared by every firmware ELF
 * (starvation deadline, I2C timeouts, any future pacing). The prescaler
 * stays at its reset value 0: the counter ticks at the timer clock, i.e.
 * TIMER_TICKS_PER_US ticks per microsecond.
 *
 * The constant matches BOTH worlds by construction: the real F407 boots
 * on the 16 MHz HSI (APB1 /1 -> TIM2 x1) and nothing in this firmware
 * reconfigures clocks yet, and stm32f407zg.repl pins its whole clock
 * tree to the same HSI reset state because Renode's RCC does not gate.
 * When the clock-init milestone moves the tree to 168 MHz, the repl
 * frequency and this constant move together.
 *
 * Timestamps are RAW TICKS; only timer_elapsed_us converts to
 * microseconds, after the modular subtraction. Absolute pacing marks
 * advance in ticks through TIMER_US_TO_TICKS.
 */
#ifndef TIMER_MONOTONIC_H
#define TIMER_MONOTONIC_H

#include <stdint.h>

#define TIMER_TICKS_PER_US 16u
#define TIMER_US_TO_TICKS(us) ((us) * TIMER_TICKS_PER_US)

void timer_monotonic_start(void);
uint32_t timer_ticks(void);
/* microsecond delta from a raw-tick timestamp: subtract modulo 2^32
 * ticks first, then divide -- correct across the ~268 s wrap */
uint32_t timer_elapsed_us(uint32_t since_ticks);

#endif /* TIMER_MONOTONIC_H */
