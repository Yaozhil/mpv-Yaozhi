"""Compile the actual paused bitmap gate and reject regression mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
CONFIG=HERE.parents[2]

def sha(raw): return hashlib.sha256(raw).hexdigest()
def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),'-c','core.autocrlf=false',
        '-c','user.name=mpv-Yaozhi','-c','user.email=yaozhi@localhost',*args],timeout=45)

def predicate(text):
    matches=re.findall(r'if \((\(!osd->secondary_sample_held.*?sub_is_secondary_visible\(obj->sub\))\) \{',text,re.S)
    assert len(matches)==1, 'Expected one actual secondary bitmap gate'
    return (matches[0].replace('osd->secondary_sample_held','held')
        .replace('osd->secondary_sampler.valid','valid').replace('osd->secondary_rate','rate')
        .replace('sub_is_secondary_visible(obj->sub)','visible').replace('obj->sub','sub'))

FIXTURE=r'''
#include <stdbool.h>
#include <stdio.h>
static bool original(bool held,bool valid,double rate,bool sub,bool visible) {
    (void)rate; return ORIGINAL;
}
static bool candidate(bool held,bool valid,double rate,bool sub,bool visible) {
    (void)held; (void)valid; (void)rate; (void)sub; (void)visible; return CANDIDATE;
}
int main(void) {
    int checks=0;
    const double rates[]={0,24,60,72,82.5,120,144,165,240,360};
    for(int h=0;h<2;h++)for(int v=0;v<2;v++)for(int s=0;s<2;s++)
    for(int vis=0;vis<2;vis++)for(int i=0;i<10;i++) {
        bool got=candidate(h,v,rates[i],s,vis);
        bool expected=s&&vis&&(rates[i]==0||!h||v);
        if(got!=expected)return 2;
        if(rates[i]>0 && got!=original(h,v,rates[i],s,vis))return 3;
        checks++;
    }
    if(original(true,false,0,true,true)||!candidate(true,false,0,true,true))return 4;
    printf("checks=%d failures=0\n",checks);
    return 0;
}
'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--cc',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply-to-baseline',action='store_true')
    a=ap.parse_args(); source=a.source.resolve()
    lock=json.loads((HERE/'source-lock.json').read_bytes()); fix=lock['native_ass_pause_fix']
    patch=CONFIG/fix['patch']
    assert sha(patch.read_bytes())==fix['patch_sha256']
    assert not git(source,'status','--porcelain').strip()
    if a.apply_to_baseline:
        assert sha((source/'sub/osd.c').read_bytes())==fix['before_osd_sha256']
        git(source,'am','--3way',str(patch))
    assert git(source,'diff','--name-only','HEAD^','HEAD').decode().splitlines()==['sub/osd.c']
    before=git(source,'show','HEAD^:sub/osd.c'); after=(source/'sub/osd.c').read_bytes()
    assert sha(before)==fix['before_osd_sha256'] and sha(after)==fix['after_osd_sha256']
    # Validate the unchanged clock, display forecast, budget and VO bytes too.
    for name,digest in lock['native_ass_candidate']['source_sha256'].items():
        if name!='sub/osd.c': assert sha((source/name).read_bytes())==digest,name
    assert '(mpv-Yaozhi)' in (source/'common/version.c').read_text()
    original=predicate(before.decode()); fixed=predicate(after.decode())
    cases={'candidate':fixed,'old_pause_failure':original,
        'active_hold_bypass':'sub && visible',
        'hidden_track_bypass':'(!held || valid || rate <= 0) && sub',
        'missing_track_bypass':'(!held || valid || rate <= 0) && visible'}
    out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,expression in cases.items():
        for release in (False,True):
            stem=name+('-ndebug' if release else '')
            c=out.parent/(stem+'.c');exe=out.parent/(stem+'.exe')
            c.write_text(FIXTURE.replace('ORIGINAL',original).replace('CANDIDATE',expression),encoding='utf-8')
            command=[str(a.cc),'-std=c11','-Wall','-Wextra','-Werror']
            if release: command+=['-DNDEBUG']
            command+=['-o',str(exe),str(c)]
            compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
            assert compiled.returncode==0,(name,compiled.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            assert run.returncode==(0 if name=='candidate' else 2),(name,run.returncode,run.stdout)
            if name=='candidate':assert run.stdout.strip()=='checks=160 failures=0'
            rows.append({'case':stem,'returncode':run.returncode,'stdout':run.stdout,
                         'translation_sha256':sha(c.read_bytes())})
    assert sha((source/'sub/osd.c').read_bytes())==fix['after_osd_sha256']
    assert not git(source,'status','--porcelain').strip()
    report={'status':'PAUSED_BITMAP_CPU_CONTRACT_PASS_NOT_RUNTIME',
        'source_commit':git(source,'rev-parse','HEAD').decode().strip(),
        'source_tree':git(source,'rev-parse','HEAD^{tree}').decode().strip(),
        'patch_sha256':fix['patch_sha256'],'actual_osd_sha256':sha(after),'cases':rows,
        'runtime_verified':False,'Display_accepted':False}
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','source_tree','actual_osd_sha256')}))

if __name__=='__main__':main()
