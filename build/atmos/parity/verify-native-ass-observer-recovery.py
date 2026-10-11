"""GCC CPU observer recovery contracts; no actual Display acceptance."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_ass_observer_source import CONFIG, HERE, git, require, sha, verify_observer_source


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--cc',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply-to-prepass',action='store_true')
    a=ap.parse_args(); source=a.source.resolve(); out=a.output.resolve()
    lock=json.loads((HERE/'source-lock.json').read_bytes())
    fix=lock['native_ass_observer_recovery_fix']
    require(not git(source,'status','--porcelain').strip(), 'Source must be clean')
    patch=CONFIG/fix['patch']
    require(sha(patch.read_bytes())==fix['patch_sha256'], 'Observer patch SHA differs')
    if a.apply_to_prepass:
        for name,digest in fix['before_source_sha256'].items():
            require(sha((source/name).read_bytes())==digest, 'Prepass source SHA differs: '+name)
        for name,digest in fix['before_test_sha256'].items():
            require(sha((source/name).read_bytes())==digest, 'Prepass test SHA differs: '+name)
        git(source,'am','--3way',str(patch))
    verify_observer_source(source)
    compiler=subprocess.run([str(a.cc),'--version'],capture_output=True,text=True,timeout=15)
    version=compiler.stdout
    require(compiler.returncode==0 and bool(re.search(r'gcc|GCC|Free Software Foundation',version)),
            'This build gate requires actual GCC, not a limited local compiler')
    fixture_names=('observer-recovery-independent-contract.c',
                   'observer-recovery-long-phase.c','observer-recovery-field-prefix.c')
    require(set(fix['cpu_fixture_sha256'])==set(fixture_names), 'Wrong recovery fixture set')
    for name in fixture_names:
        require(sha((HERE/name).read_bytes())==fix['cpu_fixture_sha256'][name],
                'Recovery fixture SHA differs: '+name)
    out.parent.mkdir(parents=True,exist_ok=True)
    old=out.parent/'old-physical';old.mkdir(exist_ok=True)
    (old/'secondary_ass_physical.h').write_bytes(
        git(source,'show','HEAD^:video/out/secondary_ass_physical.h'))
    rows=[]
    for name in fixture_names+('old-field-prefix',):
        original=(HERE/'observer-recovery-field-prefix.c' if name=='old-field-prefix'
                  else HERE/name)
        for release in (False,True):
            stem=Path(name).stem+('-ndebug' if release else '')
            exe=out.parent/(stem+'.exe')
            include=old if name=='old-field-prefix' else source/'video/out'
            cmd=[str(a.cc),'-std=c11','-Wall','-Wextra','-Werror',
                 '-I'+str(include),'-I'+str(source/'video/out'),
                 '-o',str(exe),str(original)]
            if release:cmd.insert(1,'-DNDEBUG')
            compiled=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            require(compiled.returncode==0, stem+' compile failed: '+compiled.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
            require(run.returncode==(4 if name=='old-field-prefix' else 0),
                    stem+' unexpected return: '+str(run.returncode)+' '+run.stdout+' '+run.stderr)
            details=None
            if name=='observer-recovery-long-phase.c':
                details=[json.loads(line) for line in run.stdout.splitlines()]
                require(len(details)==8, 'Long phase report shape differs')
                for rate,r in zip((60,120,144,165,240,360,480),details[:7]):
                    require(r['hz']==rate and r['duration_seconds']==300 and
                            r['max_phase_lattice_error_ns']==0 and r['resets']==0 and
                            r['single_jitter_quarantine']==30 and not r['actual_display_known'],
                            'Phase contract failed or claimed actual Display')
                require(details[-1]=={'CPU_contract_checks':4707000}, 'Long phase checks differ')
            elif name=='observer-recovery-field-prefix.c':
                details=json.loads(run.stdout)
                require(details=={'observations':3,'recovery_call_observation':False,
                    'H_and_gap_coordinates_unchanged':True,'epoch_unchanged':True,
                    'final_phase_ns':37363405500,'final_phase_slot':4294968945,
                    'actual_display_known':False}, 'Field prefix recovery contract differs')
            elif name=='observer-recovery-independent-contract.c':
                require(bool(re.fullmatch(r'PASS independent recovery contracts: [1-9][0-9]* checks, 7 rates, actual helper\n',run.stdout)),
                        'Independent recovery check output differs')
            rows.append({'case':stem,'returncode':run.returncode,
                'stdout':run.stdout.strip(),'stderr':run.stderr.strip(),'details':details,
                'fixture_sha256':sha(original.read_bytes()),
                'compiler_command':cmd})
    require(not git(source,'status','--porcelain').strip(), 'CPU test modified source')
    report={'status':'CPU_OBSERVER_RECOVERY_CONTRACT_PASS_NOT_DISPLAY_ACCEPTANCE',
        'source_commit':git(source,'rev-parse','HEAD').decode().strip(),
        'source_tree':git(source,'rev-parse','HEAD^{tree}').decode().strip(),
        'locked_source_commit':fix['source_commit'],'patch_sha256':fix['patch_sha256'],
        'source_sha256':fix['source_sha256'],'test_sha256':fix['test_sha256'],
        'fixture_sha256':fix['cpu_fixture_sha256'],'compiler_version':version,
        'cases':rows,'runtime_verified':False,'Display_accepted':False,'deployed':False}
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
