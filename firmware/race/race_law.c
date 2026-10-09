/* race_law.c -- the mission law extracted verbatim from main.c (the
 * pure-move split of 2026-10-01): the state machine, the observation
 * law, the speed plan and both control loops, with every platform
 * effect (PWM, mailbox, pins, link lines) replaced by writes into
 * race_law_out_t. The shell applies those in its own order; the
 * mission arithmetic mirrors race/controller.py, including the filtered
 * encoder-speed estimate used only by the stopped check. */
#include <math.h>

#include "race_law.h"
#include "twin_fwconfig.h"
#include "race_fwconfig.h"

#define PI_F      3.14159265358979f

/* ---- mission state (task selection + RaceController's self.*) ---- */

static const race_seg_t *route;
static int route_n;
static uint8_t fw_task, turbo;
static float speeds[2][3];             /* [turbo][straight, r40, node] */
static uint32_t law_seq;

/* ---- control core state (one-to-one with RaceController's self.*) ---- */

static balance_tilt_t tilt_f;           /* complementary-filter state (core) */
static uint8_t have_enc;
static int32_t last_enc_l, last_enc_r;
static float psi, odo_x, odo_y;         /* odometry (travel axis) */
static float y_pos, y_ref, v_plan;      /* LQR sliding reference (chassis +Y domain) */
static uint8_t phase;
static int seg_i;
static float t_now, t_start, t_done, stop_hold;
static uint16_t buzzer_ms, led_ms, prev_bits;
static line_tracker_t line_tracker;
static line_endpoint_t line_endpoint;
static float e_lat, w_cmd, tau_d, lost_t, blob_t;
static float align_t0, w_integ, w_f, v_stop;
static int duty_d_prev;

void race_law_configure(uint8_t task, uint8_t turbo_bit)
{
    fw_task = task;
    turbo = (turbo_bit || fw_task == 4) ? 1u : 0u;
    switch (fw_task) {
    case 1:
        route = RACE_ROUTE_T1;
        route_n = (int)(sizeof RACE_ROUTE_T1 / sizeof RACE_ROUTE_T1[0]);
        break;
    case 2:
        route = RACE_ROUTE_T2;
        route_n = (int)(sizeof RACE_ROUTE_T2 / sizeof RACE_ROUTE_T2[0]);
        break;
    case 3:
        route = RACE_ROUTE_T3;
        route_n = (int)(sizeof RACE_ROUTE_T3 / sizeof RACE_ROUTE_T3[0]);
        break;
    case 4:
        route = RACE_ROUTE_T4;
        route_n = (int)(sizeof RACE_ROUTE_T4 / sizeof RACE_ROUTE_T4[0]);
        break;
    default:
        route = 0;
        route_n = 0;
        break;
    }
    speeds[0][0] = RACE_V_STRAIGHT;
    speeds[0][1] = RACE_V_R40;
    speeds[0][2] = RACE_V_NODE;
    speeds[1][0] = RACE_VT_STRAIGHT;
    speeds[1][1] = RACE_VT_R40;
    speeds[1][2] = RACE_VT_NODE;
}

static void mission_init(void)
{
    t_now = 0.0f;
    tilt_f.have = 0;
    have_enc = 0;
    last_enc_l = last_enc_r = 0;
    /* spawn prior: the rules' point A + first-segment tangent (exactly
     * the three numbers controller.reset(x0, y0, psi0) receives; the
     * firmware derives the same triple from its own route table) */
    track_point(&route[0], 0.0f, &odo_x, &odo_y);
    psi = track_heading(&route[0], 0.0f);
    y_pos = y_ref = v_plan = 0.0f;
    phase = RACE_PHASE_ARM;
    seg_i = 0;
    t_start = t_done = -1.0f;
    stop_hold = 0.0f;
    buzzer_ms = led_ms = 0;
    line_tracker = (line_tracker_t){0};
    line_endpoint = (line_endpoint_t){0};
    prev_bits = 0;
    e_lat = w_cmd = tau_d = lost_t = blob_t = 0.0f;
    w_integ = w_f = v_stop = 0.0f;
    align_t0 = -1e9f;
    duty_d_prev = 0;
    if (fw_task != 1) {                 /* start beep+LED (same as controller.reset) */
        buzzer_ms = RACE_BEEP_MS;
        led_ms = RACE_LED_MS;
    }
}

