/* balance.h -- the vehicle-level balance law's single interface.
 *
 * This is the one source of the balance control law: both firmware
 * shells link balance.c, and the parallel Python reference
 * (twin/backend.py::BalanceController) is kept switchable against it.
 * Platform-free: raw-domain samples in, duty out -- the mailbox, the
 * strobe and the supervision stay in the shell.
 */
#ifndef BALANCE_H
#define BALANCE_H

#include <stdint.h>

/* complementary-filter state; the first step seeds from the gravity vector */
typedef struct {
    float theta;
    uint8_t have;
} balance_tilt_t;

/* one raw-domain sample as the shell unpacked it from its transport */
typedef struct {
    int16_t ay, az;             /* accelerometer, +-2g domain */
    int16_t gx;                 /* gyro pitch rate, +-250dps domain */
    int32_t enc_l, enc_r;       /* cumulative counts, += forward */
    uint16_t batt_mv;
} balance_sample_t;

/* ---- primitives the race law composes ---- */

/* tilt from the raw gravity ratio: a common positive scaling does not
 * change atan2, so raw values go in directly */
float balance_tilt_raw(int16_t ay, int16_t az);

/* gyro raw (+=250dps domain) -> rad/s */
float balance_gyro_rad(int16_t gx);

/* complementary filter; returns the fused tilt */
float balance_filter_step(balance_tilt_t *f, float tilt, float gyro_rad);

/* LQR state feedback z = [y, ydot, theta-theta_ref, thetadot] -> torque */
float balance_tau(float y, float ydot, float th_err, float thdot);

/* torque -> permille duty, stall cap scaled by the measured battery
 * voltage; a dead reading (<1 V) does not drive */
int balance_duty(float tau, uint16_t batt_mv);

/* ---- the twin's law: stationary station-keeping on the mean encoder ---- */

typedef struct {
    balance_tilt_t tilt;
    uint8_t have_enc;
    float last_enc_mean;
    float pos_m;
} balance_hold_t;

void balance_hold_init(balance_hold_t *h);
int  balance_hold_step(balance_hold_t *h, const balance_sample_t *s);

#endif /* BALANCE_H */
