/* Real extracted VO callers and OSD setters/getters; real production headers. */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "video/out/secondary_ass_fresh_video.h"
#include "sub/secondary_ass_clock.h"
#define MPMAX(a,b) ((a) > (b) ? (a) : (b))
static unsigned checks, scenarios;
#define CHECK_MSG(x,m) do { checks++; if (!(x)) { fprintf(stderr,"FAIL line %d: %s: %s\n",__LINE__,m,#x); return 1; } } while(0)
#define CHECK(x) CHECK_MSG(x,"contract")
/* Lock-only shell: all actual timing and sampling functions remain production. */
static void mp_mutex_lock(int *lock) { (void)lock; }
static void mp_mutex_unlock(int *lock) { (void)lock; }
struct osd_state {
    int lock;
    bool secondary_sample_held, secondary_has_output, secondary_physical_phase;
    bool secondary_display_forecast, secondary_forecast_forced_sample;
    double secondary_rate, secondary_speed, secondary_requested_speed;
    struct secondary_ass_clock secondary_clock;
    struct secondary_ass_sampler secondary_sampler;
    uint64_t secondary_physical_epoch;
    int64_t secondary_logical_slot, secondary_target_slot;
    int64_t secondary_phase_wall, secondary_phase_slot;
    int64_t secondary_present_wall, secondary_submit_wall, secondary_vsync_interval;
};
struct frame_shell { bool display_synced; };
struct vo_internal {
    struct secondary_ass_physical secondary_physical;
    struct secondary_ass_present_fixed_offset secondary_fixed_offset;
    bool secondary_fixed_forecast, secondary_present_grid, secondary_present_plan;
    struct frame_shell *current_frame;
};
struct vo { struct vo_internal *in; struct osd_state *osd; };
#include VARIANT_HEADER

struct fixture { struct vo_internal in; struct osd_state osd; struct vo vo; };

static bool consume(struct fixture *f, struct secondary_ass_present_plan plan)
{
    struct secondary_ass_physical *p = &f->in.secondary_physical;
    struct osd_state *o = &f->osd;
    if (!plan.valid) { osd_hold_secondary_sample(o); return false; }
    if (!osd_set_secondary_physical_forecast_time(o, plan.target.wall,
            plan.base.slot, plan.target.slot, p->phase, p->phase_slot,
            p->interval, p->epoch, plan.submit))
        return false;
    return secondary_ass_sampler_update_physical_forecast(&o->secondary_sampler,
        &o->secondary_clock, o->secondary_rate, o->secondary_present_wall,
        o->secondary_logical_slot, o->secondary_target_slot,
        o->secondary_phase_wall, o->secondary_phase_slot,
        o->secondary_vsync_interval, o->secondary_physical_epoch);
}

static int initialize(struct fixture *f, int hz, int divisor, double speed)
{
    *f = (struct fixture){0};
    f->vo = (struct vo){&f->in, &f->osd};
    f->in.secondary_fixed_forecast = true;
    f->in.secondary_present_grid = f->in.secondary_present_plan = true;
    f->in.secondary_physical = (struct secondary_ass_physical){
        .phase = 1000000000, .phase_slot = 1000,
        .interval = (int64_t)(1000000000.0 / hz), .epoch = 7,
        .success_generation = 11, .success_contiguous = true,
        .sync_segment_consistent = true, .delay = 1};
    struct secondary_ass_physical *p = &f->in.secondary_physical;
    f->osd.secondary_rate = (double)hz / divisor;
    f->osd.secondary_has_output = true;
    f->osd.secondary_speed = f->osd.secondary_requested_speed = speed;
    f->osd.secondary_clock = (struct secondary_ass_clock){
        .valid = true, .pts = 1000, .wall = p->phase, .speed = speed};
    struct secondary_ass_physical_point g = secondary_ass_physical_point_at(p, 1010);
    struct secondary_ass_physical_point d = secondary_ass_physical_point_at(p, 1011);
    struct secondary_ass_present_plan plan = secondary_ass_present_plan_make(p, g, d);
    plan.display_forecast = true;
    CHECK(consume(f, plan));
    CHECK(secondary_ass_physical_submit_planned_point(p, 1, p->epoch, g, d));
    CHECK(osd_get_secondary_physical_sample_divisor(&f->osd) == divisor);
    scenarios++;
    return 0;
}

static void backend_reset_and_recover(struct fixture *f)
{
    struct secondary_ass_physical *p = &f->in.secondary_physical;
    int64_t interval = p->interval;
    secondary_ass_physical_update_observed(p, true, 0,
        (struct secondary_ass_physical_point){0}, 0, 0, 0, 0, 0, 0);
    /* Independently identified exact Sync/Present pair in the new epoch. */
    secondary_ass_physical_update_observed(p, false, 0,
        (struct secondary_ass_physical_point){0}, 2000000000, 2000000000,
        200, 200, 200, interval);
    secondary_ass_physical_record_present(p, true, 200, 12, 1);
}

