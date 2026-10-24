"""Fail closed on rendering dependency source, cache and compiled-library drift."""
import argparse
import ast
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import uuid

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], timeout=60).decode().strip()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepared(winbuild, variant):
    preparation = read(winbuild / 'dependency-preparation.json')
    lock_path = HERE / 'dependency-lock.json'
    require(preparation['variant'] == variant, 'Dependency preparation variant mismatch')
    require(preparation['lock_sha256'] == sha(lock_path), 'Dependency lock digest mismatch')
    for name, expected in preparation['tools_sha256'].items():
        require(sha(winbuild / 'dependency-lock-tools' / name) == expected,
                'Dependency verification tool changed: ' + name)
    for name, expected in preparation['effective_render_recipes_sha256'].items():
        require(sha(winbuild / 'packages' / (name + '.cmake')) == expected,
                'Dependency recipe/patch drift: ' + name)
    require(sha(winbuild / 'cmake/custom_steps.cmake') == preparation['retention_helper_sha256'],
            'Dependency retention helper changed')
    return preparation, read(lock_path)


def source_manifest(winbuild, lock):
    """Compare every tracked byte with its locked tree; only two gitlinks change."""
    records = {}
    for name, pin in lock['sources'].items():
        root = winbuild / 'src_packages' / name
        require(git(root, 'rev-parse', 'HEAD') == pin['commit'], 'Wrong dependency base: ' + name)
        require(git(root, 'rev-parse', 'HEAD^{tree}') == pin['tree'], 'Wrong dependency tree: ' + name)
        require(git(root, 'diff', '--cached', '--name-only') == '', 'Staged dependency changes: ' + name)
        tracked = set()
        manifest = []
        raw = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', 'HEAD'], timeout=60)
        for record in raw.split(b'\0'):
            if not record:
                continue
            metadata, relative_bytes = record.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split(' ')
            relative = relative_bytes.decode()
            path = root / relative
            tracked.add(relative)
            if kind == 'commit':
                external = {'3rdparty/glad': 'glad', '3rdparty/fast_float': 'fast_float'}.get(relative)
                if name == 'libplacebo' and external:
                    expected = (winbuild / 'src_packages' / external).resolve()
                    require(path.is_symlink() and path.resolve() == expected,
                            'Wrong external source link: ' + relative)
                    manifest.append({'path': relative, 'kind': 'locked-external',
                                     'source': external, 'commit': lock['sources'][external]['commit']})
                else:
                    require(not path.exists() or (path.is_dir() and not any(path.iterdir())),
                            'Unexpected populated submodule: ' + relative)
                    manifest.append({'path': relative, 'kind': 'empty-gitlink', 'oid': oid})
                continue
            require(path.is_file() or path.is_symlink(), 'Missing tracked source: ' + relative)
            actual = (os.readlink(path).encode() if mode == '120000' else path.read_bytes())
            blob = hashlib.sha1(b'blob ' + str(len(actual)).encode() + b'\0' + actual).hexdigest()
            require(blob == oid, 'Dirty dependency source: ' + name + '/' + relative)
            if mode != '120000':
                require(not path.is_symlink(), 'Unexpected source symlink: ' + relative)
                if os.name != 'nt':
                    actual_mode = '100755' if path.stat().st_mode & 0o111 else '100644'
                    require(actual_mode == mode, 'Dependency executable mode changed: ' + relative)
            manifest.append({'path': relative, 'mode': mode, 'sha256': digest(actual), 'size': len(actual)})
        # Inspect ignored files as well, including bytecode read by generators.
        for parent, dirs, files in os.walk(root, followlinks=False):
            retained = []
            for directory in dirs:
                if directory == '.git':
                    continue
                path = Path(parent) / directory
                if path.is_symlink():
                    relative = path.relative_to(root).as_posix()
                    require(name == 'libplacebo' and relative in ('3rdparty/glad', '3rdparty/fast_float'),
                            'Unexpected dependency directory symlink: ' + name + '/' + relative)
                    require(relative in tracked, 'Untracked external source symlink: ' + relative)
                    continue
                retained.append(directory)
            dirs[:] = retained
            for filename in files:
                path = Path(parent) / filename
                relative = path.relative_to(root).as_posix()
                if relative in tracked:
                    continue
                require(False, 'Unexpected dependency source file: ' + name + '/' + relative)
        records[name] = {'commit': pin['commit'], 'tree': pin['tree'], 'files': manifest}
    return records


