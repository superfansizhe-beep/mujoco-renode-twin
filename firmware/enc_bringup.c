/* enc_bringup: prove quadrature acquisition through the real timer
 * encoder interface (firmware/stm32f4_encoder.c). Polls both counters
 * every 1 ms, integrates positions through the wrap-correct modular
 * delta, and reports raw counts + integrated positions to a fixed SRAM
 * block. No motors are touched anywhere -- same discipline as
 * imu_bringup. Wrap/underflow are sim-gated through enc_model.cs;
 * physical pin routing remains a BOARD label in enc_status.md.
 */
#include <stdint.h>

#include "enc_bringup.h"
#include "stm32f4_encoder.h"
#include "timer_monotonic.h"

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RES_MAGIC   REG32(ENC_RESULT_BASE + 0x00)
#define RES_SAMPLES REG32(ENC_RESULT_BASE + 0x04)
#define RES_POS_L   REG32(ENC_RESULT_BASE + 0x08)
#define RES_POS_R   REG32(ENC_RESULT_BASE + 0x0C)
#define RES_CNT_L   REG32(ENC_RESULT_BASE + 0x10)
#define RES_CNT_R   REG32(ENC_RESULT_BASE + 0x14)

#define RESULT_MAGIC 0x52434E45u        /* "ENCR" little-endian */
#define POLL_PERIOD_US 1000u

int main(void)
{
    timer_monotonic_start();
    RES_MAGIC = RESULT_MAGIC;
    RES_SAMPLES = 0;
    RES_POS_L = 0;
    RES_POS_R = 0;
    RES_CNT_L = 0;
    RES_CNT_R = 0;

    encoder_init();

    uint32_t mark = timer_ticks();
    uint16_t last_l = encoder_cnt_left();
    uint16_t last_r = encoder_cnt_right();
    int32_t pos_l = 0, pos_r = 0;
    for (;;) {
        if (timer_elapsed_us(mark) < POLL_PERIOD_US)
            continue;
        mark += TIMER_US_TO_TICKS(POLL_PERIOD_US);
        uint16_t cl = encoder_cnt_left();
        uint16_t cr = encoder_cnt_right();
        pos_l += encoder_delta16(cl, last_l);
        pos_r += encoder_delta16(cr, last_r);
        last_l = cl;
        last_r = cr;
        RES_SAMPLES++;
        RES_POS_L = (uint32_t)pos_l;
        RES_POS_R = (uint32_t)pos_r;
        RES_CNT_L = cl;
        RES_CNT_R = cr;
    }
}
