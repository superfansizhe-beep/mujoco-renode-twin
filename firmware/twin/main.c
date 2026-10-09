/* Balance-bot twin firmware v3 -- PERIPHERAL-DRIVEN + SERIAL LINK.
 * The control law is still ../core/balance.c (one source with the race
 * shell); v3 keeps everything from v2 and adds the USART2 link the
 * Bluetooth module rides (same driver the bring-up gate proved):
 *
 *   loop     the outer loop no longer blocks inside one 150 ms read --
 *            data-ready is polled in 2 ms slices so the UART is pumped
 *            between samples; the starvation rule MOVES TO THE SHELL,
 *            measured from the last fresh sample, same 150 ms window,
 *            same zero-duty / heartbeat-freeze / resume semantics;
 *   link TX  "T <seq> <duty> <batt_mv> <ang_mdeg>" every 20 cycles
 *            (10 Hz at the 200 Hz coupling), plus "UP" at boot and
 *            "starved"/"resume" on supervision transitions;
 *   link RX  line protocol: "ping" -> "pong", "stat" -> one telemetry
 *            line now; unknown lines ignored silently (a wireless link
 *            must not be invited to chatter). Polled single-byte RX:
 *            bytes must arrive spaced >= ~2 ms (human/typed pacing) --
 *            burst links need the IRQ RX follow-up (uart_status.md).
 *
 * The mailbox window stays the firmware-owned STATUS mirror (magic +
 * duty echo + heartbeat); the firmware never READS a sensor from it.
 */

#include <stdint.h>

#include "mailbox.h"
#include "../timer_monotonic.h"
#include "../core/balance.h"
#include "../stm32f4_i2c.h"
#include "../mpu6050.h"
#include "../stm32f4_encoder.h"
#include "../stm32f4_adc.h"
#include "../stm32f4_pwm.h"
#include "../stm32f4_uart.h"
#include "../uart_proto.h"
#include "../stm32f4_iwdg.h"

/* IMU silence deadline, now measured by the shell from the last fresh
 * data-ready (the read itself only waits one slice) */
#define STARVE_TIMEOUT_US 150000u
#define IMU_SLICE_US 2000u            /* data-ready poll slice */
/* battery resample cadence; a failed conversion keeps the last good mV */
#define BATT_PERIOD_US 10000u
#define REINIT_TRIES 3u
#define TELEM_EVERY_CYCLES 20u        /* 200 Hz / 20 = 10 Hz on the link */
#define TX_TIMEOUT_US 1000u           /* a byte is ~87 us at 115200 */
#define RX_DRAIN_MAX 32u              /* control first: bounded per pump */

static char rxline[UP_LINE_MAX + 1];
static uint32_t rxlen;

/* what the telemetry line reports; updated once per control cycle */
static uint32_t cur_seq;
static int32_t cur_duty;
static uint32_t cur_batt_mv;
static int32_t cur_ang_mdeg;

static void emit(const char *s, uint32_t n)
{
    uart2_write(s, n, TX_TIMEOUT_US);
}

static void telemetry(void)
{
    char b[48];
    int n = 0;
    b[n++] = 'T';
    b[n++] = ' ';
    n += up_fmt_u32(b + n, cur_seq);
    b[n++] = ' ';
    n += up_fmt_i32(b + n, cur_duty);
    b[n++] = ' ';
    n += up_fmt_u32(b + n, cur_batt_mv);
    b[n++] = ' ';
    n += up_fmt_i32(b + n, cur_ang_mdeg);
    b[n++] = '\n';
    emit(b, (uint32_t)n);
}

static void uart_pump(void)
{
    for (uint32_t i = 0; i < RX_DRAIN_MAX; i++) {
        char c;
        if (uart2_getc(&c, 0))
            return;
        if (up_feed(rxline, &rxlen, c)) {
            if (up_seq_eq(rxline, "ping"))
                emit("pong\n", 5);
            else if (up_seq_eq(rxline, "stat"))
                telemetry();
        }
    }
}

