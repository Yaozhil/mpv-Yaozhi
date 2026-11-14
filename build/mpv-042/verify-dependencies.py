"""Close real configure/CRT/compiled provenance gates for this exact CI attempt."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CRT_FILES = ['crt2.o', 'dllcrt2.o', 'libmingw32.a', 'libmingwex.a']


def record(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return {'path': str(path), 'sha256': h.hexdigest(), 'bytes': path.stat().st_size,
            'mtime': path.stat().st_mtime}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', type=Path, required=True)
    p.add_argument('--variant', choices=['main', 'atmos'], required=True)
    p.add_argument('--phase', choices=['configured', 'crt-built', 'compiled'], required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = a.winbuild.resolve()
    evidence = root / 'mpv-042-evidence' / a.variant
    evidence.mkdir(parents=True, exist_ok=True)
    configured = evidence / 'dependency-configure-gate.json'
    crt = evidence / 'fresh-crt.json'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    if a.phase == 'configured':
        assert not configured.exists(), 'Refuse to refresh configured proof in the same build'
        subprocess.run([sys.executable, str(HERE / 'dependencies/check_candidate_dependencies.py'),
                        '--winbuild', str(root), '--variant', a.variant, '--dependencies',
                        str(HERE / 'dependencies/dependency-provenance.json'), '--regenerate-mingw',
                        '--output', str(evidence)], check=True)
        shutil.copyfile(configured, a.output)
    elif a.phase == 'crt-built':
        configured_data = json.loads(configured.read_bytes())
        assert configured_data['status'] == 'PASS_REAL_GRAPH_BASE_PINS_AND_NEW_GENERATION_NOT_BINARY_ACCEPTANCE'
        assert configured_data['variant'] == a.variant, 'Configured receipt belongs to another variant'
        assert configured_data['github_run_id'] and configured_data['github_run_id'] == os.environ.get('GITHUB_RUN_ID')
        assert configured_data['github_run_attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT'), 'Configured receipt belongs to another CI attempt'
        assert not crt.exists(), 'Refuse to refresh CRT proof'
        mingw = root / 'src_packages/mingw-w64'
        for item in configured_data['mingw']['generated_files']:
            relative = item['path'].removeprefix('generated/')
            assert record(mingw / relative)['sha256'] == item['sha256'], 'CRT generation differs from reviewed input: ' + relative
        stamp_dirs = list((root / 'build64/toolchain').glob('**/mingw-w64-crt-stamp'))
        assert len(stamp_dirs) == 1
        stamp = stamp_dirs[0] / 'mingw-w64-crt-install'
        assert stamp.exists(), 'No successful fresh CRT install stamp'
        from datetime import datetime
        started = datetime.fromisoformat(configured_data['created_utc']).timestamp()
        assert stamp.stat().st_mtime >= started - 2, 'Stale CRT completion stamp'
        prefix = root / 'build64/install/x86_64-w64-mingw32/lib'
        files = [record(prefix / name) for name in CRT_FILES]
        assert all(r['mtime'] >= started - 2 for r in files), 'Installed CRT predates reviewed generated inputs'
        value = {'status': 'PASS_FRESH_CRT_REBUILD_FROM_NEW_GENERATION', 'variant': a.variant,
                 'github_run_id': os.environ.get('GITHUB_RUN_ID'), 'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                 'configured_receipt': record(configured), 'install_stamp': record(stamp), 'files': files}
        crt.write_text(json.dumps(value, indent=2) + '\n')
        shutil.copyfile(crt, a.output)
    else:
        value = json.loads(crt.read_bytes())
        assert value['status'] == 'PASS_FRESH_CRT_REBUILD_FROM_NEW_GENERATION'
        assert value['variant'] == a.variant, 'CRT receipt belongs to another variant'
        assert value['github_run_id'] == os.environ.get('GITHUB_RUN_ID')
        assert value['github_run_attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT')
        assert record(configured)['sha256'] == value['configured_receipt']['sha256'], 'Configured receipt changed after CRT build'
        assert all(record(Path(r['path']))['sha256'] == r['sha256'] for r in value['files']), 'CRT changed after source-bound rebuild'
        binaries = list((root / 'build64').glob('mpv-x86_64-*/mpv.exe'))
        assert len(binaries) == 1
        ffmpeg = root / 'build64/install/x86_64-w64-mingw32/bin/ffmpeg.exe'
        subprocess.run([sys.executable, str(HERE / 'dependencies/bind_compiled_dependencies.py'),
                        '--winbuild', str(root), '--variant', a.variant, '--configured-receipt', str(configured),
                        '--binary', str(binaries[0]), '--binary', str(ffmpeg), '--output', str(a.output)], check=True)
        subprocess.run(['bash', str(HERE / 'dependencies/build_custom_io_probe.sh'), str(root),
                        str(root / 'ffmpeg-nested-io-test.exe')], check=True)
    print(json.dumps({'status': 'PASS_ACTUAL_042_DEPENDENCY_GATE', 'phase': a.phase,
                      'variant': a.variant, 'receipt': str(a.output)}))


if __name__ == '__main__':
    main()
