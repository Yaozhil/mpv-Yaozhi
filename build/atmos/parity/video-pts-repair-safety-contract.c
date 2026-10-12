
#include <stdio.h>
#include <stdint.h>
#include <math.h>
#include "filters/video_pts_repair.h"
static int checks;
#define C(x) do{checks++;if(!(x)){printf("FAIL line=%d\n",__LINE__);return 9;}}while(0)
struct stream {struct mp_video_pts_repair repair;bool seeded;double raw,out,raw_pos,out_pos,max_excess;int changes,negative,block_seen;};
static void tick(struct stream *s,double raw,bool eligible,double d,double q){
 double out=mp_video_pts_repair_apply(&s->repair,eligible,raw,s->seeded?s->out:raw,d,q);
 if(s->seeded){double a=raw-s->raw,b=out-s->out;s->raw_pos+=fmax(a,0);s->out_pos+=fmax(b,0);if(b<0)s->negative++;}
 s->seeded=true;s->raw=raw;s->out=out;
 if(out!=raw)s->changes++;
 if(s->repair.blocked)s->block_seen++;
 double excess=s->out_pos-s->raw_pos;if(excess>s->max_excess)s->max_excess=excess;
}
static void report(const char *name,const struct stream *s){printf("CASE %s raw_positive=%.12f out_positive=%.12f excess=%.12f max_excess=%.12f changes=%d negative=%d blocked_seen=%d\n",name,s->raw_pos,s->out_pos,s->out_pos-s->raw_pos,s->max_excess,s->changes,s->negative,s->block_seen);}
int main(void){
 const double d=.016666666,q=.001,M=d+q;
 struct stream s={0};
 for(int i=0;i<100000;i++){tick(&s,1,true,d,q);C(s.max_excess<=M+1e-9);}
 C(s.changes==1&&s.negative==1&&s.repair.blocked);report("100000_identical",&s);
 // A short VFR tail after the first bad duplicate must not allow re-entry.
 s=(struct stream){0};
 for(int run=0;run<10000;run++){
  double base=1+run*.1;double a[]={base,base,base+.017,base+.034,base+.044,base+.070};
  for(int i=0;i<6;i++){tick(&s,a[i],true,d,q);C(s.max_excess<=M+1e-8);}
 }
 C(s.changes==3&&s.negative==1&&s.repair.blocked);report("10000_short_vfr_episodes",&s);
 // Fully successful repair prefixes must telescope back to original anchors.
 s=(struct stream){0};
 for(int run=0;run<10000;run++){
  double base=1+run*.1;double a[]={base,base,base+.017,base+.034,base+.067,base+.083};
  for(int i=0;i<6;i++){tick(&s,a[i],true,d,q);C(s.max_excess<=M+1e-8);}
 }
 C(!s.repair.blocked&&s.negative==0&&fabs(s.out_pos-s.raw_pos)<1e-8);report("10000_valid_anchor_episodes",&s);
 // Disabled stays disabled through eligibility/metadata flips, not just a
 // constant-duration stream. Explicit caller reset alone re-arms the helper.
 s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);tick(&s,1,true,d,q);C(s.repair.blocked);
 for(int i=0;i<10000;i++){
  tick(&s,1+i*.010,i%2,d+(i%3)*.01,i%3?q:0);C(s.repair.blocked&&s.out==s.raw&&s.max_excess<=M+1e-9);
 }
 report("blocked_eligibility_metadata_flips",&s);
 s.repair=(struct mp_video_pts_repair){0};s.seeded=false;
 tick(&s,200,true,d,q);tick(&s,200,true,d,q);C(s.repair.active&&!s.repair.blocked&&s.out>200);
 // Every active abnormal exit must latch, even if its new metadata is finite
 // or temporarily ineligible. A later duplicate cannot silently re-enable.
 for(int kind=0;kind<6;kind++){
  s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);C(s.repair.active);
  if(kind==0)tick(&s,1,true,d,q);
  if(kind==1)tick(&s,.5,true,d,q);
  if(kind==2)tick(&s,1.005,false,d,q);
  if(kind==3)tick(&s,1.005,true,.04,q);
  if(kind==4)tick(&s,1.005,true,0,q);
  if(kind==5)tick(&s,1.005,true,d,.01);
  C(s.repair.blocked&&!s.repair.active&&s.max_excess<=M+1e-9);
  for(int i=0;i<1000;i++){tick(&s,2,true,d,q);C(s.repair.blocked&&s.out==2&&s.max_excess<=M+1e-9);}
 }
 // Deterministic mixed duplicate/VFR/backwards streams. Bound is per explicit
 // reset interval. Existing raw negative steps are not silently erased.
 uint32_t rng=0x15a52u;double biggest=0;
 for(int run=0;run<1000;run++){
  s=(struct stream){0};double raw=1;
  for(int i=0;i<1000;i++){
   rng=rng*1664525u+1013904223u;unsigned kind=(rng>>16)%10;
   raw+=kind<3?0:kind==3?-.004:kind==4?.010:kind==5?.033:.017;
   tick(&s,raw,true,d,q);C(s.max_excess<=M+1e-7);C(s.out_pos-s.raw_pos>=-1e-7);
  }
  if(s.max_excess>biggest)biggest=s.max_excess;
 }
 printf("CASE 1000_mixed_streams maximum_excess=%.12f bound=%.12f\n",biggest,M);
 // A separate LIMITATION: mpv also discards >=10000-second forward steps.
 // A bound on positive-part sums alone does not cover crossing that cutoff.
 s=(struct stream){0};tick(&s,1,true,d,q);tick(&s,1,true,d,q);
 double prev=s.out,raw_prev=s.raw;tick(&s,10001.005,true,d,q);
 double old_delta=s.raw-raw_prev,new_delta=s.out-prev;
 double old_player=old_delta>0&&old_delta<1e4?old_delta:0;
 double new_player=new_delta>0&&new_delta<1e4?new_delta:0;
 C(old_player==0&&new_player>9999);
 printf("LIMITATION large_discontinuity_cutoff raw_delta=%.12f out_delta=%.12f player_added_difference=%.12f\n",old_delta,new_delta,new_player-old_player);
 printf("PASS fail_closed_prefix checks=%d; no universal player-clock or Display claim\n",checks);
 return 0;
}
