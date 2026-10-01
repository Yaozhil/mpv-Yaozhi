#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "secondary_ass_presentation.h"

int main(void)
{
    const double rates[] = {59.94, 60, 75, 90, 119.88, 120, 144, 165, 180, 240, 360, 480, 540};
    int combinations = 0;
    for (unsigned r = 0; r < sizeof(rates)/sizeof(rates[0]); r++) {
        int64_t step = (int64_t)(1000000000 / rates[r]);
        struct secondary_ass_presentation p = {0};
        int64_t now = 1000000000;
        int64_t target = secondary_ass_predict_present(&p, now, step);
        for (int f = 0; f < 500; f++) {
            secondary_ass_present_feedback(&p, target);
            // Random-looking CPU completion phase does not alter a queued
            // presentation lattice when real feedback is available.
            now = target - step/2 + (f%7 - 3)*10000;
            int64_t next = secondary_ass_predict_present(&p, now, step);
            assert(next - target == step);
            target = next;
        }
        // Stale/missing feedback and a long stall must not cause backsteps or
        // a catch-up burst; predict one future slot in the existing lattice.
        secondary_ass_present_feedback(&p, target - step*5);
        int64_t next = secondary_ass_predict_present(&p, target-step/2, step);
        assert(next == target+step);
        secondary_ass_present_feedback(&p, -1);
        now = next + step*23 + step/3;
        next = secondary_ass_predict_present(&p, now, step);
        assert(next > now && next-now <= step);
        int64_t draw_step = step*(int)ceil(rates[r]/120.5);
        struct secondary_ass_presentation q = {0};
        int64_t deadline = secondary_ass_next_draw(&q, now, draw_step);
        secondary_ass_consume_draw(&q, now+draw_step/3); // fresh source arrives
        assert(secondary_ass_next_draw(&q, now+draw_step/3, draw_step)==deadline);
        secondary_ass_consume_draw(&q, deadline+10000);
        assert(q.next_draw==deadline+draw_step);
        secondary_ass_consume_draw(&q, q.next_draw+draw_step*10+1234);
        assert(q.next_draw>deadline+draw_step*11+1234);
        assert(q.next_draw<=deadline+draw_step*12+1234);
        combinations++;
    }
    struct secondary_ass_presentation p={0};
    int64_t first=secondary_ass_predict_present(&p,1000000000,6944444);
    secondary_ass_present_feedback(&p,first);
    int64_t next=secondary_ass_predict_present(&p,1005000000,4166666);
    assert(next==1009166666); // switch to another display, discard old lattice
    printf("PRESENTATION_PASS displays=%d frames_per_display=500 lifecycle=stale,missing,stall,source,rate-change\n",combinations);
    return 0;
}
