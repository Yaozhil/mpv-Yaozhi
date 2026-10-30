#!/usr/bin/env python3
"""Exercise actual mpv fallback/probe functions with deterministic C stubs.

The C under test is extracted from --source, never a rewritten state model.
No media, display, GPU, decoder, or network access is used by this test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def function(text, name):
    match = re.search(r"^static [^;\n]+\b" + re.escape(name) +
                      r"\([^;]*?\)\s*\{", text, re.M)
    if not match:
        raise RuntimeError(f"Missing actual function: {name}")
    start = match.start()
    pos = text.index("{", match.start())
    depth = 0
    state = "code"
    while pos < len(text):
        c, pair = text[pos], text[pos:pos + 2]
        if state == "line":
            if c == "\n":
                state = "code"
        elif state == "comment":
            if pair == "*/":
                state = "code"
                pos += 1
        elif state in ('"', "'"):
            if c == "\\":
                pos += 1
            elif c == state:
                state = "code"
        elif pair == "//":
            state = "line"
            pos += 1
        elif pair == "/*":
            state = "comment"
            pos += 1
        elif c in ('"', "'"):
            state = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
        pos += 1
    raise RuntimeError(f"Unbalanced function: {name}")


COMMON = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MPMIN(a,b) ((a) < (b) ? (a) : (b))
#define MP_HANDLE_OOM(p) assert(p)
#define mp_assert assert
#define MP_VERBOSE(...) ((void)0)
#define MP_TRACE(...) ((void)0)
#define MP_ERR(...) (++errors)
#define AVERROR(x) (-(x))
#define AVERROR_EOF (-100)
#define AVERROR_EXIT (-101)
#define EAGAIN 11
#define MSGL_WARN 1
#define MSGL_V 2
static int errors;
#define TA_FREEP(p) do { talloc_free(*(p)); *(p) = NULL; } while(0)
#define MP_TARRAY_APPEND(parent,array,num,item) do { \
    (array) = realloc((array), ((num) + 1) * sizeof(*(array))); \
    assert(array); (array)[(num)++] = (item); \
} while(0)
'''

FALLBACK = r'''
typedef struct { const char *start; int len; } bstr;
#define BSTR_P(b) (b).len, (b).start
struct demux_packet { int id, freed; };
struct mp_frame { int unused; };
typedef struct { int has_b_frames; } AVCodecContext;
struct hwdec_info { char method_name[24]; };
typedef struct lavc_ctx {
    AVCodecContext *avctx;
    bool use_hwdec, hwdec_failed, hwdec_notified, force_eof;
    int num_sent_packets, num_requeue_packets, num_attempted_hwdecs;
    int wait_for_keyframe, framedrop_flags, extra_hw_frames_hint;
    struct hwdec_info hwdec;
    bstr *attempted_hwdecs;
    struct demux_packet **sent_packets, **requeue_packets;
} vd_ffmpeg_ctx;
struct mp_filter { vd_ffmpeg_ctx *priv; void *log; };
#define HWDEC_WAIT_KEYFRAME_COUNT 96
enum dec_ctrl { VDCTRL_SET_FRAMEDROP, VDCTRL_SET_EXTRA_HW_FRAMES,
    VDCTRL_CHECK_FORCED_EOF, VDCTRL_GET_BFRAMES, VDCTRL_GET_HWDEC,
    VDCTRL_FORCE_HWDEC_FALLBACK, VDCTRL_REINIT };
enum { CONTROL_OK=1, CONTROL_TRUE=1, CONTROL_FALSE=0,
       CONTROL_ERROR=-1, CONTROL_UNKNOWN=-2 };
static AVCodecContext context;
static struct demux_packet packets[8];
static int init_calls, selections, next_method, current_method, script_len;
static struct method { bool hw; enum init_avctx_result result; } script[8];
static void talloc_free(void *ptr)
{
    if (!ptr) return;
    for (unsigned n=0; n<sizeof(packets)/sizeof(packets[0]); n++) {
        if (ptr == &packets[n]) { assert(!packets[n].freed); packets[n].freed++; return; }
    }
    free(ptr);
}
static void mp_msg(void *log, int level, const char *fmt, ...) {}
static void uninit_avctx(struct mp_filter *vd)
{
    vd_ffmpeg_ctx *ctx=vd->priv;
    for (int n=0; n<ctx->num_sent_packets; n++) talloc_free(ctx->sent_packets[n]);
    for (int n=0; n<ctx->num_requeue_packets; n++) talloc_free(ctx->requeue_packets[n]);
    ctx->num_sent_packets=ctx->num_requeue_packets=0;
    ctx->avctx=NULL; ctx->use_hwdec=false; ctx->hwdec_failed=false;
}
static void select_and_set_hwdec(struct mp_filter *vd)
{
    assert(next_method < script_len);
    current_method=next_method++;
    selections++;
    vd_ffmpeg_ctx *ctx=vd->priv;
    ctx->use_hwdec=script[current_method].hw;
    if (ctx->use_hwdec) {
        bstr name={"mock-hw",7};
        MP_TARRAY_APPEND(ctx,ctx->attempted_hwdecs,ctx->num_attempted_hwdecs,name);
    }
}
static enum init_avctx_result init_avctx(struct mp_filter *vd)
{
    init_calls++;
    assert(init_calls <= 8);
    enum init_avctx_result ret=script[current_method].result;
    assert((ret != INIT_AVCTX_HWDEC_FAILED) || vd->priv->use_hwdec);
    if (ret == INIT_AVCTX_OK) vd->priv->avctx=&context;
    else uninit_avctx(vd);
    return ret;
}
static int decode_frame(struct mp_filter *vd) { return -202; }
'''

FALLBACK_TESTS = r'''
static vd_ffmpeg_ctx ctx;
static struct mp_filter filter={&ctx,NULL};
static void setup(const struct method *methods, int count)
{
    uninit_avctx(&filter);
    talloc_free(ctx.sent_packets); talloc_free(ctx.requeue_packets);
    talloc_free(ctx.attempted_hwdecs);
    memset(&ctx,0,sizeof(ctx)); memset(packets,0,sizeof(packets));
    if (count) {
        memcpy(script, methods, count * sizeof(*methods));
    }
    script_len = count;
    next_method=current_method=init_calls=selections=errors=0;
}
static void runtime_packets(void)
{
    bstr label={"previous-hw",11};
    MP_TARRAY_APPEND(&ctx,ctx.attempted_hwdecs,ctx.num_attempted_hwdecs,label);
    ctx.avctx=&context; ctx.use_hwdec=true; ctx.hwdec_failed=true;
    MP_TARRAY_APPEND(&ctx,ctx.sent_packets,ctx.num_sent_packets,&packets[0]);
    MP_TARRAY_APPEND(&ctx,ctx.sent_packets,ctx.num_sent_packets,&packets[1]);
    MP_TARRAY_APPEND(&ctx,ctx.requeue_packets,ctx.num_requeue_packets,&packets[2]);
    MP_TARRAY_APPEND(&ctx,ctx.requeue_packets,ctx.num_requeue_packets,&packets[3]);
}
int main(void)
{
    struct method hw_soft[]={{true,INIT_AVCTX_HWDEC_FAILED},{false,INIT_AVCTX_OK}};
    setup(hw_soft,2); reinit(&filter);
    assert(ctx.avctx && !ctx.use_hwdec && init_calls==2 && selections==2);
    struct method multi[]={{true,INIT_AVCTX_HWDEC_FAILED},{true,INIT_AVCTX_HWDEC_FAILED},
                          {true,INIT_AVCTX_HWDEC_FAILED},{false,INIT_AVCTX_OK}};
    setup(multi,4); reinit(&filter);
    assert(ctx.avctx && init_calls==4 && selections==4);
    struct method fail[]={{true,INIT_AVCTX_HWDEC_FAILED},{true,INIT_AVCTX_HWDEC_FAILED},
                         {false,INIT_AVCTX_FAILED}};
    setup(fail,3); reinit(&filter);
    assert(!ctx.avctx && init_calls==3 && selections==3);
    struct method swfail[]={{false,INIT_AVCTX_FAILED}};
    setup(swfail,1); reinit(&filter);
    assert(!ctx.avctx && init_calls==1 && selections==1);
    setup(hw_soft,2); runtime_packets(); struct mp_frame out={0};
    assert(receive_frame(&filter,&out)==0);
    assert(ctx.avctx && ctx.num_requeue_packets==4 && init_calls==2);
    for(int n=0;n<4;n++) assert(ctx.requeue_packets[n]==&packets[n] && !packets[n].freed);
    uninit_avctx(&filter);
    for(int n=0;n<4;n++) assert(packets[n].freed==1);
    setup(fail,3); runtime_packets();
    assert(receive_frame(&filter,&out)==AVERROR_EOF);
    assert(!ctx.avctx && !ctx.num_requeue_packets && !ctx.num_sent_packets && errors==1);
    for(int n=0;n<4;n++) assert(packets[n].freed==1);
    // A subsequent receive cannot reenter fallback or allocate/release packets.
    assert(receive_frame(&filter,&out)==-202 && init_calls==3);
    setup(hw_soft,2); runtime_packets();
    assert(control(&filter,VDCTRL_FORCE_HWDEC_FALLBACK,NULL)==CONTROL_ERROR);
    assert(init_calls==1 && selections==1 && !ctx.avctx);
    for(int n=0;n<4;n++) assert(packets[n].freed==1);
    setup(NULL,0);
    puts("PASS fallback: initial finite success/failure; runtime replay ownership; forced single attempt");
    return 0;
}
'''

PROBE = r'''
#define AVMEDIA_TYPE_UNKNOWN (-1)
#define AVMEDIA_TYPE_VIDEO 0
#define AVMEDIA_TYPE_AUDIO 1
#define AVMEDIA_TYPE_DATA 2
#define AV_CODEC_ID_NONE 0
#define AV_CODEC_ID_VC1 1
#define AV_CODEC_ID_AC3 2
#define AV_CODEC_ID_MP3 3
#define AV_TIME_BASE 1000000
#define AVFMT_FLAG_NOBUFFER 64
enum AVDiscard { AVDISCARD_DEFAULT=0, AVDISCARD_ALL=48 };
#define DISC_VC1_PROBE_BYTES (8 * 1024 * 1024)
#define DISC_VC1_PROBE_SECONDS 5
#define STREAM_CTRL_GET_NAV_STATE 1
typedef struct AVCodecParameters {
    int codec_type,codec_id,width,height,extradata_size,profile,level,format;
    uint8_t *extradata;
} AVCodecParameters;
typedef struct { AVCodecParameters *codecpar; int disposition,id; enum AVDiscard discard; } AVStream;
typedef struct { int error,eof_reached; } AVIOContext;
typedef struct {
    unsigned nb_streams; AVStream **streams; int64_t probesize,max_analyze_duration;
    int skip_estimate_duration_from_pts,flags;
} AVFormatContext;
struct stream_info { const char *name; };
struct stream { struct stream_info *info; int eof; int64_t pos; };
struct stream_nav_state { int playlist; };
struct demux_lavf_opts { int probeinfo; };
typedef struct lavf_priv {
    struct stream *stream; struct demux_lavf_opts *opts; AVFormatContext *avfc;
    AVIOContext *pb; bool disc_vc1_probing,disc_vc1_probe_limited,disc_vc1_probe_read_eof;
    int64_t disc_vc1_probe_bytes_left,disc_vc1_probe_deadline;
} lavf_priv_t;
struct demuxer_params { bool skip_lavf_probing; };
typedef struct demuxer { lavf_priv_t *priv; struct demuxer_params *params; bool canceled; } demuxer_t;
static int64_t now;
static int read_eof,read_calls,max_request,copy_fail,known_audio_packets;
static int64_t read_bytes;
static int behavior;
static uint8_t headers[18]={0,0,1,15,1,2,3,4,5,6,7,8,0,0,1,14,1,2};
static void talloc_free(void *p) { free(p); }
#define talloc_zero_array(parent,type,num) ((type *)calloc((num),sizeof(type)))
static int64_t mp_time_ns(void) { return now; }
static int64_t mp_time_ns_add(int64_t n,double seconds) { return n+(int64_t)(seconds*1000000000); }
static bool demux_read_interrupted(struct demuxer *d) { return d->canceled; }
static bool matches_avinputformat_name(lavf_priv_t *p,const char *s) { return behavior!=9; }
static int stream_control(struct stream *s,int cmd,struct stream_nav_state *nav) { nav->playlist=12; return 1; }
static int stream_read_partial(struct stream *s,uint8_t *buf,int size)
{
    read_calls++; if(size>max_request) max_request=size;
    if(read_eof) { s->eof=1; return 0; }
    read_bytes+=size; s->pos+=size; return size;
}
static AVCodecParameters *allocated_params[128];
static int num_allocated_params;
static AVCodecParameters *avcodec_parameters_alloc(void)
{
    assert(num_allocated_params < 128);
    AVCodecParameters *p=calloc(1,sizeof(AVCodecParameters));
    allocated_params[num_allocated_params++]=p;
    return p;
}
static void avcodec_parameters_free(AVCodecParameters **p)
{
    for(int n=0;n<num_allocated_params;n++) {
        if(*p && *p==allocated_params[n]) { free(*p); allocated_params[n]=NULL; break; }
    }
    *p=NULL;
}
static int avcodec_parameters_copy(AVCodecParameters *to,const AVCodecParameters *from)
{
    if (copy_fail > 0 && --copy_fail == 0) {
        return -1;
    }
    *to = *from;
    return 0;
}
static int mp_read(void*,uint8_t*,int);
static int interrupt_cb(void*);
static int avformat_find_stream_info(AVFormatContext *avfc,void *unused);
'''

PROBE_TESTS = r'''
static struct stream_info backend={"bd"};
static struct stream stream={&backend,0,0};
static struct demux_lavf_opts opts={-2};
static AVIOContext pb;
static AVCodecParameters video,audio,known_audio,extra;
static AVStream vst={&video,1,0x1011,AVDISCARD_DEFAULT};
static AVStream ast={&audio,7,0x1100,AVDISCARD_DEFAULT};
static AVStream kst={&known_audio,3,0x1101,AVDISCARD_DEFAULT};
static AVStream xst={&extra,0,0x1234,AVDISCARD_DEFAULT};
static AVStream *streams[4]={&vst,&ast,&kst,&xst};
static AVFormatContext avfc;
static lavf_priv_t priv;
static struct demuxer_params params;
static struct demuxer demux;
static void complete_video(void)
{ video.width=1920; video.height=1080; video.extradata=headers; video.extradata_size=sizeof(headers); }
static int avformat_find_stream_info(AVFormatContext *avfc,void *unused)
{
    assert(priv.disc_vc1_probing && !(avfc->flags & AVFMT_FLAG_NOBUFFER));
    assert(avfc->skip_estimate_duration_from_pts==1);
    // Fixed FFmpeg MPEG-TS skips AVDISCARD_ALL PES streams before codec
    // detection. Without the production guard this models the hidden parser
    // becoming MP3, which a later codecpar-only restoration cannot repair.
    assert(ast.discard==AVDISCARD_ALL);
    if(ast.discard!=AVDISCARD_ALL) {
        audio.codec_id=AV_CODEC_ID_MP3; audio.codec_type=AVMEDIA_TYPE_AUDIO;
    }
    assert(kst.discard==AVDISCARD_DEFAULT);
    known_audio_packets++; // known audio remains buffered for initial playback
    ast.disposition=99;
    uint8_t byte;
    if(behavior==1 || behavior==2) {
        assert(mp_read(&demux,&byte,DISC_VC1_PROBE_BYTES*2)==DISC_VC1_PROBE_BYTES);
        assert(read_bytes==DISC_VC1_PROBE_BYTES);
        assert(mp_read(&demux,&byte,1)==AVERROR_EOF);
        pb.eof_reached=1; pb.error=AVERROR_EOF;
    } else if(behavior==3) {
        now=priv.disc_vc1_probe_deadline;
        assert(interrupt_cb(&demux)==1);
        pb.error=AVERROR_EXIT;
    } else if(behavior==4) {
        demux.canceled=true;
        assert(interrupt_cb(&demux)==1);
        assert(mp_read(&demux,&byte,1)==AVERROR_EXIT);
        pb.error=AVERROR_EXIT;
        return AVERROR_EXIT;
    } else if(behavior==5 || behavior==7 || behavior==8) {
        read_eof=1; assert(mp_read(&demux,&byte,32)==AVERROR_EOF);
        pb.eof_reached=1;
        if(behavior==8) { now=priv.disc_vc1_probe_deadline; assert(interrupt_cb(&demux)==1); }
    } else if(behavior==6) avfc->nb_streams=4;
    if(behavior==0 || behavior==1 || behavior==6 || behavior==7) complete_video();
    return behavior==0 || behavior==6 || behavior==7 ? 0 : AVERROR_EXIT;
}
static void setup(int mode)
{
    video=(AVCodecParameters){.codec_type=AVMEDIA_TYPE_VIDEO,.codec_id=AV_CODEC_ID_VC1};
    audio=(AVCodecParameters){.codec_type=AVMEDIA_TYPE_DATA,.codec_id=AV_CODEC_ID_NONE};
    known_audio=(AVCodecParameters){.codec_type=AVMEDIA_TYPE_AUDIO,.codec_id=AV_CODEC_ID_AC3};
    vst.codecpar=&video; ast.codecpar=&audio; ast.disposition=7;
    ast.discard=AVDISCARD_DEFAULT; kst.codecpar=&known_audio; kst.disposition=3;
    kst.discard=AVDISCARD_DEFAULT;
    avfc=(AVFormatContext){3,streams,5000000,0,0,AVFMT_FLAG_NOBUFFER};
    pb=(AVIOContext){0}; opts.probeinfo=-2; backend.name="bd";
    priv=(lavf_priv_t){.stream=&stream,.opts=&opts,.avfc=&avfc,.pb=&pb};
    params=(struct demuxer_params){0}; demux=(struct demuxer){&priv,&params,false};
    stream.eof=0; stream.pos=0;
    behavior=mode; now=read_eof=read_calls=max_request=read_bytes=errors=copy_fail=known_audio_packets=0;
}
static void restored(void)
{
    assert(ast.codecpar->codec_id==AV_CODEC_ID_NONE && ast.codecpar->codec_type==AVMEDIA_TYPE_DATA);
    assert(ast.disposition==7 && ast.discard==AVDISCARD_DEFAULT);
    assert(kst.discard==AVDISCARD_DEFAULT && kst.codecpar->codec_id==AV_CODEC_ID_AC3);
    assert(kst.disposition==3 && avfc.probesize==5000000 && avfc.max_analyze_duration==0);
    assert(!priv.disc_vc1_probing && avfc.skip_estimate_duration_from_pts==0);
    assert(avfc.flags==AVFMT_FLAG_NOBUFFER);
    // Restored codecpar is allocated independently; original audio is stack/static.
    if(ast.codecpar!=&audio) { avcodec_parameters_free(&ast.codecpar); ast.codecpar=&audio; }
    if(kst.codecpar!=&known_audio) { avcodec_parameters_free(&kst.codecpar); kst.codecpar=&known_audio; }
}
int main(void)
{
    setup(0); assert(disc_vc1_needs_probe(&demux));
    opts.probeinfo=0; assert(!disc_vc1_needs_probe(&demux)); opts.probeinfo=-2;
    backend.name="file"; assert(!disc_vc1_needs_probe(&demux));
    backend.name="http"; assert(!disc_vc1_needs_probe(&demux)); backend.name="bd";
    params.skip_lavf_probing=true; assert(!disc_vc1_needs_probe(&demux)); params.skip_lavf_probing=false;
    behavior=9; assert(!disc_vc1_needs_probe(&demux)); behavior=0;
    complete_video(); assert(!disc_vc1_needs_probe(&demux));
    headers[15]=0; assert(disc_vc1_needs_probe(&demux)); headers[15]=14;
    video.extradata_size=15; assert(disc_vc1_needs_probe(&demux));
    setup(0); assert(probe_disc_vc1(&demux) && !disc_vc1_needs_probe(&demux));
    assert(known_audio_packets==1); restored();
    setup(1); assert(probe_disc_vc1(&demux));
    assert(read_calls==1 && max_request==DISC_VC1_PROBE_BYTES && !pb.error && !pb.eof_reached); restored();
    setup(2); assert(!probe_disc_vc1(&demux) && errors==1); restored();
    setup(3); assert(!probe_disc_vc1(&demux) && !read_calls && errors==1); restored();
    setup(4); assert(!probe_disc_vc1(&demux) && demux.canceled && pb.error==AVERROR_EXIT); restored();
    setup(5); assert(!probe_disc_vc1(&demux) && pb.eof_reached && !priv.disc_vc1_probe_limited); restored();
    setup(6); assert(!probe_disc_vc1(&demux) && avfc.nb_streams==4 && errors==2); restored();
    setup(7); assert(probe_disc_vc1(&demux) && pb.eof_reached && !priv.disc_vc1_probe_limited); restored();
    setup(8); assert(!probe_disc_vc1(&demux) && pb.eof_reached && priv.disc_vc1_probe_limited); restored();
    setup(0); copy_fail=1; assert(!probe_disc_vc1(&demux) && ast.codecpar==&audio && !read_calls); restored();
    // A later backup failure must restore an auxiliary stream already masked.
    setup(0); copy_fail=2; assert(!probe_disc_vc1(&demux) && !read_calls);
    assert(ast.discard==AVDISCARD_DEFAULT); restored();
    puts("PASS probe: scope/headers; byte/time/cancel; real EOF; stream-layout rejection; auxiliary-PID guard; known-audio buffering; parameter/discard restoration");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.is_dir() or not args.output.suffix:
        args.output = args.output / "verification.json"
    vd = (args.source / "video/decode/vd_lavc.c").read_text(encoding="utf-8")
    lavf = (args.source / "demux/demux_lavf.c").read_text(encoding="utf-8")
    enum = re.search(r"enum init_avctx_result \{.*?\};", vd, re.S).group(0)
    # The complete recovery block is retained. Frame conversion after the
    # recovery block is outside this CPU harness's scope.
    receive = function(vd, "receive_frame")
    marker = "\n    if (ret == AVERROR(EAGAIN) && ctx->num_requeue_packets)"
    if marker not in receive:
        raise RuntimeError("Runtime recovery boundary changed; review the harness")
    receive = receive.split(marker)[0] + "\n    return ret;\n}\n"
    cases = {
        "fallback": COMMON + enum + FALLBACK + "\n" + "\n\n".join(
            function(vd, name) for name in ("force_fallback", "finish_fallback", "reinit"))
            + "\n" + receive + "\n" + function(vd, "control") + FALLBACK_TESTS,
        "probe": COMMON + PROBE + "\n" + "\n\n".join(
            function(lavf, name) for name in ("mp_read", "interrupt_cb", "is_bluray_stream",
            "vc1_has_headers", "disc_vc1_needs_probe", "log_disc_vc1_params", "probe_disc_vc1"))
            + PROBE_TESTS,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"source": str(args.source.resolve()), "status": "failed", "tests": []}
    try:
        for name, source in cases.items():
            cpath = args.output.with_suffix(f".{name}.c")
            binary = args.output.with_suffix(f".{name}" + (".exe" if os.name == "nt" else ".out"))
            cpath.write_text(source, encoding="utf-8")
            command = [args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                       str(cpath), "-o", str(binary)]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)
            tested = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
            report["tests"].append({"name": name, "returncode": tested.returncode,
                                    "stdout": tested.stdout, "stderr": tested.stderr,
                                    "extracted_c_sha256": hashlib.sha256(source.encode()).hexdigest()})
            if tested.returncode:
                raise RuntimeError(tested.stdout + tested.stderr)
        report["status"] = "passed"
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
