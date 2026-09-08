"""Decode synthetic Blu-ray PCM after removing only the PMT registration.

No media samples, accounts, disks or audio devices are needed. The fallback is
opt-in and must not replace a different explicit program registration.
"""
import argparse
import array
import hashlib
import json
import subprocess
from pathlib import Path


def crc32_mpeg(data):
    crc = 0xffffffff
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
    return crc.to_bytes(4, 'big')


def alter_pmt(source, target, registration):
    data = bytearray(source.read_bytes())
    changed = 0
    for start in range(0, len(data) - 191, 192):
        packet = data[start + 4:start + 192]
        assert packet[0] == 0x47
        if ((packet[1] & 31) << 8 | packet[2]) != 0x100 or not packet[1] & 64:
            continue
        assert packet[3] & 16
        pos = 4 + (packet[4] + 1 if packet[3] & 32 else 0)
        pos += 1 + packet[pos]
        length = 3 + ((packet[pos + 1] & 15) << 8 | packet[pos + 2])
        section = packet[pos:pos + length]
        assert section[0] == 2 and crc32_mpeg(section) == b'\0' * 4
        size = (section[10] & 15) << 8 | section[11]
        descriptors = section[12:12 + size]
        assert b'\x05\x04HDMV' in descriptors
        descriptors = descriptors.replace(b'\x05\x04HDMV',
            b'\x05\x04' + registration if registration else b'', 1)
        section = section[:12] + descriptors + section[12 + size:-4]
        section[10] = (section[10] & 0xf0) | (len(descriptors) >> 8)
        section[11] = len(descriptors) & 255
        section[1] = (section[1] & 0xf0) | ((len(section) + 1) >> 8)
        section[2] = (len(section) + 1) & 255
        section += crc32_mpeg(section)
        assert pos + len(section) <= 188
        packet[pos:] = section + b'\xff' * (188 - pos - len(section))
        data[start + 4:start + 192] = packet
        changed += 1
    assert changed > 1, 'Synthetic PMT not found'
    target.write_bytes(data)
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--mpv', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    results = []

    def run(label, command, expect=0):
        proc = subprocess.run([str(x) for x in command], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
        text = proc.stdout.decode('utf-8', errors='replace')
        (args.work / (label + '.log')).write_text(text, encoding='utf-8')
        if expect == 0:
            assert proc.returncode == 0, (label, proc.returncode, text[-3000:])
        else:
            assert proc.returncode != 0, label + ': unregistered PCM unexpectedly recognized'
        return text

    for rate, channels in [(48000, 2), (96000, 6)]:
        label = f'{rate}-{channels}'
        valid = args.work / (label + '.m2ts')
        missing = args.work / (label + '-missing.m2ts')
        other = args.work / (label + '-other.m2ts')
        run(label + '-generate', [args.ffmpeg, '-hide_banner', '-f', 'lavfi', '-i',
            'color=c=navy:s=160x90:r=24:d=1', '-f', 'lavfi', '-i',
            f'sine=frequency=997:sample_rate={rate}:duration=1', '-map', '0:v',
            '-map', '1:a', '-c:v', 'mpeg2video', '-c:a', 'pcm_bluray', '-ac', channels,
            '-mpegts_m2ts_mode', '1', '-y', valid])
        alter_pmt(valid, missing, b'')
        alter_pmt(valid, other, b'TEST')
        raw = args.work / (label + '-reference.pcm')
        def decode(name, media, output, force=False, expect=0):
            command = [args.ffmpeg, '-hide_banner']
            if force:
                command += ['-force_hdmv', '1']
            command += ['-i', media, '-map', '0:a:0', '-c:a', 'pcm_s16le',
                '-f', 's16le', '-y', output]
            return run(label + '-' + name, command, expect)
        decode('valid-default', valid, raw)
        samples = array.array('h', raw.read_bytes())
        assert len(samples) >= rate * channels * .9 and max(map(abs, samples)) > 100
        decode('missing-default', missing, args.work / (label + '-absent.pcm'), expect=1)
        if not args.baseline:
            for name, media in [('valid-forced', valid), ('missing-forced', missing)]:
                output = args.work / (label + '-' + name + '.pcm')
                decode(name, media, output, force=True)
                assert output.read_bytes() == raw.read_bytes(), name + ': decoded audio changed'
            decode('explicit-other', other, args.work / (label + '-other.pcm'), force=True, expect=1)
            if args.mpv:
                # Exercise the linked lavf in each player, not just ffmpeg.exe.
                output = args.work / (label + '-mpv.wav')
                log = run(label + '-mpv', [args.mpv, '--no-config', '--load-scripts=no',
                    '--vo=null', '--ao=pcm', '--ao-pcm-file=' + str(output),
                    '--media-controls=no', '--demuxer-lavf-o=force_hdmv=1', missing])
                assert 'pcm_bluray' in log and output.stat().st_size > 90000
        results.append({'rate': rate, 'channels': channels, 'samples': len(samples),
            'pcm_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
            'result': 'BASELINE_REPRODUCED' if args.baseline else 'PASS'})
    (args.work / 'result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