static int controls(void)
{
    for (int fault = 0; fault < 13; fault++) {
        struct fixture f;
        CHECK(initialize(&f, 144, 2, 1) == 0);
        backend_reset_and_recover(&f);
        struct secondary_ass_physical *p = &f.in.secondary_physical;
        if (fault == 0) p->outlier_pending = true;
        if (fault == 1) p->phase = p->phase_slot = 0;
        if (fault == 2) p->success_contiguous = false;
        if (fault == 3) p->success_generation = 0;
        if (fault == 4) p->sync_segment_consistent = false;
        if (fault == 5) p->epoch = 0;
        if (fault == 6) p->epoch_exhausted = true;
        if (fault == 7) p->interval = 0;
        if (fault == 8) f.osd.secondary_sampler.epoch = 0;
        if (fault == 11) f.osd.secondary_sampler.divisor = 3;
        if (fault == 12) f.osd.secondary_has_output = false;
        int64_t due = 2020000000, ready = due + 1000000;
        if (fault == 9) ready = 0;
        if (fault == 10) due = 0;
        double rate = f.osd.secondary_rate;
        struct secondary_ass_sampler before = f.osd.secondary_sampler;
        struct secondary_ass_present_plan plan = secondary_forecast_fresh_video_plan(
            &f.vo, ready, due, secondary_next_sample(&f.vo, 2), 2, rate);
        CHECK(!plan.valid);
        CHECK(plan.submit == due && plan.fallback_submit == due && plan.lifecycle_safe_wait == due);
        CHECK(!consume(&f, plan));
        CHECK(memcmp(&before, &f.osd.secondary_sampler, sizeof(before)) == 0);
        scenarios++;
    }
    /* Same epoch no-due-G must remain held, even if sample.valid is false. */
    for (int held = 0; held < 2; held++) {
        struct fixture f;
        CHECK(initialize(&f, 144, 2, 1) == 0);
        f.osd.secondary_sample_held = held;
        struct secondary_ass_physical *p = &f.in.secondary_physical;
        int64_t due = f.osd.secondary_sampler.sample_wall - p->interval;
        struct secondary_ass_sampler before = f.osd.secondary_sampler;
        struct secondary_ass_present_plan plan = secondary_forecast_fresh_video_plan(
            &f.vo, due + 1000, due, secondary_next_sample(&f.vo, 2), 2, 72);
        CHECK(!plan.valid);
        CHECK(plan.submit == due && plan.fallback_submit == due && plan.lifecycle_safe_wait == due);
        CHECK(!consume(&f, plan));
        CHECK(memcmp(&before, &f.osd.secondary_sampler, sizeof(before)) == 0);
        scenarios++;
    }
    /* Held is not invalid lifecycle identity: same-epoch due G still advances. */
    for (int held = 0; held < 2; held++) {
        struct fixture f;
        CHECK(initialize(&f, 144, 2, 1.25) == 0);
        f.osd.secondary_sample_held = held;
        struct secondary_ass_physical *p = &f.in.secondary_physical;
        int64_t origin = f.osd.secondary_sampler.origin_slot;
        int64_t due = f.osd.secondary_sampler.sample_wall + 8 * p->interval;
        double previous = f.osd.secondary_sampler.pts;
        struct secondary_ass_present_plan plan = secondary_forecast_fresh_video_plan(
            &f.vo, due + 1000, due, secondary_next_sample(&f.vo, 2), 2, 72);
        CHECK(plan.valid && plan.epoch == 7);
        CHECK(plan.submit == due && plan.fallback_submit == due && plan.lifecycle_safe_wait == due);
        CHECK(consume(&f, plan));
        CHECK(f.osd.secondary_sampler.origin_slot == origin);
        CHECK(f.osd.secondary_sampler.tick > 0 && f.osd.secondary_sampler.pts > previous);
        CHECK(!f.osd.secondary_sample_held);
        scenarios++;
    }
    return 0;
}


static int phase_then_caller(void)
{
    for (int sign=-1; sign<=1; sign+=2) {
        struct fixture f;
        CHECK(initialize(&f,144,2,1)==0);
        struct secondary_ass_physical *p=&f.in.secondary_physical;
        int64_t T=p->interval, q=INT64_C(51000000000), wall=INT64_C(2000000000);
        uint64_t epoch=p->epoch;
        int64_t origin=f.osd.secondary_sampler.origin_slot;
        p->sync_qpc_ns=q;
        p->sync_count=100;
        p->sync_slot=1144;
        secondary_ass_physical_measure_anchor(p,q,100);
        secondary_ass_physical_update_observed(p,false,0,(struct secondary_ass_physical_point){0},q,wall,100,100,100,T);
        int64_t jitter=sign*(T/4+T/100);
        for(int k=1;k<=3;k++) {
            secondary_ass_physical_update_observed(p,false,0,(struct secondary_ass_physical_point){0},q+k*T+jitter,wall+k*T+jitter,100+k,99+k,100+k,T);
            if(k==2) CHECK(!p->phase && !p->phase_slot);
        }
        CHECK_MSG(p->phase>0 && p->phase_slot>0,"phase recovery");
        CHECK(p->epoch==epoch && p->history_floor_slot>0);
        osd_hold_secondary_sample(&f.osd);
        double previous=f.osd.secondary_sampler.pts;
        unsigned accepted=0;
        for(int k=0;k<72;k++) {
            int64_t due=wall+(k+4)*INT64_C(41666667);
            struct secondary_ass_present_plan plan=secondary_forecast_fresh_video_plan(
                &f.vo,due+1000000,due,secondary_next_sample(&f.vo,2),2,72);
            CHECK(plan.submit==due && plan.fallback_submit==due && plan.lifecycle_safe_wait==due);
            if(plan.valid) {
                CHECK(consume(&f,plan));
                CHECK(secondary_ass_physical_submit_planned_point(p,300+k,p->epoch,plan.base,plan.target));
                CHECK(f.osd.secondary_sampler.origin_slot==origin);
                CHECK(f.osd.secondary_sampler.pts>=previous);
                previous=f.osd.secondary_sampler.pts;
                accepted++;
            }
        }
        CHECK(accepted>20 && !f.osd.secondary_sample_held);
        scenarios++;
    }
    return 0;
}

