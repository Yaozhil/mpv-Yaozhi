"""Compile candidates using the exact restored variant-specific static prefix.
This receipt explicitly reuses pinned build inputs; it is not an r8 fresh-CRT proof.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=['main','atmos'],required=True)
args=parser.parse_args();variant=args.variant
here=Path(__file__).resolve().parent
root=Path.cwd();wb=root/'winbuild/mpv-winbuild-cmake';source=wb/'src_packages/mpv'
out=root/'preflight-artifact';out.mkdir(exist_ok=True)
spec=json.loads((here/f'{variant}-source.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def verify(which):
 for name,expected in spec[which].items():
  p=source/name
  assert p.is_file() and sha(p)==expected,(which,name)
def run(cmd,log):
 with (out/log).open('wb') as f:
  p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
 if p.returncode:
  print((out/log).read_text(errors='replace')[-18000:])
  raise RuntimeError(f'{cmd[0]} exited {p.returncode}')
verify('before')
run(['git','-C',str(source),'apply','--check',str(here/f'{variant}.patch')],'patch-check.log')
run(['git','-C',str(source),'apply','--whitespace=nowarn',str(here/f'{variant}.patch')],'patch-apply.log')
verify('after')
build=wb/'build64/packages/mpv-prefix/src/mpv-build'
assert (build/'meson-private/coredata.dat').is_file(),str(build)
assert (build/'config.h').is_file()
original_config=(build/'config.h').read_text()
(out/'baseline-config.h').write_text(original_config)
prefix=wb/'build64/install'
cc=prefix/'bin/cross-gcc'
# The restored compiler wrapper invokes the host ccache binary. Installing it
# after Meson would poison feature/library probes with exit 127.
policy=subprocess.check_output(['apt-cache','policy','ccache'],text=True)
version=next(line.split(':',1)[1].strip() for line in policy.splitlines() if 'Candidate:' in line)
assert version!='(none)' and version and all(c.isalnum() or c in '.:+~-_' for c in version)
(out/'ccache-package-pin.txt').write_text(version+'\n'+policy)
run(['sudo','apt-get','-o','Acquire::Retries=3','-o','Acquire::http::Timeout=30',
     'install','-y','--no-install-recommends','ccache='+version],'ccache-install.log')
run([str(cc),'-v'],'compiler.log')
inputs={str(p.relative_to(wb)):sha(p) for p in (prefix/'x86_64-w64-mingw32/lib').glob('*.a')}
assert len(inputs)>35
(out/'static-inputs-before.json').write_text(json.dumps(inputs,indent=2))
info=json.loads((build/'meson-info/meson-info.json').read_text())
meson_version=info['meson_version']['full']
assert meson_version and all(c in '0123456789.' for c in meson_version)
run([sys.executable,'-m','pip','install','--disable-pip-version-check',f'meson=={meson_version}',
     'ninja==1.13.2','Mako==1.3.10','rst2pdf==0.103.1'],'host-tools.log')
run([sys.executable,'-m','pip','freeze'],'host-tools-resolved.txt')
os.environ['PATH']=str(prefix/'bin')+os.pathsep+os.environ['PATH']
pkgdir=prefix/'x86_64-w64-mingw32/lib/pkgconfig'
assert (pkgdir/'libavcodec.pc').is_file()
os.environ['PKG_CONFIG_LIBDIR']=str(pkgdir)
os.environ['PKG_CONFIG_PATH']=str(pkgdir)
run([str(prefix/'bin/x86_64-w64-mingw32-pkgconf'),'--static','--cflags','--libs',
     'libavcodec','libavformat','libavutil','libass','libplacebo'],'pkg-config-preflight.log')
run(['meson','setup','--reconfigure','--clearcache','--wrap-mode=nodownload',str(build),str(source)],'meson-reconfigure.log')
new_config=(build/'config.h').read_text()
enabled=lambda text:set(re.findall(r'^#define\s+(HAVE_[A-Z0-9_]+)\s+1\s*$',text,re.M))
lost=enabled(original_config)-enabled(new_config)
assert not lost,'Previously enabled features disappeared: '+str(sorted(lost))
(out/'preserved-features.json').write_text(json.dumps(dict(baseline=sorted(enabled(original_config)),candidate=sorted(enabled(new_config)),lost=sorted(lost)),indent=2))
previous={}
for name in ('mpv.exe','mpv.com'):
 path=build/name
 if path.is_file():
  previous[name]=dict(sha256=sha(path),mtime=path.stat().st_mtime)
  # Ephemeral restored build outputs only. Force real link targets to run,
  # including the unchanged console launcher, without touching static inputs.
  assert path.resolve().parent==build.resolve()
  path.unlink()
(out/'previous-outputs.json').write_text(json.dumps(previous,indent=2))
start=time.time()
run(['ninja','-v','-d','keeprsp','-j2','-C',str(build),'mpv.exe','mpv.com'],'compile.log')
abi_probe=here/'dv-abi-probe.c'
if abi_probe.exists():
 for language,compiler in [('c','cross-gcc'),('cpp','x86_64-w64-mingw32-g++')]:
  run([str(prefix/'bin'/compiler),'-x','c++' if language=='cpp' else 'c',
       '-O2','-static','-Wno-deprecated-declarations',
       '-I'+str(prefix/'x86_64-w64-mingw32/include'),str(abi_probe),
       '-o',str(out/f'dv-metadata-abi-{language}.exe')],f'dv-metadata-abi-{language}-compile.log')
verify('after')
assert all(sha(wb/name)==digest for name,digest in inputs.items()),'static dependency changed during mpv-only build'
binaries={}
for name in ('mpv.exe','mpv.com'):
 path=build/name
 assert path.is_file() and path.stat().st_mtime>=start,name
 import shutil
 shutil.copyfile(path,out/name)
 binaries[name]=dict(sha256=sha(path),bytes=path.stat().st_size)
for name in ('config.h','build.ninja','meson-info/intro-buildoptions.json','meson-info/intro-dependencies.json','meson-logs/meson-log.txt'):
 p=build/name
 assert p.is_file(),name
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
receipt=dict(variant=variant,phase=spec['phase'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
 config_commit=os.environ['GITHUB_SHA'],checked_out_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 source_inventory=spec['after'],static_inputs=inputs,binaries=binaries,
 reused_exact_cached_dependencies=True,fresh_crt_built=False,compiled=True,runtime_verified=False,production_installed=False)
(out/'compile-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(dict(variant=variant,compiled=True,binaries=binaries,runtime_verified=False)))