def source_identity(manifest):
    return digest(canonical(manifest))


def check_options(build, lock, prefix):
    options_path = build / 'meson-info/intro-buildoptions.json'
    options = {item['name']: item['value'] for item in read(options_path)}
    for name, expected in lock['libplacebo_options'].items():
        require(options.get(name) == expected, 'Unexpected libplacebo Meson option: ' + name)
    require(Path(options['prefix']).resolve() == prefix.resolve(), 'Wrong libplacebo installation prefix')
    require(Path(options['libdir']).resolve() == (prefix / 'lib').resolve(), 'Wrong libplacebo libdir')
    require(Path(options['vulkan-registry']).resolve() == (prefix / 'share/vulkan/registry/vk.xml').resolve(),
            'Wrong libplacebo Vulkan registry')
    return {'sha256': sha(options_path), 'values': options}


def configured_resource_input(source, build, path, target):
    """Recognize the pinned LP configure_file -> Windows resource input only."""
    expected = build / 'win32/libplacebo.rc'
    require(path == expected and path.is_file() and not path.is_symlink(),
            'Configured source escaped locked trees: ' + str(path))
    require(target['type'] == 'custom' and target.get('name') == 'libplacebo.rc' and
            Path(target['defined_in']).resolve() == source / 'src/meson.build',
            'Configured resource belongs to an unexpected target: ' + str(path))
    declaration = (source / 'win32/meson.build').read_text()
    require(re.search(r"libplacebo_rc\s*=\s*configure_file\(\s*input:\s*'libplacebo\.rc\.in',\s*"
                      r"output:\s*'libplacebo\.rc',\s*configuration:\s*version_config\s*\)", declaration),
            'Missing locked configure_file resource declaration: ' + str(path))
    consumer = (source / 'src/meson.build').read_text()
    require(re.search(r'windows\.compile_resources\(libplacebo_rc\s*,', consumer),
            'Missing locked Windows resource consumer: ' + str(path))
    template = source / 'win32/libplacebo.rc.in'
    buildsystem = read(build / 'meson-info/intro-buildsystem_files.json')
    require(template in [Path(name).resolve() for name in buildsystem],
            'Resource template is not a Meson configuration input: ' + str(template))
    project = read(build / 'meson-info/intro-projectinfo.json')
    # These units are fixed by the already checked c9076f7 source tree. Do not
    # accept arbitrary generated C files or arbitrary resource configuration.
    require(project['version'] == '7.387.0', 'Unexpected locked LP resource version: ' + str(path))
    expected_text = template.read_text()
    for key, value in zip(('PL_MAJOR', 'PL_MINOR', 'PL_PATCH'), ('7', '387', '0')):
        require('@' + key + '@' in expected_text, 'Missing locked resource substitution: ' + str(template))
        expected_text = expected_text.replace('@' + key + '@', value)
    require(path.read_text() == expected_text, 'Configured resource differs from locked template: ' + str(path))
    return path.relative_to(build).as_posix()


