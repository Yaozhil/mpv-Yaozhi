#include <stdio.h>
#include <stdint.h>
#include <math.h>
#include "filters/video_pts_repair.h"
static int checks;
#define C(x) do {checks++;if(!(x)){printf("FAIL line=%d\n",__LINE__);return 9;}}while(0)
struct stream {struct mp_video_pts_repair r;bool seeded;double raw,out,rawpos,outpos,maximum;int changed,negative,hold;};
static void tick(struct stream *s,double raw,bool eligible,double d,double q){
 double out=mp_video_pts_repair_apply(&s->r,eligible,raw,s->seeded?s->out:raw,d,q);
 if(s->seeded){s->rawpos+=fmax(raw-s->raw,0);s->outpos+=fmax(out-s->out,0);if(out<s->out)s->negative++;}
 s->seeded=true;s->raw=raw;s->out=out;s->changed+=out!=raw;s->hold+=s->r.recovering;
 if(s->outpos-s->rawpos>s->maximum)s->maximum=s->outpos-s->rawpos;
}
static void show(const char *name,struct stream *s){printf("CASE %s raw_positive=%.12f out_positive=%.12f excess=%.12f max_excess=%.12f changes=%d negative=%d hold=%d blocked=%d\n",name,s->rawpos,s->outpos,s->outpos-s->rawpos,s->maximum,s->changed,s->negative,s->hold,s->r.blocked);}
int main(void){
 const double d=.016666666,q=.001,M=d+q;struct stream s={0};
 for(int i=0;i<100000;i++){tick(&s,1,true,d,q);C(s.maximum<=M+1e-9);}
 C(s.negative==0&&!s.r.blocked&&s.r.recovering);show("100000_identical",&s);
 s=(struct stream){0};
 for(int run=0;run<10000;run++){
  double b=1+run*.1,a[]={b,b,b+.017,b+.034,b+.044,b+.070};
  for(int i=0;i<6;i++){tick(&s,a[i],true,d,q);C(s.maximum<=M+1e-8);C(s.out>=s.raw&&s.out-s.raw<=M+1e-8);}
 }
 C(s.negative==0&&!s.r.blocked&&!s.r.active&&s.changed==40000);C(fabs(s.outpos-s.rawpos)<1e-8);show("10000_short_vfr_episodes",&s);
 s=(struct stream){0};
 for(int run=0;run<10000;run++){
  double b=1+run*.1,a[]={b,b,b+.017,b+.034,b+.067,b+.083};
  for(int i=0;i<6;i++){tick(&s,a[i],true,d,q);C(s.maximum<=M+1e-8);}
 }
 C(s.negative==0&&!s.r.blocked&&s.changed==30000);C(fabs(s.outpos-s.rawpos)<1e-8);show("10000_valid_anchor_episodes",&s);
 // All positive CFR/VFR intervals are unchanged, even with historical faults.
 for(int eligible=0;eligible<2;eligible++){
  s=(struct stream){0};double a[]={0,.01,.035,.04,.1,.117,.14,.144,.19};
  for(int i=0;i<9;i++){tick(&s,a[i],eligible,d,q);C(s.out==a[i]);}
 }
 // Actual backwards raw, metadata and eligibility failures still pass raw and
 // fail closed. This proposal handles a monotonic short tail, not discontinuity.
 for(int kind=0;kind<7;kind++){
  s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);C(s.r.active);
  if(kind==0)tick(&s,.5,true,d,q);
  if(kind==1)tick(&s,1.005,false,d,q);
  if(kind==2)tick(&s,1.005,true,.04,q);
  if(kind==3)tick(&s,1.005,true,0,q);
  if(kind==4)tick(&s,1.005,true,d,.01);
  if(kind==5)tick(&s,NAN,true,d,q);
  if(kind==6)tick(&s,.9995,true,d,q);
  C(s.r.blocked&&!s.r.active);
  for(int i=0;i<1000;i++){tick(&s,2,true,d,q);C(s.r.blocked&&s.out==2&&s.maximum<=M+1e-8);}
 }

 // A recovery anchor may be far smaller than next-quantum; preserve it exactly.
 s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);tick(&s,1,true,d,q);
 C(s.r.recovering&&!s.r.blocked);double recovery_anchor=s.out+.0001;
 tick(&s,recovery_anchor,true,d,q);
 C(s.out==recovery_anchor&&!s.r.active&&!s.r.recovering&&!s.r.blocked);
 tick(&s,recovery_anchor,true,d,q);C(s.r.active&&!s.r.blocked);
 // Captured startup triple raw=734.750 must not disable all later prefixes.
 s=(struct stream){0};double prefix[]={734.683,734.683,734.700,734.717,734.750,734.750,734.750};
 for(int i=0;i<7;i++)tick(&s,prefix[i],true,d,q);
 C(s.r.recovering&&!s.r.blocked&&s.negative==0&&s.hold==1);
 C(fabs(s.out-734.766666666)<1e-8);
 tick(&s,734.817,true,d,q);C(s.out==734.817&&!s.r.active&&!s.r.recovering);
 tick(&s,735.017,true,d,q);tick(&s,735.017,true,d,q);C(s.r.active&&!s.r.blocked&&s.out>735.017);
 uint32_t rng=0x15a52;double max_mono=0,max_mixed=0;
 for(int run=0;run<1000;run++){
  s=(struct stream){0};double raw=1;
  for(int i=0;i<1000;i++){
   rng=rng*1664525u+1013904223u;unsigned kind=(rng>>16)%10;
   raw+=kind<3?0:kind==3?.001:kind==4?.01:kind==5?.033:.017;
   tick(&s,raw,true,d,q);C(s.negative==0&&!s.r.blocked);C(s.maximum<=M+1e-7);C(s.out-s.raw>=0&&s.out-s.raw<=M+1e-7);
  }
  if(s.maximum>max_mono)max_mono=s.maximum;
 }
 for(int run=0;run<1000;run++){
  s=(struct stream){0};double raw=1;
  for(int i=0;i<1000;i++){
   rng=rng*1664525u+1013904223u;unsigned kind=(rng>>16)%10;
   raw+=kind<3?0:kind==3?-.004:kind==4?.01:kind==5?.033:.017;
   tick(&s,raw,true,d,q);C(s.maximum<=M+1e-7);C(s.outpos-s.rawpos>=-1e-7);
  }
  if(s.maximum>max_mixed)max_mixed=s.maximum;
 }
 printf("CASE 1000_monotonic_and_1000_mixed maximum_mono=%.12f maximum_mixed=%.12f bound=%.12f\n",max_mono,max_mixed,M);
 // Arbitrary large gaps can still cross player's 10000-second delta cutoff.
 s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);double previous=s.out;tick(&s,10001.005,true,d,q);
 C(s.raw-1>=10000&&s.out-previous<10000);
 printf("LIMITATION actual backwards or invalid metadata still latch; zero hold intervals remain; large-discontinuity cutoff unchanged\n");
 printf("PASS bounded_prefix_hold checks=%d no GPU Display claim\n",checks);return 0;
}
