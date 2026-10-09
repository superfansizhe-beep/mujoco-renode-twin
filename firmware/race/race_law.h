/* race_law.h -- the race mission law, one source for the ELF shell
 * (main.c) and the host build (race.hostc_backend loads the DLL).
 * Platform-free: raw-domain samples in, one output struct out; the PWM,
 * the mailbox window, the buzzer/LED pins and the serial link stay in
 * the shell. Line-by-line isomorphic with race/controller.py -- that
 * A/B cross-check is the port-correctness proof, unchanged by this
 * split. */
#ifndef RACE_LAW_H
#define RACE_LAW_H

#include <stdint.h>

#include "../core/balance.h"     /* balance_tilt_t + the balance primitives */
#include "../core/line.h"        /* line_tracker_t / line_endpoint_t */
#include "track.h"               /* race_seg_t + the baked route tables */

enum { RACE_PHASE_ARM = 0, RACE_PHASE_RUN = 1,
       RACE_PHASE_BRAKE = 2, RACE_PHASE_DONE = 3 };

/* One cycle's observable outputs, in the RAC2 status-mirror's own
 * domains: the shell copies these to PWM/mailbox/pins and formats the
 * link lines from them (the host build hands the same struct to
 * ctypes). */
typedef struct {
    int16_t  duty_l, duty_r;      /* what PWM holds (permille) */
    uint16_t buzzer_ms, led_ms;   /* post-countdown mirrors */
    uint16_t line_bits;           /* the PF0-7 echo (telemetry only) */
    uint32_t status;              /* phase | seg_i<<8 | source<<16
                                     | line_status<<18 | centered<<20 */
    uint32_t t_mission_ms;
    int16_t  e_lat_mm;
    uint16_t v_plan_mm_s;
    int16_t  odo_x_cm, odo_y_cm;
    uint32_t fw_seq;              /* heartbeat, one per cycle */
    uint8_t  node_edge;           /* segment advanced -> "node <seg>" */
    uint8_t  done_edge;           /* done entered -> "done <t_ms>" */
} race_law_out_t;

/* Task selection: the task-word bit0-7 + bit8 (turbo); task 4 forces
 * turbo (same rule as the stub's constructor). Invalid task leaves the
 * routes unset -- the shell decides what no-drive means. */
void race_law_configure(uint8_t task, uint8_t turbo_bit);

/* mission_init: spawn prior from the route table, phase arm, start
 * cue. Also resets the heartbeat counter. */
void race_law_init(void);
uint16_t race_law_buzzer_ms(void);   /* the boot mirror (main only) */
uint16_t race_law_led_ms(void);

/* One control cycle. Inputs are the shell's already-latched readings:
 * the IMU burst (ay/az/gx/gz raw), cumulative encoder counts, the PF0-7
 * line word and battery mV. node_edge/done_edge are cleared first. */
void race_law_cycle(race_law_out_t *out,
                    int16_t ay, int16_t az, int16_t gx, int16_t gz,
                    int32_t enc_l, int32_t enc_r,
                    uint16_t line_bits, uint16_t batt_mv);

#endif /* RACE_LAW_H */
