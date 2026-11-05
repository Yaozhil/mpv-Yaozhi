"""Bind reachable Git checkouts, with exact retained FFmpeg/AV3A patch trees."""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

MPV = 'b0841e8c4d156b8403dc1876c4cbd9011eb583f3'
PATCHED_COMMITS = {'fontconfig', 'libbs2b', 'luajit', 'mujs', 'spirv-cross'}
RENDER = {'libplacebo', 'glad', 'fast_float'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args, env=None, data=None):
    result = subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', str(source), *args],
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, timeout=180)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')[-5000:]
    return result.stdout


def identity(source):
    # rev-parse by itself would otherwise discover a parent repository for an
    # absent checkout. Require this directory to be the actual worktree root.
    assert source.is_dir(), 'Missing reachable checkout: ' + str(source)
    top = Path(git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    assert top == source.resolve(), 'Checkout resolved into another worktree: ' + str(source)
    return {'head': git(source, 'rev-parse', 'HEAD').decode().strip(),
            'tree': git(source, 'rev-parse', 'HEAD^{tree}').decode().strip(),
            'tracked_status': git(source, 'status', '--porcelain', '--untracked-files=no').decode().strip()}


def reachable(data, ledger):
    text = data.decode('utf-8', 'replace')
    assert text.startswith('digraph ninja {') and 'label="mpv"' in text
    labels = re.findall(r'\[label="((?:[^"\\]|\\.)*)"', text)
    selected = []
    for row in ledger:
        name = row['name']
        pattern = re.compile(r'(?:^|[/\\])' + re.escape(name) + r'(?:-prefix(?:[/\\]|$)|$)')
        matches = [x for x in labels if pattern.search(x)]
        if matches or name in {'mingw-w64', 'cppwinrt'}:
            selected.append({'name': name, 'reason': 'MPV_GRAPH' if matches else 'EXPLICIT_WINDOWS_BUILD_INPUT',
                             'matching_nodes': len(matches)})
    assert any(x['name'] == 'mpv' for x in selected)
    return selected


def index_env(path):
    env = os.environ.copy()
    env['GIT_INDEX_FILE'] = str(path.resolve())
    return env


def set_blob(source, env, relative, raw):
    oid = git(source, 'hash-object', '-w', '--stdin', env=env, data=raw).decode().strip()
    git(source, 'update-index', '--add', '--cacheinfo', '100644,' + oid + ',' + relative, env=env)


def retained_expectation(root, row, out):
    """Replay only the two retained, non-committing private patch inputs.

    Use a separate Git index: no checkout, production source, source index or
    working file is edited. Every resulting tracked/new source byte is compared
    against this tree after compilation, not merely against a filename allowlist.
    """
    name = row['name']
    assert name in {'ffmpeg', 'avs3-audiodec'}
    source = root / 'src_packages' / name
    recipe = root / row['recipe_path']
    text = recipe.read_text('utf-8-sig')
    patch_block = text.split('PATCH_COMMAND', 1)[1].split('CONFIGURE_COMMAND', 1)[0]
    patches = re.findall(r'git apply (?!\-\-check)(?:\s*)\$\{CMAKE_CURRENT_SOURCE_DIR\}/([^\s]+)', patch_block)
    assert patches and len(patches) == len(set(patches)), 'Unexpected retained patch commands: ' + name
    assert len(patches) == (16 if name == 'ffmpeg' else 5), 'Private patch count drift: ' + name
    inputs = []
    with tempfile.TemporaryDirectory(prefix='expected-index-', dir=out) as temporary:
        env = index_env(Path(temporary) / 'index')
        git(source, 'read-tree', row['base_commit'], env=env)
        if name == 'ffmpeg':
            copies = re.findall(r'-E copy \$\{CMAKE_CURRENT_SOURCE_DIR\}/([^\s]+)\s+([^\s]+)', patch_block)
            assert copies == [('ffmpeg-8998-dovi-split.c', 'libavcodec/bsf/dovi_split.c')]
            raw = (root / 'packages' / copies[0][0]).read_bytes()
            set_blob(source, env, copies[0][1], raw)
            inputs.append({'path': 'packages/' + copies[0][0], 'sha256': digest(raw)})
        else:
            normalizer = root / 'packages/avs3-normalize-source-eol.py'
            module = ast.parse(normalizer.read_bytes())
            assignments = [x for x in module.body if isinstance(x, ast.Assign) and
                           any(isinstance(y, ast.Name) and y.id == 'SOURCE_FILES' for y in x.targets)]
            assert len(assignments) == 1
            paths = ast.literal_eval(assignments[0].value)
            assert isinstance(paths, tuple) and len(paths) == 7
            for relative in paths:
                assert isinstance(relative, str) and not Path(relative).is_absolute() and '..' not in Path(relative).parts
                raw = git(source, 'show', row['base_commit'] + ':' + relative)
                set_blob(source, env, relative, raw.replace(b'\r\n', b'\n'))
            inputs.append({'path': 'packages/avs3-normalize-source-eol.py', 'sha256': digest(normalizer.read_bytes())})
        for filename in patches:
            patch = root / 'packages' / filename
            assert patch.resolve().parent == (root / 'packages').resolve()
            git(source, 'apply', '--cached', '--check', str(patch), env=env)
            git(source, 'apply', '--cached', str(patch), env=env)
            inputs.append({'path': 'packages/' + filename, 'sha256': digest(patch.read_bytes())})
        tree = git(source, 'write-tree', env=env).decode().strip()
        changed = git(source, 'diff', '--cached', '--name-only', '-z', row['base_commit'], env=env)
        paths = [x.decode() for x in changed.split(b'\0') if x]
    return {'expected_worktree_tree': tree, 'source_paths': paths, 'inputs': inputs,
            'method': 'Fixed base + exact recipe patch/copy/normalization bytes replayed into an isolated Git index'}


def configured_sources(root, ledger, graph, out, mingw_generated):
    rows = {x['name']: x for x in ledger}
    selected = reachable(graph, ledger)
    result = []
    for selection in selected:
        row = rows[selection['name']]
        name = row['name']
        expected = MPV if name == 'mpv' else row['base_commit']
        assert expected, 'Reachable dependency has no proven base: ' + name
        source = root / 'src_packages' / name
        actual = identity(source)
        assert actual['head'] == expected, 'Downloaded dependency HEAD differs from fixed base: ' + name
        base_tree = git(source, 'rev-parse', expected + '^{tree}').decode().strip()
        assert actual['tree'] == base_tree
        if row.get('observed_head') == expected and row.get('observed_tree'):
            assert base_tree == row['observed_tree'], 'Frozen base tree mismatch: ' + name
        dirty = git(source, 'diff', '--name-only', '-z').split(b'\0')
        dirty = [x.decode() for x in dirty if x]
        assert not git(source, 'diff', '--cached', '--name-only').strip(), 'Unexpected staged source: ' + name
        if name == 'mingw-w64':
            assert set(dirty) <= set(mingw_generated), 'Unexpected MinGW change before regeneration'
        else:
            assert not actual['tracked_status'], 'Dirty checkout before build: ' + name
        record = {**selection, 'base_commit': expected, 'base_tree': base_tree,
                  'recipe_path': row['recipe_path'], 'recipe_sha256': digest((root / row['recipe_path']).read_bytes()),
                  'configured': actual}
        if name in PATCHED_COMMITS:
            assert row.get('observed_tree'), 'Missing proven private git-am tree: ' + name
            record['allowed_patched_tree'] = row['observed_tree']
        if name in {'ffmpeg', 'avs3-audiodec'}:
            record['retained_private_source'] = retained_expectation(root, row, out)
        result.append(record)
    return {'schema': 'MPV_042_REACHABLE_SOURCE_BINDING_V1', 'selected': result,
            'not_reachable': [x['name'] for x in ledger if x['name'] not in {r['name'] for r in selected}],
            'required_download_targets': [x['name'] + '-download' for x in selected]}


def actual_retained_tree(source, expectation, out):
    untracked = [x.decode() for x in git(source, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x]
    assert set(untracked) <= set(expectation['source_paths']), 'Unexpected untracked retained source: ' + repr(untracked)
    with tempfile.TemporaryDirectory(prefix='actual-index-', dir=out) as temporary:
        env = index_env(Path(temporary) / 'index')
        # Start from the checkout's real full index, preserving sparse entries.
        index = Path(git(source, 'rev-parse', '--git-path', 'index').decode().strip())
        if not index.is_absolute():
            index = source / index
        shutil.copyfile(index, Path(temporary) / 'index')
        git(source, 'add', '-u', env=env)
        for relative in expectation['source_paths']:
            if (source / relative).exists():
                git(source, 'add', '--force', '--', relative, env=env)
        return git(source, 'write-tree', env=env).decode().strip()


def compiled_sources(root, binding, out):
    assert binding['schema'] == 'MPV_042_REACHABLE_SOURCE_BINDING_V1'
    records = []
    for record in binding['selected']:
        name = record['name']
        recipe = root / record['recipe_path']
        assert digest(recipe.read_bytes()) == record['recipe_sha256'], 'Recipe changed after configure: ' + name
        source = root / 'src_packages' / name
        actual = identity(source)
        if name == 'mpv':
            # verify-source.py separately binds the full reviewed aggregate tree,
            # its official parent and actual mpv objects/binary in this attempt.
            git(source, 'merge-base', '--is-ancestor', record['base_commit'], 'HEAD')
            assert not actual['tracked_status'], 'Dirty reviewed mpv source'
            method = 'DELEGATED_FULL_REVIEWED_TREE_TO_VERIFY_SOURCE'
        else:
            if name in PATCHED_COMMITS and actual['head'] != record['base_commit']:
                git(source, 'merge-base', '--is-ancestor', record['base_commit'], 'HEAD')
                assert actual['tree'] == record['allowed_patched_tree'], 'Unreviewed private descendant tree: ' + name
            else:
                assert actual['head'] == record['base_commit'] and actual['tree'] == record['base_tree'], 'Source pin drift after configure: ' + name
            if name in RENDER:
                method = 'DELEGATED_EXACT_BYTES_AND_GITLINKS_TO_RENDER_DEPENDENCY_GATE'
            elif name == 'mingw-w64':
                method = 'SIX_GENERATED_BYTES_BOUND_BY_COMPILED_CRT_GATE'
            elif 'retained_private_source' in record:
                expectation = record['retained_private_source']
                for item in expectation['inputs']:
                    assert digest((root / item['path']).read_bytes()) == item['sha256'], 'Private source input drift: ' + item['path']
                tree = actual_retained_tree(source, expectation, out)
                assert tree == expectation['expected_worktree_tree'], 'Retained private source bytes differ from exact replay: ' + name
                actual['actual_worktree_tree'] = tree
                actual['private_source_files'] = [{'path': p, 'sha256': digest((source / p).read_bytes())}
                                                  for p in expectation['source_paths'] if (source / p).is_file()]
                method = 'EXACT_RETAINED_PRIVATE_SOURCE_TREE'
            else:
                assert not actual['tracked_status'], 'Unexpected dirty dependency after build: ' + name
                method = 'CLEAN_FIXED_BASE_OR_PROVEN_GIT_AM_TREE'
        records.append({'name': name, 'verification': method, **actual})
    return records
