#!/usr/bin/env python3
"""Compile and run the actual SDK content getter against bounded graph fixtures.

Uses the platform's native C compiler, not the player or NN decoder. The SDK
source must already contain the content-selection layer. The supplied fixture
was generated from independently parsed metadata of the DVB No3 MP4 sample.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    sdk = args.sdk_source.resolve()
    if (sdk / 'av3adecoder').is_dir():
        sdk /= 'av3adecoder'
    source = sdk / 'avs3Decoder/src/avs3_spatial_contents.c'
    header = sdk / 'avs3Decoder/include/avs3_spatial_contents.h'
    interface = sdk / 'avs3Decoder/include/avs3_decoder_interface.h'
    case = here / 'content-graph-cases.c'
    fixture = here / 'sample_fixture.inc'
    provenance = here / 'content-graph-fixture.json'
    for path in (source, header, interface, case, fixture, provenance):
        if not path.is_file():
            raise SystemExit(f'Required source/fixture missing: {path}')
    args.output.mkdir(parents=True, exist_ok=False)
    exe = args.output / 'content-graph-test.exe'
    command = [args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
               '-DAVS3_AUDIODEC_LIBRARY=1',
               '-I' + str(sdk / 'avs3Decoder/include'),
               '-I' + str(sdk / 'libavs3_common'), '-I' + str(here),
               str(source), str(case), '-o', str(exe)]
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (args.output / 'compile.stdout').write_bytes(compiled.stdout)
    (args.output / 'compile.stderr').write_bytes(compiled.stderr)
    if compiled.returncode:
        raise SystemExit(f'Content graph compilation failed: {compiled.returncode}; '
                         f'see {args.output / "compile.stderr"}')
    started = time.monotonic()
    result = subprocess.run([str(exe)], capture_output=True, timeout=10)
    elapsed = time.monotonic() - started
    (args.output / 'stdout.log').write_bytes(result.stdout)
    (args.output / 'stderr.log').write_bytes(result.stderr)
    if result.returncode:
        raise SystemExit(f'Content graph contracts failed: {result.returncode}; '
                         f'see {args.output / "stderr.log"}')
    report = json.loads(result.stdout.decode('utf-8').splitlines()[-1])
    if not report.get('passed') or report.get('cases') != 81:
        raise SystemExit('Unexpected graph contract receipt')
    report.update(wall_seconds=elapsed, compiler=args.cc,
                  compile_command=command,
                  sdk_source=str(sdk),
                  fixture_provenance=json.loads(provenance.read_text(encoding='utf-8')),
                  sources=[dict(path=str(path), sha256=sha256(path)) for path in
                           (source, header, interface, case, fixture, provenance)])
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n',
                                           encoding='utf-8')
    print(f'PASS: {report["cases"]} actual SDK getter contracts; no player/media/GPU')


if __name__ == '__main__':
    main()
