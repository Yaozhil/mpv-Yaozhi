"""Package only successful source-bound candidates; never installs them."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil

HERE = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', type=Path, required=True)
    p.add_argument('--variant', choices=['main', 'atmos'], required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = a.winbuild.resolve()
    out = a.output.resolve()
    assert not out.exists()
    source = json.loads(Path('mpv-042-compiled-source-' + a.variant + '.json').read_bytes())
    assert source['status'] == 'PASS_COMPILED_042_SOURCE_AND_BINARY_BINDING_NOT_PLAYBACK'
    assert source['variant'] == a.variant and source['compiled'] is True
    assert source['migration_lock']['sha256'] == sha(HERE / 'migration-lock.json'), 'Source receipt uses another migration lock'
    lock = json.loads((HERE / 'migration-lock.json').read_bytes())
    assert source['upstream_commit'] == lock['upstream_commit']
    assert source['source_tree'] == lock['variants'][a.variant]['source_tree']
    deps = json.loads(Path('mpv-042-dependencies-compiled-' + a.variant + '.json').read_bytes())
    assert deps['status'] == 'PASS_CONFIGURED_INPUTS_TO_DEMUX_ARCHIVE_AND_MPV_LINK_NOT_RUNTIME_ACCEPTANCE'
    assert deps['variant'] == a.variant
    for receipt in [source, deps]:
        assert receipt['github_run_id'] and receipt['github_run_id'] == os.environ.get('GITHUB_RUN_ID'), 'Wrong CI run'
        assert receipt['github_run_attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT'), 'Wrong CI attempt'
    for row in source['binaries']:
        assert sha(Path(row['path'])) == row['sha256']
    dirs = list((root / 'build64').glob('mpv-x86_64-*'))
    assert len(dirs) == 1 and dirs[0].is_dir()
    main_binary = dirs[0] / 'mpv.exe'
    assert any(Path(r['path']).resolve() == main_binary and r['sha256'] == sha(main_binary) for r in source['binaries'])
    ffmpeg = root / 'build64/install/x86_64-w64-mingw32/bin/ffmpeg.exe'
    for binary in [main_binary, ffmpeg]:
        assert any(Path(r['path']).resolve() == binary and r['sha256'] == sha(binary) for r in deps['binaries']), 'Missing or stale compiled dependency binding'
    probe = root / 'ffmpeg-nested-io-test.exe'
    assert probe.is_file(), 'Missing callback probe'
    for suffix in ['.build.json', '.compiler-version.txt']:
        assert Path(str(probe) + suffix).is_file(), 'Missing callback probe compiler evidence'
    probe_build = json.loads(Path(str(probe) + '.build.json').read_bytes())
    assert probe_build['status'] == 'PASS_PROBE_COMPILED_NOT_RUN'
    assert probe_build['binary']['sha256'] == sha(probe), 'Callback probe differs from compiler receipt'
    assert probe_build['source']['sha256'] == sha(HERE / 'dependencies/test_custom_io_cleanup.c'), 'Callback probe uses another test source'
    out.mkdir()
    for path in dirs[0].iterdir():
        if path.is_file():
            shutil.copy2(path, out / path.name)
    prefix = root / 'build64/install/x86_64-w64-mingw32/bin'
    for name in ['ffmpeg.exe', 'ffprobe.exe']:
        if name == 'ffprobe.exe' and not (prefix / name).exists():
            continue  # This established FFmpeg recipe explicitly disables ffprobe.
        assert (prefix / name).is_file()
        shutil.copy2(prefix / name, out / ('ffmpeg-av3a-validation.exe' if name == 'ffmpeg.exe' else name))
    assert probe.is_file()
    shutil.copy2(probe, out / probe.name)
    for suffix in ['.build.json', '.compiler-version.txt']:
        sidecar = Path(str(probe) + suffix)
        assert sidecar.is_file(), 'Missing callback probe compiler evidence'
        shutil.copy2(sidecar, out / sidecar.name)
    for report in Path('.').glob('mpv-042-*.json'):
        shutil.copy2(report, out / report.name)
    rows = [{'path': p.relative_to(out).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
            for p in sorted(out.rglob('*')) if p.is_file()]
    (out / 'CANDIDATE-SHA256.json').write_text(json.dumps({'variant': a.variant, 'files': rows,
                  'upstream_commit': lock['upstream_commit'], 'source_tree': source['source_tree'],
                  'migration_lock_sha256': sha(HERE / 'migration-lock.json'),
                  'github_run_id': os.environ.get('GITHUB_RUN_ID'), 'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                  'production_installed': False, 'runtime_acceptance': False}, indent=2) + '\n')
    (out / 'SHA256SUMS.txt').write_text(''.join(r['sha256'] + '  ' + r['path'] + '\n' for r in rows))
    print(json.dumps({'status': 'PACKAGED_SOURCE_BOUND_042_CANDIDATE', 'variant': a.variant, 'files': len(rows)}))


if __name__ == '__main__':
    main()
