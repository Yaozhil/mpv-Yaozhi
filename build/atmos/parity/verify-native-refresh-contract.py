"""Compile the real fresh-video planner and real ASS sampler against final source."""
import argparse, hashlib, json, os
from pathlib import Path
import subprocess, tempfile
HERE=Path(__file__).resolve().parent
CONFIG=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,required=True);p.add_argument('--cc',default='cc');p.add_argument('--output',type=Path,required=True)
 a=p.parse_args(); source=a.source.resolve()
 contract=CONFIG/'build/feedback/tests/verify-secondary-ass-fresh-video.c'
 result={'status':'FAIL','source_vo_sha256':sha(source/'video/out/vo.c'),'source_helper_sha256':sha(source/'video/out/secondary_ass_fresh_video.h'),'contract_sha256':sha(contract),'runtime_verified':False}
 try:
  with tempfile.TemporaryDirectory(prefix='native-refresh-contract-')as folder:
   exe=Path(folder)/('contract.exe'if os.name=='nt'else'contract')
   cmd=[a.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(source/'video/out'),'-I'+str(source),str(contract),'-o',str(exe)]
   compiled=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
   result.update(compile_exit=compiled.returncode,compile_stdout=compiled.stdout,compile_stderr=compiled.stderr)
   if compiled.returncode:raise RuntimeError('Real source contract compile failed')
   ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
   result.update(run_exit=ran.returncode,run_stdout=ran.stdout,run_stderr=ran.stderr)
   if ran.returncode:raise RuntimeError('Real source contract failed')
   result['status']='NATIVE_REFRESH_REAL_PLANNER_SAMPLER_PASS'
 finally:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result))
if __name__=='__main__':main()
