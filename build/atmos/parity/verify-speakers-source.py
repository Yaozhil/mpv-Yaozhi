"""Verify the exact appended AV3A speaker layer without relaxing parent gates.

The actual compiled FFmpeg checkout stays unchanged. The complete old parent
tree is materialized in a bounded local shared clone and checked with the
original preselection verifier and its original three C contracts.
"""
import argparse
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CONFIG=HERE.parents[2]
PARENT_CONFIG='df1084fc3bd41d372acb789508334c95391db645'
PARENT_LOCK_SHA256='edd4197d78438f814b51ea9284bb7f0bb08268fa5842f29da16e6ca8a605697a'
LIBRARY_COMMIT='d149ed9744fd399b835c6f2920511f8cbcfce5ea'
LIBRARY_TREE='e23e9e16463cb3c2179d73de1bce220118be4950'
SOURCE_FILES=('configure','libavcodec/Makefile','libavcodec/libarcdav3a.c',
              'libavcodec/libarcdav3a_speakers.cpp','libavcodec/libarcdav3a_speakers.h')
WORKFLOW='.github/workflows/build-mpv-v100-parity.yml'
REQUIRED_TOOLS=frozenset((
    WORKFLOW,'build/av3a/libspatialaudio.cmake',
    'build/atmos/parity/prepare-speakers-winbuild.py',
    'build/atmos/parity/verify-speakers-source.py',
    'build/atmos/parity/test-speakers-source-gate.py',
    'build/atmos/parity/verify-speakers-build.py',
    'build/atmos/parity/test-speakers-build-gate.py',
    'build/av3a/test-speaker-build-glue.py'))

def require(test,message):
    if not test:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def command(argv,cwd=None,timeout=90):
    result=subprocess.run([str(x) for x in argv],cwd=cwd,capture_output=True,
        timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    require(result.returncode==0,'Command failed: '+repr(argv)+'\n'+
        result.stderr.decode('utf-8','replace')[:12000])
    return result.stdout

def git(source,*args):return command(['git','-C',source,'-c','core.autocrlf=false',*args])

def checked_file(config,relative,digest):
    require(isinstance(relative,str) and relative and '\\' not in relative and
        not Path(relative).is_absolute() and '..' not in Path(relative).parts,
        'Unsafe configuration path: '+str(relative))
    path=(config/relative).resolve()
    require(path.is_relative_to(config.resolve()),'Configuration path escape')
    require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),
        'Invalid digest: '+relative)
    require(path.is_file() and sha(path.read_bytes())==digest,'Input digest differs: '+relative)
    return path

def load_parent_gate(config=CONFIG):
    path=config/'build/atmos/parity/verify-preselections-source.py'
    spec=importlib.util.spec_from_file_location('speaker_parent_gate',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def validate_lock(lock,config=CONFIG):
    layer=lock['av3a_speakers']
    require(layer['version']==1,'Review a new speaker source schema')
    require(layer['parent_config_commit']==PARENT_CONFIG,'Wrong complete parent configuration')
    require(layer['parent_source_lock_sha256']==PARENT_LOCK_SHA256,'Wrong parent source-lock identity')
    original=git(config,'show',PARENT_CONFIG+':build/atmos/parity/source-lock.json')
    require(sha(original)==PARENT_LOCK_SHA256,'Parent configuration source-lock differs')
    retained=copy.deepcopy(lock);del retained['av3a_speakers']
    require(retained==json.loads(original),'A historical source-lock field was modified')
    require(set(layer['patches'])=={'ffmpeg'},'Exactly one appended FFmpeg patch is required')
    item=layer['patches']['ffmpeg']
    require(tuple(sorted(item['changed_files']))==SOURCE_FILES,'Speaker patch must change exactly five approved paths')
    patch=checked_file(config,item['path'],item['sha256'])
    old=load_parent_gate(config)
    require(old.changed_paths(config,patch)==list(SOURCE_FILES),'Actual patch scope differs')
    for key in ('before_source_sha256','source_sha256'):
        require(set(layer[key])==set(SOURCE_FILES),'Incomplete five-path digest set: '+key)
        require(all(v is None or isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v)
                    for v in layer[key].values()),'Invalid five-path digest: '+key)
    require(all(layer['source_sha256'][p] is not None for p in SOURCE_FILES),'Missing final speaker source')
    require(layer['before_source_sha256']['libavcodec/libarcdav3a_speakers.cpp'] is None and
            layer['before_source_sha256']['libavcodec/libarcdav3a_speakers.h'] is None,
            'New bridge paths must be absent in the parent')
    dep=layer['libspatialaudio']
    require(dep['repository']=='https://github.com/videolan/libspatialaudio.git' and
            dep['commit']==LIBRARY_COMMIT and dep['tree']==LIBRARY_TREE,'Unapproved speaker library source')
    require(set(layer['tools_sha256'])>=REQUIRED_TOOLS,'Incomplete new speaker tool identities')
    for path,digest in layer['tools_sha256'].items():checked_file(config,path,digest)
    # Every actually executed parent tool and all parent inputs remain byte
    # exact. The old workflow is evaluated separately in the parent view.
    parent=lock['av3a_preselections']
    for path,digest in parent['tools_sha256'].items():checked_file(config,path,digest)
    for item in parent['patches'].values():
        path=checked_file(config,item['path'],item['sha256'])
        require(old.changed_paths(config,path)==sorted(item['changed_files']),'Parent patch scope differs')
    for kind in ('sdk','ffmpeg'):
        for item in parent['dependencies'][kind]['baseline_patches']:
            checked_file(config,item['path'],item['sha256'])
    require(layer['contracts'],'At least one actual speaker contract is required')
    for item in layer['contracts']:
        checked_file(config,item['path'],item['sha256'])
        require(1<=item.get('timeout_seconds',120)<=300,'Invalid speaker contract timeout')
    return layer

