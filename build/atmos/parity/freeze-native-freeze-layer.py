"""Freeze reviewed 0065 mailbox replay on both installed canonical trees."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONFIG = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identity-main', required=True, type=Path)
    p.add_argument('--identity-atmos', required=True, type=Path)
    p.add_argument('--patch', default='build/bluray-menu/patches/0065-native-ass-epoch-bootstrap.patch')
    p.add_argument('--epoch-contract', default='build/feedback/tests/verify-secondary-ass-epoch-bootstrap.c')
    p.add_argument('--physical-contract')
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('native_freeze_gate', HERE/'verify-native-freeze-source.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    patch = (CONFIG/a.patch).resolve()
    gate.require(patch.is_relative_to(CONFIG) and patch.is_file(), 'Patch must exist inside new config')
    files = gate.changed_paths(CONFIG, patch)
    gate.require(files and set(files) <= gate.ALLOWED_SOURCE_FILES and 'video/out/vo.c' in files,
        'Unreviewed source patch scope')
    gate.require(not (HERE/'native-freeze-lock.json').exists(), 'Refuse to overwrite a frozen lock')
    variants = {}
    for variant, identity in (('main', a.identity_main), ('atmos', a.identity_atmos)):
        baseline = gate.PARENT_TREES[variant]
        gate.require(gate.git(identity, 'cat-file', '-t', baseline).strip() == b'tree',
            'Missing installed canonical source tree')
        with tempfile.TemporaryDirectory(prefix='native-freeze-canonical-index-') as folder:
            index = Path(folder)/'index'
            gate.git(identity, 'read-tree', baseline, index=index)
            gate.git(identity, 'apply', '--cached', '--check', patch, index=index)
            gate.git(identity, 'apply', '--cached', patch, index=index)
            final = gate.git(identity, 'write-tree', index=index).decode().strip()
        before, after = {}, {}
        for relative in files:
            existed = gate.git(identity, 'ls-tree', baseline, '--', relative).strip()
            before[relative] = gate.sha(gate.git(identity, 'show', baseline+':'+relative)) if existed else None
            after[relative] = gate.sha(gate.git(identity, 'show', final+':'+relative))
        variants[variant] = dict(baseline_tree=baseline, source_tree=final,
            before_source_sha256=before, source_sha256=after)
    contracts = [dict(id='exact-vo-osd-epoch-bootstrap', kind='extracted-epoch',
        runner=a.epoch_contract, expected_stdout_prefix='PASS scenarios=', run_arguments=[], inputs=[])]
    if a.physical_contract:
        contracts.append(dict(id='physical-phase-recovery', kind='c', runner=a.physical_contract,
            expected_stdout_prefix='FIXED:', run_arguments=['fixed'], inputs=[]))
    contracts.append(dict(id='existing-fresh-video-and-sampler', kind='c',
        runner='build/feedback/tests/verify-secondary-ass-fresh-video.c',
        expected_stdout_prefix='PASS scenarios=', run_arguments=[], inputs=[]))
    tools = set(gate.REQUIRED_TOOLS)
    tools.update(contract['runner'] for contract in contracts)
    lock = dict(version=1, parent_config_commit=gate.PARENT_CONFIG,
        parent_config_tree=gate.PARENT_CONFIG_TREE,
        parent_native_refresh_lock_sha256=gate.PARENT_NATIVE_LOCK_SHA256,
        parent_source_lock_sha256=gate.PARENT_SOURCE_LOCK_SHA256,
        dependency_lock_sha256=gate.DEPENDENCY_LOCK_SHA256,
        patch=dict(path=a.patch, sha256=gate.sha(patch.read_bytes()), changed_files=files),
        variants=variants, cpu_contracts=contracts,
        tools_sha256={rel: gate.sha((CONFIG/rel).read_bytes()) for rel in sorted(tools)})
    gate.validate_lock(lock)
    (HERE/'native-freeze-lock.json').write_text(json.dumps(lock, indent=2)+'\n', encoding='utf-8')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(status='EXACT_INSTALLED_CANONICAL_PATCH_REPLAY_FROZEN_NOT_RUNTIME',
        parent_config_commit=gate.PARENT_CONFIG, patch_sha256=lock['patch']['sha256'],
        variants=variants, native_freeze_lock_sha256=gate.sha((HERE/'native-freeze-lock.json').read_bytes()))
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
