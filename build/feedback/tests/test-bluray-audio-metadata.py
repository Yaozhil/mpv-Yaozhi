"""Compile the production metadata query and demux fill against tiny stubs.

This tests source functions directly without needing the complete Windows mpv
toolchain. --include must contain the real libbluray/bluray.h.
"""
import argparse
import json
import pathlib
import subprocess


def function(source, name):
    start = source.index("static void " + name + "(")
    opening = source.index("{", start)
    depth = 1
    closing = opening + 1
    while depth:
        depth += (source[closing] == "{") - (source[closing] == "}")
        closing += 1
    return source[start:closing]


parser = argparse.ArgumentParser()
parser.add_argument("--compiler", required=True)
parser.add_argument("--source", required=True, type=pathlib.Path)
parser.add_argument("--include", required=True, type=pathlib.Path)
parser.add_argument("--output", required=True, type=pathlib.Path)
args = parser.parse_args()
stream = (args.source / "stream/stream_bluray.c").read_text(encoding="utf-8")
demux = (args.source / "demux/demux_disc.c").read_text(encoding="utf-8")
query = stream[stream.index("    case STREAM_CTRL_GET_BD_AUDIO_RATE: {"):
               stream.index("    case STREAM_CTRL_GET_LANG: {")]
fill = function(demux, "get_bd_audio_rate")
harness = r'''
#include <assert.h>
#include <stdio.h>
#include "stream/bluray_audio_rate.h"
#define STREAM_CTRL_GET_BD_AUDIO_RATE 1
#define STREAM_OK 1
#define STREAM_UNSUPPORTED -1
#define STREAM_AUDIO 1
#define STREAM_VIDEO 2
#define MP_VERBOSE(...) ((void)0)
struct stream_bd_audio_rate_req {
    int id;
    const char *codec;
    int samplerate;
};
struct bluray_priv_s {
    BLURAY_TITLE_INFO *title_info;
    int current_playitem;
    int overlay_lock;
};
static void mp_mutex_lock(int *p) { (void)p; }
static void mp_mutex_unlock(int *p) { (void)p; }
static int query_rate(struct bluray_priv_s *b, int command, void *arg)
{
    switch (command) {
QUERY
    default: return STREAM_UNSUPPORTED;
    }
}
struct stream { struct bluray_priv_s *b; };
struct priv { bool is_bd; };
struct mp_codec_params { int samplerate; const char *codec; };
struct sh_stream {
    int type, demuxer_id;
    struct mp_codec_params *codec;
};
struct demuxer { struct priv *priv; struct stream *stream; };
static int queries;
static int stream_control(struct stream *s, int command, void *arg)
{
    queries++;
    return query_rate(s->b, command, arg);
}
FILL
static void expect(struct demuxer *d, struct sh_stream *sh, int expected)
{
    get_bd_audio_rate(d, sh);
    assert(sh->codec->samplerate == expected);
}
int main(void)
{
    BLURAY_STREAM_INFO primary0[] = {
        {.pid=0x1100, .coding_type=0x86, .rate=4},
        {.pid=0x1101, .coding_type=0x81, .rate=1},
    };
    BLURAY_STREAM_INFO primary1[] = {
        {.pid=0x1100, .coding_type=0x86, .rate=1},
    };
    BLURAY_STREAM_INFO secondary[] = {
        {.pid=0x1a00, .coding_type=0xa2, .rate=14},
    };
    BLURAY_CLIP_INFO clips[] = {
        {.audio_stream_count=2, .audio_streams=primary0,
         .sec_audio_stream_count=1, .sec_audio_streams=secondary},
        {.audio_stream_count=1, .audio_streams=primary1},
    };
    BLURAY_TITLE_INFO ti = {.clip_count=2, .clips=clips};
    struct bluray_priv_s b = {.title_info=&ti};
    struct stream s = {.b=&b};
    struct priv p = {.is_bd=true};
    struct demuxer d = {.priv=&p, .stream=&s};
    struct mp_codec_params codec = {.codec="dts"};
    struct sh_stream sh = {.type=STREAM_AUDIO, .demuxer_id=0x1100,
                           .codec=&codec};
    expect(&d, &sh, 96000); // missing rate filled before decoder creation
    codec.samplerate=44100;
    int before=queries;
    expect(&d, &sh, 44100); assert(queries==before); // probed rate wins
    codec.samplerate=0; p.is_bd=false;
    expect(&d, &sh, 0); assert(queries==before); // ordinary media untouched
    p.is_bd=true; sh.type=STREAM_VIDEO;
    expect(&d, &sh, 0); assert(queries==before); // audio only
    sh.type=STREAM_AUDIO; b.current_playitem=1;
    expect(&d, &sh, 48000); // current clip, not first playlist clip
    codec.samplerate=0; b.current_playitem=-1;
    expect(&d, &sh, 0); // unavailable clip keeps unknown-rate fallback
    b.current_playitem=2;
    expect(&d, &sh, 0); // invalid clip cannot read beyond title_info
    b.current_playitem=0; sh.demuxer_id=0x1101;
    expect(&d, &sh, 0); // unrelated PID/codec combination must not be used
    codec.codec="ac3";
    expect(&d, &sh, 48000); // same PID resolves only matching codec
    codec.samplerate=0; codec.codec="dts"; sh.demuxer_id=0x1a00;
    expect(&d, &sh, 96000); // secondary presentation metadata
    codec.samplerate=0; sh.demuxer_id=0x9999;
    expect(&d, &sh, 0); // no matching PID
    sh.codec=NULL; before=queries;
    get_bd_audio_rate(&d, &sh); assert(queries==before); // absent parameters
    sh.codec=&codec; b.title_info=NULL;
    expect(&d, &sh, 0); // navigator metadata not available yet
    printf("BLURAY_AUDIO_METADATA_PASS 13 cases\n");
    return 0;
}
'''.replace("QUERY", query).replace("FILL", fill)
args.output.mkdir(parents=True, exist_ok=True)
test = args.output / "test-bluray-audio-metadata.c"
exe = args.output / "test-bluray-audio-metadata.exe"
test.write_text(harness, encoding="utf-8")
command = [args.compiler, "-std=c11", "-Wall", "-Werror",
           "-I" + str(args.source), "-I" + str(args.include), str(test),
           "-o", str(exe)]
compile_result = subprocess.run(command, capture_output=True, text=True)
assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
run = subprocess.run([str(exe)], capture_output=True, text=True)
assert run.returncode == 0, run.stdout + run.stderr
report = {"result": "PASS", "cases": 13, "stdout": run.stdout,
          "compiler": args.compiler, "tests_production_functions": True}
(args.output / "metadata-unit-test.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(run.stdout, end="")
