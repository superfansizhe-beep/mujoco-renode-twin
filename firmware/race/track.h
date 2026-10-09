/* track.h -- the field: projection math over the baked route tables,
 * the C mirror of race/track.py. The geometry itself is generated into
 * race_fwconfig.h (race.fwconfig bakes tasks.py's routes, orientation
 * folded in); these are the readers. */
#ifndef RACE_TRACK_H
#define RACE_TRACK_H

#include <stdint.h>

#include "race_fwconfig.h"   /* race_seg_t, the baked RACE_ROUTE_T* tables */

float wrapf(float a);        /* fold into [-pi, pi) (track._wrap) */
float clampf(float v, float lo, float hi);
int   clampi(int v, int lo, int hi);

void  track_project(const race_seg_t *g, float x, float y,
                    float *s, float *lat);
float track_heading(const race_seg_t *g, float s);
float track_curvature(const race_seg_t *g, float s);
void  track_point(const race_seg_t *g, float s, float *x, float *y);
int   track_class(float kappa);   /* 0 straight, 1 the R40 arcs */

#endif /* RACE_TRACK_H */