def prepare_legacy_config(destination,config=CONFIG):
    require(not destination.exists(),'Refuse to overwrite legacy configuration view')
    archive=git(config,'archive','--format=tar',PARENT_CONFIG)
    require(len(archive)<=64*1024*1024,'Legacy configuration archive exceeds bound')
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
        members=tar.getmembers()
        require(len(members)<=2000,'Legacy configuration file count exceeds bound')
        total=0
        for member in members:
            path=destination/member.name
            require(path.resolve().is_relative_to(destination.resolve()) and
                    (member.isdir() or member.isfile()),'Unsafe legacy archive entry')
            if member.isdir():path.mkdir(parents=True,exist_ok=True);continue
            total+=member.size;require(total<=64*1024*1024,'Legacy configuration expansion exceeds bound')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(tar.extractfile(member).read())
            os.chmod(path,member.mode)
    require(sha((destination/'build/atmos/parity/source-lock.json').read_bytes())==PARENT_LOCK_SHA256,
            'Materialized legacy configuration differs')
    # CI places this view inside the current checkout. Give it an independent
    # Git root so the unchanged parent `git apply --numstat` commands do not
    # inherit the outer repository's subdirectory prefix and filter all paths.
    git(destination,'init','--quiet')
    require(Path(git(destination,'rev-parse','--show-toplevel').decode().strip()).resolve()==destination.resolve(),
            'Legacy configuration must have its own independent Git root')
    return {'parent_config_commit':PARENT_CONFIG,'archive_sha256':sha(archive),
            'files':sum(m.isfile() for m in members),'bytes':total,
            'parent_source_lock_sha256':PARENT_LOCK_SHA256}

def expected_parent_tree(source,parent,old):
    expected=parent['dependencies']['ffmpeg']
    require(old.git(source,'rev-parse','HEAD').decode().strip()==expected['base_commit'],
            'Unexpected pinned FFmpeg commit')
    with old.temporary_index(source) as index:
        for rel in expected.get('normalize_lf_files',[]):
            entry=old.index_entry(source,index,rel);require(entry,'Missing normalization input')
            content=old.git(source,'cat-file','blob',entry[1])
            old.install_blob(source,index,rel,content.replace(b'\r\n',b'\n'))
        for item in expected.get('seed_files',[]):
            path=old.config_file(item['source']);raw=path.read_bytes()
            require(sha(raw)==item['sha256'],'Parent seed differs')
            old.install_blob(source,index,item['path'],raw,item.get('mode','100644'))
        for item in expected['baseline_patches']:old.replay_patch(source,index,item)
        for rel,digest in expected['before_source_sha256'].items():
            entry=old.index_entry(source,index,rel)
            raw=old.git(source,'cat-file','blob',entry[1]) if entry else None
            require((sha(raw) if raw is not None else None)==digest,'Historical FFmpeg before digest differs')
        old.replay_patch(source,index,parent['patches']['ffmpeg'])
        for rel,digest in expected['source_sha256'].items():
            entry=old.index_entry(source,index,rel)
            raw=old.git(source,'cat-file','blob',entry[1]) if entry else None
            require((sha(raw) if raw is not None else None)==digest,'Historical FFmpeg final digest differs')
        return old.git(source,'write-tree',index=index).decode().strip()

