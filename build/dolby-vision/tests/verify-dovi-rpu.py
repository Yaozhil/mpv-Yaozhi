"""Verify tiny upstream RPU fixtures using the player FFmpeg parser + helper."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--probe', type=Path, required=True)
parser.add_argument('--fixtures', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--commit', default=os.environ.get('GITHUB_SHA', 'local'))
parser.add_argument('--variant', default='local')
args = parser.parse_args()
manifest = json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['commit'] == '614c816b6446dcd1dbaf433403d499a6026fbb5a'
assert len(manifest['fixtures']) == 4
observed = {}
for name, expected in manifest['fixtures'].items():
    fixture = args.fixtures / name
    data = fixture.read_bytes()
    assert len(data) == expected['bytes'], name
    assert hashlib.sha256(data).hexdigest() == expected['sha256'], name
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == expected['git_blob'], name
    run = subprocess.run([str(args.probe.resolve()), str(fixture.resolve()), expected['expected_el_type']],
                         check=True, capture_output=True, text=True, timeout=15)
    result = json.loads(run.stdout)
    assert result['result'] == 'PASS' and result['rpu_present'] and result['profile'] == 7, name
    assert result['el_type'] == expected['expected_el_type'], name
    observed[name] = {**result, 'fixture_sha256': expected['sha256']}
args.output.mkdir(parents=True, exist_ok=True)
result = {'result': 'PASS', 'build_commit': args.commit, 'variant': args.variant,
          'scope': 'actual linked player FFmpeg ff_dovi_rpu_parse / ff_dovi_get_metadata then production identification helper; no video/rendering',
          'fixture_commit': manifest['commit'],
          'probe_sha256': hashlib.sha256(args.probe.read_bytes()).hexdigest(), 'fixtures': observed}
(args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
