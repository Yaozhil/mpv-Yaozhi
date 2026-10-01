#include <assert.h>
#include <stdio.h>
#include "secondary_ass_physical.h"

int main(void)
{
    int rates[] = {60,75,90,120,144,165,180,240,360,480,540,720,1000};
    unsigned checks = 0;
    for (unsigned r = 0; r < sizeof(rates)/sizeof(rates[0]); r++) {
        int64_t t = 1000000000 / rates[r], origin = 1000000000;
        for (int delay = 0; delay <= 2; delay++) {
            struct secondary_ass_physical p = {0};
            secondary_ass_physical_feedback(&p, origin, t, 1);
            for (unsigned n = 2; n < 502; n++) {
                int64_t ready = origin + (int64_t)n * (3 + delay) * t - t / 2;
                int64_t slot = secondary_ass_physical_predict(&p, ready);
                assert(slot > ready);
                assert((slot - origin) % t == 0);
                secondary_ass_physical_submit(&p, n, slot);
                // Feedback is only delivered after submission, keyed to that
                // same ID. A future prediction never establishes phase.
                int64_t base = p.submitted[(p.next + 31) % 32].base;
                secondary_ass_physical_feedback(&p, base + delay * t, t, n);
                assert(p.delay == delay);
                assert(p.phase == base + delay * t);
                checks += 5;
            }
        }
        assert(secondary_ass_physical_slot(origin, t, origin) == origin + t);
        assert(secondary_ass_physical_slot(origin, t, origin+t-1) == origin+t);
        assert(secondary_ass_physical_slot(origin, t, origin+t) == origin+2*t);
        struct secondary_ass_physical p = {.phase=origin,.interval=t,.delay=1};
        assert(secondary_ass_physical_prepare(&p, origin+10*t) == origin+9*t-t/2);
        int64_t render = secondary_ass_physical_render_time(&p, origin+10*t, 1500000);
        int64_t submit = secondary_ass_physical_prepare(&p, origin+10*t);
        assert(render <= submit);
        assert(origin+10*t - t - render >= 2500000);
        assert(submit - render < 2500000);
        checks += 7;
    }
    struct secondary_ass_physical p = {.phase=1,.interval=1,.last_base=INT64_MAX};
    assert(!secondary_ass_physical_predict(&p, 4));
    assert(!secondary_ass_physical_slot(INT64_MAX-1, 3, INT64_MAX));
    p=(struct secondary_ass_physical){.phase=1000000000,.interval=1000000};
    secondary_ass_physical_submit(&p, 12, 1100000000);
    secondary_ass_physical_feedback(&p, 1090000000, 1000000, 12);
    assert(p.delay_count==0); // late prediction cannot become fake zero delay
    secondary_ass_physical_feedback(&p, 1200000000, 2000000, 13);
    assert(p.delay_count==0 && !p.last_base); // monitor change clears queue history
    printf("secondary physical display phase: PASS (%u checks)\n", checks+4);
    return 0;
}