def check_build_graph(winbuild, source, build):
    source, build = source.resolve(), build.resolve()
    expected = winbuild / 'build64/packages/libplacebo-prefix/src/libplacebo-build'
    require(build == expected, 'Wrong actual libplacebo compiler build directory: ' + str(build))
    info = read(build / 'meson-info/meson-info.json')
    require(Path(info['directories']['source']).resolve() == source and
            Path(info['directories']['build']).resolve() == build,
            'Meson source/build directories differ from the locked compilation: ' + repr(info['directories']))
    machines = read(build / 'meson-info/intro-machines.json')
    for name in ('host', 'target'):
        machine = machines[name]
        require(machine['system'] == 'windows' and machine['cpu_family'] == 'x86_64' and
                machine['endian'] == 'little', 'Wrong Meson cross machine: ' + name)
    cross = winbuild / 'build64/meson_cross.txt'
    command_line = configparser.ConfigParser(interpolation=None)
    command_line.read(build / 'meson-private/cmd_line.txt')
    cross_files = ast.literal_eval(command_line['properties']['cross_file'])
    require(len(cross_files) == 1 and Path(cross_files[0]).resolve() == cross,
            'Meson did not configure with the verified cross file')
    require(not ast.literal_eval(command_line['properties'].get('native_file', '[]')),
            'Unexpected native machine override')
    cross_config = configparser.ConfigParser(interpolation=None)
    cross_config.read(cross)
    compiler = Path(ast.literal_eval(cross_config['binaries']['c'])).absolute()
    cpp = Path(ast.literal_eval(cross_config['binaries']['cpp'])).absolute()
    require(compiler == winbuild / 'build64/install/bin/x86_64-w64-mingw32-gcc' and
            cpp == winbuild / 'build64/install/bin/x86_64-w64-mingw32-g++',
            'Cross file selects an unexpected compiler: ' + str(compiler) + ' / ' + str(cpp))
    machine = subprocess.check_output([str(compiler), '-dumpmachine'], timeout=60).decode().strip()
    require(machine == 'x86_64-w64-mingw32', 'Compiler target differs from Windows x86_64')
    targets = read(build / 'meson-info/intro-targets.json')
    archive = build / 'src/libplacebo.a'
    placebo = [target for target in targets if target['type'] == 'static library' and
               archive in [Path(name).resolve() for name in target['filename']]]
    require(len(placebo) == 1, 'Missing unique configured libplacebo static archive target')
    generated, declared, object_roots, configured_inputs = set(), set(), [], set()
    roots = [(winbuild / 'src_packages' / name).resolve() for name in ('libplacebo', 'glad', 'fast_float')]
    for target in targets:
        require(Path(target['defined_in']).resolve().is_relative_to(source),
                'Build target is defined outside the locked source: ' + str(target['defined_in']))
        filenames = [Path(name).resolve() for name in target['filename']]
        if target['type'] == 'custom':
            require(all(name.is_relative_to(build) for name in filenames), 'Generated target escaped the build: ' + repr(filenames))
            generated.update(filenames)
        if target['type'] == 'static library':
            object_roots.extend(Path(str(name) + '.p') for name in filenames)
        for group in target.get('target_sources', []):
            for name in group.get('sources', []):
                path = Path(name).resolve()
                if not any(path.is_relative_to(root) for root in roots):
                    configured_inputs.add(configured_resource_input(source, build, path, target))
                declared.add(path)
            for name in group.get('generated_sources', []):
                path = Path(name).resolve()
                require(path.is_relative_to(build), 'Configured generated source escaped build: ' + str(path))
                generated.add(path)
    commands = read(build / 'compile_commands.json')
    require(bool(commands), 'No libplacebo compilation commands')
    actual_inputs = []
    for command in commands:
        directory = Path(command['directory']).resolve()
        require(directory == build, 'Compilation command belongs to another build directory: ' + str(directory))
        path = Path(command['file'])
        path = (directory / path).resolve() if not path.is_absolute() else path.resolve()
        require(path in declared or path in generated, 'Compilation input not declared by the locked Meson graph: ' + str(path))
        output = Path(command['output'])
        output = (directory / output).resolve() if not output.is_absolute() else output.resolve()
        require(any(output.is_relative_to(root) for root in object_roots),
                'Compilation output does not belong to a configured static archive: ' + str(output))
        invocation = command.get('command', ' '.join(command.get('arguments', [])))
        require(str(compiler) in invocation or str(cpp) in invocation or 'windres' in invocation,
                'Compilation command selects an unexpected compiler: ' + invocation)
        actual_inputs.append({'source': str(path), 'output': str(output)})
    return {'source_directory': str(source), 'build_directory': str(build),
            'compiler_machine': machine, 'compiler_sha256': sha(compiler),
            'cpp_compiler_sha256': sha(cpp), 'compile_inputs': actual_inputs,
            'configured_inputs': sorted(configured_inputs),
            'metadata_sha256': {name: sha(build / name) for name in (
                'meson-info/meson-info.json', 'meson-info/intro-machines.json',
                'meson-info/intro-targets.json', 'meson-private/cmd_line.txt', 'compile_commands.json',
                *sorted(configured_inputs),
                *(('meson-info/intro-buildsystem_files.json', 'meson-info/intro-projectinfo.json') if configured_inputs else ()))}}


