#include "timer_monotonic.h"
#include "stm32f4_rcc.h"

#define TIM2_BASE 0x40000000u
#define TIM2_CR1  (*(volatile uint32_t *)(TIM2_BASE + 0x00))
#define TIM2_CNT  (*(volatile uint32_t *)(TIM2_BASE + 0x24))

void timer_monotonic_start(void)
{
    /* the clock enable comes first: on silicon TIM2 is dead until
     * APB1ENR.TIM2EN (the repl stores the bit but gates nothing) */
    RCC_APB1ENR |= RCC_APB1ENR_TIM2EN;
    /* CEN only: upcounter, free-running, no interrupts (this firmware
     * family polls everything) */
    TIM2_CR1 = 1u;
}

uint32_t timer_ticks(void)
{
    return TIM2_CNT;
}

uint32_t timer_elapsed_us(uint32_t since_ticks)
{
    /* subtract in the RAW tick domain, THEN scale: the counter wraps at
     * 2^32 ticks (~268 s at 16 MHz), and dividing the operands first
     * would shrink the modulus to 2^28 us and turn a 32 us delta across
     * the wrap into ~4.0e9 us (review 2026-09-29, finding 5) */
    return (uint32_t)(TIM2_CNT - since_ticks) / TIMER_TICKS_PER_US;
}
