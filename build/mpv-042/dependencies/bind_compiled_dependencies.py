"""Fail closed when configured generated inputs or the compiled demux object drift."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import importlib.util
import shlex
import shutil

HERE = Path(__file__).resolve().parent
_source_spec = importlib.util.spec_from_file_location('source_gate', HERE / 'source_gate.py')
source_gate = importlib.util.module_from_spec(_source_spec)
_source_spec.loader.exec_module(source_gate)
DEMUX_AFTER = '0e342a33de59df9af36756b888c45d8d73fa232bb55e85740f7c3f586175e9e9'
BASE = '18c01ad424ca7712ef9a9d46953308efc75c4776'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': sha(raw), 'size': len(raw)}


def run(cmd, cwd=None):
    r = subprocess.run([str(x) for x in cmd], cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=120)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')[-5000:]
    return r.stdout



def bind_demux_dependency(raw, build, obj, demux):
    """Bind GCC's unique primary Make rule to the actual source and object."""
    text = raw.decode('utf-8', 'strict').replace('\\\r\n', ' ').replace('\\\n', ' ')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0].count(':') == 1, 'Expected one primary GCC dependency rule'
    assert not any(char in lines[0] for char in ('$', '#', ';', '|')), 'Unsupported Make dependency syntax'
    target, prerequisites = lines[0].split(':', 1)
    targets, inputs = shlex.split(target), shlex.split(prerequisites)
    assert len(targets) == 1 and inputs, 'Missing unique dependency target or primary source'
    actual_target = (build / targets[0]).resolve(strict=True)
    actual_source = (build / inputs[0]).resolve(strict=True)
    assert actual_target == obj.resolve(strict=True), 'Dependency rule targets another object'
    assert actual_source == demux.resolve(strict=True), 'Dependency rule compiles another primary source'
    link = build / 'src'
    assert link.is_symlink() and link.resolve(strict=True) == demux.parent.parent.resolve(strict=True), 'FFmpeg build/src selects another source tree'
    return {'target': targets[0], 'primary_source': inputs[0],
            'resolved_target': str(actual_target), 'resolved_primary_source': str(actual_source),
            'build_source_link': str(link), 'build_source_link_target': str(link.resolve(strict=True))}