/* _mission: the mission state machine. Node names never enter the firmware --
 * the harness synthesizes events from buzzer rising edges in route order
 * (beeps fire in route order by construction). */
static void mission_step(float v_travel, uint8_t trigger)
{
    if (phase == RACE_PHASE_ARM) {
        if (t_now >= RACE_ARM_S) {
            phase = RACE_PHASE_RUN;
            t_start = t_now;
        }
        return;
    }
    if (phase == RACE_PHASE_DONE)
        return;
    if (phase == RACE_PHASE_RUN) {
        const race_seg_t *seg = &route[seg_i];
        uint8_t blind = !seg->taped;
        if ((lost_t > RACE_PARK_LOST_S && !blind) || fabsf(e_lat) > 0.5f) {
            /* hopelessly lost: on a TAPED leg a dark bar that long is
             * the failure (a flicker would only clear the lost timer,
             * hence the error bound as well): brake hard so the grader
             * fails it cleanly instead of cruising the whole field. A
             * blind leg's dark bar is the plan; only its cross-track
             * bound can park it */
            phase = RACE_PHASE_BRAKE;
            return;
        }
        float ex, ey;
        track_point(seg, seg->len, &ex, &ey);
        float s2, lat2;
        track_project(seg, odo_x, odo_y, &s2, &lat2);
        (void)lat2;
        float dist_end = hypotf(odo_x - ex, odo_y - ey);
        uint8_t at_node = dist_end <= RACE_TRIGGER_R;
        /* s saturation alone over-triggers (arc encoder overread puts odo
         * ~0.3 m ahead), so the saturated fallback also needs the distance
         * constraint; the junction blob (tape-end folded in) is the
         * preferred on-tape true signal */
        uint8_t passed_end = (s2 >= seg->len - 1e-6f && dist_end <= 0.25f);
        float lead = (route_n == 1) ? RACE_FINAL_LEAD_SHORT
                                    : RACE_FINAL_LEAD;
        uint8_t final_line = (seg_i == route_n - 1
                              && s2 >= seg->len - lead);
        /* dead-reckoned triggers need fresh odometry ON TAPED LEGS (odo
         * built while the bar was dark for long is fiction -- sphere-
         * tire scrub). A BLIND leg is dead reckoning by design -- its
         * straights are where the odometry is cleanest -- so there the
         * odo triggers fire ungated. The 2 s window lets an arc's dark
         * TAIL still dead-reckon its finish (bring-up: task-2 sagged
         * off the DA tape with a healthy odo and the 1 s gate refused
         * the final-A line until the park timer ended the run) */
        uint8_t fresh = (lost_t < 2.0f) || blind;
        if (trigger || (fresh && (at_node || passed_end || final_line))) {
            buzzer_ms = RACE_BEEP_MS;   /* beep+LED cue (exam scoring point) */
            led_ms = RACE_LED_MS;
            /* node resync: POSITION binned to the node. The HEADING
             * integral is kept -- snapping it to the sheet tangent lies
             * whenever the car crosses off-tangent (arc-scrub exits run
             * 8-11 deg late), and the lie goes straight down the next
             * leg's dead reckoning (bring-up: task-2's CD landed 15 cm
             * off D). A new leg also starts with a fresh lost timer:
             * darkness carried over from a blind leg must not pre-arm
             * the next leg's park timer */
            odo_x = ex;
            odo_y = ey;
            lost_t = 0.0f;
            seg_i++;
            align_t0 = t_now;
            if (seg_i >= route_n)
                phase = RACE_PHASE_BRAKE;
        }
        return;
    }
    /* brake: stop on the controller's own estimates (the filtered yaw
     * rate -- the raw gyro rides contact ringing and never settles into
     * the threshold) */
    if (fabsf(v_travel) < RACE_STOP_V && fabsf(w_f) < RACE_STOP_W)
        stop_hold += TWIN_DT_S;
    else
        stop_hold = 0.0f;
    if (stop_hold >= RACE_STOP_S) {
        phase = RACE_PHASE_DONE;
        t_done = t_now;
        buzzer_ms = 3 * RACE_BEEP_MS;   /* arrival triple beep */
        led_ms = RACE_LED_MS;
    }
}

/* Every error means tape-to-travel-left, including recovery. */
static float lateral_error(uint16_t bits, float recovery, uint8_t blind)
{
    return line_track(&line_tracker, line_observe(blind ? 0 : bits),
                      recovery, TWIN_DT_S, !blind);
}

