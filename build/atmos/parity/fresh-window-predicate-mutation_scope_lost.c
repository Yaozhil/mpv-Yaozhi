
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include "video/out/secondary_ass_present_plan.h"
static unsigned checks,failures;
#define CHECK(x) do {checks++;if(!(x)){failures++;if(failures<5)printf("FAIL %d: %s\n",__LINE__,#x);}}while(0)
static bool reject(const struct secondary_ass_present_plan *input,
                   int64_t original_video_target,bool uncaptured_fixed_fresh) {
 struct secondary_ass_present_plan present_plan=*input;
 return present_plan.display_forecast && present_plan.valid &&
                    !present_plan.fresh_clock_only &&
                    present_plan.base.wall < original_video_target &&
                    (false ||
                     present_plan.submit < original_video_target);
}
int main(void) {
 // Real observed proposal: G is historical identity, S can satisfy video F.
 struct secondary_ass_present_plan p={.valid=true,.display_forecast=true,
  .base={.wall=25209142800LL},.target={.wall=25229973366LL},
  .submit=25224029844LL};
 CHECK(!reject(&p,25216366491LL,true));
 CHECK(reject(&p,25216366491LL,false)); // Captured/legacy scope remains protected.
 int hz[]={60,120,144,165,240,360,500};
 for(int h=0;h<7;h++)for(int offset=0;offset<=4;offset++) {
  int64_t T=1000000000LL/hz[h],G=1000000000LL,D=G+offset*T;
  int64_t guard=T/4<1000000?T/4:1000000,S=D-T+guard;
  p=(struct secondary_ass_present_plan){.valid=true,.display_forecast=true,
    .base={.wall=G},.target={.wall=D},.submit=S};
  // Compare decisive boundaries against independently stated expectations.
  CHECK(!reject(&p,G,false));CHECK(!reject(&p,G-1,true));
  if(S>G) {
   CHECK(!reject(&p,S,true));CHECK(!reject(&p,S-1,true));
   CHECK(reject(&p,S+1,true));CHECK(reject(&p,G+1,false));
  } else {
   CHECK(reject(&p,G+1,true));CHECK(reject(&p,G+1,false));
  }
  int64_t points[]={G-1,G,G+1,S-1,S,S+1,D-1,D,D+1};
  for(int i=0;i<9;i++)for(int scope=0;scope<2;scope++) {
   p.valid=false;CHECK(!reject(&p,points[i],scope));p.valid=true;
   p.display_forecast=false;CHECK(!reject(&p,points[i],scope));p.display_forecast=true;
   p.fresh_clock_only=true;CHECK(!reject(&p,points[i],scope));p.fresh_clock_only=false;
  }
 }
 printf("checks=%u failures=%u\n",checks,failures);return failures?7:0;
}
