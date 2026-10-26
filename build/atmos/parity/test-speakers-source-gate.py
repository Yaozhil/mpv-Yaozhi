"""Exercise full-tree replay and isolated legacy-parent verification with Git."""
import argparse
import copy
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('speaker_gate',HERE/'verify-speakers-source.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
sha=lambda b:hashlib.sha256(b).hexdigest()

def run(argv,cwd=None):
    p=subprocess.run(argv,cwd=cwd,capture_output=True,timeout=45,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise ValueError(repr(argv)+'\n'+p.stderr.decode('utf-8','replace'))
    return p.stdout

def git(source,*args):return run(['git','-C',str(source),'-c','core.autocrlf=false',*args])

def write(source,name,data):
    path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

def patch(config,name,before,after):
    content=''
    for path in sorted(set(before)|set(after)):
        b=before.get(path,b'').decode().splitlines(keepends=True)
        a=after.get(path,b'').decode().splitlines(keepends=True)
        content+=''.join(difflib.unified_diff(b,a,
            fromfile='a/'+path if path in before else '/dev/null',
            tofile='b/'+path if path in after else '/dev/null'))
    write(config,name,content.encode())
    return {'path':name,'sha256':sha(content.encode())}

def observe_files(source):
    return {p.relative_to(source).as_posix():p.read_bytes()
            for p in source.rglob('*') if p.is_file() and '.git' not in p.relative_to(source).parts}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();results=[]
    with tempfile.TemporaryDirectory(prefix='speaker-gate-contract-') as folder:
        root=Path(folder);config=root/'config';config.mkdir();source=root/'ffmpeg';source.mkdir()
        git(source,'init','--quiet')
        initial={'configure':b'base configure\n','libavcodec/Makefile':b'base objects\n',
                 'libavcodec/libarcdav3a.c':b'base decoder\n','unrelated/sentinel.txt':b'complete-tree sentinel\n'}
        for name,data in initial.items():write(source,name,data)
        git(source,'add','--all')
        git(source,'-c','user.name=Speaker gate fixture','-c','user.email=fixture@localhost','commit','--quiet','-m','Pinned fixture base')
        base=git(source,'rev-parse','HEAD').decode().strip()
        first={'libavcodec/libarcdav3a.c':b'base decoder\nspatial metadata\n'}
        baseline_patch=patch(config,'baseline.patch',{'libavcodec/libarcdav3a.c':initial['libavcodec/libarcdav3a.c']},first)
        git(source,'apply',str(config/baseline_patch['path']))
        parent_c=b'base decoder\nspatial metadata\npreselections\n'
        preselection=patch(config,'preselections.patch',first,{'libavcodec/libarcdav3a.c':parent_c})
        git(source,'apply',str(config/preselection['path']))
        parent={'dependencies':{'ffmpeg':{'base_commit':base,'normalize_lf_files':[],
            'seed_files':[],'baseline_patches':[baseline_patch],
            'before_source_sha256':{'libavcodec/libarcdav3a.c':sha(first['libavcodec/libarcdav3a.c'])},
            'source_sha256':{'libavcodec/libarcdav3a.c':sha(parent_c)}}},
            'patches':{'ffmpeg':dict(preselection,changed_files=['libavcodec/libarcdav3a.c'])}}
        before={name:(source/name).read_bytes() for name in gate.SOURCE_FILES if (source/name).is_file()}
        after={name:data+b'speaker integration\n' for name,data in before.items()}
        after.update({'libavcodec/libarcdav3a_speakers.cpp':b'int speaker_bridge() { return 12; }\n',
                      'libavcodec/libarcdav3a_speakers.h':b'int speaker_bridge();\n'})
        incremental=patch(config,'speakers.patch',before,after)
        layer={'patches':{'ffmpeg':dict(incremental,changed_files=list(gate.SOURCE_FILES))},
            'before_source_sha256':{name:sha(before[name]) if name in before else None for name in gate.SOURCE_FILES},
            'source_sha256':{name:sha(after[name]) for name in gate.SOURCE_FILES}}
        git(source,'apply',str(config/incremental['path']))
        old=gate.load_parent_gate();old.CONFIG=config
        frozen=observe_files(source)
        positive=gate.verify_final_ffmpeg(source,parent,layer,old)
        assert positive['source_tree']==positive['observed_tree']
        results.append({'case':'complete-final-tree-replay','passed':True})
        with gate.materialized_parent(source,positive['parent_tree'],base) as isolated:
            checked=old.verify_dependency(isolated,'ffmpeg',parent)
            assert checked['source_tree']==positive['parent_tree']
            assert not (isolated/'libavcodec/libarcdav3a_speakers.cpp').exists()
            assert (isolated/'unrelated/sentinel.txt').read_bytes()==initial['unrelated/sentinel.txt']
        assert observe_files(source)==frozen
        results.append({'case':'real-complete-parent-checkout-original-verifier-no-final-mutation','passed':True})

        def refuse(name,mutate,restore,changed_layer=None,changed_parent=None):
            mutate()
            try:
                gate.verify_final_ffmpeg(source,changed_parent or parent,changed_layer or layer,old)
            except Exception as error:
                results.append({'case':name,'passed':True,'refusal':str(error)[:500]})
            else:raise AssertionError('Gate accepted '+name)
            finally:restore()
            assert observe_files(source)==frozen

        extra=source/'unrelated/new-source.cpp'
        refuse('unrelated-new-source-rejected',lambda:extra.write_bytes(b'new source\n'),lambda:extra.unlink())
        sentinel=source/'unrelated/sentinel.txt'
        refuse('unrelated-tracked-change-rejected',lambda:sentinel.write_bytes(b'changed\n'),
               lambda:sentinel.write_bytes(frozen['unrelated/sentinel.txt']))
        header=source/'libavcodec/libarcdav3a_speakers.h'
        refuse('missing-new-bridge-rejected',lambda:header.unlink(),
               lambda:header.write_bytes(frozen['libavcodec/libarcdav3a_speakers.h']))
        cpp=source/'libavcodec/libarcdav3a_speakers.cpp'
        refuse('modified-new-bridge-rejected',lambda:cpp.write_bytes(b'wrong bridge\n'),
               lambda:cpp.write_bytes(frozen['libavcodec/libarcdav3a_speakers.cpp']))
        bad=copy.deepcopy(layer);bad['source_sha256']['configure']='0'*64
        refuse('wrong-frozen-after-digest-rejected',lambda:None,lambda:None,changed_layer=bad)
        bad=copy.deepcopy(layer);bad['before_source_sha256']['configure']='0'*64
        refuse('wrong-frozen-before-digest-rejected',lambda:None,lambda:None,changed_layer=bad)
        bad=copy.deepcopy(layer);bad['patches']['ffmpeg']['sha256']='0'*64
        refuse('wrong-patch-bytes-rejected',lambda:None,lambda:None,changed_layer=bad)
        bad=copy.deepcopy(parent);bad['dependencies']['ffmpeg']['base_commit']='0'*40
        refuse('wrong-pinned-base-rejected',lambda:None,lambda:None,changed_parent=bad)
        bad=copy.deepcopy(parent);bad['dependencies']['ffmpeg']['source_sha256']['libavcodec/libarcdav3a.c']='0'*64
        refuse('changed-parent-preselection-digest-rejected',lambda:None,lambda:None,changed_parent=bad)
        dep={'libspatialaudio':{'repository':'fixture-only','commit':base,
             'tree':git(source,'rev-parse','HEAD^{tree}').decode().strip()}}
        # Use a separate genuinely clean repository for source identity checks.
        library=root/'library'
        run(['git','-c','core.autocrlf=false','clone','--quiet','--shared',str(source),str(library)])
        gate.verify_spatialaudio(library,dep)
        (library/'untracked.cpp').write_bytes(b'extra\n')
        try:gate.verify_spatialaudio(library,dep)
        except ValueError:results.append({'case':'untracked-library-source-rejected','passed':True})
        else:raise AssertionError('Dirty speaker library accepted')
        (library/'untracked.cpp').unlink();dep['libspatialaudio']['tree']='0'*40
        try:gate.verify_spatialaudio(library,dep)
        except ValueError:results.append({'case':'wrong-library-tree-rejected','passed':True})
        else:raise AssertionError('Wrong speaker library tree accepted')
        binaries=[{'path':str(root/name),'sha256':str(n)*64}
                  for n,name in enumerate(('mpv.exe','mpv.com','ffmpeg.exe'),1)]
        gate.check_binary_bindings(binaries,{'binaries':list(reversed(binaries))})
        results.append({'case':'three-binary-path-digest-binding-order-independent','passed':True})
        def binary_refuse(name,actual,expected):
            try:gate.check_binary_bindings(actual,{'binaries':expected})
            except ValueError:results.append({'case':name,'passed':True})
            else:raise AssertionError('Binary gate accepted '+name)
        binary_refuse('missing-produced-binary-refused',binaries[:2],binaries)
        binary_refuse('missing-build-binary-refused',binaries,binaries[:2])
        binary_refuse('duplicate-produced-binary-refused',[binaries[0],binaries[0],binaries[2]],binaries)
        wrong=copy.deepcopy(binaries);wrong[0]['path']=str(root/'copied-mpv.exe')
        binary_refuse('same-digest-different-binary-path-refused',binaries,wrong)
        wrong=copy.deepcopy(binaries);wrong[0]['sha256']='f'*64
        binary_refuse('same-path-different-binary-digest-refused',binaries,wrong)
        # Reproduce the CI checkout layout, rather than placing legacy config
        # outside every Git repository as the original local fixture did.
        outer=root/'current-config-checkout';outer.mkdir();git(outer,'init','--quiet')
        nested=outer/'uninitialized-legacy';nested.mkdir()
        parent_gate=gate.load_parent_gate()
        actual_patch=HERE.parents[2]/'build/bluray-menu/patches/0062-windows-paths-and-pipes.patch'
        nested_patch=nested/'windows-paths.patch';nested_patch.write_bytes(actual_patch.read_bytes())
        assert parent_gate.changed_paths(nested,nested_patch)==[], 'Expected outer Git prefix filtering before init'
        results.append({'case':'nested-legacy-without-own-git-root-reproduces-empty-old-scope','passed':True})
        git(nested,'init','--quiet')
        expected_scope=['misc/path_utils.c','options/parse_commandline.c','osdep/io.c','test/paths.c']
        assert parent_gate.changed_paths(nested,nested_patch)==expected_scope
        results.append({'case':'nested-legacy-git-init-restores-exact-original-scope','passed':True})
        actual_legacy=outer/'legacy-network-config'
        prepared=gate.prepare_legacy_config(actual_legacy)
        assert prepared['parent_config_commit']==gate.PARENT_CONFIG
        assert Path(git(actual_legacy,'rev-parse','--show-toplevel').decode().strip()).resolve()==actual_legacy.resolve()
        legacy_gate=gate.load_parent_gate(actual_legacy)
        legacy_patch=actual_legacy/'build/bluray-menu/patches/0062-windows-paths-and-pipes.patch'
        assert legacy_gate.changed_paths(actual_legacy,legacy_patch)==expected_scope
        assert (actual_legacy/'build/atmos/parity/verify-preselections-source.py').read_bytes()==(HERE/'verify-preselections-source.py').read_bytes()
        results.append({'case':'actual-legacy-archive-preparation-has-independent-nested-git-root','passed':True})
    report={'passed':True,'cases':results,'count':len(results),
        'gate_sha256':sha((HERE/'verify-speakers-source.py').read_bytes())}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'count':len(results),'report':str(a.output)}))

if __name__=='__main__':main()
