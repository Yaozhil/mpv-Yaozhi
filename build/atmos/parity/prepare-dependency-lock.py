"""Freeze the rendering dependency recipe and preserve its actual build inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(winbuild, variant):
    winbuild = winbuild.resolve()
    lock_path = HERE / 'dependency-lock.json'
    lock = json.loads(lock_path.read_bytes())
    tools = winbuild / 'dependency-lock-tools'
    tools.mkdir(exist_ok=True)
    for name in ('dependency-lock.json', 'verify-dependency-build.py'):
        shutil.copyfile(HERE / name, tools / name)
    original = {}
    effective = {}
    for name, source in lock['sources'].items():
        path = winbuild / 'packages' / (name + '.cmake')
        text = path.read_text()
        original[name] = hashlib.sha256(text.encode()).hexdigest()
        if original[name] != lock['original_recipes_sha256'][name]:
            raise ValueError('Unreviewed rendering dependency recipe: ' + name)
        repository = '    GIT_REPOSITORY ' + source['repository'] + '\n'
        if text.count(repository) != 1:
            raise ValueError('Unexpected rendering dependency repository: ' + name)
        if 'PATCH_COMMAND' in text:
            raise ValueError('Unexpected rendering dependency patch chain: ' + name)
        text = re.sub(r'^    GIT_TAG .*\n', '', text, flags=re.M)
        text = re.sub(r'^    GIT_REMOTE_NAME .*\n', '', text, flags=re.M)
        text = text.replace(repository, repository + '    GIT_TAG ' + source['commit'] + '\n', 1)
        # Do not let a generic `ninja update` fetch/reset these frozen checkouts.
        force = 'force_rebuild_git(' + name + ')\n'
        if text.count(force) != 1:
            raise ValueError('Unexpected rendering dependency update hook: ' + name)
        text = text.replace(force, '', 1)
        if name == 'libplacebo':
            common = ('python3 ${PROJECT_SOURCE_DIR}/dependency-lock-tools/verify-dependency-build.py '
                      '--winbuild ${PROJECT_SOURCE_DIR} --variant ' + variant + ' '
                      '--source <SOURCE_DIR> --build <BINARY_DIR> '
                      '--prefix ${MINGW_INSTALL_PREFIX} ')
            build = '    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>\n'
            install = '    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install\n'
            if text.count(build) != 1 or text.count(install) != 1:
                raise ValueError('Unexpected libplacebo build/install recipe')
            text = text.replace(build, '    BUILD_COMMAND ' + common + '--phase before\n'
                '        COMMAND ${EXEC} ninja -C <BINARY_DIR>\n', 1)
            text = text.replace(install, install + '        COMMAND ' + common + '--phase after\n', 1)
        path.write_text(text)
        effective[name] = sha(path)

    helper = winbuild / 'cmake/custom_steps.cmake'
    text = helper.read_text()
    old = '    if(NOT "${_name}" MATCHES "^(avs3-audiodec|ffmpeg|mpv)$")\n'
    if text.count(old) != 1:
        raise ValueError('Expected the frozen round-two source retention boundary')
    helper.write_text(text.replace(old, old.replace('|mpv)', '|mpv|libplacebo|glad|fast_float)'), 1))
    inventory = []
    recipe_paths = list((winbuild / 'packages').glob('*.cmake'))
    recipe_paths.extend((winbuild / 'toolchain').rglob('*.cmake'))
    for path in sorted(recipe_paths):
        text = path.read_text()
        repo = re.search(r'^\s+GIT_REPOSITORY\s+(.+)$', text, re.M)
        if not repo:
            continue
        tag = re.search(r'^\s+GIT_TAG\s+(.+)$', text, re.M)
        ref = tag.group(1).strip() if tag else ''
        inventory.append({'name': path.stem, 'recipe_path': path.relative_to(winbuild).as_posix(),
                          'repository': repo.group(1).strip(),
                          'ref': ref, 'full_commit_pin': bool(re.fullmatch('[0-9a-f]{40}', ref)),
                          'recipe_sha256': sha(path)})
    report = {'schema': 1, 'variant': variant, 'lock_sha256': sha(lock_path),
              'original_render_recipes_sha256': original,
              'effective_render_recipes_sha256': effective,
              'retention_helper_sha256': sha(helper), 'git_inventory': inventory,
              'tools_sha256': {p.name: sha(p) for p in tools.iterdir() if p.is_file()}}
    (winbuild / 'dependency-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--winbuild', type=Path, required=True)
    parser.add_argument('--variant', choices=('main', 'atmos'), required=True)
    args = parser.parse_args()
    report = prepare(args.winbuild, args.variant)
    print('DEPENDENCY_LOCK_PREPARED ' + report['lock_sha256'])


if __name__ == '__main__':
    main()
