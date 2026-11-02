#!/usr/bin/env python3
"""Bounded loopback HTTP contracts against a real mpv executable.

The stream-dump cases compare the bytes delivered by mpv's actual curl stream,
without using a demuxer to hide truncated/repeated transfers. All URLs are local.
Run once with the installed baseline (--role old), then each candidate (--role new).
No user configuration, sound device, player instance, or remote service is used.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.parse

PAYLOAD = bytes((i * 73 + (i // 251) * 19) % 256 for i in range(32835))
BLOCK = 4096


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.records = []
        self.lock = threading.Lock()
        self.stopping = threading.Event()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        key = urllib.parse.urlsplit(self.path).path.strip("/")
        mode = key.split("/")[-1]
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        start = int(match[1]) if match else 0
        requested_end = int(match[2]) if match and match[2] else len(PAYLOAD) - 1
        with self.server.lock:
            count = sum(r["key"] == key for r in self.server.records) + 1
            rec = dict(key=key, count=count, range=self.headers.get("Range"),
                       start=start, requested_end=requested_end,
                       monotonic=time.monotonic())
            self.server.records.append(rec)
        # Protect both the server and a defective old client from infinite loops.
        if count > 24:
            # Deliberately incomplete response makes the old client's existing
            # retry budget stop too; a successful empty response would loop.
            return self.reply(rec, 500, b"", declared_length=1)
        if mode == "redirect":
            return self.reply(rec, 302, b"", Location="/" + key.rsplit("/", 1)[0] + "/known-short")
        if mode in ("empty-416", "empty-416-unspecified"):
            extra = {"Content-Range": "bytes */0"} if mode == "empty-416" else {}
            return self.reply(rec, 416, b"", **extra)
        if mode == "empty-200":
            return self.reply(rec, 200, b"", **{"Accept-Ranges": "bytes"})
        if mode == "initial-error":
            return self.reply(rec, 403, b"ERROR BODY MUST NOT BE DATA")
        if mode == "cancel":
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            rec.update(status=206, body_bytes=0, deliberately_stalled=True)
            try:
                # A short first chunk lets stream_dump enter its input loop.
                self.wfile.write(PAYLOAD[:4096])
                self.wfile.flush()
                rec["body_bytes"] = 4096
                self.server.stopping.wait(6)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        if mode == "plain-200":
            return self.reply(rec, 200, PAYLOAD)
        if mode == "ignore-followup" and start > 0:
            return self.reply(rec, 200, PAYLOAD, **{"Accept-Ranges": "bytes"})
        if mode == "wrong-followup" and start > 0:
            return self.reply(rec, 206, PAYLOAD[:BLOCK], **{
                "Content-Range": f"bytes 0-{BLOCK-1}/{len(PAYLOAD)}", "Accept-Ranges": "bytes"})
        if mode == "error-followup" and start > 0:
            return self.reply(rec, 403, b"ERROR BODY MUST NOT BE DATA")
        if mode == "contradictory-416" and start > 0:
            return self.reply(rec, 416, b"ERROR BODY MUST NOT BE DATA", **{
                "Content-Range": f"bytes */{len(PAYLOAD)}"})
        if mode == "zero-data":
            return self.reply(rec, 206, b"", **{
                "Content-Range": f"bytes {start}-{min(start+BLOCK-1,len(PAYLOAD)-1)}/{len(PAYLOAD)}",
                "Accept-Ranges": "bytes"})
        if start >= len(PAYLOAD):
            return self.reply(rec, 416, b"", **{"Content-Range": f"bytes */{len(PAYLOAD)}"})
        end = min(requested_end, len(PAYLOAD)-1)
        if mode != "known-full":
            end = min(end, start+BLOCK-1)
        body = PAYLOAD[start:end+1]
        total = "*" if mode in ("unknown-short", "contradictory-416") else str(len(PAYLOAD))
        if mode == "retry-partial" and count == 1:
            # Advertise a larger response, then disconnect. Both versions must
            # resume at the first missing byte instead of duplicating the prefix.
            return self.reply(rec, 206, body[:1024], declared_length=len(body), **{
                "Content-Range": f"bytes {start}-{end}/{total}", "Accept-Ranges": "bytes"})
        return self.reply(rec, 206, body, **{
            "Content-Range": f"bytes {start}-{end}/{total}", "Accept-Ranges": "bytes"})

    def reply(self, rec, status, body, declared_length=None, **headers):
        rec.update(status=status, body_bytes=len(body), headers=headers)
        self.send_response(status)
        self.send_header("Content-Length", str(len(body) if declared_length is None else declared_length))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Connection", "close")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        self.close_connection = True


CASES = [
    # name, server mode, request cap (0=unbounded), expected delivered bytes,
    # required log fragment, exact request count or None.
    ("known-full", "known-full", 0, PAYLOAD, None, 1),
    ("known-short", "known-short", 0, PAYLOAD, None, 9),
    ("known-capped", "known-short", BLOCK, PAYLOAD, None, 9),
    ("unknown-short", "unknown-short", 0, PAYLOAD, None, 10),
    ("unknown-capped", "unknown-short", BLOCK, PAYLOAD, None, 10),
    ("zero-data", "zero-data", BLOCK, b"", "Server sent back no data at offset 0", 1),
    ("contradictory-416", "contradictory-416", BLOCK, PAYLOAD[:BLOCK], "HTTP error 416", 2),
    ("initial-empty-416", "empty-416", 0, b"", None, 1),
    ("initial-empty-416-unspecified", "empty-416-unspecified", 0, b"", None, 1),
    ("initial-empty-200", "empty-200", BLOCK, b"", None, 1),
    ("plain-200", "plain-200", 0, PAYLOAD, None, 1),
    ("ignore-followup", "ignore-followup", BLOCK, PAYLOAD[:BLOCK], "unexpected reply with offset 0", 2),
    ("wrong-followup", "wrong-followup", BLOCK, PAYLOAD[:BLOCK], "unexpected reply with offset 0", 2),
    ("error-followup", "error-followup", BLOCK, PAYLOAD[:BLOCK], "HTTP error 403", 2),
    ("retry-partial", "retry-partial", BLOCK, PAYLOAD, "retrying (#1) from 1024", None),
    ("redirect", "redirect", 0, PAYLOAD, None, None),
    ("initial-error", "initial-error", 0, None, "HTTP error 403", 1),
    ("cancel", "cancel", 0, None, None, 1),
]


def run_case(exe, out, server, item):
    name, mode, cap, expected, log_fragment, exact_requests = item
    target = out / name
    target.mkdir()
    log = target / "mpv.log"
    dump = target / "dump.bin"
    key = name + "/" + mode
    url = f"http://127.0.0.1:{server.server_port}/{key}"
    cmd = [str(exe), "--no-config", "--load-scripts=no", "--osc=no", "--ytdl=no",
           "--vo=null", "--ao=null", "--input-terminal=no", "--terminal=yes",
           "--idle=no", "--curl-enabled=yes",
           "--curl-http-version=1.1", "--curl-connect-timeout=2", "--curl-max-retries=2",
           "--network-timeout=3", "--curl-max-request-size=" + str(cap),
           "--msg-level=all=warn,curl=trace", "--log-file=" + str(log)]
    if name == "cancel":
        # Cancellation is a normal asynchronous demux/playback contract. The
        # stream-dump command itself reads synchronously on mpv's core thread.
        script = target / "quit.lua"
        script.write_text('mp.add_timeout(0.35, function() mp.commandv("quit") end)\n', encoding="utf-8")
        cmd += ["--demuxer=rawaudio", "--demuxer-rawaudio-format=s16le",
                "--demuxer-rawaudio-rate=48000", "--demuxer-rawaudio-channels=stereo",
                "--script=" + str(script)]
    else:
        cmd += ["--stream-dump=" + str(dump)]
    cmd.append(url)
    started = time.monotonic()
    timed_out = False
    env = os.environ.copy()
    # Do not let a workstation HTTP proxy send the local fixture elsewhere.
    env.update(NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    with (target / "console.log").open("wb") as console:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=console,
                                stderr=subprocess.STDOUT, env=env)
        pid = proc.pid
        try:
            proc.wait(timeout=4 if name == "cancel" else 6)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()  # Only the Popen process owned by this case.
            proc.wait(timeout=3)
        finally:
            proc.stdin.close()
    elapsed = time.monotonic() - started
    with server.lock:
        records = [dict(r) for r in server.records if r["key"].startswith(name + "/")]
    data = dump.read_bytes() if dump.exists() else None
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    checks = {"bounded_completion": not timed_out,
              "request_bound": len(records) <= 24,
              "used_real_curl": "proto=http" in text or name == "cancel"}
    if expected is not None:
        checks["byte_exact"] = data == expected
    if log_fragment:
        checks["expected_diagnostic"] = log_fragment in text
    if exact_requests is not None:
        checks["exact_request_count"] = len(records) == exact_requests
    if name.startswith("initial-empty"):
        checks["stream_opened_successfully"] = dump.exists() and "Failed to open" not in text
    if name in ("unknown-short", "unknown-capped"):
        checks["terminal_416"] = bool(records and records[-1].get("status") == 416)
        checks["416_is_eof"] = "HTTP error 416" not in text
    if name in ("ignore-followup", "wrong-followup", "error-followup", "contradictory-416"):
        checks["error_body_dropped"] = data == PAYLOAD[:BLOCK]
    if name == "redirect":
        checks["redirect_followed"] = any(r.get("status") == 302 for r in records)
        checks["complete_after_redirect"] = len(records) == 18
    if name == "initial-error":
        checks["error_body_dropped"] = data in (None, b"")
    if name == "cancel":
        checks["cancellation_completed"] = not timed_out and elapsed < 4
        checks["normal_quit_processed"] = "Run command: quit" in text
    record = dict(name=name, pass_=all(checks.values()), checks=checks,
                  command=cmd, pid=pid, child_exited=proc.poll() is not None,
                  exit_code=proc.returncode, seconds=elapsed, timeout=timed_out,
                  dump_exists=dump.exists(), output_bytes=len(data) if data is not None else None,
                  output_sha256=sha(data) if data is not None else None,
                  expected_sha256=sha(expected) if expected is not None else None,
                  request_count=len(records), requests=records)
    (target / "case.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name}: {'PASS' if record['pass_'] else 'FAIL'} ({len(records)} requests, {elapsed:.3f}s)", flush=True)
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mpv", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--role", choices=("old", "new"), required=True)
    args = ap.parse_args()
    exe = args.mpv.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=False)
    identity = dict(path=str(exe), size=exe.stat().st_size, sha256=sha(exe.read_bytes()))
    server = Server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        records = [run_case(exe, args.out, server, case) for case in CASES]
    finally:
        server.stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    unchanged = identity["sha256"] == sha(exe.read_bytes())
    passed = sum(r["pass_"] for r in records)
    failed = [r["name"] for r in records if not r["pass_"]]
    old_red = bool(set(failed) & {"known-short", "unknown-short", "zero-data", "initial-empty-416"})
    ok = unchanged and (passed == len(records) if args.role == "new" else old_red)
    summary = dict(status="PASS_HTTP_RANGE_RUNTIME" if args.role == "new" and ok else
                   "PASS_OLD_HTTP_DEFECTS_REPRODUCED" if ok else "FAIL_HTTP_RANGE_RUNTIME",
                   role=args.role, binary=identity, binary_unchanged=unchanged,
                   fixture_sha256=sha(Path(__file__).read_bytes()),
                   payload_bytes=len(PAYLOAD), payload_sha256=sha(PAYLOAD),
                   passed=passed, total=len(records), failed=failed, cases=records,
                   server_closed=not thread.is_alive(),
                   scope="real mpv curl stream I/O and cancellation; no public network or physical playback")
    (args.out / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary["status"], flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