def cache(winbuild, variant):
    preparation, _ = prepared(winbuild, variant)
    marker = winbuild / 'build64/dependency-cache-identity.json'
    if marker.exists():
        previous = read(marker)
        require(previous['lock_sha256'] == preparation['lock_sha256'] and previous['variant'] == variant,
                'Foreign dependency cache identity')
    else:
        # A restored cache without the new identity is never silently trusted.
        require(not (winbuild / 'build64/CMakeCache.txt').exists(), 'Unidentified dependency build cache')
    invocation = uuid.uuid4().hex
    write(marker, {'schema': 1, 'variant': variant, 'lock_sha256': preparation['lock_sha256'],
                   'invocation': invocation, 'started_ns': time.time_ns()})
    # Rebuild these sources and the archive even after an exact cache hit.
    for name in ('libplacebo', 'glad', 'fast_float'):
        for target in (winbuild / 'src_packages' / name, winbuild / 'build64/packages' / (name + '-prefix')):
            require(target.resolve().is_relative_to(winbuild), 'Cache reset escaped build workspace')
            if target.is_symlink():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
    prefix = winbuild / 'build64/install/x86_64-w64-mingw32'
    for target in (prefix / 'lib/libplacebo.a', prefix / 'lib/pkgconfig/libplacebo.pc'):
        target.unlink(missing_ok=True)
    include = prefix / 'include/libplacebo'
    if include.exists():
        shutil.rmtree(include)
    evidence = winbuild / 'dependency-evidence'
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir()
    shutil.copyfile(winbuild / 'dependency-preparation.json', evidence / 'preparation.json')
    shutil.copyfile(HERE / 'dependency-lock.json', evidence / 'dependency-lock.json')
    shutil.copyfile(marker, evidence / 'invocation.json')
    for recipe in preparation['git_inventory']:
        target = evidence / 'recipes' / recipe['recipe_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(winbuild / recipe['recipe_path'], target)


def snapshot(winbuild, manifest, evidence):
    write(evidence / 'actual-source-manifest.json', manifest)
    # Keep the actual compiler input bytes, including the two external repositories.
    with tarfile.open(evidence / 'actual-source.tar.gz', 'w:gz') as archive:
        for name, value in manifest.items():
            root = winbuild / 'src_packages' / name
            for item in value['files']:
                if 'sha256' in item:
                    archive.add(root / item['path'], arcname=name + '/' + item['path'], recursive=False)
    for name in manifest:
        result = subprocess.check_output(['git', '-C', str(winbuild / 'src_packages' / name),
                                          'diff', '--binary', 'HEAD', '--', '.',
                                          ':(exclude)3rdparty/glad', ':(exclude)3rdparty/fast_float'], timeout=60)
        (evidence / (name + '-actual.diff')).write_bytes(result)


def phase(args):
    winbuild = args.winbuild.resolve()
    if args.phase == 'cache':
        cache(winbuild, args.variant)
        return {'status': 'PASS_DEPENDENCY_CACHE_IDENTITY'}
    preparation, lock = prepared(winbuild, args.variant)
    evidence = winbuild / 'dependency-evidence'
    invocation = read(winbuild / 'build64/dependency-cache-identity.json')
    require(invocation == read(evidence / 'invocation.json'), 'Dependency invocation changed')
    require(invocation['variant'] == args.variant and invocation['lock_sha256'] == sha(HERE / 'dependency-lock.json'),
            'Dependency invocation identity mismatch')
    manifest = source_manifest(winbuild, lock)
    identity = source_identity(manifest)
    common = {'schema': 1, 'variant': args.variant, 'invocation': invocation['invocation'],
              'lock_sha256': preparation['lock_sha256'], 'source_identity_sha256': identity}
    if args.phase == 'before':
        require(os.environ.get('PYTHONDONTWRITEBYTECODE') == '1', 'Generator bytecode guard is missing')
        require(args.source.resolve() == winbuild / 'src_packages/libplacebo', 'Wrong compiler source directory')
        require(args.build.resolve() == winbuild / 'build64/packages/libplacebo-prefix/src/libplacebo-build',
                'Wrong actual compiler build directory: ' + str(args.build))
        options = check_options(args.build, lock, args.prefix)
        require(not (evidence / 'before.json').exists(), 'Dependency build receipt already exists')
        # Keep the raw real schema even when a new guard rejects it. These
        # files alone never constitute a successful compiler-input receipt.
        for relative in ('build.ninja', 'compile_commands.json', 'meson-info/intro-buildoptions.json',
                         'meson-logs/meson-log.txt', 'meson-info/meson-info.json',
                         'meson-info/intro-machines.json', 'meson-info/intro-targets.json',
                         'meson-private/cmd_line.txt'):
            source = args.build / relative
            require(source.is_file(), 'Missing configured dependency evidence: ' + relative)
            destination = evidence / 'configuration' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        graph = check_build_graph(winbuild, args.source, args.build)
        for relative in (*graph['configured_inputs'],
                         *(('meson-info/intro-buildsystem_files.json', 'meson-info/intro-projectinfo.json')
                           if graph['configured_inputs'] else ())):
            destination = evidence / 'configuration' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.build / relative, destination)
        snapshot(winbuild, manifest, evidence)
        cross = winbuild / 'build64/meson_cross.txt'
        shutil.copyfile(cross, evidence / 'configuration/meson_cross.txt')
        write(evidence / 'before.json', common | {'status': 'PASS_DEPENDENCY_COMPILER_INPUTS',
              'started_ns': time.time_ns(), 'options': options, 'cross_file_sha256': sha(cross),
              'configured_build_graph': graph,
              'source_archive_sha256': sha(evidence / 'actual-source.tar.gz')})
    elif args.phase == 'after':
        before = read(evidence / 'before.json')
        require(all(before[k] == v for k, v in common.items()), 'Dependency source changed during compilation')
        require(check_options(args.build, lock, args.prefix) == before['options'], 'Dependency build options changed')
        require(check_build_graph(winbuild, args.source, args.build) == before['configured_build_graph'],
                'Dependency configured compiler graph changed')
        installed = args.prefix / 'lib/libplacebo.a'
        require(installed.is_file() and installed.stat().st_mtime_ns > before['started_ns'],
                'Dependency archive is missing or stale')
        libraries = [p for p in args.build.rglob('libplacebo.a') if p.is_file()]
        require(len(libraries) == 1 and sha(libraries[0]) == sha(installed),
                'Installed dependency archive differs from this compilation')
        shutil.copyfile(installed, evidence / 'libplacebo.a')
        for relative in ('.ninja_log', 'meson-logs/install-log.txt'):
            path = args.build / relative
            require(path.is_file(), 'Missing dependency compilation/install log: ' + relative)
            shutil.copyfile(path, evidence / Path(relative).name)
        write(evidence / 'after.json', common | {'status': 'PASS_DEPENDENCY_COMPILED_ARCHIVE',
              'before_receipt_sha256': sha(evidence / 'before.json'),
              'installed_archive_sha256': sha(installed), 'installed_archive_size': installed.stat().st_size})
    elif args.phase == 'final':
        after = read(evidence / 'after.json')
        require(all(after[k] == v for k, v in common.items()), 'Final dependency source identity mismatch')
        require(sha(evidence / 'before.json') == after['before_receipt_sha256'], 'Compiler input receipt changed')
        before = read(evidence / 'before.json')
        require(sha(evidence / 'actual-source.tar.gz') == before['source_archive_sha256'], 'Source snapshot changed')
        require(source_identity(read(evidence / 'actual-source-manifest.json')) == identity, 'Source manifest changed')
        installed = winbuild / 'build64/install/x86_64-w64-mingw32/lib/libplacebo.a'
        require(sha(installed) == after['installed_archive_sha256'] == sha(evidence / 'libplacebo.a'),
                'Linked dependency archive changed')
        mpv_build = winbuild / 'build64/packages/mpv-prefix/src/mpv-build'
        commands = subprocess.check_output(['ninja', '-C', str(mpv_build), '-t', 'commands', 'mpv.exe'], timeout=60)
        links = [line for line in commands.decode().splitlines()
                 if re.search(r'(?:^|\s)-o\s+[\'\"]?mpv\.exe(?:[\'\"]?\s|$)', line)]
        require(len(links) == 1 and str(installed) in links[0],
                'mpv.exe link command does not consume the verified dependency archive')
        query = subprocess.check_output(['ninja', '-C', str(mpv_build), '-t', 'query', 'mpv.exe'], timeout=60)
        inputs = query.decode().split('  outputs:', 1)[0]
        require(inputs.startswith('mpv.exe:') and str(installed) in inputs,
                'mpv.exe link edge does not have the verified archive as a direct input')
        (evidence / 'mpv-build-commands.txt').write_bytes(commands)
        (evidence / 'mpv-link-command.txt').write_text(links[0] + '\n')
        (evidence / 'mpv-link-query.txt').write_bytes(query)
        inventory = []
        for recipe in preparation['git_inventory']:
            entry = dict(recipe)
            require(sha(winbuild / recipe['recipe_path']) == recipe['recipe_sha256'],
                    'Dependency inventory recipe changed: ' + recipe['name'])
            candidates = [winbuild / 'src_packages' / recipe['name'],
                          winbuild / 'build64/toolchain' / (recipe['name'] + '-prefix') / 'src' / recipe['name']]
            root = next((path for path in candidates if (path / '.git').exists()), candidates[0])
            if (root / '.git').exists():
                entry.update({'observed_head': git(root, 'rev-parse', 'HEAD'),
                              'observed_tree': git(root, 'rev-parse', 'HEAD^{tree}'),
                              'observed_status': git(root, 'status', '--porcelain', '--ignore-submodules=all')})
            else:
                entry['not_downloaded'] = True
            inventory.append(entry)
        binaries = []
        require(len(args.binary) >= 2, 'Require both final mpv.exe and mpv.com')
        for binary in args.binary:
            require(binary.is_file() and binary.stat().st_mtime_ns > before['started_ns'], 'Missing/stale final binary')
            binaries.append({'name': binary.name, 'sha256': sha(binary), 'size': binary.stat().st_size})
        report = common | {'status': 'PASS_DEPENDENCY_BUILD_BOUND_TO_BINARIES',
                          'archive_sha256': sha(installed), 'binaries': binaries,
                          'mpv_link_command_sha256': sha(evidence / 'mpv-link-command.txt'),
                          'mpv_link_query_sha256': sha(evidence / 'mpv-link-query.txt'),
                          'after_receipt_sha256': sha(evidence / 'after.json'), 'git_dependency_inventory': inventory}
        write(evidence / 'final.json', report)
        write(evidence / 'evidence-index.json', {p.relative_to(evidence).as_posix(): sha(p)
              for p in sorted(evidence.rglob('*')) if p.is_file() and p.name != 'evidence-index.json'})
        return report
    return common | {'status': 'PASS_DEPENDENCY_' + args.phase.upper()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--winbuild', type=Path, required=True)
    parser.add_argument('--variant', choices=('main', 'atmos'), required=True)
    parser.add_argument('--phase', choices=('cache', 'before', 'after', 'final'), required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--binary', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = phase(args)
    if args.output:
        write(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k in ('status', 'variant', 'source_identity_sha256')}))


if __name__ == '__main__':
    main()
