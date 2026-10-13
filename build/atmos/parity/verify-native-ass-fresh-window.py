"""Check the reviewed source layer and compile its actual selection caller.

This is CPU evidence, not full-core ABI, rendering or Display acceptance.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CONFIG=HERE.parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=mpv-Yaozhi','-c','user.email=yaozhi@localhost',*args],timeout=60)
def verify_source(source):
    lock=json.loads((HERE/'source-lock.json').read_bytes());fix=lock['native_ass_fresh_window_fix']
    assert not git(source,'status','--porcelain').strip()
    tree=git(source,'rev-parse','HEAD^{tree}').decode().strip()
    parent=git(source,'rev-parse','HEAD^'+'^{tree}').decode().strip()
    variants=[v for v,s in fix['variants'].items()
              if any(s[p+'parent_tree']==parent and s[p+'tree']==tree for p in ('','linux_'))]
    assert len(variants)==1,('Unreviewed source tree',parent,tree)
    assert git(source,'diff','--name-only','HEAD^','HEAD').decode().splitlines()==['video/out/vo.c']
    assert sha(source/'video/out/vo.c')==fix['vo_sha256']
    patch=CONFIG/fix['patch']
    assert sha(patch)==fix['patch_sha256']==lock['common_patches'][fix['patch']]
    assert patch.read_bytes().startswith(('From '+fix['source_commit']+' ').encode())
    assert fix['parent_commit']==lock['native_ass_neutral_ab']['source_commit']
    for name,digest in fix['tools_sha256'].items():assert sha(HERE/name)==digest,name
    assert b'(mpv-Yaozhi)' in (source/'common/version.c').read_bytes()
    return {**fix,'variant':variants[0]}
def declaration(gate,text,name):
    start=text.index('struct '+name+' {');mask=gate.mask_c(text);depth=0;opened=False
    for i in range(start,len(text)):
        if mask[i]=='{':depth+=1;opened=True
        elif mask[i]=='}':
            depth-=1
            if opened and depth==0:return text[start:i+2]
    raise AssertionError(name)
def verify_caller(source,code):
    spec=importlib.util.spec_from_file_location('gate',HERE/'verify-native-ass-integration-v31.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    vo=(source/'video/out/vo.c').read_text(encoding='utf-8')
    vf=gate.functions(vo);cf=gate.functions(code);render=vf['render_frame']['text']
    start=render.index('        int64_t display_interval =')
    end=render.index('        if (!secondary_target_updated && in->secondary_trace)',start)
    selection=render[start:end]
    assert selection.count('frame->current->pts')==1
    selection=selection.replace('frame->current->pts','fixture_media_pts(frame->current)',1)
    m=re.search(r'\bstruct\s+secondary_ass_sample_snapshot\s+sample\s*=[^;]+;',gate.mask_c(selection));assert m
    statement=selection[m.start():m.end()]
    selection=selection.replace(statement,'fixture_v30_new_osd_scope = true;\n'+statement+'\nfixture_v30_new_osd_scope = false;',1)
    assert code.count(selection)==1,'Fixture must contain the complete current selection'
    assert declaration(gate,code,'vo_internal')==declaration(gate,vo,'vo_internal')
    helpers=['secondary_forecast_fresh_plan','secondary_forecast_fresh_clock_plan',
        'secondary_forecast_next','secondary_fixed_forecast_offset','secondary_forecast_plan',
        'secondary_trace_plan_missed','secondary_plan_enabled','secondary_forecast_enabled']
    for name in helpers:assert cf[name]['text']==vf[name]['text'],name
    return dict(selection_sha256=hashlib.sha256(selection.encode()).hexdigest(),helpers_verbatim=helpers)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--cc',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply-to-neutral',action='store_true');a=ap.parse_args()
    source=a.source.resolve();out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    assert not out.exists();work=out.parent/'fresh-window-cpu';work.mkdir()
    report=dict(status='FRESH_WINDOW_CPU_FAIL',Display_accepted=False,runtime_verified=False,cases=[])
    try:
        if a.apply_to_neutral:
            fix=json.loads((HERE/'source-lock.json').read_bytes())['native_ass_fresh_window_fix']
            assert not git(source,'status','--porcelain').strip()
            assert git(source,'rev-parse','HEAD^{tree}').decode().strip() in [v[p+'parent_tree'] for v in fix['variants'].values() for p in ('','linux_')]
            assert sha(CONFIG/fix['patch'])==fix['patch_sha256']
            git(source,'am','--3way',str(CONFIG/fix['patch']))
        fix=verify_source(source)
        code=(HERE/'fresh-window-actual-selection.c').read_text(encoding='utf-8')
        report['caller']=verify_caller(source,code)
        old='''present_plan.base.wall < original_video_target &&
                    (!uncaptured_fixed_fresh ||
                     present_plan.submit < original_video_target)'''
        assert code.count(old)==1
        cases={
            'actual_caller':(code,0),
            'restore_G_rejection':(code.replace(old,'present_plan.base.wall < original_video_target'),7),
            'reverse_submit_guard':(code.replace('present_plan.submit < original_video_target','present_plan.submit >= original_video_target'),7),
        }
        for name in ('candidate','original_counterexample','mutation_scope_lost','mutation_submit_equality_rejected'):
            cases['predicate_'+name]=((HERE/('fresh-window-predicate-'+name+'.c')).read_text(encoding='utf-8'),0 if name=='candidate' else 7)
        for name,(text,expected) in cases.items():
            c=work/(name+'.c');c.write_bytes(text.encode())
            for mode in ('normal','NDEBUG'):
                exe=work/(name+'-'+mode+'.exe')
                cmd=[str(a.cc.resolve()),'-std=c99','-I'+str(source),'-I'+str(source/'video/out')]
                if mode=='NDEBUG':cmd+=['-DNDEBUG']
                cmd+=[str(c),'-o',str(exe)]
                if not a.cc.name.lower().startswith('tcc'):cmd+=['-lm']
                build=subprocess.run(cmd,capture_output=True,timeout=60)
                (work/(name+'-'+mode+'-compile.log')).write_bytes(build.stdout+build.stderr)
                assert build.returncode==0,build.stderr
                run=subprocess.run([str(exe)],capture_output=True,timeout=90)
                (work/(name+'-'+mode+'.log')).write_bytes(run.stdout+run.stderr)
                value=dict(name=name,mode=mode,expected_exit=expected,exit=run.returncode)
                report['cases'].append(value);assert run.returncode==expected,value
                if not name.startswith('predicate_'):
                    assert b'fresh_window_new_case_completed' in run.stdout
                    if expected:assert b'r.plan.valid && !r.plan.fresh_clock_only' in run.stdout+run.stderr
                elif expected==0:assert b'checks=2088 failures=0' in run.stdout
        report.update(status='FRESH_WINDOW_SOURCE_CALLER_NEGATIVES_PASS_NOT_DISPLAY',variant=fix['variant'],
            source_tree=git(source,'rev-parse','HEAD^{tree}').decode().strip(),vo_sha256=fix['vo_sha256'],
            fixture_sha256=sha(HERE/'fresh-window-actual-selection.c'),
            limits=['Actual selection/declarations/helpers and current inline headers; platform/OSD endpoints are test fixtures.',
                    'No physical screen, GPU, full-core ABI or pacing acceptance.'])
    finally:out.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report))
if __name__=='__main__':main()
