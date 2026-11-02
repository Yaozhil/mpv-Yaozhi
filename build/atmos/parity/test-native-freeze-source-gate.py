"""Check exact-source admission and refusal against the actual candidate."""
import argparse, copy, importlib.util, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('freeze_gate',HERE/'verify-native-freeze-source.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('source','parent-config','legacy-speaker-config','output'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--variant',choices=('main','atmos'),required=True)
 a=p.parse_args();lock=json.loads((HERE/'native-freeze-lock.json').read_bytes());checks=[]
 def verify(value):return gate.verify(a.source,a.variant,value,parent_config=a.parent_config,legacy_speaker_config=a.legacy_speaker_config)
 proof=verify(lock)
 assert proof['status']=='EXACT_NATIVE_FREEZE_FINAL_SOURCE_AND_PATCH_REPLAY_PASS'
 checks.append('Exact full tree, patch replay and unchanged frozen parent gates')
 def reject(name,change,expected):
  value=copy.deepcopy(lock);change(value)
  try:verify(value)
  except ValueError as error:
   assert expected in str(error),(name,str(error))
   checks.append(name);return
  raise AssertionError('Unexpected acceptance: '+name)
 reject('Wrong parent config',lambda v:v.update(parent_config_commit='0'*40),'Frozen installed parent')
 reject('Wrong dependency lock',lambda v:v.update(dependency_lock_sha256='0'*64),'Frozen installed parent')
 reject('Missing variant',lambda v:v['variants'].pop('atmos'),'Both exact variants')
 reject('Wrong complete final tree',lambda v:v['variants'][a.variant].update(source_tree='0'*40),'complete final source tree')
 reject('Wrong complete installed tree',lambda v:v['variants'][a.variant].update(baseline_tree='0'*40),'installed complete parent tree')
 reject('Unfrozen final tree',lambda v:v['variants'][a.variant].update(source_tree='TODO'),'Unfrozen complete source tree')
 reject('Wrong before source',lambda v:v['variants'][a.variant]['before_source_sha256'].update({'video/out/vo.c':'0'*64}),'Installed parent source digest')
 reject('Wrong after source',lambda v:v['variants'][a.variant]['source_sha256'].update({'video/out/vo.c':'0'*64}),'Final source digest')
 reject('Incomplete source set',lambda v:v['variants'][a.variant]['source_sha256'].pop('video/out/vo.c'),'Incomplete source digest')
 reject('Patch byte drift',lambda v:v['patch'].update(sha256='0'*64),'Input digest mismatch')
 reject('Patch scope expansion',lambda v:v['patch']['changed_files'].append('unrelated.c'),'Unexpected approved source scope')
 reject('Tool byte drift',lambda v:v['tools_sha256'].update({'build/atmos/parity/prepare-native-freeze-winbuild.py':'0'*64}),'Input digest mismatch')
 reject('Missing tool identity',lambda v:v.update(tools_sha256={}), 'Incomplete new source gate')
 reject('No CPU contracts',lambda v:v.update(cpu_contracts=[]),'reviewed actual-source CPU contract')
 reject('Unknown CPU kind',lambda v:v['cpu_contracts'][0].update(kind='shell'),'Unknown CPU runner')
 reject('Unbound CPU runner',lambda v:v['cpu_contracts'][0].update(runner='unreviewed.py'),'Unbound CPU runner')
 reject('Unbound CPU input',lambda v:v['cpu_contracts'][0].update(inputs=['unreviewed.h']),'Unbound CPU fixture')
 reject('Unsafe tool path',lambda v:v['tools_sha256'].update({'../escape':'0'*64}),'Unsafe configuration path')
 marker=a.source/'.native-freeze-owned-negative-fixture'
 assert not marker.exists()
 try:
  marker.write_text('Owned gate negative fixture\n',encoding='utf-8')
  try:verify(lock)
  except ValueError as error:assert 'completely clean' in str(error)
  else:raise AssertionError('Untracked file accepted')
  checks.append('Untracked source refused')
 finally:marker.unlink()
 assert not gate.git(a.source,'status','--porcelain','--untracked-files=all').strip()
 result=dict(status='NATIVE_FREEZE_SOURCE_GATE_CONTRACTS_PASS',count=len(checks),checks=checks,runtime_verified=False)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result))
if __name__=='__main__':main()
