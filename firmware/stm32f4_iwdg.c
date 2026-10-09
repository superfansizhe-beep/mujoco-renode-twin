#include "stm32f4_iwdg.h"

#define IWDG_BASE 0x40003000u
#define IWDG_KR   (*(volatile uint32_t *)(IWDG_BASE + 0x00))
#define IWDG_PR   (*(volatile uint32_t *)(IWDG_BASE + 0x04))
#define IWDG_RLR  (*(volatile uint32_t *)(IWDG_BASE + 0x08))

/* LSI 32 kHz / 32 (PR=3) -> 1 kHz ticks, ~300 ms to reset. The real
 * LSI carries a wide +-tolerance (RM: ~17-47 kHz) -- this is a
 * last-resort guard, not a timer, and the exact board timeout is the
 * arrival-day measurement (race_status.md). */
#define IWDG_PR_DIV32     3u
#define IWDG_RELOAD_300MS 299u

void iwdg_start(void)
{
    IWDG_KR = 0x5555u;               /* unlock PR/RLR */
    IWDG_PR = IWDG_PR_DIV32;
    IWDG_RLR = IWDG_RELOAD_300MS;
    IWDG_KR = 0xCCCCu;               /* start the counter */
    IWDG_KR = 0xAAAAu;               /* first reload */
}

void iwdg_kick(void)
{
    IWDG_KR = 0xAAAAu;
}