/* ---- one control cycle (line-by-line isomorphic with controller.step()) ---- */

void race_law_cycle(race_law_out_t *out,
                    int16_t ay, int16_t az, int16_t gx, int16_t gz,
                    int32_t enc_l, int32_t enc_r,
                    uint16_t line_bits, uint16_t batt_mv)
{
    uint8_t ph0 = phase;             /* the link's done edge */
    int seg0 = seg_i;                /* the link's node edge */
    out->node_edge = 0;
    out->done_edge = 0;
    /* 1) raw frame snapshot -- the peripheral path: the IMU sample came
     * off the I2C driver's coherent burst, the encoders are integrated
     * from the TIM3/TIM4 counters, line_bits is a straight PF0-7 read
     * and battery mV came from ADC1 */
    line_bits &= 0xFFu;
    line_observation_t line_obs = line_observe(line_bits);
    out->line_bits = line_bits;        /* actual GPIO read, telemetry only */

    t_now += TWIN_DT_S;

    /* 2) raw -> SI. Python also differences out v_diff (left/right
     *    wheel-speed difference low pass) but nothing downstream uses
     *    it -- omitted */
    float gyro_x = balance_gyro_rad(gx);
    float gyro_z = balance_gyro_rad(gz);
    float theta = balance_filter_step(&tilt_f, balance_tilt_raw(ay, az),
                                      gyro_x);

    float d_enc = 0.0f;
    if (!have_enc) {
        have_enc = 1;
    } else {
        float d_enc_l = (float)(enc_l - last_enc_l) * RACE_ENC_SCALE;
        float d_enc_r = (float)(enc_r - last_enc_r) * RACE_ENC_SCALE;
        d_enc = (d_enc_l + d_enc_r) * 0.5f;
    }
    last_enc_l = enc_l;
    last_enc_r = enc_r;
    float v_cy = d_enc / TWIN_COUNTS_PER_M / TWIN_DT_S;
    y_pos += v_cy * TWIN_DT_S;
    float v_travel = -v_cy;
    /* scrub compensation: on arcs ball-wheel yaw scrub makes the encoders
     * overread body displacement (measured ~15% at w=0.45 rad/s); discount
     * by yaw rate -- a legitimate firmware calibration term */
    v_travel *= fmaxf(0.0f, 1.0f - RACE_SCRUB_K * fabsf(gyro_z));
    /* yaw integration with tilt compensation: psi_dot in the world
     * frame is omega_z/cos(theta) -- the body-frame gyro reads ~4.3%
     * short at the 16.7 deg cruise trim, and over a 180-deg arc that
     * is ~8 deg of heading lie (bring-up: task-2 exited C with the car
     * 11 deg off the tangent while the estimate said on-tangent) */
    psi = wrapf(psi + gyro_z / fmaxf(0.5f, cosf(theta)) * TWIN_DT_S);
    /* Software yaw-rate filtering suppresses contact ringing without
     * the phase lag that reinforces the servo's slew-limit oscillation.
     * The shared frequency is separate from the chip's hardware DLPF. */
    float a_lpf = TWIN_DT_S
                  / (TWIN_DT_S + 1.0f / (2.0f * PI_F * RACE_W_LPF_HZ));
    w_f += (gyro_z - w_f) * a_lpf;
    odo_x += v_travel * cosf(psi) * TWIN_DT_S;
    odo_y += v_travel * sinf(psi) * TWIN_DT_S;

    /* 3) mission pre-projection (_mission may advance the segment; the
     * main projection recomputes afterwards) */
    const race_seg_t *seg = &route[seg_i < route_n ? seg_i : route_n - 1];
    float s_seg, lat_odom;
    track_project(seg, odo_x, odo_y, &s_seg, &lat_odom);
    int pop = line_obs.count;
    if (line_obs.status == LINE_WIDE && pop >= RACE_BLOB_MIN)
        blob_t += TWIN_DT_S;
    else
        blob_t = 0.0f;
    /* Optical node evidence needs the planned arc's endpoint as well
     * as a pattern transition; missing input alone is not an endpoint. */
    float line_lead = LINE_CFG_BAR_AHEAD / fmaxf(0.5f, cosf(theta));
    uint8_t near_tape_end = seg->taped
        && s_seg >= seg->len - line_lead - RACE_TRIGGER_R;
    /* Confirm a clean-to-white endpoint. Longitudinal odometry drifts
     * on arcs, so use a late-arc window plus persistent white input. */
    uint8_t junction = blob_t >= RACE_BLOB_S && near_tape_end;
    uint8_t tape_end = line_endpoint_update(&line_endpoint, line_obs, seg->taped,
        s_seg >= LINE_CFG_END_PROGRESS_MIN * seg->len, TWIN_DT_S);
    prev_bits = line_bits;
    /* Encoder bins can chatter above STOP_V while the body is still.
     * Filter only this estimate; raw deltas still drive odometry, balance
     * and curvature feed-forward. The stop threshold/hold are unchanged. */
    float av_stop = TWIN_DT_S
                 / (TWIN_DT_S + 1.0f / (2.0f * PI_F * RACE_STOP_V_LPF_HZ));
    v_stop += (v_travel - v_stop) * av_stop;
    mission_step(v_stop, (uint8_t)(junction || tape_end));
    if (seg_i != seg0) line_endpoint = (line_endpoint_t){0};
    if (seg_i != seg0 && seg_i < route_n)
        out->node_edge = 1;          /* link: entering leg seg_i (0-based) */

    /* 4) speed plan (travel axis, applied through the chassis minus sign) */
    seg = &route[seg_i < route_n ? seg_i : route_n - 1];
    track_project(seg, odo_x, odo_y, &s_seg, &lat_odom);
    uint8_t blind = !seg->taped;   /* untaped leg: planned open-white run */
    const float *sp = speeds[turbo];
    float v_target = (phase == RACE_PHASE_BRAKE || phase == RACE_PHASE_DONE)
                         ? 0.0f
                         : sp[track_class(track_curvature(seg, s_seg))];
    /* node slowdown: task 3/4 nodes carry a 39-deg tangent kink (the
     * figure-8 diagonals), and the +-47.5 mm capture band survives a
     * kink crossing only while v*sin(kink) is small -- cap speed for
     * the 15 cm before every node */
    if (s_seg > seg->len - 0.15f)
        v_target = fminf(v_target, sp[2]);
    float kink_err = 9.9f;
    if (t_now - align_t0 < RACE_ALIGN_MAX_S) {
        kink_err = fabsf(wrapf(track_heading(seg, 0.05f) - psi));
        if (kink_err > RACE_KINK_GO) {
            if (kink_err > RACE_KINK_STOP)
                v_target = 0.0f;        /* turn the kink out in place, then go */
            else
                v_target = fminf(v_target, sp[2]);
        }
    }
    /* spawn crawl: the launch itself is the risk (yaw servo churning
     * the differential at its cap tips the pitch past recovery --
     * bring-up: +21 deg runaway); the first 12 cm go gentle */
    if (seg_i == 0 && s_seg < 0.12f)
        v_target = fminf(v_target, 0.16f);
    /* final-segment finish: balance braking coasts ~0.2 m; the last 30
     * cm crawls into the exam stop window */
    if (seg_i == route_n - 1 && s_seg > seg->len - 0.30f)
        v_target = fminf(v_target, 0.10f);
    /* re-acquire slowly after an UNPLANNED loss; on a blind leg a dark
     * bar is the plan and full cruise continues */
    if (lost_t > RACE_LOST_S && !blind)
        v_target = fminf(v_target, 0.12f);
    /* lateral error slows the cruise: the differential churn of a big
     * correction couples into pitch above ~0.3 m/s */
    if (fabsf(e_lat) > RACE_E_SLOW)
        v_target = fminf(v_target, RACE_E_SLOW_V);
    float dv = v_target - v_plan;
    /* full ramp only when tracking is solid: on tape a clean bar (dark
     * flicker / |e| over half the band), on a blind leg a tight
     * odometry cross-track -- marginal tracking plus the full ramp
     * excites pitch into the rail-chasing dive (root cause of both
     * bring-up line losses) */
    uint8_t solid = ((line_obs.status == LINE_TRACK || blind) && fabsf(e_lat) <= 0.025f
                     && t_now - align_t0 >= 2.5f);
    float ramp = (dv > 0.0f) ? (solid ? RACE_A_MAX : RACE_A_MAX_KINK)
                             : RACE_A_MAX_BRAKE;
    v_plan += clampf(dv, -ramp * TWIN_DT_S, ramp * TWIN_DT_S);
    float v_cy_ref = -v_plan;
    y_ref += v_cy_ref * TWIN_DT_S;
    /* one-sided reference governor: gives back only while y lags the
     * reference (ramp segments) -- a symmetric leak endorses overspeed
     * too (v settles at plan+leak rate, bring-up). While braking, the
     * reference also follows the car DOWN (forward overspeed leaves y
     * ahead of its station, and holding that station reverses the car
     * a third of a meter back past the node, bring-up task-1) */
    float e0 = y_pos - y_ref;
    if (e0 > 0.0f) {
        y_ref += fminf(RACE_REF_LEAK * TWIN_DT_S, e0);
    } else if (e0 < 0.0f
               && (phase == RACE_PHASE_BRAKE || phase == RACE_PHASE_DONE)) {
        y_ref -= fminf(RACE_REF_LEAK_BRAKE * TWIN_DT_S, -e0);
    }

    /* 5) line tracking -> yaw-rate command. Continuous tape following:
     * bar centroid + rate damping around the curvature feed-forward
     * (damping the absolute rate fights the arc's steady turn: on R60
     * e sits at -22 mm); the centroid rides straight through junctions;
     * odometry enters only the curvature lookup, the post-node align
     * servo, and recovery. Positive error always means tape to
     * travel-left. */
    /* The forward bar is a different point from the odometric origin. */
    float lead = line_lead;
    float s_bar, lat_bar;
    track_project(seg, odo_x + lead * cosf(psi), odo_y + lead * sinf(psi),
                  &s_bar, &lat_bar);
    float psi_bar = track_heading(seg, s_bar);
    float cross = cosf(wrapf(psi - psi_bar));
    float recovery = blind ? -lat_odom : -lat_bar / fmaxf(0.5f, cross);
    e_lat = lateral_error(line_bits, recovery, blind);
    /* line-aided odometry: on clean tape (1-4 sensors) the bar measures
     * the cross-axis offset directly, continuously clearing lateral
     * odometry drift; longitudinal drift waits for node resync */
    if (line_obs.status == LINE_TRACK && !blind && cross >= 0.5f) {
        float lat_err = clampf(lat_bar + line_obs.error * cross, -0.05f, 0.05f);
        float lx = -sinf(psi_bar), ly = cosf(psi_bar);
        odo_x -= lx * lat_err * RACE_ODO_K;
        odo_y -= ly * lat_err * RACE_ODO_K;
    }
    float s_look = fminf(s_seg + 0.08f, seg->len);
    float psi_path = track_heading(seg, s_look);
    float kappa = track_curvature(seg, s_look);
    /* feed-forward on measured speed: otherwise bursts beyond the plan
     * understeer (on R40 +0.05 m/s is 0.125 rad/s of missing rate -- the
     * root cause of the bring-up tape-edge riding) */
    float v_meas = fabsf(v_cy);
    float w_ff = kappa * v_meas;
    float w;
    if (line_obs.status == LINE_TRACK && !blind) {
        lost_t = 0.0f;
    } else {
        lost_t += TWIN_DT_S;
    }
    /* Search after unexpected loss only; allow entry capture to settle. */
    float psi_aim = psi_path;
    if (!blind && lost_t > RACE_SWEEP_AFTER && t_now - align_t0 > 4.0f)
        psi_aim += RACE_SWEEP_RAD
                   * sinf(2.0f * PI_F * (lost_t - RACE_SWEEP_AFTER)
                          / RACE_SWEEP_T);
    w = w_ff + RACE_KP_LAT * e_lat
      + RACE_KP_HEAD * wrapf(psi_aim - psi)
      - RACE_KD_RATE * (w_f - w_ff);
    /* post-node align servo: resync just rewrote psi, twist the bot onto
     * the new tangent -- the centroid alone cannot swallow a 50 deg kink;
     * the speed plan cooperates with v=0 turn-in-place on large kinks */
    if (kink_err <= 9.0f && kink_err > RACE_KINK_GO * 0.5f) {
        float kink = wrapf(track_heading(seg, 0.05f) - psi);
        w += clampf(RACE_K_ALIGN * kink, -1.6f, 1.6f);
    }
    uint8_t braking = (phase == RACE_PHASE_BRAKE || phase == RACE_PHASE_DONE);
    if (braking)
        w = 0.0f;   /* no steering while braking/done: the rate servo pushing
                     * against platform jitter snaps the nose */
    w_cmd = clampf(w, -RACE_W_CMD_CAP, RACE_W_CMD_CAP);

    /* 6) balance common mode: twin LQR sliding reference (speed tracking
     *    = station keeping on a moving reference, the standard segway
     *    approach) */
    float z0 = y_pos - y_ref;
    float z1 = v_cy - v_cy_ref;
    float z2 = theta - TWIN_THETA_REF_RAD;
    float z3 = gyro_x;
    float tau_c = balance_tau(z0, z1, z2, z3);

    /* 7) steering differential: yaw-rate torque servo (P + slow integral;
     *    duty_d>0 = torque to the right wheel = CCW). The integral makes
     *    up P's shortfall (arc steering scrub leaves pure P delivering
     *    only ~70% of the commanded rate); the hard clamp prevents
     *    thermal relay chatter */
    if (braking) {
        tau_d = 0.0f;
        w_integ = 0.0f;
    } else {
        w_integ = clampf(w_integ
                         + RACE_KI_YAW * (w_cmd - w_f) * TWIN_DT_S,
                         -RACE_TAU_WI_CAP, RACE_TAU_WI_CAP);
        tau_d = clampf(RACE_K_YAW * (w_cmd - w_f) + w_integ,
                       -RACE_TAU_D_CAP, RACE_TAU_D_CAP);
    }

    /* 8) tau -> duty: scale the stall limit by the battery voltage the
     *    mailbox reports; with no reading (<1V) do not drive -- honest
     *    defense (a real board behaves exactly so with the sense line
     *    unplugged) */
    int duty_l = 0, duty_r = 0;
    if (batt_mv >= 1000u) {
        int duty_c = balance_duty(tau_c, batt_mv);
        int duty_d = balance_duty(tau_d, batt_mv);
        /* differential slew: the bar's +-5.5 mm quantization steps the
         * yaw command; without slewing duty_d flips +-150 permille every
         * few cycles -- a pitch disturbance for nothing */
        duty_d = clampi(duty_d, duty_d_prev - RACE_DUTY_D_SLEW,
                        duty_d_prev + RACE_DUTY_D_SLEW);
        duty_d_prev = duty_d;
        /* the differential must not eat common-mode headroom: balance
         * authority always outranks steering */
        int cap = TWIN_DUTY_CAP_PM;
        int headroom = cap - (duty_c < 0 ? -duty_c : duty_c);
        duty_d = clampi(duty_d, -headroom, headroom);
        duty_l = clampi(duty_c - duty_d, -cap, cap);
        duty_r = clampi(duty_c + duty_d, -cap, cap);
    }
    out->duty_l = (int16_t)duty_l;      /* status echo: what PWM holds */
    out->duty_r = (int16_t)duty_r;

    /* 9) beep/LED countdown + mission telemetry + heartbeat */
    if (buzzer_ms > 0)
        buzzer_ms = (buzzer_ms > RACE_MS_PER_CYCLE)
                        ? (uint16_t)(buzzer_ms - RACE_MS_PER_CYCLE) : 0;
    if (led_ms > 0)
        led_ms = (led_ms > RACE_MS_PER_CYCLE)
                     ? (uint16_t)(led_ms - RACE_MS_PER_CYCLE) : 0;
    out->buzzer_ms = buzzer_ms;         /* telemetry mirrors */
    out->led_ms = led_ms;
    out->status = (uint32_t)phase | ((uint32_t)seg_i << 8)
                | ((uint32_t)line_tracker.source << 16)
                | ((uint32_t)line_obs.status << 18)
                | ((uint32_t)line_obs.centered << 20);
    float t_m = 0.0f;
    if (t_start >= 0.0f)
        t_m = (phase == RACE_PHASE_DONE ? t_done : t_now) - t_start;
    out->t_mission_ms = (uint32_t)lroundf(t_m * 1000.0f);
    out->e_lat_mm = (int16_t)lroundf(e_lat * 1000.0f);
    out->v_plan_mm_s = (uint16_t)lroundf(v_plan * 1000.0f);
    out->odo_x_cm = (int16_t)lroundf(odo_x * 100.0f);
    out->odo_y_cm = (int16_t)lroundf(odo_y * 100.0f);
    law_seq++;
    out->fw_seq = law_seq;
    if (phase == RACE_PHASE_DONE && ph0 != RACE_PHASE_DONE)
        out->done_edge = 1;           /* link: arrival, mission clock in ms */
}

void race_law_init(void)
{
    law_seq = 0;
    mission_init();
}

uint16_t race_law_buzzer_ms(void) { return buzzer_ms; }
uint16_t race_law_led_ms(void) { return led_ms; }
