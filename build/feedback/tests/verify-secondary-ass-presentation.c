#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "secondary_ass_presentation.h"
#include "secondary_ass_clock.h"

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
        double sample_rate = rates[r]/ceil(rates[r]/120.5);
        struct secondary_ass_clock clock = {.speed=1};
        struct secondary_ass_sampler sampler = {0};
        secondary_ass_clock_anchor(&clock, 0, 1000000000, false);
        assert(secondary_ass_sampler_update(&sampler, &clock, sample_rate,
                                           1000000000, step));
        struct secondary_ass_presentation scheduled = {0};
        scheduled.last_display = scheduled.last_target = 1000000000;
        // Bind the VO timer to the actual production sampler: waking at the
        // due boundary must select every tick, even before the next vblank.
        for (int tick = 1; tick <= 500; tick++) {
            int64_t sample = secondary_ass_sampler_next_wall(&sampler);
            int64_t prepare = secondary_ass_sample_prepare_time(sample, step);
            assert(!secondary_ass_sampler_update_at_draw(&sampler, &clock,
                sample_rate, sample+3*step, step, prepare-1000));
            assert(sampler.tick==(uint64_t)tick-1);
            int64_t present = secondary_ass_predict_present(&scheduled, prepare, step);
            assert(present >= prepare);
            assert(secondary_ass_sampler_update_at_draw(&sampler, &clock, sample_rate,
                                                present, step, prepare));
            assert(sampler.tick == (uint64_t)tick);
            secondary_ass_present_feedback(&scheduled, present);
        }
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
    // The observed 25fps/audio failure: a cached draw at 3.640s repeated tick
    // 247, then fresh video skipped 248. Replay both sides of that boundary.
    struct secondary_ass_clock clock = {.valid=true, .speed=1};
    struct secondary_ass_sampler sampler = {
        .valid=true, .rate=71.9996125, .tick=247,
        .origin_wall=202670182, .sample_wall=3633244200,
    };
    assert(!secondary_ass_sampler_update(&sampler, &clock, sampler.rate,
                                        3640726881, 6944481));
    int64_t due=secondary_ass_sampler_next_wall(&sampler);
    struct secondary_ass_presentation q = {
        .last_display=3633782400, .last_target=3633786281,
    };
    int64_t prepare=secondary_ass_sample_prepare_time(due,6944481);
    next=secondary_ass_predict_present(&q,prepare,6944481);
    assert(secondary_ass_sampler_update(&sampler,&clock,sampler.rate,next,6944481));
    assert(sampler.tick==248);
    // Actual audio fresh174 was submitted BEFORE its own selection boundary
    // yet its predicted queue target already selected174. Hold173 until the
    // independent cached deadline; do not move the grid or queue prediction.
    sampler=(struct secondary_ass_sampler){
        .valid=true, .rate=71.9996125, .tick=173,
        .origin_wall=183992481, .sample_wall=2586783190,
    };
    uint64_t held=sampler.tick;
    due=secondary_ass_sampler_next_wall(&sampler);
    prepare=secondary_ass_sample_prepare_time(due,6944481);
    assert(2593328300<prepare);
    assert(!secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                               2603000862,6944481,2596059263));
    assert(sampler.tick==held);
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                              due+6944481*2,6944481,prepare));
    assert(sampler.tick==held+1);
    sampler.force=true;
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                              due,6944481,2593328300));
    secondary_ass_sampler_reset(&sampler);
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,71.9996125,
                                              due,6944481,2593328300));
    // A future startup origin holds until its first ordinary due boundary.
    assert(!secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                                 due+6944481,6944481,2593328300));
    assert(!secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                                 due,6944481,due+100000000));
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,90,
                                                due+100000000,6944481,due));
    clock.display_synced=true;
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,90,
                                                due+120000000,6944481,due));
    // Opposite measured case: fresh142 starts CPU work before prepare, but
    // its scheduled flip is AFTER prepare. It must absorb142 so cached ASS
    // does not queue an extra old/new pair just after the same video frame.
    clock.display_synced=false;
    sampler=(struct secondary_ass_sampler){
        .valid=true, .rate=71.9996125, .tick=141,
        .origin_wall=161987181, .sample_wall=2120331054,
    };
    due=secondary_ass_sampler_next_wall(&sampler);
    prepare=secondary_ass_sample_prepare_time(due,6944481);
    assert(2130000000<prepare && prepare<2133729465);
    assert(secondary_ass_sampler_update_at_draw(&sampler,&clock,sampler.rate,
                                                2137984262,6944481,2133729465));
    assert(sampler.tick==142);
    assert(secondary_ass_sample_prepare_time(0,6944481)==0);
    assert(secondary_ass_sample_prepare_time(123,0)==0);
    printf("PRESENTATION_PASS displays=%d frames_per_display=500 lifecycle=stale,missing,stall,source,rate-change\n",combinations);
    return 0;
}
