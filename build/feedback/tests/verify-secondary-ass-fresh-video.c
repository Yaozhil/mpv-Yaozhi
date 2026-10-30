/* Exercise the real proposed planner, immutable physical helpers and sampler. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "secondary_ass_fresh_video.h"
#include "sub/secondary_ass_clock.h"
static unsigned checks, scenarios;
#define CHECK(x) do { checks++; if (!(x)) {fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);return 1;} } while(0)
static struct secondary_ass_physical physical(int hz) {
 return (struct secondary_ass_physical){.phase=1000000000LL,.phase_slot=100,
 .interval=(int64_t)(1000000000.0/hz),.epoch=2,.success_generation=1,
 .success_contiguous=true,.sync_segment_consistent=true,.delay=1};
}
int main(void) {
 for(int hz_index=0;hz_index<4;hz_index++) {
  int hz=(int[]){60,120,144,240}[hz_index];
  for(int divisor=1;divisor<=4;divisor++) {
   double rate=(double)hz/divisor;
   for(int fps_index=0;fps_index<8;fps_index++) {
    double fps=(double[]){23.976,24,30,50,59.94,60,120,240}[fps_index];
    for(int offset=0;offset<=4;offset++) {
     struct secondary_ass_physical p=physical(hz);
     struct secondary_ass_clock clock={.valid=true,.pts=0,.wall=p.phase,.speed=1};
     struct secondary_ass_sampler s={0};
     int64_t origin=200;
     struct secondary_ass_physical_point g=secondary_ass_physical_point_at(&p,origin);
     struct secondary_ass_physical_point d=secondary_ass_physical_point_at(&p,origin+offset);
     CHECK(secondary_ass_sampler_update_physical_forecast(&s,&clock,rate,d.wall,g.slot,d.slot,
       p.phase,p.phase_slot,p.interval,p.epoch));
     p.last_base_slot=origin;
     double previous=s.pts;
     int advanced=0, held=0;
     for(int n=1;n<=(int)(fps*30);n++) {
      int64_t due=g.wall+(int64_t)((double)n*1e9/fps);
      int64_t ready=due+1000000;
      p.delay=(n/11)%5; /* changing historical delay must not accelerate ticks */
      int64_t next=secondary_ass_sampler_next_slot(&s);
      struct secondary_ass_present_plan plan=secondary_ass_fresh_video_plan(&p,origin,next,
        divisor,offset,ready,due);
      CHECK(plan.submit==due && plan.fallback_submit==due && plan.lifecycle_safe_wait==due);
      if(plan.valid) {
       CHECK(plan.base.slot>=next && (plan.base.slot-origin)%divisor==0);
       if(!(plan.target.wall>ready && plan.target.wall-ready<= (offset+2)*p.interval))
        fprintf(stderr,"hz=%d div=%d fps=%f offset=%d n=%d delta=%lld interval=%lld last=%lld G=%lld D=%lld\n",hz,divisor,fps,offset,n,(long long)(plan.target.wall-ready),(long long)p.interval,(long long)p.last_base_slot,(long long)plan.base.slot,(long long)plan.target.slot);
       CHECK(plan.target.wall>ready && plan.target.wall-ready<= (offset+2)*p.interval);
       CHECK(plan.fresh_clock_only && plan.display_forecast);
       CHECK(secondary_ass_sampler_update_physical_forecast(&s,&clock,rate,
        plan.target.wall,plan.base.slot,plan.target.slot,p.phase,p.phase_slot,p.interval,p.epoch));
       CHECK(secondary_ass_physical_submit_planned_point(&p,n,p.epoch,plan.base,plan.target));
       advanced++;
      } else {CHECK(plan.base.slot==0 && plan.target.slot==0);held++;}
      CHECK(s.pts>=previous);previous=s.pts;
      double video=(double)(due-p.phase)*1e-9;
      CHECK(s.pts-video<=(offset+3)*p.interval*1e-9+.001);
      CHECK(video-s.pts<=(1.0/fps+1.0/rate+2*p.interval*1e-9));
     }
     if(fps>=rate) {
      double elapsed=(double)((int)(fps*30))/fps;
      CHECK(fabs((double)s.tick-elapsed*rate)<3.1);
      CHECK(advanced>0);
     }
     CHECK(advanced+held==(int)(fps*30)); scenarios++;
    }
   }
  }
 }
 struct secondary_ass_physical p=physical(144);
 for(int fault=0;fault<9;fault++) {
  struct secondary_ass_physical q=p;int64_t origin=200,next=203,divisor=3,ready=2000000000LL,due=1999000000LL;
  if(fault==0)q.outlier_pending=true;if(fault==1)q.epoch=0;if(fault==2)q.epoch_exhausted=true;
  if(fault==3)q.success_contiguous=false;if(fault==4)q.success_generation=0;
  if(fault==5)q.sync_segment_consistent=false;if(fault==6)divisor=0;if(fault==7)origin=0;if(fault==8)next=202;
  struct secondary_ass_present_plan z=secondary_ass_fresh_video_plan(&q,origin,next,divisor,1,ready,due);
  CHECK(!z.valid && z.target.slot==0 && z.base.slot==0 && z.submit==due && z.fallback_submit==due && z.lifecycle_safe_wait==due);scenarios++;
 }
 printf("PASS scenarios=%u assertions=%u; mandatory deadlines, real sampler 30s progress, delay drift, holds and invalid authority\n",scenarios,checks);
 return 0;
}
