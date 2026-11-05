#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "video/out/secondary_ass_physical.h"
#include "video/out/secondary_ass_fresh_video.h"
#include "sub/secondary_ass_clock.h"
static unsigned long long checks, cases;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(2); } } while(0)
static const int64_t origin = INT64_C(1000000000);
static const int64_t qpc_origin = INT64_C(51000000000);
static void update(struct secondary_ass_physical *p, int64_t qpc, int64_t wall,
                   uint32_t count, uint32_t present, uint64_t id, int64_t T)
{
    secondary_ass_physical_update_observed(p, false, 0,
        (struct secondary_ass_physical_point){0}, qpc, wall,
        count, present, id, T);
}
static struct secondary_ass_physical gap(int64_t T, uint32_t count, int sign)
{
    struct secondary_ass_physical p={0};
    update(&p,qpc_origin,origin,count,count,1,T);
    CHECK(p.phase==origin && p.phase_slot==INT64_C(4294967296));
    int64_t jitter = sign * (T / 4 + T / 100);
    for(int k=1;k<=2;k++) {
        update(&p,qpc_origin+k*T+jitter,origin+k*T+jitter,
            count+k,count+k-1,(uint64_t)k+1,T);
    }
    CHECK(!p.phase && !p.phase_slot && !p.outlier_pending);
    CHECK(!p.sync_segment_consistent && p.history_floor_slot==INT64_C(4294967298));
    return p;
}
static void fixed_case(int64_t T, uint32_t count, int sign, int offset, int expect_fixed)
{
    cases++;
    struct secondary_ass_physical p=gap(T,count,sign);
    int64_t jitter = sign * (T / 4 + T / 100);
    const int64_t floor=p.history_floor_slot;
    const uint64_t epoch=p.epoch;
    for(int k=3;k<=10003;k++) {
        update(&p,qpc_origin+k*T+jitter,origin+k*T+jitter,
            count+k,count+k+offset,(uint64_t)k+1,T);
        CHECK(p.sync_segment_consistent && !p.outlier_pending);
        CHECK(p.historical_id==1 && !p.delay_count && !p.next);
        CHECK(p.history_floor_slot==floor && p.epoch==epoch);
        CHECK(p.sync_qpc_ns==qpc_origin+k*T+jitter);
        struct secondary_ass_physical_point next=
            secondary_ass_physical_predict_point(&p,origin+(k+1)*T+jitter);
        if(expect_fixed) {
            CHECK(p.phase==origin+k*T+jitter || (k>3 && p.phase==origin+3*T+jitter));
            CHECK(p.phase_slot==INT64_C(4294967299));
            CHECK(next.slot>p.sync_slot && next.wall>origin+(k+1)*T+jitter);
        } else {
            CHECK(!p.phase && !p.phase_slot && !next.slot);
        }
    }
    if (!expect_fixed) return;
    // A restored Sync phase is not fake historical Present feedback. A new,
    // genuine planned submission still has to cross the preserved floor.
    struct secondary_ass_physical_point base=secondary_ass_physical_predict_point(
        &p,origin+10005*T+jitter);
    struct secondary_ass_physical_point target=secondary_ass_physical_point_at(&p,base.slot+1);
    CHECK(secondary_ass_physical_submit_planned_point(&p,20001,p.epoch,base,target));
    CHECK(p.submitted[0].base_slot==base.slot && p.submitted[0].target_slot==target.slot);
    const int delay_before=p.delay_count;
    const uint64_t historical_before=p.historical_id;
    // An unregistered/gap historical ID remains barred from crossing a raw offset.
    update(&p,qpc_origin+10006*T+jitter,origin+10006*T+jitter,
        count+10006,count+10005,19999,T);
    CHECK(p.delay_count==delay_before && p.historical_id==historical_before);
    // Accepted post-floor history learns actual-minus-immutable-base only.
    update(&p,qpc_origin+10007*T+jitter,origin+10007*T+jitter,
        count+10007,count+10006,20001,T);
    CHECK(p.historical_id==20001);
    CHECK(p.submitted[0].base_slot==base.slot && p.submitted[0].target_slot==target.slot);
    CHECK(p.delay_count==1 && p.delay==0);
    CHECK(p.epoch==epoch);
}
static void negative_case(int64_t T)
{
    cases++;
    struct secondary_ass_physical p=gap(T,100,1), saved=p;
    // A duplicate recovery observation is not a stable post-recovery segment.
    update(&p,p.sync_qpc_ns,origin+2*T+T/4+T/100,p.sync_count,p.sync_count-1,3,T);
    CHECK(!p.phase && !p.sync_segment_consistent && p.historical_id==1);
    p=saved;
    update(&p,qpc_origin+3*T+T/4+T/100,origin+3*T+T/4+T/100,103,136,4,T);
    CHECK(!p.phase && p.historical_id==1 && !p.delay_count);
    p=saved;
    update(&p,qpc_origin+3*T+T/4+T/100,0,103,102,4,T);
    CHECK(!p.phase && p.historical_id==1 && !p.delay_count);
    p=saved;
    update(&p,qpc_origin+3*T+T/4+T/100,origin+3*T+T/4+T/100,103,102,0,T);
    CHECK(!p.phase && p.historical_id==1 && !p.delay_count);
    p=saved; p.epoch_exhausted=true;
    update(&p,qpc_origin+3*T+T/4+T/100,origin+3*T+T/4+T/100,103,102,4,T);
    CHECK(!p.phase && p.historical_id==1 && !p.delay_count);
    p=saved;
    secondary_ass_physical_update_observed(&p,true,0,(struct secondary_ass_physical_point){0},
        qpc_origin+3*T,origin+3*T,103,102,4,T);
    CHECK(!p.phase && !p.history_floor_slot && p.epoch==saved.epoch+1);
}
int main(int argc, char **argv)
{
    int expect_fixed=argc>1 && !strcmp(argv[1],"fixed");
    int rates[]={60,120,144,165,240,360,480};
    for(unsigned r=0;r<sizeof(rates)/sizeof(rates[0]);r++) {
        int64_t T=INT64_C(1000000000)/rates[r];
        for(int sign=-1;sign<=1;sign+=2)
            for(int offset=-1;offset<=1;offset+=2) {
                fixed_case(T,100,sign,offset,expect_fixed);
                fixed_case(T,UINT32_MAX-1,sign,offset,expect_fixed);
            }
        if(expect_fixed) negative_case(T);
    }
    printf("%s: %llu cases; %llu checks; real headers; separate QPC and wall domains\n",
        expect_fixed ? "FIXED" : "BASELINE_PERMANENT_PHASE_ZERO",cases,checks);
    return 0;
}
