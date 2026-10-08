"""Read compiled no-ETW property probes and parser receipts; no live capture."""
import argparse
import hashlib
import json
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', required=True, type=Path)
    args = parser.parse_args()
    out = args.artifact_dir
    baseline = json.loads((out / 'props-baseline.json').read_text(encoding='utf-8-sig'))
    patched = json.loads((out / 'props-patched.json').read_text(encoding='utf-8-sig'))
    require(baseline['MinimumBuffers'] == baseline['MaximumBuffers'] == 0,
            'Baseline defaults differ')
    require(patched['MinimumBuffers'] == 128 and patched['MaximumBuffers'] == 512,
            'Compiled startup counts differ')
    for data in (baseline, patched):
        require(data['intercepted_StartTrace_calls'] == 1 and data['real_ETW_calls'] == 0
                and data['status'] == 5 and data['WNODE_HEADER_size'] == 48
                and data['properties_size'] == 120 and data['WnodeBufferSize'] == 640
                and data['ClientContext'] == 1 and data['WnodeFlags'] == 0x20000
                and data['BufferSize'] == 0 and data['LogFileMode'] == 0x100
                and data['LoggerNameOffset'] == 120, 'Compiled ABI/clock/mode differs')
    expected_bytes = bytearray.fromhex(baseline['raw_properties_hex'])
    expected_bytes[52:56] = (128).to_bytes(4, 'little')
    expected_bytes[56:60] = (512).to_bytes(4, 'little')
    require(bytes.fromhex(patched['raw_properties_hex']) == bytes(expected_bytes),
            'Compiled StartTrace properties changed beyond the two ULONG counts')
    parser_receipt = json.loads((out / 'parser-receipt.json').read_text(encoding='utf-8-sig'))
    help_text = (out / 'help.txt').read_text(encoding='utf-8-sig')
    version_text = (out / 'version-invalid.txt').read_text(encoding='utf-8-sig')
    require(parser_receipt == {'help_exit_code': 1, 'version_exit_code': 1},
            'Official parser exits differ')
    require('PresentMon 2.3.1' in help_text and 'unrecognized option' not in help_text,
            'Official help/version banner differs')
    require("unrecognized option '--version'" in version_text
            and 'PresentMon 2.3.1' in version_text,
            'The official unsupported --version behavior was changed')
    executable = out / 'PresentMon-2.3.1-v30-buffers-x64.exe'
    result = {'status': 'COMPILED_CONSOLE_AND_NO_ETW_START_PROPS_VERIFIED_NOT_RUNTIME',
              'exe_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'MinimumBuffers': 128, 'MaximumBuffers': 512,
              'all_other_120_property_bytes_preserved': True,
              'help_prints_version': '2.3.1', 'version_option_supported': False,
              'live_capture_performed': False, 'Display_acceptance': False}
    (out / 'compiled-check.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
