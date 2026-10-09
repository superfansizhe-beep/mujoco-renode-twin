#include <stdint.h>

#include "stm32f4_line.h"
#include "stm32f4_rcc.h"

#define GPIOF_BASE 0x40021400u
#define GPIO_MODER 0x00u
#define GPIO_PUPDR 0x0Cu
#define GPIO_IDR   0x10u

#define REG32(addr) (*(volatile uint32_t *)(addr))

void line_bar_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOF;
    /* PF0-PF7: inputs (00) with pull-ups (01) -- harmless behind the
     * module's push-pull drivers, required if its outputs are
     * open-collector; the real board's wiring settles it (race_status) */
    uint32_t pair = 0xFFFFu;             /* 2 bits x 8 pins */
    uint32_t moder = REG32(GPIOF_BASE + GPIO_MODER) & ~pair;
    REG32(GPIOF_BASE + GPIO_MODER) = moder;
    uint32_t pupdr = REG32(GPIOF_BASE + GPIO_PUPDR) & ~pair;
    REG32(GPIOF_BASE + GPIO_PUPDR) = pupdr | 0x5555u;
}

uint16_t line_bar_read(void)
{
    uint32_t raw = REG32(GPIOF_BASE + GPIO_IDR) & 0xFFu;
#if LINE_SENSORS_ACTIVE_LOW
    return (uint16_t)(~raw) & 0xFFu;     /* module pulls LOW on-tape */
#else
    return (uint16_t)raw;
#endif
}
