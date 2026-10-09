/* battery_bringup: prove the battery path through the real ADC
 * driver (firmware/stm32f4_adc.c) -- one conversion every 10 ms,
 * results echoed to the carved block for the gates. The Renode ADC
 * model quantizes the bench's battery millivolts against VREF; the
 * divider ratio itself is board-labeled (battery_status.md).
 */
#include <stdint.h>

#include "battery_bringup.h"
#include "stm32f4_adc.h"
#include "timer_monotonic.h"

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RES_MAGIC   REG32(BATTERY_RESULT_BASE + 0x00)
#define RES_SAMPLES REG32(BATTERY_RESULT_BASE + 0x04)
#define RES_MV      REG32(BATTERY_RESULT_BASE + 0x08)
#define RES_PIN_MV  REG32(BATTERY_RESULT_BASE + 0x0C)
#define RES_RAW     REG32(BATTERY_RESULT_BASE + 0x10)
#define RES_TIMEOUTS REG32(BATTERY_RESULT_BASE + 0x14)

#define RESULT_MAGIC 0x52544142u        /* "BATR" little-endian */
#define SAMPLE_PERIOD_US 10000u

int main(void)
{
    timer_monotonic_start();
    RES_MAGIC = RESULT_MAGIC;
    RES_SAMPLES = 0;
    RES_MV = 0;
    RES_PIN_MV = 0;
    RES_RAW = 0;
    RES_TIMEOUTS = 0;

    adc1_init();

    uint32_t mark = timer_ticks();
    for (;;) {
        if (timer_elapsed_us(mark) < SAMPLE_PERIOD_US)
            continue;
        mark += TIMER_US_TO_TICKS(SAMPLE_PERIOD_US);
        RES_SAMPLES++;
        uint16_t raw;
        if (adc1_read(ADC_CH_VBAT, &raw)) {
            RES_TIMEOUTS++;
            continue;                        /* conversion lost: keep the
                                              * last good sample */
        }
        /* raw == 0 is a VALID conversion (sense at ground): publish it */
        RES_RAW = raw;
        RES_PIN_MV = (uint32_t)raw * ADC_VREF_MV / 4095u;
        RES_MV = RES_PIN_MV * VBAT_DIVIDER;
    }
}
