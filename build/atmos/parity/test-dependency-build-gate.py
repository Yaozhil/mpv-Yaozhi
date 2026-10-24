"""Exercise rendering dependency rejection contracts without compiling a player."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


def repository(path):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.name', 'dependency contract')
    git(path, 'config', 'user.email', 'contract@localhost')
    git(path, 'config', 'core.autocrlf', 'false')
    (path / 'source.c').write_text('int dependency_identity = 1;\n')
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'base')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare = module('prepare_dependency_contract', HERE / 'prepare-dependency-lock.py')
    verify = module('verify_dependency_contract', HERE / 'verify-dependency-build.py')
    checks = []

    def check(name, function, reject=False):
        try:
            function()
        except (ValueError, FileNotFoundError, KeyError, subprocess.CalledProcessError) as exc:
            if not reject:
                raise
            checks.append({'name': name, 'status': 'PASS_REJECTED', 'reason': str(exc)})
        else:
            if reject:
                raise AssertionError('Gate accepted invalid input: ' + name)
            checks.append({'name': name, 'status': 'PASS'})

    with tempfile.TemporaryDirectory(prefix='dependency-gate-') as temporary:
        root = Path(temporary)
        winbuild = root / 'winbuild'
        packages = winbuild / 'packages'
        packages.mkdir(parents=True)
        (winbuild / 'cmake').mkdir()
        helper = '    if(NOT "${_name}" MATCHES "^(avs3-audiodec|ffmpeg|mpv)$")\n'
        (winbuild / 'cmake/custom_steps.cmake').write_text(helper)
        for name in ('libplacebo', 'glad', 'fast_float'):
            shutil.copyfile(HERE / 'dependency-lock-fixtures' / (name + '.cmake'), packages / (name + '.cmake'))
        prepare.prepare(winbuild, 'main')
        verify.HERE = winbuild / 'dependency-lock-tools'
        check('effective recipes and tool identities', lambda: verify.prepared(winbuild, 'main'))
        check('variant mismatch', lambda: verify.prepared(winbuild, 'atmos'), True)
        recipe = packages / 'libplacebo.cmake'
        original = recipe.read_bytes()
        recipe.write_bytes(original + b'\n# unexpected patch\n')
        check('recipe or patch mutation', lambda: verify.prepared(winbuild, 'main'), True)
        recipe.write_bytes(original)
        lock_path = verify.HERE / 'dependency-lock.json'
        original_lock = lock_path.read_bytes()
        lock_path.write_bytes(original_lock + b' ')
        check('lock mutation', lambda: verify.prepared(winbuild, 'main'), True)
        lock_path.write_bytes(original_lock)
        cache_marker = winbuild / 'build64/dependency-cache-identity.json'
        verify.write(cache_marker, {'variant': 'atmos', 'lock_sha256': verify.sha(lock_path)})
        check('foreign variant cache', lambda: verify.cache(winbuild, 'main'), True)
        verify.write(cache_marker, {'variant': 'main', 'lock_sha256': '0' * 64})
        check('foreign lock cache', lambda: verify.cache(winbuild, 'main'), True)
        cache_marker.unlink()
        cmake_cache = winbuild / 'build64/CMakeCache.txt'
        cmake_cache.write_text('old unidentified cache')
        check('unidentified cache', lambda: verify.cache(winbuild, 'main'), True)
        cmake_cache.unlink()
        check('cold cache initialization', lambda: verify.cache(winbuild, 'main'))
        verify.write(cache_marker, {'variant': 'main', 'lock_sha256': verify.sha(lock_path)})
        check('matching cache initialization', lambda: verify.cache(winbuild, 'main'))
        # Use disposable commits to test byte/tree/dirty/link rejection. These
        # fixtures are explicitly not provenance evidence for upstream code.
        lock = verify.read(lock_path)
        for name in lock['sources']:
            repository(winbuild / 'src_packages' / name)
        lp = winbuild / 'src_packages/libplacebo'
        (lp / '3rdparty').mkdir()
        for name in ('glad', 'fast_float'):
            target = winbuild / 'src_packages' / name
            git(lp, 'update-index', '--add', '--cacheinfo',
                '160000,' + git(target, 'rev-parse', 'HEAD') + ',3rdparty/' + name)
        git(lp, 'commit', '-qm', 'external sources')
        for name in lock['sources']:
            path = winbuild / 'src_packages' / name
            lock['sources'][name]['commit'] = git(path, 'rev-parse', 'HEAD')
            lock['sources'][name]['tree'] = git(path, 'rev-parse', 'HEAD^{tree}')
        for name in ('glad', 'fast_float'):
            (lp / '3rdparty' / name).symlink_to(winbuild / 'src_packages' / name, target_is_directory=True)
        check('locked base and two allowed external links', lambda: verify.source_manifest(winbuild, lock))
        wrong = copy.deepcopy(lock)
        wrong['sources']['libplacebo']['commit'] = '0' * 40
        check('wrong base commit', lambda: verify.source_manifest(winbuild, wrong), True)
        wrong = copy.deepcopy(lock)
        wrong['sources']['libplacebo']['tree'] = '0' * 40
        check('wrong tree', lambda: verify.source_manifest(winbuild, wrong), True)
        source = lp / 'source.c'
        original_source = source.read_bytes()
        source.write_bytes(original_source + b'int drift;\n')
        check('unapproved tracked dirty bytes', lambda: verify.source_manifest(winbuild, lock), True)
        source.write_bytes(original_source)
        source.write_bytes(original_source + b'int staged_drift;\n')
        git(lp, 'add', 'source.c')
        check('staged source mutation', lambda: verify.source_manifest(winbuild, lock), True)
        git(lp, 'reset', '-q', 'HEAD', '--', 'source.c')
        source.write_bytes(original_source)
        (lp / 'unexpected.c').write_text('int untracked;')
        check('unexpected untracked source', lambda: verify.source_manifest(winbuild, lock), True)
        (lp / 'unexpected.c').unlink()
        (lp / '.git/info/exclude').write_text('ignored.c\n')
        (lp / 'ignored.c').write_text('int ignored;')
        check('unexpected ignored source', lambda: verify.source_manifest(winbuild, lock), True)
        (lp / 'ignored.c').unlink()
        bytecode = winbuild / 'src_packages/glad/__pycache__/generator.cpython-313.pyc'
        bytecode.parent.mkdir()
        bytecode.write_bytes(b'cached generator code')
        check('Python generator bytecode rejected', lambda: verify.source_manifest(winbuild, lock), True)
        bytecode.unlink()
        bytecode.parent.rmdir()
        link = lp / '3rdparty/glad'
        link.unlink()
        link.symlink_to(winbuild / 'src_packages/fast_float', target_is_directory=True)
        check('wrong external source link', lambda: verify.source_manifest(winbuild, lock), True)
        link.unlink()
        link.symlink_to(winbuild / 'src_packages/glad', target_is_directory=True)
        extra_link = lp / 'untracked-headers'
        extra_link.symlink_to(winbuild / 'src_packages/glad', target_is_directory=True)
        check('unexpected directory symlink', lambda: verify.source_manifest(winbuild, lock), True)
        extra_link.unlink()
        dirty = winbuild / 'src_packages/glad/source.c'
        original_source = dirty.read_bytes()
        dirty.write_bytes(original_source + b'int external_drift;\n')
        check('external source dirty bytes', lambda: verify.source_manifest(winbuild, lock), True)
        dirty.write_bytes(original_source)
        # Verify the real Meson option decoder independently of source fixtures.
        build = winbuild / 'build64/packages/libplacebo-prefix/src/libplacebo-build'
        prefix = winbuild / 'build64/install/x86_64-w64-mingw32'
        options = [{'name': key, 'value': value} for key, value in lock['libplacebo_options'].items()]
        options += [{'name': 'prefix', 'value': str(prefix)},
                    {'name': 'libdir', 'value': str(prefix / 'lib')},
                    {'name': 'vulkan-registry', 'value': str(prefix / 'share/vulkan/registry/vk.xml')}]
        options_path = build / 'meson-info/intro-buildoptions.json'
        verify.write(options_path, options)
        check('Meson options match', lambda: verify.check_options(build, lock, prefix))
        options[0]['value'] = 'shared'
        verify.write(options_path, options)
        check('Meson option drift', lambda: verify.check_options(build, lock, prefix), True)
        options[0]['value'] = 'static'
        verify.write(options_path, options)
        # Run the complete lifecycle against explicit fixture commits. The
        # archive/binary bytes below simulate compiler outputs, not a player.
        lock_path.write_text(json.dumps(lock, indent=2) + '\n')
        preparation_path = winbuild / 'dependency-preparation.json'
        preparation = verify.read(preparation_path)
        preparation['lock_sha256'] = verify.sha(lock_path)
        preparation['tools_sha256']['dependency-lock.json'] = verify.sha(lock_path)
        verify.write(preparation_path, preparation)
        invocation = verify.read(cache_marker)
        invocation['lock_sha256'] = verify.sha(lock_path)
        verify.write(cache_marker, invocation)
        verify.write(winbuild / 'dependency-evidence/invocation.json', invocation)
        for relative in ('build.ninja', 'meson-logs/meson-log.txt'):
            path = build / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture compiler configuration\n')
        compiler = winbuild / 'build64/install/bin/x86_64-w64-mingw32-gcc'
        cpp = compiler.with_name('x86_64-w64-mingw32-g++')
        compiler.parent.mkdir(parents=True)
        compiler.write_text('fixture C compiler')
        cpp.write_text('fixture C++ compiler')
        cross_path = winbuild / 'build64/meson_cross.txt'
        cross_path.write_text('[binaries]\nc = ' + repr(str(compiler)) + '\ncpp = ' + repr(str(cpp)) + '\n')
        verify.write(build / 'meson-info/meson-info.json', {'directories': {'source': str(lp), 'build': str(build)}})
        machines = {name: {'system': 'windows', 'cpu_family': 'x86_64', 'endian': 'little'} for name in ('host', 'target')}
        verify.write(build / 'meson-info/intro-machines.json', machines)
        (build / 'meson-private').mkdir()
        (build / 'meson-private/cmd_line.txt').write_text('[properties]\ncross_file = ' + repr([str(cross_path)]) + '\n')
        verify.write(build / 'meson-info/intro-targets.json', [
            {'type': 'static library', 'filename': [str(build / 'src/libplacebo.a')],
             'defined_in': str(lp / 'meson.build'),
             'target_sources': [{'sources': [str(source)], 'generated_sources': []}]}])
        command = {'directory': str(build), 'file': str(source),
                   'output': str(build / 'src/libplacebo.a.p/source.c.o'),
                   'command': str(compiler) + ' -c ' + str(source)}
        verify.write(build / 'compile_commands.json', [command])
        real_compiler_output = subprocess.check_output

        def compiler_output(arguments, *values, **kwargs):
            if arguments[0] == str(compiler):
                return b'x86_64-w64-mingw32\n'
            return real_compiler_output(arguments, *values, **kwargs)

        verify.subprocess.check_output = compiler_output
        check('Meson source/build machine and compilation graph', lambda: verify.check_build_graph(winbuild, lp, build))
        info_path = build / 'meson-info/meson-info.json'
        original_info = info_path.read_bytes()
        verify.write(info_path, {'directories': {'source': str(root), 'build': str(build)}})
        check('Meson source points at another checkout', lambda: verify.check_build_graph(winbuild, lp, build), True)
        info_path.write_bytes(original_info)
        machines['host']['system'] = 'linux'
        verify.write(build / 'meson-info/intro-machines.json', machines)
        check('Meson host machine mismatch', lambda: verify.check_build_graph(winbuild, lp, build), True)
        machines['host']['system'] = 'windows'
        verify.write(build / 'meson-info/intro-machines.json', machines)
        command['file'] = str(root / 'unrelated.c')
        verify.write(build / 'compile_commands.json', [command])
        check('Compilation command uses unrelated source', lambda: verify.check_build_graph(winbuild, lp, build), True)
        command['file'] = str(source)
        command['directory'] = str(root)
        verify.write(build / 'compile_commands.json', [command])
        check('Compilation command uses unrelated build directory', lambda: verify.check_build_graph(winbuild, lp, build), True)
        command['directory'] = str(build)
        verify.write(build / 'compile_commands.json', [command])
        # Meson 1.12.1 classifies configure_file -> Windows resource input
        # under custom target `sources`, not under `generated_sources`.
        (lp / 'win32').mkdir()
        (lp / 'win32/meson.build').write_text(
            "libplacebo_rc = configure_file(input: 'libplacebo.rc.in',\n"
            "                               output: 'libplacebo.rc',\n"
            "                               configuration: version_config)\n")
        (lp / 'src').mkdir()
        (lp / 'src/meson.build').write_text("sources += windows.compile_resources(libplacebo_rc, depends: version_h)\n")
        template = lp / 'win32/libplacebo.rc.in'
        template.write_text('FILEVERSION @PL_MAJOR@, @PL_MINOR@, @PL_PATCH@\n')
        resource = build / 'win32/libplacebo.rc'
        resource.parent.mkdir()
        resource.write_text('FILEVERSION 7, 387, 0\n')
        verify.write(build / 'meson-info/intro-projectinfo.json', {'version':'7.387.0'})
        verify.write(build / 'meson-info/intro-buildsystem_files.json', [str(template)])
        resource_target = {'name':'libplacebo.rc','type':'custom','defined_in':str(lp/'src/meson.build'),
            'filename':[str(build/'src/win32_libplacebo.rc_libplacebo.o')],
            'target_sources':[{'sources':[str(resource)],'generated_sources':[]}]}
        target_path = build / 'meson-info/intro-targets.json'
        original_targets = target_path.read_bytes()
        targets = verify.read(target_path)
        targets.append(resource_target)
        verify.write(target_path,targets)
        check('Meson configured resource input exact declaration and bytes',lambda:verify.check_build_graph(winbuild,lp,build))
        resource.write_text('FILEVERSION 7, 387, 0\nint injected_code;\n')
        check('configured resource injected bytes',lambda:verify.check_build_graph(winbuild,lp,build),True)
        resource.write_text('FILEVERSION 7, 387, 0\n')
        (lp / 'win32/meson.build').write_text("libplacebo_rc = 'unrelated resource'\n")
        check('configured resource missing source declaration',lambda:verify.check_build_graph(winbuild,lp,build),True)
        (lp / 'win32/meson.build').write_text(
            "libplacebo_rc = configure_file(input: 'libplacebo.rc.in', output: 'libplacebo.rc', configuration: version_config)\n")
        verify.write(build / 'meson-info/intro-buildsystem_files.json', [])
        check('configured resource template not a configure input',lambda:verify.check_build_graph(winbuild,lp,build),True)
        verify.write(build / 'meson-info/intro-buildsystem_files.json', [str(template)])
        rogue = build / 'win32/unregistered.c'
        rogue.write_text('int unregistered;\n')
        resource_target['target_sources'][0]['sources']=[str(rogue)]
        verify.write(target_path,targets)
        check('unregistered C source inside fixed build rejected',lambda:verify.check_build_graph(winbuild,lp,build),True)
        resource_target['target_sources'][0]['sources']=[str(root/'escaped.c')]
        verify.write(target_path,targets)
        check('configured source outside build rejected',lambda:verify.check_build_graph(winbuild,lp,build),True)
        resource_target['target_sources'][0]['sources']=[str(resource)]
        resource_target['defined_in']=str(root/'other-meson.build')
        verify.write(target_path,targets)
        check('resource definition outside locked source rejected',lambda:verify.check_build_graph(winbuild,lp,build),True)
        target_path.write_bytes(original_targets)
        # Remove the schema-only source fixture additions before exercising
        # the original locked repository compiler lifecycle below.
        shutil.rmtree(lp / 'win32')
        shutil.rmtree(lp / 'src')
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        phase = SimpleNamespace(winbuild=winbuild, variant='main', source=lp, build=build,
                                prefix=prefix, binary=[], phase='before')
        check('before compiler snapshot lifecycle', lambda: verify.phase(phase))
        check('duplicate compiler snapshot receipt', lambda: verify.phase(phase), True)
        phase.phase = 'after'
        source.write_bytes(original_source + b'int compile_drift;\n')
        check('source drift during compilation', lambda: verify.phase(phase), True)
        source.write_bytes(original_source)
        installed = prefix / 'lib/libplacebo.a'
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b'fixture static archive')
        compiled = build / 'src/libplacebo.a'
        compiled.parent.mkdir(parents=True)
        compiled.write_bytes(installed.read_bytes())
        (build / '.ninja_log').write_text('fixture compilation log\n')
        (build / 'meson-logs/install-log.txt').write_text('fixture install log\n')
        before = verify.read(winbuild / 'dependency-evidence/before.json')
        old = before['started_ns'] - 1000000000
        os.utime(installed, ns=(old, old))
        check('stale installed archive', lambda: verify.phase(phase), True)
        installed.write_bytes(compiled.read_bytes())
        compiled.write_bytes(b'other compilation')
        check('different compiled archive', lambda: verify.phase(phase), True)
        compiled.write_bytes(installed.read_bytes())
        check('after compiler archive lifecycle', lambda: verify.phase(phase))
        phase.phase = 'final'
        binaries = [root / 'mpv.exe', root / 'mpv.com']
        for path in binaries:
            path.write_bytes(b'fixture binary output ' + path.suffix.encode())
        phase.binary = binaries
        real_check_output = subprocess.check_output
        link_commands = (str(installed) + ' -o mpv.exe').encode()

        def command_output(command, *arguments, **kwargs):
            if command[0] == 'ninja':
                if 'query' in command:
                    return ('mpv.exe:\n  input: c_LINKER\n    ' + str(installed) + '\n  outputs:\n').encode()
                return link_commands
            return real_check_output(command, *arguments, **kwargs)

        verify.subprocess.check_output = command_output
        try:
            check('final binary and actual archive link binding', lambda: verify.phase(phase))
            original_archive = installed.read_bytes()
            installed.write_bytes(original_archive + b'drift')
            check('archive changed before final link gate', lambda: verify.phase(phase), True)
            installed.write_bytes(original_archive)
            link_commands = b'other.a -o mpv.exe'
            check('link graph consumes different archive', lambda: verify.phase(phase), True)
            link_commands = (str(installed) + ' -o libmpv.dll\nother.a -o mpv.exe').encode()
            check('different target consumes verified archive', lambda: verify.phase(phase), True)
            link_commands = (str(installed) + ' -o mpv.exe').encode()
            os.utime(binaries[0], ns=(old, old))
            check('stale player binary', lambda: verify.phase(phase), True)
            binaries[0].write_bytes(b'fixture binary output .exe')
            snapshot = winbuild / 'dependency-evidence/actual-source.tar.gz'
            original_snapshot = snapshot.read_bytes()
            snapshot.write_bytes(original_snapshot + b'drift')
            check('source snapshot changed', lambda: verify.phase(phase), True)
            snapshot.write_bytes(original_snapshot)
            check('restored final lifecycle', lambda: verify.phase(phase))
        finally:
            verify.subprocess.check_output = real_compiler_output
        # Every actual upstream pin is checked syntactically and by the recipe
        # frozen above. CI compilation performs the real source/library gate.
        upstream_lock = json.loads(original_lock)
        for name, pin in upstream_lock['sources'].items():
            import re
            assert re.fullmatch('[0-9a-f]{40}', pin['commit']) and re.fullmatch('[0-9a-f]{40}', pin['tree'])
            assert '    GIT_TAG ' + pin['commit'] + '\n' in (packages / (name + '.cmake')).read_text()
        checks.append({'name': 'three full upstream recipe pins', 'status': 'PASS'})

    report = {'status': 'PASS_DEPENDENCY_GATE_CONTRACTS', 'checks': checks, 'count': len(checks),
              'scope': 'disposable repository rejection contracts; real compiled sources are checked by build hooks'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'count': len(checks)}))


if __name__ == '__main__':
    main()
