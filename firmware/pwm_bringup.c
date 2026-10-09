/* pwm_bringup: prove the motor PWM path without any motor attached.
 * The harness posts signed permille duties; the firmware runs them
 * through firmware/stm32f4_pwm.c (TIM1 20 kHz + TB6612 direction
 * pins) and echoes the applied CCR / direction word. The waveform's
 * average duty is measured from the pins by the harness; the
 * electrical layer is the BOARD label (pwm_status.md).
 */
#include <stdint.h>

#include "pwm_bringup.h"
#include "stm32f4_pwm.h"
#include "timer_monotonic.h"

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RES_MAGIC  REG32(PWM_RESULT_BASE + 0x00)
#define RES_TICKS  REG32(PWM_RESULT_BASE + 0x04)
#define RES_DUTY_L REG32(PWM_RESULT_BASE + 0x08)
#define RES_DUTY_R REG32(PWM_RESULT_BASE + 0x0C)
#define RES_CCR1   REG32(PWM_RESULT_BASE + 0x10)
#define RES_CCR2   REG32(PWM_RESULT_BASE + 0x14)
#define RES_DIR    REG32(PWM_RESULT_BASE + 0x18)

#define CMD_BASE    (PWM_RESULT_BASE + 0x40)
#define CMD_MAGIC   REG32(CMD_BASE + 0x00)
#define CMD_DUTY_L  REG32(CMD_BASE + 0x04)
#define CMD_DUTY_R  REG32(CMD_BASE + 0x08)

#define RESULT_MAGIC 0x524D5750u        /* "PWMR" little-endian */
#define CMD_MAGIC_VALUE 0x434D5750u     /* "PWMC" */
#define TICK_PERIOD_US 1000u

int main(void)
{
    timer_monotonic_start();
    RES_MAGIC = RESULT_MAGIC;
    RES_TICKS = 0;
    RES_DUTY_L = 0;
    RES_DUTY_R = 0;
    RES_CCR1 = 0;
    RES_CCR2 = 0;
    RES_DIR = 0;

    pwm_motor_init();
    pwm_motor_set(0, 0);

    uint32_t mark = timer_ticks();
    int32_t duty_l = 0, duty_r = 0;
    for (;;) {
        if (timer_elapsed_us(mark) < TICK_PERIOD_US)
            continue;
        mark += TIMER_US_TO_TICKS(TICK_PERIOD_US);
        if (CMD_MAGIC == CMD_MAGIC_VALUE) {
            duty_l = (int32_t)CMD_DUTY_L;
            duty_r = (int32_t)CMD_DUTY_R;
        }
        pwm_motor_set(duty_l, duty_r);
        RES_TICKS++;
        RES_DUTY_L = (uint32_t)duty_l;
        RES_DUTY_R = (uint32_t)duty_r;
        RES_CCR1 = pwm_motor_ccr1();
        RES_CCR2 = pwm_motor_ccr2();
        RES_DIR = pwm_motor_dir_word();
    }
}
