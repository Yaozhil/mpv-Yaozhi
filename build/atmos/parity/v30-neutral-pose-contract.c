#include <stdio.h>
#include <string.h>
#include "video/out/secondary_ass_neutral_pose.h"

static int checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; \
    printf("FAIL %d: %s\n", __LINE__, #x); } } while (0)

struct fixture {
    struct secondary_ass_physical p;
    struct secondary_ass_present_plan prefix, next;
    struct secondary_ass_sample_snapshot before, after;
    struct secondary_ass_neutral_pose pose;
    int64_t now, f, release, prepare;
};

static struct fixture fixture(void)
{
    struct fixture f = {0};
    int64_t t = 6944444, phase = 1000000000;
    f.p = (struct secondary_ass_physical){
        .phase = phase, .interval = t, .epoch = 1, .phase_slot = 100,
        .sync_slot = 100, .sync_segment_consistent = true, .historical_id = 9,
        .last_submit_id = 10, .success_first_id = 9, .success_last_id = 10,
        .success_generation = 7, .success_contiguous = true, .next = 1,
        .last_base_slot = 104, .last_base = phase + 4 * t,
    };
    f.prefix = (struct secondary_ass_present_plan){
        .valid = true, .display_forecast = true,
        .base = {104, phase + 4 * t}, .target = {104, phase + 4 * t},
        .submit = phase + 3 * t + 1000000, .deadline = phase + 4 * t,
        .fallback_submit = phase + 3 * t + 1000000,
        .lifecycle_safe_wait = phase + 4 * t,
        .interval = t, .epoch = 1, .generation = 7,
    };
    f.p.submitted[0].id = 10;
    f.p.submitted[0].base = f.prefix.base.wall;
    f.p.submitted[0].base_slot = 104;
    f.p.submitted[0].target_slot = 104;
    f.after = (struct secondary_ass_sample_snapshot){
        .valid = true, .rate = 72, .speed = 1, .requested_speed = 1,
        .epoch = 1, .next_slot = 106, .next_wall = phase + 6 * t,
        .divisor = 2, .phase_wall = phase, .phase_slot = 100, .interval = t,
        .origin_slot = 100, .sample_slot = 104, .display_forecast = true,
    };
    f.before = f.after;
    f.before.sample_slot = 102;
    f.before.next_slot = 104;
    f.before.next_wall = f.prefix.base.wall;
    f.next = f.prefix;
    f.next.base = (struct secondary_ass_physical_point){106, phase + 6 * t};
    f.next.target = f.next.base;
    f.next.submit = phase + 5 * t + 1000000;
    f.next.fallback_submit = f.next.submit;
    f.next.deadline = f.next.target.wall;
    f.next.lifecycle_safe_wait = f.next.deadline;
    f.now = phase + 32000000;
    f.f = phase + 34000000;
    f.release = phase + 34500000;
    f.prepare = f.next.submit - 500000;
    return f;
}

static bool capture(struct fixture *f, bool valid, bool reset)
{
    return secondary_ass_neutral_pose_capture(&f->pose, &f->p, &f->prefix,
        &f->before, &f->after, true, true, true, valid, reset, 10, 7, 1);
}

static bool admit(struct fixture *f)
{
    return secondary_ass_neutral_pose_admit(&f->pose, &f->p, &f->after,
        &f->next, true, f->now, f->f, f->release, f->prepare);
}

int main(void)
{
    struct fixture f = fixture();
    CHECK(capture(&f, true, false));
    CHECK(admit(&f));
    struct secondary_ass_neutral_pose saved = f.pose;
    CHECK(!capture(&f, false, false));
    CHECK(!f.pose.valid);
    f = fixture(); CHECK(!capture(&f, true, true));
    f = fixture(); f.after.force = true; CHECK(!capture(&f, true, false));
    f = fixture(); f.after.sample_forced = true; CHECK(!capture(&f, true, false));
    f = fixture(); f.before.next_slot = 102; CHECK(!capture(&f, true, false));
    f = fixture(); f.after.next_slot = 108; CHECK(!capture(&f, true, false));
    f = fixture(); f.after.phase_wall++; CHECK(!capture(&f, true, false));
    f = fixture(); f.p.submitted[0].id = 11; CHECK(!capture(&f, true, false));
    f = fixture(); f.prefix.fresh_clock_only = true;
    CHECK(!capture(&f, true, false));

#define REJECT(mutate) do { f = fixture(); f.pose = saved; mutate; \
    CHECK(!admit(&f)); } while (0)
    REJECT(f.after.force = true);
    REJECT(f.after.held = true);
    REJECT(f.after.rate = 120);
    REJECT(f.after.divisor = 1);
    REJECT(f.after.requested_speed = 1.5);
    REJECT(f.after.origin_slot = 102);
    REJECT(f.p.epoch++);
    REJECT(f.p.success_generation++);
    REJECT(f.p.last_submit_id++);
    REJECT(f.p.success_contiguous = false);
    REJECT(f.p.outlier_pending = true);
    REJECT(f.p.history_floor_slot = 100);
    REJECT(f.next.base.slot += 2);
    REJECT(f.next.target.slot++);
    REJECT(f.next.captured_forecast++);
    REJECT(f.f = f.next.submit);
    REJECT(f.release = f.prepare);
    REJECT(f.release = f.f - 1);
    REJECT(f.p.success_last_id = f.p.historical_id);
    REJECT(f.p.historical_id = 5); // FIFO lower equals next D: known collision.
    f = fixture(); f.pose = saved;
    secondary_ass_neutral_pose_clear(&f.pose);
    CHECK(!admit(&f));

    // Real neutral FIFO occupancy advances, but no old G/D is registered into H.
    f = fixture();
    unsigned old_next = f.p.next;
    int64_t old_g = f.p.last_base_slot;
    int old_h_count = f.p.delay_count;
    f.p.last_submit_id = 11;
    secondary_ass_physical_update_observed(&f.p, false, 0,
        (struct secondary_ass_physical_point){0}, 0, 0, 0, 0, 0, f.p.interval);
    secondary_ass_physical_record_present(&f.p, true, 11, 7, 1);
    CHECK(f.p.success_contiguous && f.p.success_last_id == 11);
    CHECK(f.p.next == old_next && f.p.last_base_slot == old_g);
    CHECK(f.p.delay_count == old_h_count);
    secondary_ass_physical_feedback_point(&f.p,
        (struct secondary_ass_physical_point){105, 1034722220}, 11);
    CHECK(f.p.historical_id == 11 && f.p.phase_slot == 105);
    CHECK(f.p.delay_count == old_h_count);
    CHECK(f.p.next == old_next && f.p.last_base_slot == old_g);
    printf("neutral-pose contracts: %d checks, %d failures; CPU only, no Display claim\n",
           checks, failures);
    return failures ? 7 : 0;
}