def verify_final_ffmpeg(source,parent,layer,old):
    parent_tree=expected_parent_tree(source,parent,old)
    with old.temporary_index(source) as index:
        old.git(source,'read-tree',parent_tree,index=index)
        for rel,digest in layer['before_source_sha256'].items():
            entry=old.index_entry(source,index,rel)
            raw=old.git(source,'cat-file','blob',entry[1]) if entry else None
            require((sha(raw) if raw is not None else None)==digest,'Speaker before source differs: '+rel)
        old.replay_patch(source,index,layer['patches']['ffmpeg'])
        final_tree=old.git(source,'write-tree',index=index).decode().strip()
        scope=sorted(old.git(source,'diff','--name-only',parent_tree,final_tree).decode().splitlines())
        require(scope==list(SOURCE_FILES),'Speaker incremental scope differs')
        for rel,digest in layer['source_sha256'].items():
            entry=old.index_entry(source,index,rel)
            raw=old.git(source,'cat-file','blob',entry[1]) if entry else None
            require((sha(raw) if raw is not None else None)==digest,'Speaker final source differs: '+rel)
    with old.temporary_index(source) as index:observed,edits=old.observe_worktree(source,index)
    if observed!=final_tree:
        detail=old.git(source,'diff-tree','--no-commit-id','--name-status','-r',final_tree,observed).decode()
        raise ValueError('Complete speaker FFmpeg tree differs from exact replay: '+detail[:12000])
    return {'base_commit':parent['dependencies']['ffmpeg']['base_commit'],
            'parent_tree':parent_tree,'source_tree':final_tree,'observed_tree':observed,
            'incremental_changed_files':scope,'observed_changed_files':edits,
            'source_sha256':layer['source_sha256'],'complete_locked_patch_replay_matches':True}

@contextmanager
def materialized_parent(source,tree,base_commit):
    with tempfile.TemporaryDirectory(prefix='av3a-speaker-parent-') as folder:
        parent=Path(folder)/'ffmpeg'
        command(['git','-c','core.autocrlf=false','clone','--shared','--no-checkout',source,parent])
        git(parent,'update-ref','--no-deref','HEAD',base_commit)
        git(parent,'read-tree',tree)
        git(parent,'checkout-index','--all','--force')
        yield parent

def verify_spatialaudio(source,layer):
    expected=layer['libspatialaudio']
    commit=git(source,'rev-parse','HEAD').decode().strip()
    tree=git(source,'rev-parse','HEAD^{tree}').decode().strip()
    require(commit==expected['commit'] and tree==expected['tree'],'Pinned libspatialaudio identity differs')
    require(not git(source,'status','--porcelain','--untracked-files=all').strip(),
            'libspatialaudio complete source must be clean')
    return {'repository':expected['repository'],'commit':commit,'tree':tree,
            'complete_clean_source_verified':True}

def run_speaker_contracts(layer,substitutions,output):
    require(not output.exists(),'Refuse to overwrite speaker contracts')
    output.mkdir(parents=True)
    results=[]
    for number,item in enumerate(layer['contracts']):
        script=checked_file(CONFIG,item['path'],item['sha256'])
        values=dict(substitutions,output_dir=str(output.resolve()))
        argv=[sys.executable,'-B',str(script),*[arg.format_map(values) for arg in item['args']]]
        p=subprocess.run(argv,capture_output=True,timeout=item.get('timeout_seconds',120),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/f'contract-{number}.stdout.log').write_bytes(p.stdout)
        (output/f'contract-{number}.stderr.log').write_bytes(p.stderr)
        results.append({'command':argv,'exit':p.returncode,'script_sha256':item['sha256']})
        require(p.returncode==0,'Actual speaker contract failed: '+str(script))
    return results

