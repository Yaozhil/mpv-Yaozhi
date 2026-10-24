"""Isolated real-mpv Windows path, wildcard and named-pipe integration gate.

Usage: python windows-paths-runtime.py --mpv C:/candidate/mpv.exe --output C:/evidence
Use --expect-old only for the known old red control; no assertions are weakened.
No user mpv process is controlled. Pipe names are local, unique and bounded.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import hashlib
import io
import json
import ntpath
import os
from pathlib import Path
import subprocess
import time
import uuid
import wave

HERE = Path(__file__).resolve().parent
K = ctypes.WinDLL('kernel32', use_last_error=True)


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                ('Offset', w.DWORD), ('OffsetHigh', w.DWORD), ('hEvent', w.HANDLE)]


K.CreateNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, ctypes.c_void_p]
K.CreateNamedPipeW.restype = w.HANDLE
K.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
K.CreateEventW.restype = w.HANDLE
K.ConnectNamedPipe.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED)]
K.ConnectNamedPipe.restype = w.BOOL
K.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
K.WaitForSingleObject.restype = w.DWORD
K.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
K.WriteFile.restype = w.BOOL
K.GetOverlappedResult.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(w.DWORD), w.BOOL]
K.GetOverlappedResult.restype = w.BOOL
K.CancelIoEx.argtypes = [w.HANDLE, ctypes.c_void_p]
K.CloseHandle.argtypes = [w.HANDLE]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wav_data():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b'\0\0\0\0' * 14400)
    return out.getvalue()


def path_cases(cwd):
    cases = [
        ('relative-Chinese-space', '子目录 空格/../测试 片.wav', ntpath.join(str(cwd), '测试 片.wav')),
        ('drive-relative-current-drive', str(cwd)[:2] + '测试 片.wav', ntpath.join(str(cwd), '测试 片.wav')),
        ('root-relative', '\\测试 片.wav', str(cwd)[:2] + '\\测试 片.wav'),
        ('URL-preserved', 'https://server.example/a//b', 'https://server.example/a//b'),
        ('stdin-preserved', '-', '-'),
        ('old-parent', 'C:/foo/bar/../baz', 'C:\\foo\\baz'),
        ('old-extended-drive', '\\\\?\\C:\\folder\\..\\file.mkv', 'C:\\file.mkv'),
        ('forward-UNC', '//server/share/path', '\\\\server\\share\\path'),
        ('mixed-UNC', '//server\\share/path', '\\\\server\\share\\path'),
        ('UNC-parent', '//server/share/sub/../path', '\\\\server\\share\\path'),
        ('UNC-share-root', '//server/share/../../path', '\\\\server\\share\\path'),
        ('forward-extended-UNC', '//?/UNC/server/share/path', '\\\\server\\share\\path'),
        ('forward-extended-drive', '//?/C:/folder/../file.mkv', 'C:\\file.mkv'),
        ('native-device-pipe', '\\\\.\\pipe\\mpv', '\\\\.\\pipe\\mpv'),
        ('forward-device-pipe', '//./pipe/mpv', '\\\\.\\pipe\\mpv'),
        ('device-drive', '//./C:/folder/../file.mkv', '\\\\.\\C:\\file.mkv'),
    ]
    long_input = 'C:/' + 'segment012345678901234567890123456789/' * 8 + '测试 片.mkv'
    cases.append(('long-path-prefix', long_input, '\\\\?\\' + long_input.replace('/', '\\')))
    return [{'name': name, 'input': value, 'expected': expected} for name, value, expected in cases]


def launch(mpv, folder, name, payload, media=None):
    input_file = folder / f'{name}-input.json'
    output_file = folder / f'{name}-result.json'
    log_file = folder / f'{name}-mpv.log'
    input_file.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    env = os.environ.copy()
    env['PWD'] = 'Z:\\stale-pwd-from-other-shell'
    env['YAOZHI_WINDOWS_TEST_INPUT'] = str(input_file)
    env['YAOZHI_WINDOWS_TEST_OUTPUT'] = str(output_file)
    cmd = [str(mpv), '--no-config', '--load-scripts=no', '--vo=null', '--ao=null',
           '--osc=no', '--ytdl=no', '--resume-playback=no', '--save-position-on-quit=no',
           '--no-terminal', '--msg-level=all=info', f'--log-file={log_file}',
           '--script=' + str(HERE / 'windows-paths-runtime.lua')]
    if media is None: cmd += ['--idle=yes']
    else: cmd += ['--length=0.15', '--audio-display=no', '--video=no', '--', media]
    child = subprocess.Popen(cmd, cwd=payload['cwd'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return child, output_file, log_file, cmd


def collect(child, output_file, log_file, cmd, timeout=10):
    timed_out = False
    try: stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        child.kill()  # Only the exact child created above.
        stdout, stderr = child.communicate(timeout=3)
    result = json.loads(output_file.read_text(encoding='utf-8')) if output_file.exists() else None
    log = log_file.read_text(encoding='utf-8', errors='replace') if log_file.exists() else ''
    return {'exit_code': child.returncode, 'timed_out': timed_out, 'script': result,
            'log': str(log_file), 'command': cmd,
            'stdout': stdout.decode('utf-8', 'replace'), 'stderr': stderr.decode('utf-8', 'replace'),
            'log_text': log}


def pipe_case(mpv, folder, cwd, data):
    pipe = '\\\\.\\pipe\\yaozhi-mpv-windows-' + str(os.getpid()) + '-' + uuid.uuid4().hex
    server = K.CreateNamedPipeW(pipe, 0x00000002 | 0x40000000, 0, 1, 1 << 20, 1 << 20, 0, None)
    if server == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    event = K.CreateEventW(None, True, False, None)
    connected = OVERLAPPED(hEvent=event)
    pending = not K.ConnectNamedPipe(server, ctypes.byref(connected))
    error = ctypes.get_last_error() if pending else 0
    if pending and error not in (997, 535): raise ctypes.WinError(error)
    child = None
    written, served, write_error = w.DWORD(), False, None
    try:
        child, output, log, cmd = launch(mpv, folder, 'pipe', {'mode':'playback','cwd':str(cwd)}, pipe)
        wait = K.WaitForSingleObject(event, 5000) if error == 997 else 0
        if wait == 0:
            n = w.DWORD()
            complete = K.GetOverlappedResult(server, ctypes.byref(connected), ctypes.byref(n), False)
            if complete or error == 535:
                write_event = K.CreateEventW(None, True, False, None)
                writing = OVERLAPPED(hEvent=write_event)
                buffer = ctypes.create_string_buffer(data)
                try:
                    served = bool(K.WriteFile(server, buffer, len(data), ctypes.byref(written), ctypes.byref(writing)))
                    if not served:
                        write_error = ctypes.get_last_error()
                        if write_error == 997 and K.WaitForSingleObject(write_event, 3000) == 0:
                            served = bool(K.GetOverlappedResult(server, ctypes.byref(writing), ctypes.byref(written), False))
                finally: K.CloseHandle(write_event)
        result = collect(child, output, log, cmd)
        result.update({'pipe_name': pipe, 'connect_wait': wait, 'served': served,
                       'written': written.value, 'write_error': write_error})
        return result
    finally:
        K.CancelIoEx(server, None)
        K.CloseHandle(event)
        K.CloseHandle(server)
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mpv', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-old', action='store_true')
    args = parser.parse_args()
    args.mpv = args.mpv.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    cwd = args.output / '中文 空格 工作目录'
    cwd.mkdir(exist_ok=True)
    data = wav_data()
    (cwd / '测试 片.wav').write_bytes(data)
    (cwd / 'glob-a.wav').write_bytes(data)
    (cwd / 'glob-b.wav').write_bytes(data)
    payload = {'mode':'paths', 'cwd':str(cwd), 'paths':path_cases(cwd)}
    child, output, log, cmd = launch(args.mpv, args.output, 'paths', payload)
    paths = collect(child, output, log, cmd)
    cases = {'paths': paths}
    for name, media in [('relative-playback','测试 片.wav'),
                        ('drive-relative-playback',str(cwd)[:2] + '测试 片.wav'),
                        ('absolute-playback',str(cwd / '测试 片.wav')),
                        ('wildcard-playlist','glob-*.wav')]:
        child, output, log, cmd = launch(args.mpv, args.output, name, {'mode':'playback','cwd':str(cwd)}, media)
        result = collect(child, output, log, cmd)
        loaded = (result.get('script') or {}).get('loaded', [])
        expected_count = 2 if name == 'wildcard-playlist' else 1
        result['passed'] = (not result['timed_out'] and result['exit_code'] == 0 and
                            len(loaded) == expected_count and all(item.get('channels') == 2 for item in loaded))
        cases[name] = result
    child, output, log, cmd = launch(args.mpv, args.output, 'missing-parent',
        {'mode':'playback','cwd':str(cwd)}, str(cwd / 'does-not-exist' / 'child.wav'))
    missing = collect(child, output, log, cmd)
    missing['passed'] = (not missing['timed_out'] and missing['exit_code'] == 2 and
                         'No such file or directory' in missing['log_text'])
    cases['missing-parent'] = missing
    cases['pipe'] = pipe_case(args.mpv, args.output, cwd, data)
    pipe = cases['pipe']
    loaded = (pipe.get('script') or {}).get('loaded', [])
    pipe['passed'] = (not pipe['timed_out'] and pipe['exit_code'] == 0 and pipe['served'] and
                      len(loaded) == 1 and loaded[0].get('channels') == 2)
    checks = (paths.get('script') or {}).get('checks', [])
    paths['passed'] = (not paths['timed_out'] and paths['exit_code'] == 0 and len(checks) == 18 and
                       all(item['pass'] for item in checks))
    failed_path_checks = [item['name'] for item in checks if not item['pass']]
    if args.expect_old:
        passed = ('stale-PWD-working-directory' in failed_path_checks and 'forward-UNC' in failed_path_checks and
                  not pipe['passed'] and pipe['exit_code'] == 2 and 'Cannot open file' in pipe['log_text'] and
                  missing['exit_code'] == 2 and 'Invalid argument' in missing['log_text'] and
                  cases['absolute-playback']['passed'] and all(
                      cases[name]['exit_code'] == 2 and not cases[name]['passed'] for name in
                      ['relative-playback','drive-relative-playback','wildcard-playlist']))
    else: passed = all(item['passed'] for item in cases.values())
    for case in cases.values(): case.pop('log_text', None)
    report = {'status': ('PASS_WINDOWS_OLD_RED_CONTROL' if args.expect_old else 'PASS_WINDOWS_RUNTIME')
              if passed else 'FAIL_WINDOWS_RUNTIME', 'mpv':str(args.mpv), 'mpv_sha256':sha(args.mpv),
              'expect_old':args.expect_old, 'path_check_count':len(checks), 'failed_path_checks':failed_path_checks,
              'cases':cases, 'scope':'Real CLI/property/normalize-path/WAV decode and local unique named pipe; UNC normalization only, no SMB server claim'}
    (args.output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__': main()
