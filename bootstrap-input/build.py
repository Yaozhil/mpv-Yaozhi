from pathlib import Path
import subprocess,os,re,shlex,json,hashlib,tarfile
root=Path.cwd();work=root/'bootstrap-build';work.mkdir()
out=root/'bootstrap-artifact';out.mkdir()
manifest=json.loads((root/'bootstrap-input/manifest.json').read_text())
archive=root/'bootstrap-input/source.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
with tarfile.open(archive) as tar:tar.extractall(work,filter='data')
b=root/'winbuild/mpv-winbuild-cmake/build64'
cm=(b/'packages/mpv-prefix/src/mpv-stamp/mpv-configure-.cmake').read_text()
command=re.search(r'set\(command "(.*?)"\)',cm)[1].split(';')
assert command[1:4]==['CONF=1','meson','setup']
command[4]=str(work/'build');command[5]=str(work/'mpv')
command=[a for a in command if not a.startswith(('-Dorender=','-Dasio=','-Dasio-sdk='))]
# Preserve actual cached compiler/options; split the one historical combined flag.
command=[v for a in command for v in (a.split(' ') if a=='-Dgl=enabled -Degl-angle=enabled' else [a])]
command=[a.replace("-Dc_args='-Wno-error=int-conversion'",'-Dc_args=-Wno-error=int-conversion') for a in command]
(out/'configure-command.json').write_text(json.dumps(command,indent=2))
for name in ['exec','meson_cross.txt']:
    (out/name).write_bytes((b/name).read_bytes())
for stage,cmd in [('configure',command),('compile',[str(b/'exec'),'LTO_JOB=1','PDB=1','ninja','-j2','-C',str(work/'build'),'mpv.exe','mpv.com'])]:
    with (out/(stage+'.log')).open('w') as log:
        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    if result.returncode:
        print((out/(stage+'.log')).read_text()[-22000:]);raise SystemExit(result.returncode)
for name in ['mpv.exe','mpv.com','config.h','compile_commands.json']:
    p=work/'build'/name
    if p.exists():(out/name).write_bytes(p.read_bytes())
manifest['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*') if p.is_file()}
(out/'build-proof.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest))
