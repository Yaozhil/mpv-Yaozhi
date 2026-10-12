"""Verify exact bounded-PTS source and execute the actual header/caller.

No GPU, installation or Display acceptance. Old stage gates remain unchanged.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CONFIG=HERE.parents[2]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=mpv-Yaozhi','-c','user.email=yaozhi@localhost',*args],timeout=60)
def verify_source(source):
    lock=json.loads((HERE/'source-lock.json').read_bytes());fix=lock['native_video_pts_repair']
    assert fix['parent_commit']==lock['native_ass_observer_recovery_fix']['source_commit']
    assert not git(source,'status','--porcelain').strip()
    assert git(source,'diff','--name-only','HEAD^','HEAD').decode().splitlines()==fix['changed_files']
    patch=(CONFIG/fix['patch']).resolve();assert patch.is_relative_to(CONFIG)
    raw=patch.read_bytes()
    assert sha(raw)==fix['patch_sha256']==lock['common_patches'][fix['patch']]
    assert raw.startswith(('From '+fix['source_commit']+' ').encode())
    before={name:sha(git(source,'show','HEAD^:'+name)) for name in fix['before_source_sha256']}
    matches=[name for name,data in fix['variants'].items() if data['before_source_sha256']==before]
    assert len(matches)==1,('Unknown main/Atmos input',before)
    variant=matches[0];exact=fix['variants'][variant]
    for name,digest in {**exact['source_sha256'],**fix['preserved_ass_sha256']}.items():
        assert sha((source/name).read_bytes())==digest,name
    for name,digest in fix['preserved_ass_sha256'].items():
        assert sha(git(source,'show','HEAD^:'+name))==digest,name
    mkv=(source/'demux/demux_mkv.c').read_text(encoding='utf-8')
    constructor=re.search(r'static int demux_mkv_open_video\([^;]*?\)\s*\{.*?\n\}\n',mkv,re.S)
    assert constructor
    constructor=constructor[0]
    declaration='mkv_demuxer_t *mkv_d = demuxer->priv;'
    assert constructor.count(declaration)==1, 'Existing MKV context declaration must be reused'
    assert constructor.index(declaration)<constructor.index('sh_v->video_timestamp_quantum = mkv_d->tc_scale / 1e9;')
    assert (source/'common/version.c').read_bytes()==git(source,'show','HEAD^:common/version.c')
    assert b'(mpv-Yaozhi)' in (source/'common/version.c').read_bytes()
    for key in ('cpu_tool_sha256','cpu_fixture_sha256'):
        for name,digest in fix[key].items():assert sha((HERE/name).read_bytes())==digest,name
    return {**fix,**exact,'variant':variant}

STUB=r'''
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "filters/video_pts_repair.h"
#define MP_NOPTS_VALUE (-1e10)
#define MP_WARN(...) ((void)0)
#define MP_TRACE(...) ((void)0)
struct codec {double video_default_duration,video_timestamp_quantum;const char *codec;};
struct header {bool image,still_image;};
struct opts {bool correct_pts;};
struct mp_image {double pts,pkt_duration;};
struct priv {struct codec *codec;struct header *header;struct opts *opts;
 double pts,fps,first_packet_pdts;int play_dir,num_codec_pts_problems,has_broken_decoded_pts;
 struct mp_video_pts_repair video_pts_repair;};
'''
CASES=r'''
static int checks;
#define C(x) do {checks++;if(!(x)){printf("FAIL line %d\n",__LINE__);return 7;}}while(0)
int main(void){
 struct codec codec={.video_default_duration=.016666666,.video_timestamp_quantum=.001,.codec="hevc"};
 struct header header={0};struct opts opts={.correct_pts=true};
 struct priv p={.codec=&codec,.header=&header,.opts=&opts,.pts=735,.fps=60,.play_dir=1,.num_codec_pts_problems=1};
 double a[]={735.017,735.017,735.033,735.050,735.083};
 for(int i=0;i<5;i++){
  double previous=p.pts;struct mp_image m={.pts=a[i]};correct_video_pts(&p,&m);
  C(m.pts>previous);C(m.pts-a[i]>=0 && m.pts-a[i]<=codec.video_default_duration+.001);
  if(i==0 || i==4)C(m.pts==a[i]);
 }
 // Each actual caller gate must prevent entry, including a duplicate pair.
 for(int kind=0;kind<8;kind++){
  codec=(struct codec){.video_default_duration=.016666666,.video_timestamp_quantum=.001,.codec="hevc"};
  header=(struct header){0};opts.correct_pts=true;
  p=(struct priv){.codec=&codec,.header=&header,.opts=&opts,.pts=1,.fps=60,.play_dir=1,.num_codec_pts_problems=1};
  if(kind==0)p.num_codec_pts_problems=0;
  if(kind==1)header.image=true;
  if(kind==2)header.still_image=true;
  if(kind==3)codec.codec="h264";
  if(kind==4)codec.video_default_duration=0;
  if(kind==5)codec.video_timestamp_quantum=0;
  if(kind==6)p.play_dir=-1;
  if(kind==7)opts.correct_pts=false;
  for(int i=0;i<2;i++){
   struct mp_image m={.pts=1};correct_video_pts(&p,&m);
   C(!p.video_pts_repair.active);
   if(kind<6)C(m.pts==1);
  }
 }
 codec=(struct codec){.video_default_duration=.016666666,.video_timestamp_quantum=.001,.codec="hevc"};
 opts.correct_pts=true;header=(struct header){0};
 p=(struct priv){.codec=&codec,.header=&header,.opts=&opts,.pts=1,.play_dir=1,.num_codec_pts_problems=1};
 for(int i=0;i<2;i++){
  struct mp_image m={.pts=1,.pkt_duration=.05};correct_video_pts(&p,&m);C(m.pts==1 && !p.video_pts_repair.active);
 }
 puts("PASS actual caller guards and container-duration repair");return 0;
}
'''
def caller(source):
    text=(source/'filters/f_decoder_wrapper.c').read_text(encoding='utf-8')
    m=re.search(r'static void correct_video_pts\(.*?\n\}\n',text,re.S);assert m
    reset=re.search(r'static void reset_decoder\(.*?\n\}\n',text,re.S);assert reset
    assert 'p->video_pts_repair = (struct mp_video_pts_repair){0};' in reset[0]
    return STUB+m[0]+CASES


def source730_contract():
    fixture=json.loads((HERE/'video-pts-repair-730-fixture.json').read_bytes())
    rows=fixture['frames']
    assert len(rows)==508 and [r['n'] for r in rows]==list(range(508))
    assert sum(a['pts_us']==b['pts_us'] for a,b in zip(rows,rows[1:]))==64
    assert all(b['pts_us']>=a['pts_us'] for a,b in zip(rows,rows[1:]))
    assert len({r['checksum'] for r in rows[392:396]})==4
    assert {r['pts_us'] for r in rows[392:396]}=={734750000}
    assert fixture['software_only'] and fixture['Display_accepted'] is False
    values=','.join(format(r['pts_us']/1e6,'.6f') for r in rows)
    return r"""