def bind_avformat_link(decoded, build, archive):
    """Require a unique final link and an exact archive argument, not a substring."""
    assert isinstance(decoded, list) and all(isinstance(row, dict) for row in decoded)
    links = [row for row in decoded if row.get('output') == 'mpv.exe']
    assert len(links) == 1, 'Expected one expanded mpv.exe link edge'
    entry = links[0]
    assert Path(entry['directory']).resolve(strict=True) == build.resolve(strict=True), 'Link uses another build directory'
    command = entry['command']
    assert isinstance(command, str) and '\n' not in command and '\r' not in command
    arguments = shlex.split(command)
    assert arguments and not any(value.startswith('@') for value in arguments), 'Unexpanded link response file'
    assert arguments.count('-o') == 1 and arguments.index('-o') + 1 < len(arguments)
    assert arguments[arguments.index('-o') + 1] == 'mpv.exe', 'Link does not produce mpv.exe'
    # Only complete path arguments can select the bound archive. Compiler flags,
    # archive-name substrings and archives belonging to another prefix reject.
    archives = [value for value in arguments[1:] if not value.startswith('-') and
                (Path(value).is_absolute() or value.endswith('.a')) and
                (build / value).resolve() == archive.resolve(strict=True)]
    assert len(archives) == 1, 'mpv link did not select exactly the bound FFmpeg archive'
    return links


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--winbuild', required=True, type=Path)
    p.add_argument('--variant', required=True, choices=['main', 'atmos'])
    p.add_argument('--configured-receipt', required=True, type=Path)
    p.add_argument('--mingw-source', type=Path)
    p.add_argument('--binary', action='append', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    root = a.winbuild.resolve()
    configured = json.loads(a.configured_receipt.read_text('utf-8-sig'))
    assert configured['status'] == 'PASS_REAL_GRAPH_BASE_PINS_AND_NEW_GENERATION_NOT_BINARY_ACCEPTANCE'
    assert configured['variant'] == a.variant
    assert configured['github_run_id'] and configured['github_run_id'] == os.environ.get('GITHUB_RUN_ID'), 'different CI run'
    assert configured['github_run_attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT'), 'different CI attempt'
    evidence = a.output.resolve().parent
    evidence.mkdir(parents=True, exist_ok=True)
    source_bindings = source_gate.compiled_sources(root, configured['actual_sources'], evidence)
    mingw = a.mingw_source or root / 'src_packages/mingw-w64'
    for row in configured['mingw']['generated_files']:
        # save() stores the captured filename under generated/, while the
        # input itself is relative to the actual MinGW checkout.
        relative = row['path'].removeprefix('generated/')
        assert sha((mingw / relative).read_bytes()) == row['sha256'], 'MinGW generated bytes changed after configure: ' + relative
    ffmpeg = root / 'src_packages/ffmpeg'
    assert run(['git', 'rev-parse', 'HEAD'], ffmpeg).decode().strip() == BASE
    demux = ffmpeg / 'libavformat/demux.c'
    assert sha(demux.read_bytes()) == DEMUX_AFTER, 'FFmpeg demux fix or AV3A private hunk drift'
    build = root / 'build64/packages/ffmpeg-prefix/src/ffmpeg-build'
    obj = build / 'libavformat/demux.o'
    dep = build / 'libavformat/demux.d'
    assert obj.is_file() and dep.is_file(), 'compiled demux object/dependency list missing'
    started = datetime.datetime.fromisoformat(configured['created_utc']).timestamp()
    assert obj.stat().st_mtime >= started - 2, 'stale cached demux object predates this configured gate'
    # Preserve the real compiler inputs and final graph before any path/link
    # assertion. Failed builds retain these bytes in the provenance artifact.
    captured = root / 'mpv-042-evidence' / a.variant / 'compiled-binding-inputs'
    captured.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(dep, captured / 'demux.d')
    shutil.copyfile(build / 'ffbuild/config.mak', captured / 'ffmpeg-config.mak')
    source_link = build / 'src'
    (captured / 'ffmpeg-source-link.json').write_text(json.dumps({
        'path': str(source_link), 'is_symlink': source_link.is_symlink(),
        'raw_target': os.readlink(source_link) if source_link.is_symlink() else None,
        'resolved': str(source_link.resolve()), 'expected': str(ffmpeg.resolve())}, indent=2) + '\n')
    mpv_build = root / 'build64/packages/mpv-prefix/src/mpv-build'
    shutil.copyfile(mpv_build / 'build.ninja', captured / 'mpv-build.ninja')
    commands = run(['ninja', '-C', mpv_build, '-t', 'compdb', '-x'])
    (captured / 'mpv-expanded-compdb.json').write_bytes(commands)
    (captured / 'mpv-link-query.txt').write_bytes(run(['ninja', '-C', mpv_build, '-t', 'query', 'mpv.exe']))
    (captured / 'mpv-build-commands.txt').write_bytes(run(['ninja', '-C', mpv_build, '-t', 'commands', 'mpv.exe']))
    dependency_binding = bind_demux_dependency(dep.read_bytes(), build, obj, demux)
    prefix = root / 'build64/install/x86_64-w64-mingw32'
    archive = prefix / 'lib/libavformat.a'
    ar = root / 'build64/install/bin/x86_64-w64-mingw32-ar'
    member = run([ar, 'p', archive, 'demux.o'])
    assert sha(member) == sha(obj.read_bytes()), 'installed FFmpeg archive does not contain this compiled demux object'
    links = bind_avformat_link(json.loads(commands), mpv_build, archive)
    binaries = [file_record(x.resolve()) for x in a.binary]
    assert all(x['size'] > 10000 for x in binaries), 'not a real candidate executable'
    result = {'schema': 'MPV_042_COMPILED_DEPENDENCY_BINDING_V1', 'variant': a.variant,
              'status': 'PASS_CONFIGURED_INPUTS_TO_DEMUX_ARCHIVE_AND_MPV_LINK_NOT_RUNTIME_ACCEPTANCE',
              'configured_receipt_sha256': sha(a.configured_receipt.read_bytes()),
              'actual_sources': source_bindings,
              'ffmpeg_base': BASE, 'ffmpeg_demux': file_record(demux), 'demux_object': file_record(obj),
              'installed_avformat_archive': file_record(archive), 'archive_member_sha256': sha(member),
              'demux_dependency_list': file_record(dep), 'demux_dependency_binding': dependency_binding,
              'captured_compiler_inputs': [file_record(p) for p in sorted(captured.iterdir())],
              'expanded_compdb_sha256': sha(commands),
              'mpv_link_records': links, 'binaries': binaries,
              'github_run_id': os.environ.get('GITHUB_RUN_ID'), 'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'runtime_gate': 'Run custom_io_cleanup.exe (5 callbacks) and isolated mpv HLS failure/abort regression.'}
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'variant': a.variant, 'binaries': binaries}))


if __name__ == '__main__':
    main()
