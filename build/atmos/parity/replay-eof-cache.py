"""Replay the exact packaged main/Atmos patch order on a verified base archive."""
import argparse
import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
BASE = 'c318236b8882af860f16f936225430ad053a2179'
ARCHIVE_SHA256 = '4d104937a06fbac23e79eb91019b4ee834ea516eb4b8d5574acae15c3fc8933d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_expression(node, roots):
    if isinstance(node, ast.Name) and node.id in roots:
        return roots[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = path_expression(node.left, roots)
        if left is not None and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            return left / node.right.value
    return None


def package_patches(variant, lock):
    setup = HERE / 'prepare-winbuild.py'
    tree = ast.parse(setup.read_text(encoding='utf-8'))
    roots = {'root': CONFIG, 'here': HERE, 'packages': Path('packages')}
    patches = {'mpv-9000-candidate-c318236.patch': HERE / 'main-core.patch'}
    workflow = (CONFIG / '.github/workflows/build-mpv-v100-parity.yml').read_text(encoding='utf-8')
    assert 'packages/mpv-9000-candidate-c318236.patch' in workflow
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) != 2:
            continue
        call = node.func
        if not (isinstance(call, ast.Attribute) and call.attr == 'copyfile'
                and isinstance(call.value, ast.Name) and call.value.id == 'shutil'):
            continue
        destination = path_expression(node.args[1], roots)
        if destination is None or destination.parent != Path('packages'):
            continue
        if not destination.name.startswith('mpv-'):
            continue
        source = path_expression(node.args[0], roots)
        assert source is not None and source.resolve().is_relative_to(CONFIG)
        if variant == 'main' and destination.name == 'mpv-9100-omniphony-parity.patch':
            continue
        assert destination.name not in patches, destination.name
        patches[destination.name] = source
    ordered = sorted(patches.items())
    assert ordered[-1][0] == 'mpv-9203-video-bounded-duplicate-pts.patch'
    assert 'mpv-9202a-demux-inactive-subtitle-cache.patch' in patches
    for name, path in ordered:
        relative = path.relative_to(CONFIG).as_posix()
        expected = lock['common_patches'].get(relative)
        if expected is None:
            assert path.parent == HERE, relative
            expected = lock['patches'][path.name]
        assert sha(path) == expected, relative
    return ordered


def load_gate(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(source, *args):
    command = ['git', '-C', str(source), '-c', 'core.autocrlf=false',
               '-c', 'user.name=EOF cache verification',
               '-c', 'user.email=eof-cache-verification@localhost', *args]
    result = subprocess.run(command, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
    return result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--compiler', required=True)
    args = parser.parse_args()
    assert sha(args.archive) == ARCHIVE_SHA256, 'Unexpected upstream archive bytes'
    args.work.mkdir(parents=True, exist_ok=False)
    lock = json.loads((HERE / 'source-lock.json').read_bytes())
    reports = {}
    for variant in ('main', 'atmos'):
        target = args.work / variant
        target.mkdir()
        with tarfile.open(args.archive) as packed:
            packed.extractall(target, filter='data')
        source = target / ('mpv-' + BASE)
        assert source.is_dir()
        git(source, 'init', '--initial-branch=verification')
        git(source, 'add', '.')
        git(source, 'commit', '-m', 'Exact upstream source snapshot')
        ordered = package_patches(variant, lock)
        for _, patch in ordered:
            git(source, 'am', '--3way', str(patch.resolve()))
        pts = load_gate('verify-native-video-pts-repair.py').verify_source(source)
        eof = load_gate('verify-eof-cache-source.py').verify_source(source)
        assert pts['variant'] == variant
        subprocess.run([
            sys.executable, '-B', str(HERE / 'verify-inactive-subtitle-cache-contract.py'),
            '--source', str(source), '--compiler', args.compiler,
            '--output', str(target / 'contract'),
        ], check=True, capture_output=True, text=True, timeout=120)
        contract = json.loads((target / 'contract/report.json').read_bytes())
        reports[variant] = {
            'source': str(source.resolve()),
            'tree': git(source, 'rev-parse', 'HEAD^{tree}'),
            'head': git(source, 'rev-parse', 'HEAD'),
            'ordered_patches': [
                {'package': name, 'path': path.relative_to(CONFIG).as_posix(), 'sha256': sha(path)}
                for name, path in ordered
            ],
            'pts_source_sha256': pts['source_sha256'],
            'eof': eof,
            'contract': contract,
        }
    result = {
        'status': 'EXACT_PACKAGE_PATCH_REPLAY_DUAL_VARIANT_SOURCE_PASS',
        'archive_sha256': ARCHIVE_SHA256,
        'source_lock_sha256': sha(HERE / 'source-lock.json'),
        'variants': reports,
        'compiled': False,
        'runtime_verified': False,
    }
    (args.work / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'trees': {k: v['tree'] for k, v in reports.items()}}))


if __name__ == '__main__':
    main()