#include <stdio.h>
#include <math.h>
#include "filters/video_pts_repair.h"
#define C(x) do{if(!(x)){printf("FAIL line=%d\n",__LINE__);return 9;}}while(0)
static const double raw[]={VALUES};
int main(void){
 struct mp_video_pts_repair s={0};double d=.016666666,q=.001,previous=raw[0];
 double raw_positive=0,out_positive=0,raw_to_anchor=0,out_to_anchor=0;
 int changes=0,negative=0,zeros=0,last_anchor=-1,later_changes=0;
 for(int i=0;i<508;i++){
  double x=mp_video_pts_repair_apply(&s,true,raw[i],previous,d,q);
  if(i){
   raw_positive+=fmax(raw[i]-raw[i-1],0);out_positive+=fmax(x-previous,0);
   if(x<previous)negative++;
   if(x==previous)zeros++;
  }
  C(!s.blocked&&x>=raw[i]&&x-raw[i]<=d+q+1e-8);
  C(out_positive-raw_positive<=d+q+1e-8);
  if(x!=raw[i]){changes++;if(i>395)later_changes++;}
  if(x==raw[i]){last_anchor=i;raw_to_anchor=raw_positive;out_to_anchor=out_positive;}
  if(i==394||i==395)C(s.recovering&&fabs(x-734.766666666)<1e-8);
  if(i==396)C(x==raw[i]&&!s.active&&!s.recovering);
  previous=x;
 }
 C(negative==0&&zeros==2&&changes>150&&later_changes>30);
 C(last_anchor==504&&fabs(raw_to_anchor-out_to_anchor)<1e-8);
 C(fabs(raw_to_anchor-8.467)<1e-8);
 printf("PASS source730 frames=508 duplicate_pairs=64 repaired=%d later_repaired=%d negative=%d zero_hold=%d last_anchor=%d anchor_positive_us=8467000\n",changes,later_changes,negative,zeros,last_anchor);
 return 0;
}
""".replace('VALUES',values)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--cc',type=Path,required=True)
    ap.add_argument('--apply-to-observer',action='store_true');a=ap.parse_args()
    source=a.source.resolve();out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    result=dict(status='PTS_GATE_FAIL',Display_accepted=False,runtime_verified=False,cases=[])
    try:
        lock=json.loads((HERE/'source-lock.json').read_bytes());fix=lock['native_video_pts_repair']
        if a.apply_to_observer:
            sys.path.insert(0,str(HERE));from native_ass_observer_source import verify_observer_source
            verify_observer_source(source)
            assert sha((CONFIG/fix['patch']).read_bytes())==fix['patch_sha256']
            git(source,'am','--3way',str(CONFIG/fix['patch']))
        fix=verify_source(source)
        result.update(source_commit=git(source,'rev-parse','HEAD').decode().strip(),
            source_tree=git(source,'rev-parse','HEAD^{tree}').decode().strip(),
            source_sha256=fix['source_sha256'],preserved_ass_sha256=fix['preserved_ass_sha256'],variant=fix['variant'])
        positive=caller(source)
        # Mutations must compile and be caught by behavior, not by identity checks.
        functions={'actual_caller':positive,
            'fault_no_history':positive.replace('p->num_codec_pts_problems > 0','true'),
            'fault_no_forward':positive.replace('p->play_dir > 0','true'),
            'fault_no_still_guard':positive.replace('!p->header->image && !p->header->still_image','true'),
            'fault_no_codec_guard':positive.replace('strcmp(p->codec->codec, "hevc") == 0','true'),
            'fault_no_varying_duration':positive.replace('!(mpi->pkt_duration > 0 &&\n          fabs(mpi->pkt_duration - duration) > quantum)','true')}
        assert len(set(functions.values()))==len(functions)
        # Execute the actual header and mutations of it, rather than a Python
        # approximation. Old source/caller cases remain present and unchanged.
        header=(source/'filters/video_pts_repair.h').read_text(encoding='utf-8')
        safety=(HERE/'video-pts-repair-safety-contract.c').read_text(encoding='utf-8')
        mutations={
            'fault_safety_no_terminal_guard':header.replace('    if (s->blocked)\n        return raw;',''),
            'fault_safety_clear_on_ineligible':header.replace(
                '*s = (struct mp_video_pts_repair){.blocked = was_active};',
                '*s = (struct mp_video_pts_repair){0};'),
            'fault_safety_clear_on_metadata_change':header.replace(
                's->blocked = was_active;', 's->blocked = false;'),
            'fault_safety_ignore_raw_backwards':header.replace(
                'if (!current || raw < last_raw)', 'if (!current)'),
            'fault_safety_release_monotonic_tail':header.replace(
                'if (active && previous >= raw && previous - raw <= duration + quantum)', 'if (false)'),
            'fault_safety_skip_recovery':header.replace('if (recovering)', 'if (recovering && false)'),
            'fault_safety_delay_original_anchor':header.replace(
                'if (raw >= previous)', 'if (raw >= previous + duration - quantum)'),
            'fault_safety_relax_correction_bound':header.replace(
                'correction <= duration + quantum', 'correction <= 2 * duration + quantum'),
            'fault_safety_block_usable_anchor':header.replace(
                'if (active && raw > previous && raw >= next - quantum)\n        return raw;',
                'if (active && raw > previous && raw >= next - quantum) {\n        s->blocked = true;\n        return raw;\n    }'),
        }
        assert len(set(mutations.values()))==len(mutations) and all(x!=header for x in mutations.values())
        include='#include "filters/video_pts_repair.h"'
        assert safety.count(include)==1
        safety_cases={'safety_hold':safety, **{name:safety.replace(include,value)
            for name,value in mutations.items()}}
        result['safety_scope']='monotonic bounded-prefix recovery with original anchors; finite uncut positive interval excess per explicit reset; actual backwards/metadata/eligibility fail closed; zero hold interval and large-gap player cutoff limitations retained'
        for case,body in {'real_header':(HERE/'video-pts-repair-contract.c').read_text(),'real_header_730':source730_contract(),**functions,**safety_cases}.items():
            c=out.parent/(case+'.c');c.write_text(body,encoding='utf-8',newline='\n')
            for mode,flags in (('normal',[]),('NDEBUG',['-DNDEBUG'])):
                exe=out.parent/(case+'-'+mode+('.exe' if sys.platform=='win32' else ''))
                command=[str(a.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,'-I'+str(source),str(c),'-lm','-o',str(exe)]
                if a.cc.name.lower()=='tcc.exe':command=[str(a.cc),'-std=c11',*flags,'-I'+str(source),str(c),'-o',str(exe)]
                comp=subprocess.run(command,capture_output=True,text=True,timeout=60)
                assert comp.returncode==0,(case,mode,comp.stderr)
                run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
                expected=9 if case.startswith('fault_safety_') else 7 if case.startswith('fault_') else 0
                assert run.returncode==expected,(case,mode,run.stdout,run.stderr)
                result['cases'].append(dict(case=case,mode=mode,command=command,compile_exit=comp.returncode,
                    exit=run.returncode,stdout=run.stdout,translation_sha256=sha(c.read_bytes()),executable_sha256=sha(exe.read_bytes())))
        verify_source(source)
        result['status']='BOUNDED_PTS_REAL_HEADER_CALLER_GUARDS_PASS_NOT_FULL_BUILD_OR_DISPLAY'
        return 0
    except BaseException as error:
        result.update(error_type=type(error).__name__,error=str(error));return 1
    finally:
        out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps({k:result.get(k) for k in ('status','source_tree','error','Display_accepted')}))
if __name__=='__main__':raise SystemExit(main())
