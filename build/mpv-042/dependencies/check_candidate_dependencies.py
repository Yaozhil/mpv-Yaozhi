"""Collect real Ninja reachability, fixed source pins and fresh MinGW generated inputs."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import importlib.util

_source_spec = importlib.util.spec_from_file_location('source_gate', Path(__file__).resolve().parent / 'source_gate.py')
source_gate = importlib.util.module_from_spec(_source_spec)
_source_spec.loader.exec_module(source_gate)

OPTIONAL = ['expat', 'flac', 'libmfx', 'libopusenc', 'megasdk', 'nettle', 'opus-tools', 'opusfile', 'readline', 'llvm']
MINGW = '7ce22f6637cc93fd2eb37c8a645908c92bb80bbd'
GENERATED = ['mingw-w64-crt/aclocal.m4', 'mingw-w64-crt/build-aux/config.guess',
             'mingw-w64-crt/build-aux/config.sub', 'mingw-w64-crt/build-aux/install-sh',
             'mingw-w64-crt/config.h.in', 'mingw-w64-crt/configure',
             'mingw-w64-crt/Makefile.in', 'mingw-w64-crt/build-aux/ar-lib',
             'mingw-w64-crt/build-aux/compile', 'mingw-w64-crt/build-aux/depcomp',
             'mingw-w64-crt/build-aux/missing', 'mingw-w64-crt/build-aux/test-driver',
             'mingw-w64-crt/testcases/Makefile.in']


def run(cmd, cwd=None, timeout=120):
    r = subprocess.run([str(x) for x in cmd], cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'{cmd}: {r.returncode}: {r.stdout.decode("utf-8", "replace")[-6000:]}')
    return r.stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(out, name, data):
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {'path': name, 'sha256': sha(data), 'size': len(data)}


def analyze_graph(data):
    text = data.decode('utf-8', 'replace')
    assert text.startswith('digraph ninja {') and 'label="mpv"' in text, 'not an actual mpv Ninja graph'
    labels = re.findall(r'\[label="((?:[^"\\]|\\.)*)"', text)
    hits = {}
    for dep in OPTIONAL:
        pat = re.compile(r'(?:^|[/\\])' + re.escape(dep) + r'(?:-prefix(?:[/\\]|$)|$)')
        hits[dep] = [x for x in labels if pat.search(x)]
    blocked = {dep: nodes for dep, nodes in hits.items() if nodes}
    assert not blocked, f'unlocked optional targets selected: {blocked}'
    return [{'dependency': dep, 'status': 'PROVEN_NOT_REACHABLE_FROM_MPV', 'matching_nodes': 0} for dep in OPTIONAL]


def tools_record(out):
    records = []
    for cmd in ['autoconf', 'automake', 'aclocal', 'autoheader', 'autoreconf', 'libtoolize', 'perl', 'make', 'gcc', 'cmake', 'ninja']:
        path = shutil.which(cmd)
        assert path, f'missing generation tool: {cmd}'
        records.append({'name': cmd, 'executable': path, 'executable_sha256': sha(Path(path).read_bytes()),
                        'version': run([cmd, '--version']).decode('utf-8', 'replace')})
    save(out, 'generation-tools.json', (json.dumps(records, ensure_ascii=False, indent=2) + '\n').encode())
    return records


def mingw(source, out, regenerate):
    assert run(['git', 'rev-parse', 'HEAD'], source).decode().strip() == MINGW, 'MinGW source pin drift'
    before = {p: sha((source / p).read_bytes()) for p in GENERATED}
    toolchain = tools_record(out)
    if regenerate:
        # This is deliberately run before rebuilding the CRT. The caller must
        # invalidate old CRT configure/build/install stamps when reusing cache.
        log = run(['autoreconf', '-fi'], source / 'mingw-w64-crt', 300)
        save(out, 'mingw-autoreconf.log', log)
    status = run(['git', 'status', '--porcelain', '--untracked-files=no'], source).decode()
    dirty = [x[3:] for x in status.splitlines()]
    assert set(dirty) <= set(GENERATED), f'unexplained MinGW source changes: {dirty}'
    inputs = []
    for p in GENERATED:
        raw = (source / p).read_bytes()
        original = run(['git', 'show', f'{MINGW}:{p}'], source)
        inputs.append({'path': p, 'before_sha256': before[p], 'base_sha256': sha(original),
                       **save(out, 'generated/' + p, raw)})
    diff = run(['git', 'diff', '--binary', MINGW, '--'] + GENERATED, source)
    return {'base_commit': MINGW, 'base_tree': run(['git', 'rev-parse', 'HEAD^{tree}'], source).decode().strip(),
            'fresh_regeneration': regenerate, 'generation_command': ['autoreconf', '-fi'], 'tracked_changes': dirty,
            'diff': save(out, 'mingw-generated.diff', diff), 'generated_files': inputs, 'tools': toolchain,
            'cache_policy': 'Fresh regeneration precedes fresh CRT build. Do not accept merely regenerated files against old cached CRT.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=['main', 'atmos'])
    p.add_argument('--dependencies', required=True, type=Path, help='Frozen 97-row provenance ledger')
    p.add_argument('--mingw-source', type=Path)
    p.add_argument('--regenerate-mingw', action='store_true')
    p.add_argument('--print-required-download-targets', action='store_true',
                   help='Only print selected Git dependency download targets, one per line; do not inspect sources or write evidence')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    root = a.winbuild.resolve()
    graph = run(['ninja', '-C', root / 'build64', '-t', 'graph', 'mpv'])
    optional = analyze_graph(graph)
    ledger = json.loads(a.dependencies.read_text('utf-8-sig'))['variants'][a.variant]['dependencies']
    if a.print_required_download_targets:
        assert not a.regenerate_mingw and not a.output, 'Target discovery cannot regenerate inputs or emit receipts'
        print('\n'.join(row['name'] + '-download' for row in source_gate.reachable(graph, ledger)))
        return
    assert a.output, '--output is required for configured evidence'
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert root != out and not root.is_relative_to(out), 'invalid evidence directory'
    cache = (root / 'build64/CMakeCache.txt').read_text('utf-8')
    assert re.search(r'^COMPILER_TOOLCHAIN:STRING=gcc$', cache, re.M), 'unexpected compiler toolchain'
    graph_ref = save(out, 'mpv-build-graph.dot', graph)
    cache_ref = save(out, 'CMakeCache.txt', cache.encode())
    pins = []
    for row in ledger:
        if row['name'] in OPTIONAL:
            continue
        name = row['name']
        recipe = root / row['recipe_path']
        text = recipe.read_text('utf-8-sig')
        expected = 'b0841e8c4d156b8403dc1876c4cbd9011eb583f3' if name == 'mpv' else row['base_commit']
        if name == 'mingw-w64':
            expected = MINGW
        assert expected and re.findall(r'^\s*GIT_TAG\s+(\S+)\s*$', text, re.M) == [expected], f'{name}: wrong base pin'
        assert not re.search(r'^\s*GIT_RESET\s+', text, re.M), f'{name}: overriding reset'
        if row.get('overlay'):
            assert f'force_rebuild_git({name})' not in text, f'{name}: floating update hook'
        pins.append({'dependency': name, 'commit': expected, 'recipe_sha256': sha(recipe.read_bytes())})
    actual_sources = source_gate.configured_sources(root, ledger, graph, out, GENERATED)
    source = a.mingw_source or root / 'src_packages/mingw-w64'
    generated = mingw(source, out, a.regenerate_mingw)
    assert generated['fresh_regeneration'], 'must freshly regenerate MinGW; source inventory alone is insufficient'
    result = {'schema': 'MPV_042_DEPENDENCY_CONFIGURE_GATE_V1', 'variant': a.variant,
              'status': 'PASS_REAL_GRAPH_BASE_PINS_AND_NEW_GENERATION_NOT_BINARY_ACCEPTANCE',
              'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'graph': graph_ref, 'cache': cache_ref, 'optional_targets': optional, 'pins': pins,
              'actual_sources': actual_sources,
              'mingw': generated, 'github_run_id': os.environ.get('GITHUB_RUN_ID'),
              'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    (out / 'dependency-configure-gate.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'variant': a.variant, 'pins': len(pins), 'optional_excluded': len(optional)}))


if __name__ == '__main__':
    main()
