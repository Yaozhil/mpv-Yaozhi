"""Bind fixed speaker source to the archive, FFmpeg bridge and final links."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time

COMMIT='d149ed9744fd399b835c6f2920511f8cbcfce5ea'
TREE='e23e9e16463cb3c2179d73de1bce220118be4950'

def require(test,message):
    if not test:raise ValueError(message)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):return json.loads(path.read_bytes())

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def run(argv,timeout=60):
    p=subprocess.run([str(x) for x in argv],capture_output=True,timeout=timeout)
    require(p.returncode==0,'Build evidence command failed: '+repr(argv)+'\n'+p.stderr.decode('utf-8','replace')[:2000])
    return p.stdout

def source_identity(source):
    commit=run(['git','-C',source,'rev-parse','HEAD']).decode().strip()
    tree=run(['git','-C',source,'rev-parse','HEAD^{tree}']).decode().strip()
    require(commit==COMMIT and tree==TREE,'Speaker dependency pinned source differs')
    require(not run(['git','-C',source,'status','--porcelain','--untracked-files=all']).strip(),
            'Speaker dependency source is not completely clean')
    files={}
    for row in run(['git','-C',source,'ls-files','-s','-z']).split(b'\0'):
        if not row:continue
        left,name=row.split(b'\t',1);mode,blob,stage=left.split()
        require(mode in (b'100644',b'100755') and stage==b'0','Unexpected library source entry')
        rel=name.decode();path=source/rel;raw=path.read_bytes()
        require(hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==blob.decode(),
                'Actual library source differs from Git blob: '+rel)
        files[rel]={'sha256':sha(path),'git_blob':blob.decode(),'bytes':len(raw)}
    return {'commit':commit,'tree':tree,'files':files}

def resolve_archive(arguments,cwd,expected):
    expected=expected.resolve();direct=[];search=[]
    for index,arg in enumerate(arguments):
        if arg.startswith('-L') and len(arg)>2:search.append(Path(arg[2:]))
        elif arg=='-L':
            require(index+1<len(arguments),'Dangling library search flag');search.append(Path(arguments[index+1]))
        elif arg=='-lspatialaudio':direct.append('search')
        elif arg.endswith(('libspatialaudio.a','libspatialaudio.dll.a')):
            p=Path(arg);direct.append((cwd/p).resolve() if not p.is_absolute() else p.resolve())
    require(len(direct)==1,'Require exactly one actual spatialaudio link input')
    if direct[0]=='search':
        candidates=[]
        for folder in search:
            folder=(cwd/folder).resolve() if not folder.is_absolute() else folder.resolve()
            dynamic=folder/'libspatialaudio.dll.a'
            require(not dynamic.exists(),'Ambiguous dynamic spatialaudio archive in linker search path')
            candidate=folder/'libspatialaudio.a'
            if candidate.is_file():candidates.append(candidate)
        require(candidates and candidates[0]==expected,'-lspatialaudio resolves to a different archive')
    else:require(direct[0]==expected,'Explicit speaker archive link differs')
    return {'archive':str(expected),'sha256':sha(expected),'link_kind':'search' if direct[0]=='search' else 'explicit'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['before','after','final'],required=True)
    p.add_argument('--winbuild',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--build',type=Path);p.add_argument('--prefix',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--binary',type=Path,action='append',default=[])
    a=p.parse_args();w=a.winbuild.resolve();config=a.config.resolve();e=w/'speaker-evidence'
    source=(a.source or w/'src_packages/libspatialaudio').resolve()
    build=(a.build or w/'build64/packages/libspatialaudio-prefix/src/libspatialaudio-build').resolve()
    prefix=(a.prefix or w/'build64/install/x86_64-w64-mingw32').resolve()
    require(source==w/'src_packages/libspatialaudio' and
        build==w/'build64/packages/libspatialaudio-prefix/src/libspatialaudio-build' and
        prefix==w/'build64/install/x86_64-w64-mingw32','Wrong actual source/build/install paths')
    current=source_identity(source);installed=prefix/'lib/libspatialaudio.a'
    lock=read(config/'build/atmos/parity/source-lock.json')['av3a_speakers']
    require(sha(Path(__file__).resolve())==lock['tools_sha256']['build/atmos/parity/verify-speakers-build.py'],
            'Actual speaker build verifier differs from source lock')
    recipe=w/'packages/libspatialaudio.cmake'
    require(sha(recipe)==lock['tools_sha256']['build/av3a/libspatialaudio.cmake'],'Speaker recipe differs')
    if a.phase=='before':
        require(not (e/'before.json').exists(),'Speaker compiler-input receipt already exists')
        cache=(build/'CMakeCache.txt').read_text()
        for entry in ('BUILD_SHARED_LIBS:BOOL=OFF','HAVE_MIT_HRTF:BOOL=ON',
                      'BUILD_TESTING:BOOL=OFF','CMAKE_DISABLE_FIND_PACKAGE_MySofa:BOOL=TRUE'):
            require(entry in cache,'Speaker CMake option differs: '+entry)
        compilation=read(build/'compile_commands.json')
        require(compilation and all(Path(x['directory']).resolve()==build for x in compilation),'Wrong speaker compile directories')
        for row in compilation:
            path=Path(row['file']).resolve();require(path.is_relative_to(source),'Compile source escapes locked library')
            arguments=shlex.split(row['command']) if 'command' in row else row['arguments']
            require(arguments and Path(arguments[0]).resolve() in {
                (w/'build64/install/bin/x86_64-w64-mingw32-gcc').resolve(),
                (w/'build64/install/bin/x86_64-w64-mingw32-g++').resolve()},'Wrong actual speaker compiler')
            require('-c' in arguments,'Speaker compile command missing compile operation')
        save(e/'source-manifest.json',current)
        for rel in ('CMakeCache.txt','compile_commands.json','build.ninja'):
            target=e/'configuration'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(build/rel,target)
        report={'status':'PASS_SPEAKERS_COMPILER_INPUTS','started_ns':time.time_ns(),
            'source_manifest_sha256':sha(e/'source-manifest.json'),'recipe_sha256':sha(recipe),
            'configuration_sha256':{rel:sha(build/rel) for rel in ('CMakeCache.txt','compile_commands.json','build.ninja')}}
        save(e/'before.json',report)
    elif a.phase=='after':
        before=read(e/'before.json');require(current==read(e/'source-manifest.json'),'Speaker source changed while compiling')
        require(sha(e/'source-manifest.json')==before['source_manifest_sha256'],'Speaker source manifest changed')
        for rel,digest in before['configuration_sha256'].items():require(sha(build/rel)==digest,'Speaker compiler graph changed')
        built=build/'libspatialaudio.a'
        require(built.is_file() and installed.is_file() and sha(built)==sha(installed),'Installed speaker archive differs from build')
        require(installed.stat().st_mtime_ns>before['started_ns'],'Missing fresh installed speaker archive')
        for path in (build/'.ninja_log',build/'install_manifest.txt'):
            require(path.is_file(),'Missing real library build/install evidence');shutil.copyfile(path,e/path.name)
        shutil.copyfile(installed,e/'libspatialaudio.a')
        report={'status':'PASS_SPEAKERS_COMPILED_ARCHIVE','before_sha256':sha(e/'before.json'),
                'archive_sha256':sha(installed),'archive_bytes':installed.stat().st_size}
        save(e/'after.json',report)
    else:
        before=read(e/'before.json');after=read(e/'after.json')
        require(current==read(e/'source-manifest.json'),'Final speaker source differs')
        require(sha(e/'before.json')==after['before_sha256'] and
                sha(installed)==after['archive_sha256']==sha(e/'libspatialaudio.a'),'Final speaker archive identity differs')
        module_path=config/'build/atmos/parity/verify-dependency-build.py'
        spec=importlib.util.spec_from_file_location('speaker_link_parent',module_path)
        parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
        mpv=w/'build64/packages/mpv-prefix/src/mpv-build'
        commands=run(['ninja','-C',mpv,'-t','commands','mpv.exe'])
        query=run(['ninja','-C',mpv,'-t','query','mpv.exe'])
        expanded=run(['ninja','-C',mpv,'-t','compdb','-x']);graph=(mpv/'build.ninja').read_bytes()
        for name,raw in [('mpv-commands.txt',commands),('mpv-query.txt',query),('mpv-compdb.json',expanded),('mpv-build.ninja',graph)]:
            (e/name).write_bytes(raw)
        mpv_command,old_binding=parent.check_mpv_link(w,commands,query,json.loads(expanded),graph)
        mpv_binding=resolve_archive(shlex.split(mpv_command),mpv,installed)
        ffbuild=w/'build64/packages/ffmpeg-prefix/src/ffmpeg-build'
        log_path=w/'build64/packages/ffmpeg-prefix/src/ffmpeg-stamp/ffmpeg-build-out.log'
        require(log_path.is_file(),'Missing actual verbose FFmpeg build log')
        raw=log_path.read_bytes();(e/'ffmpeg-build-out.log').write_bytes(raw)
        links=[]
        for line in raw.decode('utf-8','replace').splitlines():
            try:args=shlex.split(line)
            except ValueError:continue
            if len(args)<3 or '-o' not in args:continue
            index=args.index('-o')
            if index+1<len(args) and args[index+1] in ('ffmpeg_g.exe','ffmpeg.exe'):
                links.append(args)
        require(len(links)==1,'Require one actual complete FFmpeg executable linker command')
        require(Path(links[0][0]).name in ('x86_64-w64-mingw32-g++','x86_64-w64-mingw32-gcc','cross-g++','cross-gcc'),
                'Unexpected FFmpeg linker compiler')
        ffmpeg_binding=resolve_archive(links[0],ffbuild,installed)
        bridge=ffbuild/'libavcodec/libarcdav3a_speakers.o'
        avcodec=ffbuild/'libavcodec/libavcodec.a'
        require(bridge.is_file() and avcodec.is_file(),'Missing actual compiled speaker bridge/archive')
        require(bridge.stat().st_mtime_ns>before['started_ns'] and
                avcodec.stat().st_mtime_ns>=bridge.stat().st_mtime_ns,
                'Speaker bridge object/archive are stale or in the wrong build order')
        ar=w/'build64/install/bin/x86_64-w64-mingw32-ar'
        members=run([ar,'t',avcodec]).decode().splitlines()
        require(members.count('libarcdav3a_speakers.o')==1,'Bridge object missing/duplicated in actual libavcodec.a')
        obj=run([ar,'p',avcodec,'libarcdav3a_speakers.o'])
        require(hashlib.sha256(obj).hexdigest()==sha(bridge),'libavcodec contains a different speaker bridge')
        bridge_lines=[line for line in raw.decode('utf-8','replace').splitlines()
                      if 'libarcdav3a_speakers.cpp' in line and 'libarcdav3a_speakers.o' in line]
        require(len(bridge_lines)==1,'Require one actual speaker C++ bridge compilation')
        bridge_args=shlex.split(bridge_lines[0]);require('-std=c++14' in bridge_args and '-c' in bridge_args,
            'Speaker bridge C++14 actual compile command missing')
        bridge_source=w/'src_packages/ffmpeg/libavcodec/libarcdav3a_speakers.cpp'
        bridge_inputs=[Path(x) for x in bridge_args if x.endswith('libarcdav3a_speakers.cpp')]
        require(len(bridge_inputs)==1 and
                ((ffbuild/bridge_inputs[0]).resolve() if not bridge_inputs[0].is_absolute()
                 else bridge_inputs[0].resolve())==bridge_source.resolve(),
                'Actual C++ bridge compiler consumes a different source')
        require(sha(bridge_source)==lock['source_sha256']['libavcodec/libarcdav3a_speakers.cpp'],
                'Actual bridge source differs from frozen source lock')
        binaries=[];require(len(a.binary)>=3,'Bind mpv.exe/mpv.com/FFmpeg executable')
        for binary in a.binary:
            require(binary.is_file() and binary.stat().st_mtime_ns>before['started_ns'],'Missing/stale produced binary')
            binaries.append({'path':str(binary.resolve()),'sha256':sha(binary),'bytes':binary.stat().st_size})
        report={'status':'PASS_SPEAKERS_ARCHIVE_BRIDGE_AND_FINAL_LINKS',
            'after_sha256':sha(e/'after.json'),'archive_sha256':sha(installed),
            'bridge_object_sha256':sha(bridge),'avcodec_archive_sha256':sha(avcodec),
            'bridge_source_sha256':sha(bridge_source),'bridge_compile_command':bridge_lines[0],
            'mpv_link':mpv_binding,'ffmpeg_link':ffmpeg_binding,
            'original_libplacebo_link_binding':old_binding,'binaries':binaries,
            'actual_source_manifest_sha256':sha(e/'source-manifest.json'),
            'source_lock_sha256':sha(config/'build/atmos/parity/source-lock.json')}
        save(e/'final.json',report)
    if a.output:save(a.output,report)
    print(json.dumps({'status':report['status']}))

if __name__=='__main__':main()
