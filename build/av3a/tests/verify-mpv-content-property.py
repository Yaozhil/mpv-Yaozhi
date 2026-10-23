"""Compile exact candidate C functions against a bounded API fixture."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mpv-source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cc', default='cc')
args = parser.parse_args()
ROOT = args.mpv_source.resolve()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)

def function(path, prefix):
    text = path.read_text(encoding='utf-8')
    begin = text.index(prefix)
    body = text.index('{', begin)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[begin:end]

control = function(ROOT / 'audio/decode/ad_lavc.c', 'static int control(')
wrapper = function(ROOT / 'filters/f_decoder_wrapper.c', 'int mp_decoder_wrapper_control(')
prop = function(ROOT / 'player/command.c', 'static int mp_property_audio_av3a_content_info(')
header = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#define CONTROL_TRUE 1
#define CONTROL_FALSE 0
#define CONTROL_UNKNOWN -1
#define STREAM_AUDIO 0
#define M_PROPERTY_UNAVAILABLE -2
#define M_PROPERTY_GET 1
#define M_PROPERTY_GET_TYPE 2
#define M_PROPERTY_SET 3
#define M_PROPERTY_NOT_IMPLEMENTED -1
#define AV_OPT_FLAG_EXPORT 1
#define AV_OPT_FLAG_READONLY 2
#define AV_OPT_TYPE_STRING 3
#define mp_assert assert
enum dec_ctrl { ADCTRL_GET_AV3A_CONTENT_INFO, VDCTRL_GET_HWDEC, OTHER_COMMAND };
typedef struct { int type, flags; } AVOption;
typedef struct { int marker; } AVClass;
typedef struct { const AVClass *priv_class; } AVCodec;
typedef struct { const AVCodec *codec; void *priv_data; } AVCodecContext;
struct option_object { const AVClass *av_class; };
struct mp_filter { void *priv; };
struct mp_decoder { struct mp_filter *f; int (*control)(struct mp_filter *, enum dec_ctrl, void *); };
struct mp_decoder_wrapper { struct mp_filter *f; };
struct priv {
    AVCodecContext *avctx;
    bool is_group;
    int num_children;
    struct mp_decoder_wrapper **children;
    struct mp_decoder *decoder;
    void *cache_lock;
    char *cur_hwdec;
};
struct sh_stream { void *group; };
struct track { struct mp_decoder_wrapper *dec; struct sh_stream *stream; };
typedef struct MPContext { struct track *current_track[1][1]; } MPContext;
struct m_property {};
static int locked, allocated, get_calls, finds;
static const AVClass option_class = { 123 };
static AVOption option = {AV_OPT_TYPE_STRING, 3};
static bool missing, fail_get;
static char *exported;
static char *copy(const char *source, size_t n) {
    char *out = malloc(n + 1); assert(out);
    memcpy(out, source, n); out[n] = 0; return out;
}
static const AVOption *av_opt_find(void *obj, const char *name, const char *unit, int flags, int search) {
    assert(locked && obj && !strcmp(name, "av3a_contents") && !unit);
    /* FFmpeg AVOptions reads the AVClass pointer at the object's start.
     * Plain codec private data is not necessarily an AVOptions object. */
    assert(((struct option_object *)obj)->av_class == &option_class);
    assert(flags == 3 && search == 0); finds++;
    return missing ? NULL : &option;
}
static int av_opt_get(void *obj, const char *name, int search, uint8_t **out) {
    assert(locked && obj && !strcmp(name, "av3a_contents") && search == 0);
    get_calls++;
    if (fail_get) return -1;
    if (exported) { *out = (uint8_t *)copy(exported, strlen(exported)); allocated++; }
    return 0;
}
static void av_free(void *value) { if (value) { free(value); allocated--; } }
static char *talloc_strndup(void *parent, const char *value, size_t n) { return copy(value,n); }
static void talloc_free(void *value) { free(value); }
static void thread_lock(struct priv *p) { assert(!locked); locked = 1; }
static void thread_unlock(struct priv *p) { assert(locked); locked = 0; }
static int update_cached_values(struct priv *p) { assert(locked); return 1; }
static void mp_mutex_lock(void *p) {}
static void mp_mutex_unlock(void *p) {}
static int m_property_strdup_ro(int action, void *arg, const char *value) {
    if (action == M_PROPERTY_GET) { *(char **)arg = copy(value,strlen(value)); return 1; }
    return action == M_PROPERTY_GET_TYPE ? 1 : M_PROPERTY_NOT_IMPLEMENTED;
}
'''
tests = r'''
static int count;
static void expect(bool value) { count++; assert(value); }
int main(void) {
    struct option_object fake_private = { &option_class };
    AVCodec codec = { &option_class };
    AVCodecContext avctx = { .codec=&codec, .priv_data=&fake_private };
    struct priv inner = {.avctx=&avctx};
    struct mp_filter decoder_filter = { &inner };
    struct mp_decoder decoder = { &decoder_filter, control };
    struct priv outer = {.decoder=&decoder};
    struct mp_filter wrapper_filter = { &outer };
    struct mp_decoder_wrapper dec = { &wrapper_filter };
    struct sh_stream stream = {0};
    struct track track = { &dec, &stream };
    MPContext context = {{{ &track }}};
    char *value = NULL;
    char original[] = "{\"version\":1}";
    exported = original;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == 1);
    expect(!strcmp(value,original) && value != original && !locked && allocated == 0);
    original[1] = '!'; expect(value[1] == '"'); free(value); value = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_SET,&value) == -1);
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET_TYPE,&value) == 1);
    option.flags = AV_OPT_FLAG_EXPORT;
    int old_gets = get_calls;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(get_calls == old_gets);
    option.flags = 3; option.type = 0;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(get_calls == old_gets); option.type = AV_OPT_TYPE_STRING;
    missing = true;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    missing = false; fail_get = true;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    fail_get = false; exported = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    exported = "";
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    char *large = malloc(16387); assert(large); memset(large,'x',16386); large[16386] = 0;
    exported = large; large[16384] = 0;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == 1);
    expect(strlen(value) == 16384); free(value); value = NULL;
    large[16384] = 'x'; large[16385] = 0;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(allocated == 0 && !locked); free(large);
    avctx.priv_data = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    avctx.priv_data = &fake_private; inner.avctx = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    inner.avctx = &avctx;
    /* PCM may allocate private fields without an AVClass. Even a non-NULL
     * private pointer must never be passed to av_opt_find in this case. */
    uintptr_t non_option_private = UINTPTR_MAX;
    AVCodec plain_codec = { .priv_class=NULL };
    int no_option_finds = finds;
    avctx.codec = &plain_codec; avctx.priv_data = &non_option_private;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(finds == no_option_finds && value == NULL && !locked);
    avctx.priv_data = &fake_private;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(finds == no_option_finds);
    avctx.codec = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(finds == no_option_finds);
    avctx.codec = &codec;
    stream.group = &fake_private; int old_finds = finds;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    expect(finds == old_finds); stream.group = NULL;
    context.current_track[0][0] = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    context.current_track[0][0] = &track; track.dec = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    track.dec = &dec; decoder.control = NULL;
    expect(mp_property_audio_av3a_content_info(&context,NULL,M_PROPERTY_GET,&value) == -2);
    decoder.control = control;
    expect(mp_decoder_wrapper_control(&dec,OTHER_COMMAND,&value) == CONTROL_UNKNOWN);
    expect(allocated == 0 && !locked);
    printf("{\"checks\":%d,\"passed\":true}\n",count);
    return 0;
}
'''
source = OUT / 'readonly-control.c'
source.write_text(header + control + '\n' + wrapper + '\n' + prop + tests, encoding='utf-8')
binary = OUT / ('readonly-control.exe' if os.name == 'nt' else 'readonly-control')
compile_result = subprocess.run([args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
    '-Wno-unused-parameter', str(source), '-o', str(binary)], text=True, capture_output=True)
(OUT / 'compile.log').write_text(compile_result.stdout + compile_result.stderr, encoding='utf-8')
compile_result.check_returncode()
run = subprocess.run([str(binary)], text=True, capture_output=True)
(OUT / 'run.log').write_text(run.stdout + run.stderr, encoding='utf-8')
run.check_returncode()
report = json.loads(run.stdout)
report.update(scope='Exact candidate ad_lavc control, unchanged decoder-wrapper control and candidate property compiled against FFmpeg/mpv API fixture; not a full mpv build',
    function_sha256={name: hashlib.sha256(value.encode()).hexdigest()
        for name,value in [('control',control),('wrapper',wrapper),('property',prop)]})
(OUT / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