int main(void)
{
    timer_monotonic_start();
    iwdg_start();                     /* ~300 ms last-resort guard: a
                                         hung loop resets coasted */
    TWIN_MAGIC = 0;                      /* heartbeat silent until up */

    i2c1_init();
    encoder_init();
    adc1_init();
    pwm_motor_init();
    uart2_init();
    pwm_motor_set(0, 0);                 /* motors never arm before the
                                            IMU is alive and talking */

    unsigned tries = 0;
    while (mpu6050_init(MPU_ADDR_GND) != MPU_OK) {
        if (++tries > REINIT_TRIES)
            for (;;)                     /* dead IMU halts here: no
                                            heartbeat, no drive */
                ;
    }

    balance_hold_t law;
    balance_hold_init(&law);

    TWIN_MAGIC = TWIN_MAILBOX_MAGIC;     /* status mirror: we are up */
    TWIN_DUTY_L = 0;
    TWIN_DUTY_R = 0;
    TWIN_FW_SEQ = 0;
    emit("UP\n", 3);

    balance_sample_t s;
    s.ay = 0; s.az = 0; s.gx = 0;
    s.enc_l = 0; s.enc_r = 0; s.batt_mv = 0;
    uint32_t mv;
    if (battery_read_mv(&mv) == 0)       /* the law derates by battery:
                                            never let cycle 1 see 0 mV */
        s.batt_mv = (uint16_t)mv;

    uint16_t last_l = encoder_cnt_left();
    uint16_t last_r = encoder_cnt_right();
    uint32_t batt_mark = timer_ticks();
    uint32_t last_fresh = timer_ticks();
    uint8_t starved = 1;                 /* nothing fresh yet */
    uint32_t cycles = 0;

    for (;;) {
        iwdg_kick();                 /* every slice: the watchdog
                                        guards a hung loop, not a
                                        data-starved one */
        mpu_sample_t m;
        mpu_status_t st = mpu6050_read(MPU_ADDR_GND, &m, IMU_SLICE_US);
        uart_pump();
        if (st == MPU_ERR_TIMEOUT) {
            /* no fresh sample this slice: if the 150 ms window since
             * the last fresh one is up, zero the duty ONCE, freeze the
             * heartbeat (no cycle) and say so; the next fresh sample
             * resumes everything */
            if (!starved && timer_elapsed_us(last_fresh) >= STARVE_TIMEOUT_US) {
                starved = 1;
                pwm_motor_set(0, 0);
                TWIN_DUTY_L = 0;
                TWIN_DUTY_R = 0;
                emit("starved\n", 8);
            }
            continue;
        }
        if (st != MPU_OK) {
            /* transport failure (NACK/flag timeout): motors off,
             * bounded re-init; a bus that stays dead halts frozen */
            pwm_motor_set(0, 0);
            unsigned i;
            for (i = 0; i < REINIT_TRIES; i++)
                if (mpu6050_init(MPU_ADDR_GND) == MPU_OK)
                    break;
            if (i == REINIT_TRIES)
                for (;;)
                    ;
            continue;
        }
        if (starved) {
            starved = 0;
            emit("resume\n", 7);
        }
        last_fresh = timer_ticks();
        s.ay = m.ay;
        s.az = m.az;
        s.gx = m.gx;

        uint16_t cl = encoder_cnt_left();
        uint16_t cr = encoder_cnt_right();
        s.enc_l += encoder_delta16(cl, last_l);
        s.enc_r += encoder_delta16(cr, last_r);
        last_l = cl;
        last_r = cr;

        if (timer_elapsed_us(batt_mark) >= BATT_PERIOD_US) {
            batt_mark += TIMER_US_TO_TICKS(BATT_PERIOD_US);
            if (battery_read_mv(&mv) == 0)
                s.batt_mv = (uint16_t)mv;
        }

        int duty = balance_hold_step(&law, &s);
        pwm_motor_set(duty, duty);
        TWIN_DUTY_L = (int16_t)duty;     /* status echo: what PWM holds */
        TWIN_DUTY_R = (int16_t)duty;
        TWIN_FW_SEQ++;

        cur_seq = TWIN_FW_SEQ;
        cur_duty = duty;
        cur_batt_mv = s.batt_mv;
        cur_ang_mdeg = (int32_t)(law.tilt.theta * 57295.78f);
        cycles++;
        if (cycles % TELEM_EVERY_CYCLES == 0)
            telemetry();
    }
}