int main(void)
{
    (void)secondary_forecast_fresh_clock_plan;
    CHECK(controls() == 0);
    CHECK(phase_then_caller() == 0);
    for (int hzindex = 0; hzindex < 4; hzindex++) {
        int hz = (int[]){60, 120, 144, 240}[hzindex];
        for (int divisor = 1; divisor <= 4; divisor++) {
            for (int speedindex = 0; speedindex < 4; speedindex++) {
                double speed = (double[]){0.5, 1, 1.25, 2}[speedindex];
                for (int held = 0; held < 2; held++) {
                    struct fixture f;
                    CHECK(initialize(&f, hz, divisor, speed) == 0);
                    f.osd.secondary_sample_held = held;
                    struct secondary_ass_sample_snapshot before = osd_get_secondary_sample_snapshot(&f.osd);
                    CHECK(before.epoch == 7 && before.held == (bool)held);
                    CHECK(before.valid == !held);
                    /* One real backend reset, followed by valid new feedback. */
                    backend_reset_and_recover(&f);
                    struct secondary_ass_physical *p = &f.in.secondary_physical;
                    CHECK(p->epoch == 8 && p->phase > 0 && p->success_contiguous);
                    CHECK(osd_get_secondary_physical_sample_divisor(&f.osd) == divisor);
                    CHECK(secondary_next_sample(&f.vo, divisor).slot == 0);
                    int64_t due = p->phase + 5 * p->interval;
                    int64_t ready = due + p->interval / 8;
                    double rate = f.osd.secondary_rate;
                    struct secondary_ass_present_plan plan = secondary_forecast_fresh_video_plan(
                        &f.vo, ready, due, secondary_next_sample(&f.vo, divisor), divisor, rate);
                    CHECK_MSG(plan.valid, "epoch bootstrap");
                    CHECK(plan.fresh_clock_only && plan.display_forecast && plan.epoch == 8);
                    CHECK(plan.submit == due && plan.fallback_submit == due && plan.lifecycle_safe_wait == due);
                    CHECK(consume(&f, plan));
                    CHECK(f.osd.secondary_sampler.epoch == 8 && !f.osd.secondary_sample_held);
                    CHECK(f.osd.secondary_sampler.tick == 0);
                    CHECK(secondary_ass_physical_submit_planned_point(p, 201, p->epoch, plan.base, plan.target));
                    int64_t origin = f.osd.secondary_sampler.origin_slot;
                    double last_pts = f.osd.secondary_sampler.pts;
                    uint64_t last_tick = 0;
                    /* 24fps mandatory draws: no further bootstrap or origin reset. */
                    for (int n = 1; n <= 72; n++) {
                        due += 41666667;
                        ready = due + 1000000;
                        struct secondary_ass_physical_point next = secondary_next_sample(&f.vo, divisor);
                        CHECK(next.slot > origin);
                        plan = secondary_forecast_fresh_video_plan(&f.vo, ready, due, next, divisor, rate);
                        CHECK(plan.submit == due && plan.fallback_submit == due && plan.lifecycle_safe_wait == due);
                        if (plan.valid) {
                            CHECK((plan.base.slot - origin) % divisor == 0);
                            CHECK(plan.base.slot >= next.slot);
                            CHECK(consume(&f, plan));
                            CHECK(secondary_ass_physical_submit_planned_point(p, 201 + n, p->epoch, plan.base, plan.target));
                            CHECK(f.osd.secondary_sampler.tick > last_tick);
                            last_tick = f.osd.secondary_sampler.tick;
                        } else {
                            CHECK(!consume(&f, plan));
                        }
                        CHECK(f.osd.secondary_sampler.origin_slot == origin);
                        CHECK(f.osd.secondary_sampler.pts >= last_pts);
                        last_pts = f.osd.secondary_sampler.pts;
                    }
                    CHECK(last_tick > 20);
                    scenarios++;
                }
            }
        }
    }
    printf("PASS scenarios=%u assertions=%u; exact VO/OSD callers, real sampler/physical headers, epoch reset recovery, original F, same-epoch guards, 24fps progress, four divisors and speeds\n", scenarios, checks);
    return 0;
}
