/* Smart-car race firmware v3 -- PERIPHERAL-DRIVEN + SERIAL LINK. The
 * mission law lives in race_law.c (the pure-move split of 2026-10-01;
 * one source with the host build, line-by-line isomorphic with
 * race/controller.py -- the A/B cross-check IS the port-correctness
 * proof). This file is everything around the law -- real hardware
 * paths:
 *
 *   IMU      real I2C driver (stm32f4_i2c.c + mpu6050.c), self-paced
 *            200 Hz on the device's own data-ready -- no harness strobe;
 *   encoders TIM3/TIM4 encoder interface integrated through delta16 --
 *            the harness feeds EDGES, never counters;
 *   line bar 8xIO on PF0-PF7 (stm32f4_line.c), bit i = sensor i on-tape;
 *   battery  ADC1 (PC0) through the modeled divider, 10 ms cadence;
 *   motors   TIM1 PWM + TB6612 direction pins -- the coupling broker
 *            reads the duty back from CCR + the direction word;
 *   buzzer/LED  GPIOF PF8/PF9, countdown unchanged;
 *   link     the USART2 shell of twin v3 (same driver, same line
 *            protocol core): the outer loop polls data-ready in 2 ms
 *            slices so uart_pump() runs between samples, the
 *            starvation rule lives in the shell (same 150 ms window,
 *            same zero-duty / heartbeat-freeze / resume semantics),
 *            "T <seq> <dl> <dr> <batt_mv> <t_ms> <seg> <phase>"
 *            telemetry at 10 Hz plus UP / node <seg> / done <t_ms> /
 *            starved / resume event lines, ping->pong, stat->fresh
 *            telemetry, unknown lines ignored silently.
 *
 * The mailbox window stays as a firmware-owned STATUS mirror (task word
 * at boot = mission CONFIGURATION the harness writes pre-boot; duty/
 * buzzer/LED/mission telemetry + heartbeat = what the grader reads).
 * Starvation = no fresh IMU sample for 150 ms: zero duty, freeze the
 * heartbeat, resume on the next fresh sample.
 */

#include <stdint.h>

#include "mailbox.h"
#include "race_law.h"
#include "../timer_monotonic.h"
#include "../stm32f4_i2c.h"
#include "../mpu6050.h"
#include "../stm32f4_encoder.h"
#include "../stm32f4_adc.h"
#include "../stm32f4_pwm.h"
#include "../stm32f4_line.h"
#include "../stm32f4_uart.h"
#include "../uart_proto.h"
#include "../stm32f4_iwdg.h"

/* IMU-silence deadline (the old strobe-supervision window, now measured
 * from the last fresh data-ready) + battery resample cadence */
#define STARVE_TIMEOUT_US 150000u
#define IMU_SLICE_US 2000u            /* data-ready poll slice */
#define BATT_PERIOD_US 10000u
#define IMU_REINIT_TRIES 3u
#define TELEM_EVERY_CYCLES 20u        /* 200 Hz / 20 = 10 Hz on the link */
#define TX_TIMEOUT_US 1000u           /* a byte is ~87 us at 115200 */
#define RX_DRAIN_MAX 32u              /* control first: bounded per pump */

/* buzzer (active) PF8 + mission LED PF9: one ODR write; the electrical
 * layer is the arrival-day label in race_status.md */
#define GPIOF_BASE 0x40021400u
#define GPIOF_MODER (*(volatile uint32_t *)(GPIOF_BASE + 0x00))
#define GPIOF_ODR   (*(volatile uint32_t *)(GPIOF_BASE + 0x14))
#define PIN_BUZZER  8u
#define PIN_LED     9u

static void ui_set(uint8_t buzzer, uint8_t led)
{
    uint32_t word = GPIOF_ODR;
    word = buzzer ? (word | (1u << PIN_BUZZER))
                  : (word & ~(1u << PIN_BUZZER));
    word = led ? (word | (1u << PIN_LED))
               : (word & ~(1u << PIN_LED));
    GPIOF_ODR = word;
}

