"""Execute the actual VO sampler selector across real refresh namespace changes."""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

BASE=Path(__file__).resolve().parent
def extract(path):
    text=path.read_text(encoding='utf-8')
    start=text.index('static struct secondary_ass_physical_point secondary_next_sample(struct vo *vo,\n')
    begin=text.index('{',start);depth=1;end=begin+1
    while depth:
        if text[end]=='{':depth+=1
        elif text[end]=='}':depth-=1
        end+=1
    return text[start:end]
PREAMBLE=r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include "video/out/secondary_ass_physical.h"
#include "sub/secondary_ass_clock.h"
struct vo_frame {bool display_synced;};
struct vo_internal {struct vo_frame *current_frame;struct secondary_ass_physical physical;};
struct vo {struct vo_internal *in;void *osd;};
static struct secondary_ass_sample_snapshot sample;
static const struct secondary_ass_physical *secondary_planning_state(struct vo *vo,
 bool ds,int64_t divisor,struct secondary_ass_physical *storage) {(void)ds;(void)divisor;(void)storage;return &vo->in->physical;}
static struct secondary_ass_sample_snapshot osd_get_secondary_sample_snapshot(void *osd) {(void)osd;return sample;}
static int64_t osd_get_secondary_physical_next_sample_slot(void *osd) {return sample.next_slot;}
static int64_t osd_get_secondary_physical_next_sample_time(void *osd) {return sample.next_wall;}
static int failures,checks;
#define CHECK(x) do {checks++;if(!(x)){failures++;fprintf(stderr,"failed line %d\n",__LINE__);}}while(0)
'''
CASES=r'''
int main(void) {
 const int hz[]={60,120,144,165,240,360};
 for(unsigned h=0;h<6;h++)for(int delta=1;delta<=600;delta+=7) {
  const int64_t T=1000000000LL/hz[h],ns=20000000000LL,origin=4294967296LL;
  struct vo_frame frame={0};struct vo_internal in={.current_frame=&frame};
  in.physical=(struct secondary_ass_physical){.phase=ns,.phase_slot=origin,
   .interval=T,.epoch=32};struct vo vo={.in=&in};
  // Captured V25 resize: old sampler has progressed; new counter namespace
  // restarts at 2^32. Its old numerical slot must not become a future wait.
  sample=(struct secondary_ass_sample_snapshot){.epoch=31,.next_slot=origin+delta,
   .next_wall=ns-T,.divisor=2};
  struct secondary_ass_physical_point point=secondary_next_sample(&vo,2);
  CHECK(point.slot==0 && point.wall==0);
  struct secondary_ass_physical_point fresh=secondary_ass_physical_predict_point(&in.physical,ns+T/3);
  CHECK(fresh.slot==origin+1 && fresh.wall==ns+T);
  // The same epoch keeps its exact divided-grid identity, including held
  // poses and one timing jitter. It must never be reselected from wall time.
  sample.epoch=32;point=secondary_next_sample(&vo,2);
  CHECK(point.slot==origin+delta && point.wall==ns+delta*T);
  sample.held=true;point=secondary_next_sample(&vo,2);
  CHECK(point.slot==origin+delta && point.wall==ns+delta*T);
  CHECK(in.physical.epoch==32 && in.physical.phase==ns && in.physical.delay==0);
  // Arbitrary cadence with no physical slot retains the old wall mapping.
  sample=(struct secondary_ass_sample_snapshot){.epoch=32,.next_wall=ns+3*T};
  point=secondary_next_sample(&vo,0);
  CHECK(point.slot==origin+3 && point.wall==ns+3*T);
  sample.epoch=31;point=secondary_next_sample(&vo,0);
  CHECK(!point.slot && !point.wall);
 }
 printf("checks=%d failures=%d\n",checks,failures);return failures?7:0;
}
'''
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',required=True)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    source=args.source;candidate=extract(source/'video/out/vo.c')
    guard = '    if (sample.epoch && sample.epoch != p->epoch)\n        return (struct secondary_ass_physical_point){0};\n'
    assert candidate.count(guard)==1, 'Epoch guard missing/ambiguous'
    original=candidate.replace(guard,'    (void)sample;\n',1)
    cases={}
    for name,body in [('candidate',candidate),('old_epoch_projection_fault',original)]:
        path=out/(name+'.c');path.write_text(PREAMBLE+body+CASES,encoding='utf-8')
        for mode,flags in [('normal',[]),('NDEBUG',['-DNDEBUG'])]:
            exe=out/(name+'-'+mode+('.exe' if __import__('os').name=='nt' else ''))
            command=[args.cc,'-std=c99','-Wall','-Werror','-I'+str(source),*flags,str(path),'-o',str(exe)]
            compile_result=subprocess.run(command,capture_output=True,text=True,timeout=20)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10) if compile_result.returncode==0 else None
            cases[name+'-'+mode]={'compile_exit':compile_result.returncode,
                'compile_stderr':compile_result.stderr,'exit':result.returncode if result else None,
                'stdout':result.stdout if result else '',
                'failure_lines':len(result.stderr.splitlines()) if result else None}
    passed=all(r['compile_exit']==0 and r['exit']==(0 if name.startswith('candidate') else 7)
        for name,r in cases.items())
    report={'status':'PASS_CPU_NOT_RUNTIME' if passed else 'FAIL','cases':cases,
        'selector_sha256':hashlib.sha256(candidate.encode()).hexdigest(),
        'scope':'Actual VO selector; OSD getters/planning state explicit fixture boundaries',
        'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'GPU_started':False,'Display_acceptance':False}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
