"""Patch one pinned, isolated PresentMon source tree. No tracing or dispatch."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

COMMIT = '717c5bf14e80a4a06b70cd16415ae8d40a7ce201'
RELATIVE_SOURCE = 'PresentData/PresentMonTraceSession.cpp'
ORIGINAL_SHA = 'e4dfe92174d0ee5d2f3bef139722f0c1a92d19e3f2060658aee1f66fa1fb7c06'
ANCHOR = (b'        sessionProps.LoggerNameOffset = offsetof(TraceProperties, mSessionName);'
          b'  // Location of session name; will be written by StartTrace()\n')
ADDITION = (b'        sessionProps.MinimumBuffers = 128;\n'
            b'        sessionProps.MaximumBuffers = 512;\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patched_source(original):
    if sha(original) != ORIGINAL_SHA or original.count(ANCHOR) != 1:
        raise ValueError('Pinned official StartTrace source differs; no patch applied')
    result = original.replace(ANCHOR, ANCHOR + ADDITION, 1)
    if result.replace(ADDITION, b'', 1) != original:
        raise ValueError('The complete source was not preserved outside the two additions')
    start = result.index(b'ULONG PMTraceSession::Start(')
    call = result.index(b'        auto status = StartTraceW(', start)
    if not start < result.index(ADDITION) < call:
        raise ValueError('Buffer assignments escaped the real-time pre-StartTrace branch')
    return result


def unified_patch(original, result):
    return ''.join(difflib.unified_diff(
        original.decode('utf-8').splitlines(keepends=True),
        result.decode('utf-8').splitlines(keepends=True),
        fromfile='a/' + RELATIVE_SOURCE, tofile='b/' + RELATIVE_SOURCE)).encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve() / RELATIVE_SOURCE
    if not source.is_file() or args.receipt.exists():
        raise ValueError('Source missing or receipt already exists')
    original = source.read_bytes()
    result = patched_source(original)
    patch = unified_patch(original, result)
    expected_patch = Path(__file__).with_name('start-buffers-only.patch').read_bytes()
    if patch != expected_patch:
        raise ValueError('Reviewed patch bytes differ')
    source.write_bytes(result)
    receipt = {'status': 'TWO_STARTTRACE_BUFFER_ASSIGNMENTS_ONLY_NOT_RUNTIME',
               'official_commit': COMMIT, 'source_relative': RELATIVE_SOURCE,
               'original_sha256': sha(original), 'patched_sha256': sha(result),
               'patch_sha256': sha(patch), 'MinimumBuffers': 128, 'MaximumBuffers': 512,
               'all_other_source_bytes_preserved': True, 'StartTrace_executed': False}
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