static void ui_init(void)
{
    uint32_t moder = GPIOF_MODER;        /* PF8/PF9: outputs (01) */
    moder &= ~((3u << (2 * PIN_BUZZER)) | (3u << (2 * PIN_LED)));
    moder |= (1u << (2 * PIN_BUZZER)) | (1u << (2 * PIN_LED));
    GPIOF_MODER = moder;
    ui_set(0, 0);
}

/* ---- the serial link (same driver + protocol core as twin v3) ---- */

static char rxline[UP_LINE_MAX + 1];
static uint32_t rxlen;

/* the law's last cycle -- the telemetry line and the mailbox mirrors
 * are formatted from this snapshot (same values the old inline writes
 * produced) */
static race_law_out_t law_out;
static uint32_t last_batt_mv;
static uint32_t cycles;

static void emit(const char *s, uint32_t n)
{
    uart2_write(s, n, TX_TIMEOUT_US);
}

static void telemetry(void)
{
    char b[64];
    int n = 0;
    b[n++] = 'T';
    b[n++] = ' ';
    n += up_fmt_u32(b + n, law_out.fw_seq);
    b[n++] = ' ';
    n += up_fmt_i32(b + n, law_out.duty_l);
    b[n++] = ' ';
    n += up_fmt_i32(b + n, law_out.duty_r);
    b[n++] = ' ';
    n += up_fmt_u32(b + n, last_batt_mv);
    b[n++] = ' ';
    n += up_fmt_u32(b + n, law_out.t_mission_ms);
    b[n++] = ' ';
    n += up_fmt_u32(b + n, (law_out.status >> 8) & 0xFFu);
    b[n++] = ' ';
    b[n++] = (char)('0' + (law_out.status & 0xFFu));
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

/* the law's outputs -> the physical world, in the shell's own order:
 * PWM first (control beats telemetry), then the pins, then the RAC2
 * mirrors, then the link lines */
static void apply_law_outputs(void)
{
    pwm_motor_set(law_out.duty_l, law_out.duty_r);
    RACE_DUTY_L = law_out.duty_l;        /* status echo: what PWM holds */
    RACE_DUTY_R = law_out.duty_r;
    ui_set(law_out.buzzer_ms > 0, law_out.led_ms > 0);
    RACE_BUZZER_MS = law_out.buzzer_ms;  /* telemetry mirrors */
    RACE_LED = law_out.led_ms > 0 ? 1u : 0u;
    RACE_STATUS = law_out.status;
    RACE_T_MISSION = law_out.t_mission_ms;
    RACE_E_LAT_MM = law_out.e_lat_mm;
    RACE_V_PLAN = law_out.v_plan_mm_s;
    RACE_ODO_X_CM = law_out.odo_x_cm;
    RACE_ODO_Y_CM = law_out.odo_y_cm;
    RACE_FW_SEQ = law_out.fw_seq;
    RACE_LINE_BITS = law_out.line_bits;
    if (law_out.node_edge) {
        char nb[8];
        int k = 0;
        nb[k++] = 'n'; nb[k++] = 'o'; nb[k++] = 'd'; nb[k++] = 'e';
        nb[k++] = ' ';
        k += up_fmt_u32(nb + k, (law_out.status >> 8) & 0xFFu);
        nb[k++] = '\n';
        emit(nb, (uint32_t)k);       /* link: entering leg seg_i (0-based) */
    }
    if (law_out.done_edge) {
        char db[16];
        int k = 0;
        db[k++] = 'd'; db[k++] = 'o'; db[k++] = 'n'; db[k++] = 'e';
        db[k++] = ' ';
        k += up_fmt_u32(db + k, law_out.t_mission_ms);
        db[k++] = '\n';
        emit(db, (uint32_t)k);       /* link: arrival, mission clock in ms */
    }
}

int main(void)
{
    /* task word: byte0 = task 1..4, bit8 = turbo; task4 forces turbo
     * (same rule as the controller constructor). It is mission
     * CONFIGURATION, not a sensor: the harness writes it into the
     * status window pre-boot and the firmware reads it once here;
     * retask = cold boot, exactly the stub's rebuild rule. An invalid
     * word = no drive, no heartbeat; the backend's boot timeout calls
     * it out. */
    uint16_t tw = RACE_TASK_WORD;
    uint8_t fw_task = (uint8_t)(tw & 0xFFu);
    switch (fw_task) {
    case 1: case 2: case 3: case 4:
        break;
    default:
        for (;;)
            ;
    }
    race_law_configure(fw_task, (uint8_t)((tw >> 8) & 1u));
    race_law_init();

    timer_monotonic_start();
    iwdg_start();                     /* ~300 ms last-resort guard: a
                                         hung loop resets coasted */
    RACE_MAGIC = 0;                      /* status mirror silent until up */
    i2c1_init();
    line_bar_init();
    ui_init();
    encoder_init();
    adc1_init();
    pwm_motor_init();
    uart2_init();
    pwm_motor_set(0, 0);                 /* motors never arm before the
                                            IMU is alive and talking */

    unsigned tries = 0;
    while (mpu6050_init(MPU_ADDR_GND) != MPU_OK) {
        if (++tries > IMU_REINIT_TRIES)
            for (;;)                     /* dead IMU halts here: no
                                            heartbeat, no drive */
                ;
    }

    RACE_MAGIC = RACE_MAILBOX_MAGIC;     /* status mirror: we are up */
    RACE_DUTY_L = 0;
    RACE_DUTY_R = 0;
    RACE_BUZZER_MS = race_law_buzzer_ms();   /* mission_init may have armed
                                                the start beep */
    RACE_LED = race_law_led_ms() > 0 ? 1u : 0u;
    RACE_FW_SEQ = 0;
    emit("UP\n", 3);

    int32_t enc_l = 0, enc_r = 0;
    uint16_t last_cl = encoder_cnt_left();
    uint16_t last_cr = encoder_cnt_right();
    uint16_t batt_mv = 0;
    uint32_t mv;
    if (battery_read_mv(&mv) == 0)       /* the duty guard wants real
                                            volts on cycle 1 */
        batt_mv = (uint16_t)mv;
    uint32_t batt_mark = timer_ticks();
    uint32_t last_fresh = timer_ticks();
    uint8_t starved = 1;                 /* nothing fresh yet */
    for (;;) {
        iwdg_kick();                 /* every slice: the watchdog guards
                                        a hung loop, not a data-starved one
                                        (v2 kicked only on fresh samples --
                                        a starving IMU would have reset
                                        the board inside its window) */
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
                ui_set(0, 0);
                RACE_DUTY_L = 0;
                RACE_DUTY_R = 0;
                emit("starved\n", 8);
            }
            continue;
        }
        if (st != MPU_OK) {
            /* transport failure: motors off, bounded re-init; a bus
             * that stays dead halts with the heartbeat frozen */
            pwm_motor_set(0, 0);
            unsigned i;
            for (i = 0; i < IMU_REINIT_TRIES; i++)
                if (mpu6050_init(MPU_ADDR_GND) == MPU_OK)
                    break;
            if (i == IMU_REINIT_TRIES)
                for (;;)
                    ;
            continue;
        }
        if (starved) {
            starved = 0;
            emit("resume\n", 7);
        }
        last_fresh = timer_ticks();
        uint16_t cl = encoder_cnt_left();
        uint16_t cr = encoder_cnt_right();
        enc_l += encoder_delta16(cl, last_cl);
        enc_r += encoder_delta16(cr, last_cr);
        last_cl = cl;
        last_cr = cr;
        if (timer_elapsed_us(batt_mark) >= BATT_PERIOD_US) {
            batt_mark += TIMER_US_TO_TICKS(BATT_PERIOD_US);
            if (battery_read_mv(&mv) == 0)
                batt_mv = (uint16_t)mv;  /* failures keep last good */
        }
        race_law_cycle(&law_out, m.ay, m.az, m.gx, m.gz,
                       enc_l, enc_r, line_bar_read(), batt_mv);
        last_batt_mv = batt_mv;
        apply_law_outputs();
        cycles++;
        if (cycles % TELEM_EVERY_CYCLES == 0)
            telemetry();
    }
}
