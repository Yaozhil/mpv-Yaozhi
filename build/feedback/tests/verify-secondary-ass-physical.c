#include <assert.h>
#include <stdio.h>
#include "secondary_ass_physical.h"
#include "secondary_ass_clock.h"

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
    assert(p.delay_count==0 && p.last_base); // one interval cannot imply a mode change
    secondary_ass_physical_reset(&p); // explicit lifecycle epoch clears history
    assert(!p.last_base && !p.delay_count);
    checks += 4;

    // Successful Present IDs survive temporarily zero historical statistics.
    p=(struct secondary_ass_physical){.phase=1000000000,.interval=1000000,.delay=1};
    secondary_ass_physical_update(&p, false, 20, 1010000000, 0, 0, 0);
    assert(p.phase==1000000000 && p.interval==1000000 && p.delay==1);
    assert(p.last_base==1009000000 && p.submitted[0].id==20);
    assert(secondary_ass_physical_predict(&p, 1008500000)==1011000000);
    secondary_ass_physical_update(&p, false, 20, 1011000000, 0, 0, 0);
    assert(p.next==1 && p.last_base==1009000000); // no new Present, no fake slot
    secondary_ass_physical_feedback(&p, 1010000000, 1000000, 20);
    assert(p.delay_count==1 && p.delay==1);
    secondary_ass_physical_feedback(&p, 1010000000, 1000000, 20);
    assert(p.delay_count==1); // repeated historical ID is not another sample
    secondary_ass_physical_update(&p, true, 21, 1012000000, 1011000000, 1000000, 21);
    assert(!p.phase && !p.interval && !p.last_base && !p.historical_id);
    assert(!p.delay && !p.delay_count && !p.delay_next && !p.next);
    for (unsigned i=0;i<32;i++)
        assert(!p.submitted[i].id && !p.submitted[i].base);
    // Recovery learns the backend's physical period, independently of a 60Hz
    // nominal/display-fps override which is not used for physical feedback.
    secondary_ass_physical_update(&p, false, 22, 0, 2000000000, 1000000000/144, 22);
    assert(p.phase==2000000000 && p.interval==1000000000/144 && !p.delay_count);
    checks += 41;

    // Regression: preparing a fresh image crosses the next physical boundary.
    // The old loop rejected cache using the earlier current-frame deadline,
    // then could sleep until queued_pts+40ms. The production decision now
    // authorizes a cache task directly, bounded by the later fresh opportunity.
    const int64_t t=1000000000/144, sample=10000000000;
    const int64_t now=sample-300000, queued_pts=sample-100000;
    p=(struct secondary_ass_physical){.phase=sample-t,.interval=t,.last_base=sample-t};
    int64_t prepare=secondary_ass_physical_cache_prepare(&p, now, sample,
        queued_pts, 40000000, 2*t, 500000, 100000, 1000000, sample-2*t);
    assert(prepare>0 && prepare<=now);
    int64_t old_deadline=secondary_ass_physical_predict(&p, queued_pts)-t/4;
    assert(!secondary_ass_budget_before_deadline(now, old_deadline,
        500000, 1000000, 1000000));
    assert(secondary_ass_physical_predict(&p, now+500000)==sample+t);
    // Each denial lets fresh video proceed rather than deferring to no task.
    assert(!secondary_ass_physical_cache_prepare(&p, now, sample, queued_pts,
        t-1, 2*t, 500000, 100000, 1000000, sample-2*t)); // source faster than display
    assert(!secondary_ass_physical_cache_prepare(&p, now, sample, queued_pts,
        40000000, 2*t, 30000000, 100000, 1000000, sample-2*t)); // overload
    assert(!secondary_ass_physical_cache_prepare(&p, now, sample+t, queued_pts,
        40000000, 2*t, 500000, 100000, 1000000, sample-2*t)); // same fresh slot
    assert(!secondary_ass_physical_cache_prepare(&p, now, sample, queued_pts,
        40000000, 2*t, 500000, 100000, 10000000, sample-2*t)); // no deadline headroom
    assert(!secondary_ass_physical_cache_prepare(&p, now, sample, queued_pts,
        40000000, 2*t, 500000, 100000, 1000000, sample+t)); // redraw throttle too late
    assert(!secondary_ass_physical_cache_prepare(&p, now, 0, queued_pts,
        40000000, 2*t, 500000, 100000, 1000000, sample-2*t));
    prepare=secondary_ass_physical_cache_prepare(&p, now, sample, queued_pts,
        1000000000/120, 2*t, 500000, 100000, 1000000, sample-2*t);
    assert(prepare>0); // source120 still has an affordable earlier cache slot at 144Hz
    checks += 10;

    // Actual v8 startup: its first physical cached draw adopted 280.090872ms
    // from the fallback sampler, outside the historical 250.407800ms lattice.
    // A physical sampler must instead initialize from the physical prediction.
    const int64_t observed_phase=250407800, observed_t=6944481;
    const int64_t fallback_next=280090872, first_ready=276996700+100000;
    p=(struct secondary_ass_physical){.phase=observed_phase,.interval=observed_t};
    int64_t first_physical=secondary_ass_physical_predict(&p, first_ready);
    assert(first_physical==278185724);
    assert((fallback_next-observed_phase)%observed_t!=0);
    assert((first_physical-observed_phase)%observed_t==0);
    struct secondary_ass_clock clock={0};
    secondary_ass_clock_set_speed(&clock, 1, observed_phase);
    assert(secondary_ass_clock_anchor(&clock, 0, observed_phase, false));
    struct secondary_ass_sampler old_sampler={0}, physical_sampler={0};
    double rate=1e9/(2*observed_t);
    assert(secondary_ass_sampler_update(&old_sampler, &clock, rate,
        fallback_next, observed_t));
    assert((old_sampler.origin_wall-observed_phase)%observed_t!=0);
    assert(secondary_ass_sampler_update(&physical_sampler, &clock, rate,
        first_physical, observed_t));
    assert((physical_sampler.origin_wall-observed_phase)%observed_t==0);
    for (unsigned n=1;n<=100;n++) {
        int64_t next=secondary_ass_sampler_next_wall(&physical_sampler);
        assert(next==first_physical+(int64_t)n*2*observed_t);
        assert((next-observed_phase)%observed_t==0);
        assert(secondary_ass_sampler_update(&physical_sampler, &clock, rate,
            next, observed_t));
        checks += 3;
    }
    checks += 8;
    // Ten-minute fixed-mode runs use the production observation and sampler
    // paths. Counts wrap and occasionally omit one refresh; timestamps jitter
    // enough to exceed the rejected instantaneous 1% period-reset rule.
    // These are deterministic models, never evidence of physical displays.
    int long_rates[] = {60, 120, 144, 165};
    for (unsigned r = 0; r < sizeof(long_rates)/sizeof(long_rates[0]); r++) {
        int hz = long_rates[r], divisor = hz > 120 ? 2 : 1;
        int64_t seed = 1000000000 / hz;
        int64_t actual_t = (int64_t)(seed * (1.0 - 114e-6));
        const int64_t start = INT64_C(4000000000000000);
        p = (struct secondary_ass_physical){0};
        struct secondary_ass_clock media = {0};
        struct secondary_ass_sampler sampler = {0};
        secondary_ass_clock_set_speed(&media, 1, start);
        assert(secondary_ass_clock_anchor(&media, 0, start, false));
        uint32_t raw = UINT32_MAX - 100;
        int64_t origin_slot = 0;
        uint64_t previous_tick = 0;
        double previous_pts = 0;
        for (unsigned n = 0; n <= (unsigned)hz * 600; n++) {
            if (n && n % 1039)
                raw++;
            int64_t noise = n % 17 == 0 ? 80000 : (n % 2 ? 30000 : -30000);
            int64_t observed = start + (int64_t)n * actual_t + noise;
            secondary_ass_physical_update_observed(&p, false, 0,
                (struct secondary_ass_physical_point){0}, observed, observed,
                raw, raw, n + 1, seed);
            assert(p.epoch == 1 && p.phase_slot == INT64_C(4294967296) + n);
            if (!n)
                origin_slot = p.phase_slot;
            assert(p.phase == observed && p.interval > 0);
            if (n > (unsigned)hz * 5)
                assert(p.interval > actual_t - 5000 && p.interval < actual_t + 5000);
            bool changed = secondary_ass_sampler_update_physical(&sampler,
                &media, (double)hz / divisor, observed, p.phase_slot,
                p.phase, p.phase_slot, p.interval, p.epoch);
            assert(changed == (n % divisor == 0));
            assert(sampler.origin_slot == origin_slot && sampler.divisor == divisor);
            assert(sampler.tick == n / divisor && sampler.tick >= previous_tick);
            assert(secondary_ass_sampler_next_slot(&sampler) ==
                origin_slot + ((int64_t)n / divisor + 1) * divisor);
            if (changed) {
                if (n)
                    assert(sampler.pts > previous_pts);
                // No accumulated 114ppm wall oscillator error over 600s.
                double ideal = (double)((int64_t)n * actual_t) * 1e-9;
                assert(fabs(sampler.pts - ideal) <= 0.000081);
                previous_pts = sampler.pts;
            } else {
                assert(sampler.pts == previous_pts);
            }
            previous_tick = sampler.tick;
            int64_t saved_phase = p.phase, saved_slot = p.phase_slot;
            unsigned saved_samples = p.delay_count;
            secondary_ass_physical_update_observed(&p, false, 0,
                (struct secondary_ass_physical_point){0}, observed, observed,
                raw, raw, n + 1, seed);
            assert(p.phase == saved_phase && p.phase_slot == saved_slot &&
                   p.delay_count == saved_samples); // one history ID is immutable
            checks += 10;
        }
        // Refining the period by .1ms cannot turn an occupied slot into a new
        // opportunity, unlike comparing floating wall timestamps.
        struct secondary_ass_physical_point first = secondary_ass_physical_predict_point(
            &p, p.phase + actual_t / 2);
        secondary_ass_physical_submit_point(&p, 2000000, first);
        p.phase += 100000;
        struct secondary_ass_physical_point second = secondary_ass_physical_predict_point(
            &p, p.phase + actual_t / 2);
        assert(second.slot > first.slot);
        int64_t submit = secondary_ass_physical_submit_time(&p, second.wall);
        assert(submit > second.wall - (p.delay + 1) * p.interval);
        assert(submit < second.wall - p.delay * p.interval);
        assert(secondary_ass_physical_render_slot_time(&p, second.wall, 200000) ==
               submit - 200000);
        uint64_t epoch = p.epoch;
        secondary_ass_physical_reset(&p);
        assert(p.epoch == epoch + 1 && !p.phase && !p.last_base_slot && !p.delay_count);
        checks += 5;
    }
    printf("secondary physical display phase: PASS (%u checks; modeled 60/120/144/165Hz x 600s)\n", checks);
    return 0;
}