def check_binary_bindings(binaries,build_report):
    expected=build_report['binaries']
    require(len(binaries)==3 and len(expected)==3,'Exactly three produced binary bindings are required')
    def identities(rows):
        items=[]
        for row in rows:
            require(isinstance(row.get('path'),str) and row['path'] and
                    isinstance(row.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',row['sha256']),
                    'Malformed binary path/digest binding')
            items.append((str(Path(row['path']).resolve()),row['sha256']))
        require(len({path for path,digest in items})==3 and len(set(items))==3,
                'Duplicate produced binary binding')
        return sorted(items)
    require(identities(binaries)==identities(expected),
            'Compiled source/link receipts bind different actual binary paths or digests')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-legacy-config',type=Path)
    p.add_argument('--sdk-source',type=Path);p.add_argument('--ffmpeg-source',type=Path)
    p.add_argument('--spatialaudio-source',type=Path);p.add_argument('--cc');p.add_argument('--cxx')
    p.add_argument('--binary',type=Path,action='append',default=[])
    p.add_argument('--build-report',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--parent-output',type=Path)
    a=p.parse_args();lock=json.loads((HERE/'source-lock.json').read_bytes());layer=validate_lock(lock)
    if a.prepare_legacy_config:
        require(not any((a.sdk_source,a.ffmpeg_source,a.spatialaudio_source,a.output,a.parent_output)),
                'Use separate legacy-view and source-verification invocations')
        print(json.dumps(prepare_legacy_config(a.prepare_legacy_config.resolve()),indent=2));return
    require(all((a.sdk_source,a.ffmpeg_source,a.spatialaudio_source,a.cc,a.cxx,a.output,a.parent_output)),
            'All three sources, C/C++ compilers and both report paths are required')
    require(not a.output.exists() and not a.parent_output.exists(),'Refuse to overwrite source evidence')
    old=load_parent_gate();parent=lock['av3a_preselections']
    result={'status':'SPEAKERS_SOURCE_FAILED','runtime_verified':False}
    try:
        final=verify_final_ffmpeg(a.ffmpeg_source,parent,layer,old)
        sdk=old.verify_dependency(a.sdk_source,'sdk',parent)
        spatial=verify_spatialaudio(a.spatialaudio_source,layer)
        with materialized_parent(a.ffmpeg_source,final['parent_tree'],final['base_commit']) as parent_source:
            old_ffmpeg=old.verify_dependency(parent_source,'ffmpeg',parent)
            contracts=old.run_contracts(parent,a.sdk_source,parent_source,a.cc,a.parent_output.with_suffix(''))
            parent_report={'status':'EXACT_PRESELECTIONS_DEPENDENCIES_AND_C_CONTRACT_PASS',
                'verification_scope':'complete-isolated-parent-of-speaker-layer',
                'actual_final_ffmpeg_checkout_unmodified':True,
                'dependencies':{'sdk':sdk,'ffmpeg':old_ffmpeg},'contracts':contracts,
                'cpu_contract_passed':True,'runtime_verified':False}
            a.parent_output.write_text(json.dumps(parent_report,indent=2)+'\n',encoding='utf-8')
        values={'sdk_source':str(a.sdk_source.resolve()),'ffmpeg_source':str(a.ffmpeg_source.resolve()),
                'spatialaudio_source':str(a.spatialaudio_source.resolve()),'cc':a.cc,'cxx':a.cxx}
        new_contracts=run_speaker_contracts(layer,values,a.output.with_suffix(''))
        require(verify_final_ffmpeg(a.ffmpeg_source,parent,layer,old)==final,
                'Actual final FFmpeg source changed during parent/contracts verification')
        require(old.verify_dependency(a.sdk_source,'sdk',parent)==sdk,'Actual SDK source changed')
        require(verify_spatialaudio(a.spatialaudio_source,layer)==spatial,'Actual speaker library changed')
        binaries=[]
        for path in a.binary:
            require(path.is_file() and path.stat().st_size>0,'Missing bound produced binary')
            binaries.append({'path':str(path.resolve()),'sha256':sha(path.read_bytes()),'size':path.stat().st_size})
        require(a.build_report and a.build_report.is_file(),'Compiled archive/bridge/link receipt required')
        build_report=json.loads(a.build_report.read_bytes())
        require(build_report['status']=='PASS_SPEAKERS_ARCHIVE_BRIDGE_AND_FINAL_LINKS' and
            build_report['source_lock_sha256']==sha((HERE/'source-lock.json').read_bytes()),
            'Compiled speaker link receipt differs')
        check_binary_bindings(binaries,build_report)
        result={'status':'EXACT_SPEAKERS_FINAL_SOURCE_AND_PARENT_CONTRACTS_PASS',
            'dependencies':{'sdk':sdk,'ffmpeg':final,'libspatialaudio':spatial},
            'parent_report_sha256':sha(a.parent_output.read_bytes()),
            'contracts':new_contracts,'bound_binary_artifacts':binaries,
            'compiled_link_report_sha256':sha(a.build_report.read_bytes()),
            'actual_final_sources_unchanged':True,'parent_lock_unchanged':True,
            'source_lock_sha256':sha((HERE/'source-lock.json').read_bytes()),
            'runtime_verified':False}
    except Exception as error:
        result['error']=str(error);raise
    finally:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
