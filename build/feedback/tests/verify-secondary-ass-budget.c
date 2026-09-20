#include <assert.h>
#include <stdio.h>
#include "secondary_ass_budget.h"
int main(void) {
 struct secondary_ass_budget b={0};
 const long long limit=5208333;
 for(int i=0;i<20;i++) assert(secondary_ass_budget_sample(&b,1000000,1800000)<limit);
 // A periodic single 30ms CPU stall must not suppress the following second.
 for(int cycle=0;cycle<1000;cycle++) {
  assert(secondary_ass_budget_sample(&b,30000000,1800000)<limit);
  for(int i=0;i<499;i++) assert(secondary_ass_budget_sample(&b,1000000,1800000)<limit);
 }
 // Sustained CPU overload must still disable extra redraws within two frames.
 secondary_ass_budget_sample(&b,8000000,1800000);
 assert(secondary_ass_budget_sample(&b,8000000,1800000)>=limit);
 for(int i=0;i<25;i++) assert(secondary_ass_budget_sample(&b,8000000,1800000)>=limit);
 secondary_ass_budget_sample(&b,1000000,1800000);
 assert(secondary_ass_budget_sample(&b,1000000,1800000)<limit);
 // Expensive asynchronous GPU work cannot be filtered out by cheap CPU draws.
 for(int i=0;i<2500;i++) assert(secondary_ass_budget_sample(&b,1000000,24000000)>=limit);
 assert(secondary_ass_budget_sample(&b,1000000,1800000)<limit);
 b=(struct secondary_ass_budget){0};
 assert(secondary_ass_budget_sample(&b,12000000,0)>=limit);
 assert(secondary_ass_budget_sample(&b,1000000,0)>=limit);
 assert(secondary_ass_budget_sample(&b,1000000,0)<limit);
 puts("PASS periodic CPU spike, sustained CPU/GPU overload, recovery and startup");
}
