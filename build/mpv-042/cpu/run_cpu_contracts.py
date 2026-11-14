"""Real migrated headers and extracted VO/OSD callers; CPU evidence only."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile
HERE=Path(__file__).resolve().parent
OSD_FUNCTIONS=('osd_get_secondary_physical_next_sample_slot','osd_get_secondary_physical_next_sample_time','osd_get_secondary_physical_sample_divisor','osd_get_secondary_sample_snapshot','osd_set_secondary_physical_forecast_time','osd_hold_secondary_sample')
VO_FUNCTIONS=('secondary_plan_enabled','secondary_fixed_forecast_offset','secondary_forecast_next','secondary_forecast_fresh_clock_plan','secondary_forecast_fresh_video_plan','secondary_planning_state','secondary_next_sample')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extract(source,name):
 at=source.index(name+'(');start=source.rfind('\n\n',0,at)+2
 brace=source.index('{',at);depth,end=1,brace+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--variant',choices=['main','atmos'],required=True);p.add_argument('--cc',default='gcc');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 ready=json.loads((HERE/'port-ready.json').read_text(encoding='utf8'));src=a.source.resolve()
 actual=subprocess.check_output(['git','-C',str(src),'write-tree'],text=True).strip()
 assert actual==ready['variants'][a.variant]['source_tree'],(actual,a.variant)
 source_hash={str(x.relative_to(src)).replace('\\','/'):sha(x) for x in src.rglob('*.h') if 'secondary_ass' in x.name}
 source_hash.update({f:sha(src/f) for f in ['video/out/vo.c','sub/osd.c']})
 entries=[('epoch-bootstrap',HERE/'cpu-tests/verify-secondary-ass-epoch-bootstrap.c',[],'PASS scenarios=',True),('phase-recovery',HERE/'cpu-tests/verify-secondary-ass-phase-recovery.c',['fixed'],'FIXED:',False),('fresh-video',HERE/'cpu-tests/verify-secondary-ass-fresh-video.c',[],'PASS scenarios=',False),('display-forecast',src/'test/secondary_ass_display_forecast.c',[],'display-forecast:',False),('fixed-forecast',src/'test/secondary_ass_fixed_forecast.c',[],'{"checks":',False),('queue-stage',src/'test/secondary_ass_queue_stage.c',[],'secondary_ass_queue_stage:',False)]
 result={'status':'MIGRATED_CPU_CONTRACTS_FAILED','variant':a.variant,'source_tree':actual,'source_sha256':source_hash,'runtime_verified':False,'Display_accepted':False,'contracts':[]}
 try:
  with tempfile.TemporaryDirectory(prefix='mpv-042-cpu-',ignore_cleanup_errors=True) as tmp:
   tmp=Path(tmp);osd=(src/'sub/osd.c').read_text(encoding='utf8');vo=(src/'video/out/vo.c').read_text(encoding='utf8')
   fragments={name:extract(osd,name) for name in OSD_FUNCTIONS};fragments.update({name:extract(vo,name) for name in VO_FUNCTIONS})
   header=tmp/'extracted-final.h';header.write_text('/* Actual migrated production callers. */\n'+'\n\n'.join(fragments.values())+'\n',encoding='utf8',newline='\n')
   result['production_function_sha256']={n:hashlib.sha256(s.encode()).hexdigest() for n,s in fragments.items()}
   for name,fixture,args,prefix,needs_extract in entries:
    exe=tmp/(name+('.exe' if os.name=='nt' else ''))
    cmd=[a.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(src),'-I'+str(src/'video/out'),'-I'+str(tmp)]
    if needs_extract:cmd+=['-DVARIANT_HEADER="extracted-final.h"']
    cmd+=[str(fixture),'-o',str(exe),'-lm']
    e={'id':name,'fixture_sha256':sha(fixture),'compile_args':cmd};result['contracts'].append(e)
    built=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    e.update(compile_exit=built.returncode,compile_stdout=built.stdout,compile_stderr=built.stderr)
    assert built.returncode==0,(name,built.stderr)
    ran=subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=60)
    e.update(run_exit=ran.returncode,run_stdout=ran.stdout,run_stderr=ran.stderr,executable_sha256=sha(exe))
    assert ran.returncode==0 and ran.stdout.startswith(prefix),(name,ran.stdout,ran.stderr)
  assert all(sha(src/f)==s for f,s in source_hash.items())
  result['status']='MIGRATED_CPU_CONTRACTS_PASS_NOT_RUNTIME'
 finally:
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
