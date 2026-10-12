"""Verify one-variable neutral A/B source and real caller; no pacing claim."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CONFIG=HERE.parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=mpv-Yaozhi','-c','user.email=yaozhi@localhost',*args],timeout=60)
def verify_source(source):
    lock=json.loads((HERE/'source-lock.json').read_bytes());fix=lock['native_ass_neutral_ab']
    assert not git(source,'status','--porcelain').strip()
    tree=git(source,'rev-parse','HEAD^{tree}').decode().strip()
    parent=git(source,'rev-parse','HEAD^'+'^{tree}').decode().strip()
    variants=[v for v,s in fix['variants'].items()
              if any(s[p+'parent_tree']==parent and s[p+'tree']==tree for p in ('','linux_'))]
    assert len(variants)==1,('Source tree not reviewed',parent,tree)
    assert git(source,'diff','--name-only','HEAD^','HEAD').decode().splitlines()==['video/out/vo.c']
    assert sha(source/'video/out/vo.c')==fix['vo_sha256']
    patch=CONFIG/fix['patch']
    assert sha(patch)==fix['patch_sha256']==lock['common_patches'][fix['patch']]
    assert patch.read_bytes().startswith(('From '+fix['source_commit']+' ').encode())
    for name,digest in fix['tools_sha256'].items():assert sha(HERE/name)==digest,name
    assert b'(mpv-Yaozhi)' in (source/'common/version.c').read_bytes()
    return {**fix,'variant':variants[0]}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--cc',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply-to-pts',action='store_true');a=ap.parse_args()
    source=a.source.resolve();out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    assert not out.exists();work=out.parent/'neutral-ab-cpu';work.mkdir()
    report={'status':'NEUTRAL_AB_CPU_FAIL','Display_accepted':False,'runtime_verified':False,'default_changed':False,'cases':[]}
    try:
        if a.apply_to_pts:
            fix=json.loads((HERE/'source-lock.json').read_bytes())['native_ass_neutral_ab']
            assert git(source,'rev-parse','HEAD^{tree}').decode().strip() in [v[p+'parent_tree'] for v in fix['variants'].values() for p in ('','linux_')]
            assert sha(CONFIG/fix['patch'])==fix['patch_sha256']
            git(source,'am','--3way',str(CONFIG/fix['patch']))
        fix=verify_source(source)
        r=subprocess.run([sys.executable,str(HERE/'verify-neutral-ab-caller.py'),'--source',str(source),
                          '--cc',str(a.cc.resolve()),'--output',str(work/'caller')],capture_output=True,timeout=120)
        (work/'caller.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,r.stderr
        caller=json.loads((work/'caller/actual-neutral-caller.json').read_bytes())
        assert caller['status']=='PASS_CPU_ACTUAL_CALLER_FRAGMENTS_NOT_CORE_NOT_DISPLAY'
        assert len(caller['runs'])==2 and all(c['result']['checks']==103 and c['exit_code']==0 for c in caller['runs'])
        real=(work/'caller/caller-fragments-generated-fix1.c').read_text(encoding='utf-8')
        mutations={
            'ignore_disabled':('!in->secondary_neutral_disabled &&','true &&'),
            'wrong_opt_in_value':('neutral && !strcmp(neutral, "0")','neutral && !strcmp(neutral, "1")'),
            'ignore_diagnostic_scope':('in->secondary_neutral_disabled = diagnostic &&','in->secondary_neutral_disabled = true &&'),
        }
        sources={'original_neutral_contract':((HERE/'v30-neutral-pose-contract.c').read_text(encoding='utf-8'),0)}
        for name,(old,new) in mutations.items():
            assert real.count(old)==1,(name,real.count(old))
            sources[name]=(real.replace(old,new),7)
        for name,(text,expected) in sources.items():
            p=work/(name+'.c');p.write_text(text,encoding='utf-8')
            for mode in ('normal','NDEBUG'):
                flags=['-DNDEBUG'] if mode=='NDEBUG' else []
                exe=work/(name+'-'+mode+'.exe')
                cmd=[str(a.cc.resolve()),'-std=c99',*flags,'-I'+str(source),str(p),'-o',str(exe)]
                if not a.cc.name.lower().startswith('tcc'):cmd+=['-lm']
                compiled=subprocess.run(cmd,capture_output=True,timeout=30)
                assert compiled.returncode==0,compiled.stderr
                run=subprocess.run([str(exe)],capture_output=True,timeout=30)
                value={'name':name,'mode':mode,'expected_exit':expected,'actual_exit':run.returncode,
                       'stdout':run.stdout.decode(errors='replace'),'stderr':run.stderr.decode(errors='replace')}
                report['cases'].append(value);assert run.returncode==expected,value
        report.update(status='NEUTRAL_AB_CPU_SOURCE_AND_NEGATIVE_CHECKS_PASS_NOT_RUNTIME',
                      source_tree=git(source,'rev-parse','HEAD^{tree}').decode().strip(),variant=fix['variant'],
                      caller_report_sha256=sha(work/'caller/actual-neutral-caller.json'),
                      caller_checks_per_mode=103,old_neutral_checks_per_mode=39,
                      unchanged_scope='Only neutral-admission diagnostic switch; all other source files, F/H/phase and production defaults remain exact.')
    finally:out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
if __name__=='__main__':main()
