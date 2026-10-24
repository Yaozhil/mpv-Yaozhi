#!/usr/bin/env python3
"""Real WAV decode and HTTP seek with independent sample-exact PCM oracles."""
import argparse
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import threading
import time
import wave

RATE = 48000
PCM = b"".join(struct.pack("<hh", ((i * 97) % 50001) - 25000,
                         ((i * 139 + 999) % 50001) - 25000) for i in range(RATE * 2))
with io.BytesIO() as raw:
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(PCM)
    MEDIA = raw.getvalue()
BLOCK = 32768


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.records = []
        self.lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        mode = self.path.strip("/")
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        start = int(match[1]) if match else 0
        end = int(match[2]) if match and match[2] else len(MEDIA)-1
        with self.server.lock:
            records = self.server.records
            count = sum(r["mode"] == mode for r in records)+1
            rec = dict(mode=mode, count=count, start=start, range=self.headers.get("Range"))
            records.append(rec)
        if count > 64:
            status, body, range_header = 503, b"", None
        elif start >= len(MEDIA):
            status, body, range_header = 416, b"", f"bytes */{len(MEDIA)}"
        else:
            if "short" in mode:
                end = min(end, start+BLOCK-1)
            end = min(end, len(MEDIA)-1)
            status, body = 206, MEDIA[start:end+1]
            total = "*" if "unknown" in mode else str(len(MEDIA))
            range_header = f"bytes {start}-{end}/{total}"
        rec.update(status=status, body_bytes=len(body), content_range=range_header)
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Connection", "close")
        if range_header:
            self.send_header("Content-Range", range_header)
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        self.close_connection = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mpv", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--role", choices=("old", "new"), required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    exe = a.mpv.resolve(strict=True)
    binary_sha = sha(exe.read_bytes())
    (a.out/"fixture.wav").write_bytes(MEDIA)
    (a.out/"oracle-full.s16le").write_bytes(PCM)
    (a.out/"oracle-seek.s16le").write_bytes(PCM[RATE*4*3//2:])
    server = Server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for name in ("known-full", "known-short", "unknown-short", "seek-known-full",
                     "seek-known-short", "seek-unknown-short"):
            target = a.out/name
            target.mkdir()
            output, log = target/"actual.s16le", target/"mpv.log"
            seek = name.startswith("seek-")
            oracle = PCM[RATE*4*3//2:] if seek else PCM
            cmd = [str(exe), "--no-config", "--load-scripts=no", "--osc=no", "--ytdl=no",
                   "--vo=null", "--video=no", "--audio-display=no", "--input-terminal=no",
                   "--cache=no", "--gapless-audio=no", "--demuxer-seekable-cache=no",
                   "--curl-enabled=yes", "--curl-http-version=1.1", "--curl-connect-timeout=2",
                   "--curl-max-retries=1", "--curl-buffer-size=32768", "--stream-buffer-size=32768",
                   "--ao=pcm", "--ao-pcm-waveheader=no", "--ao-pcm-file="+str(output),
                   "--audio-format=s16", "--audio-samplerate=48000", "--audio-channels=stereo",
                   "--volume=100", "--volume-max=100", "--msg-level=all=warn,curl=trace",
                   "--log-file="+str(log)]
            if seek:
                cmd += ["--start=1.5", "--hr-seek=yes"]
            cmd += ["--", f"http://127.0.0.1:{server.server_port}/{name}"]
            began = time.monotonic()
            stop_reason = None
            env = os.environ.copy()
            env.update(NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
            with (target/"console.log").open("wb") as console:
                proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=console,
                                        stderr=subprocess.STDOUT, env=env)
                while proc.poll() is None:
                    if time.monotonic()-began > 8:
                        stop_reason = "8s deadline"
                    if log.exists() and log.stat().st_size > 2*1024*1024:
                        stop_reason = "2MiB log bound"
                    if output.exists() and output.stat().st_size > len(PCM)*2:
                        stop_reason = "PCM output bound"
                    if stop_reason:
                        proc.kill()  # Only the Popen child belonging to this case.
                        proc.wait(timeout=3)
                        break
                    time.sleep(0.02)
            data = output.read_bytes() if output.exists() else b""
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            with server.lock:
                requests = [dict(r) for r in server.records if r["mode"] == name]
            checks = dict(child_exited=proc.poll() is not None, bounded_completion=stop_reason is None,
                          successful_exit=proc.returncode == 0, byte_exact=data == oracle,
                          real_curl="proto=http" in text, request_bound=len(requests) <= 64,
                          actual_pcm_decoder="pcm_s16le" in text,
                          actual_pcm_output="AO: [pcm] 48000Hz stereo 2ch s16" in text)
            if seek:
                # lavf can request a small preroll before the exact target;
                # the independent suffix oracle verifies sample-accurate trim.
                seek_requests = [r for r in requests if 44+RATE*4 < r["start"] <= 44+RATE*4*3//2]
                checks["real_http_seek_range"] = bool(seek_requests)
                checks["real_stream_seek"] = any(
                    "[curl] seeking to "+str(r["start"]) in text for r in seek_requests)
            record = dict(name=name, passed=all(checks.values()), checks=checks,
                          command=cmd, pid=proc.pid, exit_code=proc.returncode,
                          seconds=time.monotonic()-began, stop_reason=stop_reason,
                          actual_bytes=len(data), expected_bytes=len(oracle),
                          actual_sha256=sha(data), expected_sha256=sha(oracle),
                          requests=requests)
            (target/"case.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(record)
            print(name, "PASS" if record["passed"] else "FAIL", len(data), len(oracle),
                  "requests", len(requests), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    passed = sum(r["passed"] for r in results)
    unchanged = binary_sha == sha(exe.read_bytes())
    # The old-control full response and HTTP seek must remain valid; genuine
    # short-response truncation is the red control, not an oracle failure.
    controls = all(r["passed"] for r in results if r["name"] in ("known-full", "seek-known-full"))
    red = any(not r["checks"]["byte_exact"] for r in results if r["name"] in ("known-short", "unknown-short"))
    ok = unchanged and (passed == len(results) if a.role == "new" else controls and red)
    report = dict(status="PASS_HTTP_DECODE_AND_SEEK_PCM" if a.role == "new" and ok else
                  "PASS_OLD_HTTP_PLAYBACK_TRUNCATION_REPRODUCED" if ok else "FAIL_HTTP_DECODE_AND_SEEK_PCM",
                  role=a.role, binary=dict(path=str(exe), sha256=binary_sha, size=exe.stat().st_size),
                  binary_unchanged=unchanged, fixture_sha256=sha(Path(__file__).read_bytes()),
                  media_sha256=sha(MEDIA), pcm_sha256=sha(PCM), passed=passed, total=len(results),
                  cases=results, server_closed=not thread.is_alive(),
                  scope="real HTTP WAV decode/seek to byte-exact PCM; no physical audio device")
    (a.out/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["status"], flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
