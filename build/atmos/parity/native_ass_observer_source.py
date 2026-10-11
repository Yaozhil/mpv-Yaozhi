"""Strict source identity for the observer-only layer above pause/prepass."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]
CHANGED_FILES = ['test/secondary_ass_physical.c',
                 'video/out/secondary_ass_physical.h']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source),
        '-c', 'core.autocrlf=false', '-c', 'user.name=mpv-Yaozhi',
        '-c', 'user.email=yaozhi@localhost', *args], timeout=45)


def verify_observer_source(source):
    """Accept actual checked replay bytes, not a guessed relative source stage."""
    source = Path(source).resolve()
    lock = json.loads((HERE/'source-lock.json').read_bytes())
    fix = lock['native_ass_observer_recovery_fix']
    prepass = lock['native_ass_prepass_fix']
    require(not git(source, 'status', '--porcelain').strip(), 'Source must be clean')
    require(fix['parent_commit'] == prepass['source_commit'], 'Wrong observer parent')
    require(re.fullmatch('[0-9a-f]{40}', fix['source_commit']), 'Invalid source commit')
    require(re.fullmatch('[0-9a-f]{40}', fix['source_tree']), 'Invalid source tree')
    patch = CONFIG/fix['patch']
    require(patch.resolve().is_relative_to(CONFIG), 'Patch escapes config')
    raw = patch.read_bytes()
    require(sha(raw) == fix['patch_sha256'], 'Observer patch SHA differs')
    require(raw.startswith(('From '+fix['source_commit']+' ').encode()),
            'Observer patch provenance differs')
    require(lock['common_patches'].get(fix['patch']) == fix['patch_sha256'],
            'Observer patch missing from the common lock')
    require(git(source, 'diff', '--name-only', 'HEAD^', 'HEAD').decode().splitlines()
            == CHANGED_FILES, 'Observer delta must change only physical header and its test')
    require(fix['before_source_sha256'] == prepass['source_sha256'],
            'Observer input differs from the exact prepass output')
    require(set(fix['source_sha256']) == set(prepass['source_sha256'])
            and len(fix['source_sha256']) == 7, 'Wrong common seven-source set')
    require([name for name, digest in fix['source_sha256'].items()
             if digest != fix['before_source_sha256'][name]]
            == ['video/out/secondary_ass_physical.h'],
            'Observer recovery changed an unrelated common source')
    for name, digest in fix['before_source_sha256'].items():
        require(sha(git(source, 'show', 'HEAD^:'+name)) == digest,
                'Observer parent SHA differs: '+name)
    for name, digest in fix['source_sha256'].items():
        require(sha((source/name).read_bytes()) == digest, 'Observer source SHA differs: '+name)
    require(set(fix['before_test_sha256']) == {'test/secondary_ass_physical.c'}
            and set(fix['test_sha256']) == {'test/secondary_ass_physical.c'},
            'Unexpected test file set')
    for name, digest in fix['before_test_sha256'].items():
        require(sha(git(source, 'show', 'HEAD^:'+name)) == digest,
                'Observer parent test SHA differs: '+name)
    for name, digest in fix['test_sha256'].items():
        require(sha((source/name).read_bytes()) == digest, 'Observer test SHA differs: '+name)
    version = (source/'common/version.c').read_bytes()
    require(version == git(source, 'show', 'HEAD^:common/version.c')
            and b'(mpv-Yaozhi)' in version, 'Branding changed or missing')
    return fix
