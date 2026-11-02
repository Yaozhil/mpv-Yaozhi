#!/usr/bin/env python3
"""Compile actual AV3A C speaker routing against bounded SDK/backend fakes.

This checks C ownership, per-block masks, format reset, flush and bounded
failure. It is deliberately separate from real renderer PCM/acoustic tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

FUNCTIONS = ['arcdav3a_content_mask', 'arcdav3a_destroy_renderer',
             'arcdav3a_stream_config_changed', 'arcdav3a_ensure_renderer_output',
             'arcdav3a_select_object_metadata', 'arcdav3a_render_speakers',
             'arcdav3a_recreate_decoder', 'arcdav3a_decode_flush',
             'arcdav3a_append_spatial_frame']

def extract(source, name):
    match = re.search(r'^static (?:av_cold )?(?:int|void) '+re.escape(name)+r'\(', source, re.M)
    if not match:
        raise ValueError('Actual source function missing: ' + name)
    start = match.start()
    begin = source.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'

def generate(sdk_source, ffmpeg_source, real=False):
    source = (ffmpeg_source / 'libavcodec/libarcdav3a.c').read_text(encoding='utf-8')
    sdk = sdk_source / 'av3adecoder/avs3Decoder/include'
    spatial = (sdk / 'avs3_spatial_metadata.h').read_text(encoding='utf-8')
    contents = (sdk / 'avs3_spatial_contents.h').read_text(encoding='utf-8')
    types = source[source.index('typedef struct AVS3DecoderOutput'):source.index('/* Selection is applied')]
    selected = '\n'.join(extract(source, name) for name in FUNCTIONS)
    callback = extract(source, 'arcdav3a_decode_frame')
    return PREFIX + '\n' + spatial + '\n' + contents + '\n' + (REAL_BACKEND if real else FAKE_BACKEND) + types + PROVIDERS + selected + EXPORTS + ('' if real else CALLBACK_FAKES + callback + TEST), source, selected

def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-source', type=Path, required=True)
    parser.add_argument('--ffmpeg-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    generated, source, selected = generate(args.sdk_source, args.ffmpeg_source)
    c = args.output / 'actual-speaker-functions.c'
    c.write_text(generated, encoding='utf-8')
    exe = args.output / ('contract.exe' if os.name == 'nt' else 'contract')
    command = [args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare', str(c), '-lm', '-o', str(exe)]
    p = subprocess.run(command, capture_output=True, timeout=90)
    (args.output / 'compile.log').write_bytes(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError('Actual C speaker contract compile failed: '+p.stderr.decode(errors='replace'))
    p = subprocess.run([str(exe)], capture_output=True, timeout=30)
    (args.output / 'stdout.json').write_bytes(p.stdout)
    (args.output / 'stderr.txt').write_bytes(p.stderr)
    if p.returncode:
        raise RuntimeError('Actual C speaker contract failed: '+p.stderr.decode(errors='replace'))
    report = json.loads(p.stdout)
    report.update({'actual_functions': len(FUNCTIONS)+1, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                   'selected_functions_sha256': hashlib.sha256(selected.encode()).hexdigest(),
                   'functions': {name: hashlib.sha256(extract(source,name).encode()).hexdigest() for name in FUNCTIONS+['arcdav3a_decode_frame']},
                   'fake_renderer': True, 'physical_device_test': False, 'compile_command': command})
    (args.output / 'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])

PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define AVERROR(e) (-(e))
#define AVERROR_INVALIDDATA (-1001)
#define AVERROR_PATCHWELCOME (-1002)
#define AVERROR_EXTERNAL (-1003)
#define AVS3_DECODER_SUCCESS 1
#define AV_LOG_ERROR 1
#define AV_LOG_DEBUG 2
#define AV_LOG_WARNING 3
#define AV3A_RENDER_NATIVE 0
#define AV3A_RENDER_BINAURAL 1
#define AV3A_RENDER_SPEAKERS 2
#define AV3A_RENDER_MAX_CHANNELS 32
#define MAX_VIVID_SIZE (4096U * 64U)
#define av_cold
typedef void AVClass;
typedef void audio_context;
typedef void *AVS3DecoderHandle;
typedef struct AVCodecContext { void *priv_data;int sample_rate,sample_fmt; } AVCodecContext;
static int alloc_fail, error_logs, total_logs;
static void av_log(void *ctx,int level,const char *fmt,...) {(void)ctx;(void)fmt;++total_logs;if(level==AV_LOG_ERROR)++error_logs;}
static void av_freep(void *p) {void **pp=p;free(*pp);*pp=NULL;}
static void *av_realloc_array(void *p,size_t n,size_t size) {return alloc_fail || (size && n>SIZE_MAX/size)?NULL:realloc(p,n*size);}
static void audio_destroy(void *p) {(void)p;}
'''

REAL_BACKEND = r'''
#include "libarcdav3a_speakers.h"
'''

FAKE_BACKEND = r'''
typedef struct AV3ASpeakers { int channels; } AV3ASpeakers;
static int creates,destroys,processes,backend_fail;
static uint32_t observed_masks[16];
static float observed_bed_gains[16];
static int observed_bed_mutes[16];
static int av3a_speakers_create(AV3ASpeakers **out,const AVS3SpatialStreamInfo *info) {
    ++creates;*out=malloc(sizeof(**out));if(!*out)return -3;(*out)->channels=info->total_channels;return 0;
}
static void av3a_speakers_destroy(AV3ASpeakers *ctx) {if(ctx){++destroys;free(ctx);}}
static int av3a_speakers_process(AV3ASpeakers *ctx,const AVS3SpatialStreamInfo *info,const AVS3SpatialFrame *meta,
    const int16_t *input,size_t input_samples,size_t frames,uint32_t mask,float *output,size_t output_samples) {
    assert(ctx && input && meta && info->total_channels==ctx->channels);
    assert(input_samples==frames*(size_t)info->total_channels && output_samples==frames*12);
    assert(meta->struct_size==sizeof(*meta) && meta->abi_version==AVS3_SPATIAL_ABI_VERSION);
    assert(info->total_channels==32 || !(mask>>info->total_channels));
    observed_masks[processes%16]=mask;
    observed_bed_gains[processes%16]=info->channel_gain_linear[0];
    observed_bed_mutes[processes%16]=info->channel_muted[0];++processes;
    if(backend_fail)return backend_fail;
    for(size_t i=0;i<output_samples;++i)output[i]=(float)input[0];
    return 0;
}
static const char *av3a_speakers_error_string(int code) {(void)code;return "bounded fake";}
'''

PROVIDERS = r'''
typedef struct Provider {
    AVS3SpatialFrame frame;
    AVS3SpatialContents contents;
    int frame_ret, contents_ret;
} Provider;
static void *avs3_create_decoder(void) {Provider *p=calloc(1,sizeof(*p));return p;}
static void avs3_destroy_decoder(void *p) {free(p);}
static int avs3_get_spatial_frame(void *p,AVS3SpatialFrame *out) {Provider *v=p;*out=v->frame;return v->frame_ret;}
static int avs3_get_spatial_contents(void *p,AVS3SpatialContents *out) {Provider *v=p;*out=v->contents;return v->contents_ret;}
'''

EXPORTS = r'''
void *integration_create(void) {
    arcdav3a_context *h=calloc(1,sizeof(*h));if(!h)return NULL;
    h->m_hAvs3=avs3_create_decoder();if(!h->m_hAvs3){free(h);return NULL;}
    h->spatial_render=AV3A_RENDER_SPEAKERS;h->content_id=-1;return h;
}
int integration_add(void *opaque,const AVS3SpatialFrame *frame,const AVS3SpatialContents *table,int selected,const AVS3SpatialStreamInfo *info) {
    arcdav3a_context *h=opaque;Provider *p=h->m_hAvs3;uint32_t mask;int applied;
    p->frame=*frame;p->contents=*table;p->frame_ret=p->contents_ret=AVS3_DECODER_SUCCESS;h->content_id=selected;
    int code=arcdav3a_content_mask(h,&mask,&applied);if(code<0)return code;
    return arcdav3a_append_spatial_frame(h,mask,applied,info);
}
int integration_render(void *opaque,const AVS3SpatialStreamInfo *info,const int16_t *input,size_t samples,const float **output,size_t *written) {
    arcdav3a_context *h=opaque;AVCodecContext ctx={h,0,0};AVS3DecoderOutput decoded={0};
    decoded.have_spatial_info=1;decoded.spatial_info=*info;decoded.pOutData=(uint8_t*)input;
    decoded.nBits=16;decoded.nChannel=info->total_channels;decoded.nSamplerate=info->sample_rate;
    decoded.nlen=samples*sizeof(*input);const uint8_t *data=(const uint8_t*)input;unsigned long bytes=decoded.nlen;
    int code=arcdav3a_render_speakers(&ctx,&decoded,&data,&bytes);
    if(code==1){*output=(const float*)data;*written=bytes/sizeof(float);}else{*output=NULL;*written=0;}
    h->spatial_frame_count=0;return code;
}
void integration_flush(void *opaque) {AVCodecContext ctx={opaque,0,0};arcdav3a_decode_flush(&ctx);}
void integration_destroy(void *opaque) {
    arcdav3a_context *h=opaque;if(!h)return;arcdav3a_destroy_renderer(h);
    avs3_destroy_decoder(h->m_hAvs3);free(h->spatial_frames);free(h->contents_json);free(h);
}
'''

TEST = r'''
static void prepare(AVS3SpatialStreamInfo *info,AVS3SpatialFrame *frame,AVS3SpatialContents *table) {
    memset(info,0,sizeof(*info));memset(frame,0,sizeof(*frame));memset(table,0,sizeof(*table));
    info->struct_size=sizeof(*info);info->abi_version=AVS3_SPATIAL_ABI_VERSION;
    info->format=AVS3_SPATIAL_FORMAT_BED_OBJECTS;info->total_channels=16;info->bed_channels=12;info->object_channels=4;
    info->sample_rate=48000;info->frame_length=16;info->bit_depth=16;info->channel_config=10;
    frame->struct_size=sizeof(*frame);frame->abi_version=AVS3_SPATIAL_ABI_VERSION;
    frame->has_dynamic_metadata=frame->has_static_metadata=1;frame->object_count=4;
    for(int i=0;i<4;++i){frame->objects[i].pcm_channel=12+i;frame->objects[i].position_valid=1;frame->objects[i].z=1;}
    table->struct_size=sizeof(*table);table->abi_version=AVS3_SPATIAL_CONTENTS_ABI_VERSION;
    table->available=1;table->total_channels=16;table->num_contents=4;table->num_objects=5;
    uint32_t masks[4]={0x3fff,0x5fff,0x6fff,0x9fff};
    for(int i=0;i<4;++i){table->contents[i].content_id=i;table->contents[i].pcm_channel_mask=masks[i];}
}
int main(void) {
    AVS3SpatialStreamInfo info;AVS3SpatialFrame frame;AVS3SpatialContents table;prepare(&info,&frame,&table);
    arcdav3a_context *h=integration_create();assert(h);const float *out;size_t written;
    int16_t pcm[5*16*16]={0};pcm[0]=12;
    for(int i=-1;i<4;++i) {
        info.channel_gain_valid[0]=1;info.channel_gain_linear[0]=(i+2)*.125f;
        info.channel_muted[0]=i==0;
        assert(integration_add(h,&frame,&table,i,&info)==0);
    }
    assert(integration_render(h,&info,pcm,5*16*16,&out,&written)==1 && written==5*16*12);
    uint32_t expected[5]={0xffff,0x3fff,0x5fff,0x6fff,0x9fff};
    for(int i=0;i<5;++i) {
        assert(observed_masks[i]==expected[i]);
        assert(observed_bed_gains[i]==(i+1)*.125f && observed_bed_mutes[i]==(i==1));
    }
    assert(creates==1 && processes==5);
    info.total_bitrate++;assert(integration_add(h,&frame,&table,-1,&info)==0);
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==1 && creates==2 && destroys==1);
    h->speaker_error=-1002;h->have_last_spatial_frame=1;h->content_missing_frames=15;
    integration_flush(h);assert(!h->speaker_error && !h->have_last_spatial_frame && !h->spatial_frame_count && !h->speakers && h->contents.status==AVS3_CONTENTS_NO_METADATA);
    assert(integration_add(h,&frame,&table,-1,&info)==0);backend_fail=-2;
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==AVERROR_PATCHWELCOME && !out && !written && error_logs==1);
    int before=processes;
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==AVERROR_PATCHWELCOME && processes==before && error_logs==1);
    integration_flush(h);backend_fail=0;
    assert(integration_add(h,&frame,&table,-1,&info)==0);alloc_fail=1;
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==AVERROR(ENOMEM));alloc_fail=0;
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==AVERROR_INVALIDDATA);
    assert(integration_add(h,&frame,&table,-1,&info)==0);
    assert(integration_render(h,&info,pcm,16*16-1,&out,&written)==AVERROR_INVALIDDATA);
    assert(integration_add(h,&frame,&table,-1,&info)==0);info.format=AVS3_SPATIAL_FORMAT_CHANNELS;
    assert(integration_render(h,&info,pcm,16*16,&out,&written)==0 && !out && !written);
    info.format=AVS3_SPATIAL_FORMAT_BED_OBJECTS;integration_flush(h);
    table.contents[0].pcm_channel_mask=1u<<30;
    assert(integration_add(h,&frame,&table,0,&info)==AVERROR_INVALIDDATA);
    Provider *p=h->m_hAvs3;p->contents_ret=0;p->contents.status=AVS3_CONTENTS_NO_METADATA;h->content_id=0;uint32_t mask;int applied;
    for(int i=0;i<64;++i)assert(arcdav3a_content_mask(h,&mask,&applied)==0 && mask==0 && !applied);
    assert(arcdav3a_content_mask(h,&mask,&applied)==AVERROR_INVALIDDATA);
    integration_destroy(h);assert(creates==destroys);
    // Exercise the complete real FFmpeg legacy decode callback. The SDK
    // decoder and unrelated AVFrame allocation/layout functions are fakes.
    // A renderer failure is reported once; later packets are consumed with
    // no frame and no repeated decode/render call or generic negative code.
    prepare(&info,&frame,&table);h=integration_create();AVCodecContext avctx={h,0,0};
    h->out_frame.pOutData=calloc(MAX_VIVID_SIZE,1);assert(h->out_frame.pOutData);
    uint8_t packet_data[32]={0};AVPacket packet={packet_data,32};AVFrame avframe={0};int got=99;
    callback_info=info;
    assert(integration_add(h,&frame,&table,-1,&info)==0);backend_fail=-2;
    before=error_logs;
    assert(arcdav3a_decode_frame(&avctx,&avframe,&got,&packet)==AVERROR_PATCHWELCOME && got==0 && error_logs==before+1);
    int decoded_before=decode_calls,rendered_before=processes,logs_before=total_logs;
    for(int i=0;i<1000;++i) {
        got=99;assert(arcdav3a_decode_frame(&avctx,&avframe,&got,&packet)==packet.size && got==0);
    }
    assert(decode_calls==decoded_before && processes==rendered_before && error_logs==before+1 && total_logs==logs_before);
    integration_flush(h);backend_fail=0;
    assert(integration_add(h,&frame,&table,-1,&info)==0);
    assert(arcdav3a_decode_frame(&avctx,&avframe,&got,&packet)==packet.size && got==1 && decode_calls==decoded_before+1);
    free(avframe.data[0]);free(h->out_frame.pOutData);h->out_frame.pOutData=NULL;
    integration_destroy(h);assert(creates==destroys);
    puts("{\"status\":\"PASS_ACTUAL_AV3A_SPEAKER_C_ROUTING\",\"cases\":18,\"default_all_and_four_per_block_masks\":true,\"per_block_bed_gain_mute\":true,\"error_logged_once\":true,\"seek_flush_reset\":true,\"fatal_callback_packets_consumed\":1000,\"fatal_additional_logs\":0,\"full_actual_legacy_callback\":true}");
    return 0;
}
'''

CALLBACK_FAKES = r'''
#define AV_SAMPLE_FMT_FLT 1
#define AV_SAMPLE_FMT_S16 0
#define FFMIN(a,b) ((a)<(b)?(a):(b))
typedef struct AVFrame { int format,nb_samples,sample_rate;uint8_t *data[1]; } AVFrame;
typedef struct AVPacket { uint8_t *data;int size; } AVPacket;
static AVS3SpatialStreamInfo callback_info;
static int decode_calls;
static int dav3a_decode_frame(AVCodecContext *avctx,const uint8_t *input,unsigned long length,
    unsigned long *consumed,AVS3DecoderOutput *out) {
    (void)avctx;(void)input;++decode_calls;*consumed=length;
    out->nlen=callback_info.frame_length*callback_info.total_channels*2;
    out->nChannel=callback_info.total_channels;out->nSamplerate=callback_info.sample_rate;
    out->nBits=16;out->have_spatial_info=1;out->spatial_info=callback_info;return 0;
}
static int arcdav3a_render_binaural(AVCodecContext *ctx,AVS3DecoderOutput *out,const uint8_t **data,unsigned long *size) {
    (void)ctx;(void)out;(void)data;(void)size;return 0;
}
static int arcdav3a_publish_contents(arcdav3a_context *h,int applied) {(void)h;(void)applied;return 0;}
static int av_get_bytes_per_sample(int format) {return format==AV_SAMPLE_FMT_FLT?4:2;}
static int arcdav3a_set_binaural_layout(AVCodecContext *ctx,AVFrame *frame) {(void)ctx;(void)frame;return 0;}
static int arcdav3a_set_layout(AVCodecContext *ctx,AVFrame *frame,unsigned long channels,unsigned long config,const AVS3SpatialStreamInfo *info) {
    (void)ctx;(void)frame;(void)channels;(void)config;(void)info;return 0;
}
static int ff_get_buffer(AVCodecContext *ctx,AVFrame *frame,int flags) {
    (void)ctx;(void)flags;frame->data[0]=calloc((size_t)frame->nb_samples,12*4);return frame->data[0]?0:AVERROR(ENOMEM);
}
'''

if __name__ == '__main__':
    run()
