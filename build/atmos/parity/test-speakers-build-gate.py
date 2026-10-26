"""Exercise exact archive resolution and refuse ambiguity/stale substitutions."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('speaker_build_gate',HERE/'verify-speakers-build.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();results=[]
    compiler='x86_64-w64-mingw32-g++ -o ffmpeg_g.exe fftools/ffmpeg.o -L/locked/lib -lspatialaudio'
    strip='x86_64-w64-mingw32-strip -o ffmpeg.exe ffmpeg_g.exe'
    cases=[('verbose-link-with-exact-post-link-strip',compiler+'\n'+strip,True),
        ('verbose-link-without-strip',compiler,True),
        ('duplicate-real-executable-link',compiler+'\n'+compiler,False),
        ('second-executable-output-command',compiler+'\nother-tool -o ffmpeg.exe ffmpeg_g.exe',False),
        ('unknown-linker-compiler','other-g++ -o ffmpeg_g.exe -lspatialaudio',False),
        ('strip-without-real-link',strip,False),
        ('strip-with-library-is-not-post-link-copy',compiler+'\n'+strip+' -lspatialaudio',False),
        ('strip-with-extra-output-is-not-post-link-copy',compiler+'\n'+strip+' -o ffmpeg_g.exe',False),
        ('unknown-strip-name',compiler+'\n'+strip.replace('x86_64-w64-mingw32-strip','other-strip'),False),
        ('reversed-strip-source-output',compiler+'\nx86_64-w64-mingw32-strip -o ffmpeg_g.exe ffmpeg.exe',False)]
    for name,raw,positive in cases:
        try:gate.ffmpeg_link_command(raw.encode())
        except ValueError as error:
            assert not positive,(name,str(error))
            results.append({'case':name,'passed':True,'refusal':str(error)})
        else:
            assert positive,'Unexpected acceptance: '+name
            results.append({'case':name,'passed':True})
    with tempfile.TemporaryDirectory(prefix='speaker-build-parser-') as folder:
        root=Path(folder);prefix=root/'install/lib';prefix.mkdir(parents=True)
        archive=prefix/'libspatialaudio.a';archive.write_bytes(b'fixture archive identity\n')
        other=root/'other';other.mkdir();(other/'libspatialaudio.a').write_bytes(b'wrong archive\n')
        cases=[('exact-absolute-archive',[str(archive)],True),
            ('exact-relative-archive',[str(archive.relative_to(root))],True),
            ('exact-search-archive',['-L'+str(prefix),'-lspatialaudio'],True),
            ('split-search-archive',['-L',str(prefix),'-lspatialaudio'],True),
            ('ordered-search-finds-expected-first',['-L'+str(prefix),'-L'+str(other),'-lspatialaudio'],True),
            ('wrong-explicit-archive',[str(other/'libspatialaudio.a')],False),
            ('wrong-search-first',['-L'+str(other),'-L'+str(prefix),'-lspatialaudio'],False),
            ('duplicate-library-input',['-L'+str(prefix),'-lspatialaudio',str(archive)],False),
            ('bare-name-without-search',['-lspatialaudio'],False),
            ('substring-does-not-count',['-L'+str(prefix),'-lspatialaudio_fake'],False),
            ('unrelated-archive-does-not-count',[str(prefix/'libspatialaudio.a.fake')],False),
            ('empty-link',[],False)]
        for name,args,positive in cases:
            try:gate.resolve_archive(args,root,archive)
            except ValueError as error:
                assert not positive,(name,str(error))
                results.append({'case':name,'passed':True,'refusal':str(error)})
            else:
                assert positive,'Unexpected acceptance: '+name
                results.append({'case':name,'passed':True})
        dynamic=prefix/'libspatialaudio.dll.a';dynamic.write_bytes(b'dynamic ambiguity\n')
        try:gate.resolve_archive(['-L'+str(prefix),'-lspatialaudio'],root,archive)
        except ValueError as error:results.append({'case':'dynamic-search-ambiguity-rejected','passed':True,'refusal':str(error)})
        else:raise AssertionError('Dynamic archive ambiguity accepted')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'passed':True,'count':len(results),'cases':results},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'count':len(results),'report':str(a.output)}))

if __name__=='__main__':main()
