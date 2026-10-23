#!/usr/bin/env python3
"""Compile the actual AV3A selection/renderer functions against bounded fakes.

This checks source routing, not renderer acoustics or full codec playback.
The independent SDK getter contract checks the actual SDK metadata graph.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def function(source, name):
    start = source.index('static int ' + name + '(')
    begin = source.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end] + '\n'


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-source', type=Path, required=True)
    parser.add_argument('--ffmpeg-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sdk = args.sdk_source / 'av3adecoder/avs3Decoder/include'
    contents = (sdk / 'avs3_spatial_contents.h').read_text(encoding='utf-8')
    spatial = (sdk / 'avs3_spatial_metadata.h').read_text(encoding='utf-8')
    source = (args.ffmpeg_source / 'libavcodec/libarcdav3a.c').read_text(encoding='utf-8')
    selected = '\n'.join(function(source, n) for n in [
        'arcdav3a_content_mask', 'arcdav3a_json_add', 'arcdav3a_publish_contents',
        'arcdav3a_position_valid', 'arcdav3a_gain_valid',
        'arcdav3a_select_object_metadata', 'arcdav3a_render_block',
        'arcdav3a_append_spatial_frame',
    ])
    harness = PREFIX + '\n' + contents + '\n' + spatial + '\n' + FAKE + selected + TEST
    c = args.output / 'actual-functions.c'
    c.write_text(harness, encoding='utf-8')
    exe = args.output / ('contract.exe' if os.name == 'nt' else 'contract')
    result = subprocess.run([args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                             '-Wno-sign-compare', str(c), '-lm', '-o', str(exe)],
                            capture_output=True, timeout=90)
    (args.output / 'compile.log').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('C compile failed: ' + result.stderr.decode(errors='replace'))
    result = subprocess.run([str(exe)], capture_output=True, timeout=15)
    (args.output / 'stdout.jsonl').write_bytes(result.stdout)
    (args.output / 'stderr.txt').write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    lines = result.stdout.decode().splitlines()
    data = [json.loads(line) for line in lines]
    assert len(data) == 5
    for i, row in enumerate(data[:4]):
        assert row['applied'] is True and row['selected'] == i
        assert row['contents'][i]['mask'] == [0x3fff, 0x5fff, 0x6fff, 0x9fff][i]
        assert row['objects'][1]['name'] == 'AO_"O1\\'
    assert data[4]['applied'] is False and data[4]['render'] == 'native'
    (args.output / 'report.json').write_text(json.dumps({
        'status': 'PASS_ACTUAL_AV3A_SELECTION_FUNCTIONS',
        'actual_functions': 8, 'preset_cases': 4,
        'checks': ['bed-retained', 'only-referenced-objects', 'metadata-gain-and-mute',
                   'native-and-all-preserved', 'missing-metadata-fail-closed-bounded',
                   'invalid-and-unknown-rejected', 'json-escaping-and-size',
                   'per-block-mask-not-last-table', 'allocation-failure'],
    }, indent=2) + '\n')
    print('PASS_ACTUAL_AV3A_SELECTION_FUNCTIONS')


PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define AVERROR(e) (-(e))
#define AVERROR_INVALIDDATA (-1001)
#define AVERROR_PATCHWELCOME (-1002)
#define AVERROR_EXTERNAL (-1003)
#define AVS3_DECODER_SUCCESS 1
#define AV3A_RENDER_NATIVE 0
#define AV3A_RENDER_BINAURAL 1
#define SUCCESS 0
typedef int ambisonic_normalization_type;
enum {N3D, SN3D};
'''

FAKE = r'''
typedef struct AV3AContentFrame {
    AVS3SpatialFrame spatial;
    uint32_t pcm_mask;
    int content_applied;
} AV3AContentFrame;
typedef struct arcdav3a_context {
    void *m_hAvs3;
    int content_id, spatial_render;
    AVS3SpatialContents contents;
    char *contents_json;
    int content_missing_frames;
    AVS3SpatialFrame last_spatial_frame;
    int have_last_spatial_frame;
    float *renderer_planar;
    void *renderer;
    int renderer_bed_source_ids[32], renderer_object_source_ids[32];
    AV3AContentFrame *spatial_frames;
    int spatial_frame_count, spatial_frame_capacity;
} arcdav3a_context;
typedef struct AVCodecContext { void *priv_data; } AVCodecContext;
static AVS3SpatialContents provider;
static int provider_ret = 1, alloc_fail;
static float source_gains[32];
static int avs3_get_spatial_contents(void *unused, AVS3SpatialContents *out) {
    (void)unused; *out = provider; return provider_ret;
}
static int avs3_get_spatial_frame(void *unused, AVS3SpatialFrame *out) {
    (void)unused; out->abi_version = AVS3_SPATIAL_ABI_VERSION; return 1;
}
static char *av_strdup(const char *s) {
    if (alloc_fail) return NULL;
    size_t n = strlen(s) + 1; char *p = malloc(n); if (p) memcpy(p,s,n); return p;
}
static void av_freep(void *p) {void **pp=p; free(*pp); *pp=NULL;}
static void *av_realloc_array(void *p, size_t n, size_t size) {
    return alloc_fail ? NULL : realloc(p, n*size);
}
static int audio_set_source_gain(void *r, int id, float gain) {
    (void)r; assert(id>=0 && id<32); source_gains[id]=gain; return 0;
}
static int audio_submit_source_buffer(void *r,int id,float *p,int n) {
    (void)r;(void)id;(void)p;(void)n;return 0;
}
static int audio_set_source_position(void *r,int id,float *p) {
    (void)r;(void)id;(void)p;return 0;
}
static int audio_submit_ambisonic_channel_buffer(void *r,float *p,int o,int d,
                                                int norm,float gain) {
    (void)r;(void)p;(void)o;(void)d;(void)norm;(void)gain;return 0;
}
static int audio_update_scene(void *r) {(void)r;return 0;}
static int audio_get_interleaved_binaural_buffer(void *r,float *p,int n,int f) {
    (void)r;(void)p;(void)n;(void)f;return 0;
}
'''

TEST = r'''
int main(void) {
    arcdav3a_context h = {0}; AVCodecContext ctx = {&h};
    AVS3SpatialStreamInfo info = {0}; AVS3SpatialFrame spatial = {0};
    uint32_t masks[] = {0x3fff,0x5fff,0x6fff,0x9fff}, mask;
    int objects[][3] = {{0,1,2},{0,1,3},{0,2,3},{0,1,4}};
    float planar[16], output[2]; int16_t input[16]; int applied;
    info.format=AVS3_SPATIAL_FORMAT_BED_OBJECTS; info.total_channels=16;
    info.bed_channels=12; info.object_channels=4; info.frame_length=1;
    spatial.abi_version=AVS3_SPATIAL_ABI_VERSION;
    spatial.has_dynamic_metadata=1; spatial.object_count=4;
    h.renderer_planar=planar; h.spatial_render=AV3A_RENDER_BINAURAL;
    for (int i=0;i<16;i++) input[i]=100;
    for (int i=0;i<12;i++) h.renderer_bed_source_ids[i]=i;
    for (int i=0;i<4;i++) {
        h.renderer_object_source_ids[i]=i+12;
        spatial.objects[i].pcm_channel=i+12;
        spatial.objects[i].position_valid=1; spatial.objects[i].z=1;
    }
    provider.struct_size=sizeof(provider);
    provider.abi_version=AVS3_SPATIAL_CONTENTS_ABI_VERSION;
    provider.available=1; provider.status=AVS3_CONTENTS_OK;
    provider.total_channels=16; provider.num_contents=4; provider.num_objects=5;
    for (int i=0;i<4;i++) {
        provider.contents[i].content_id=i;
        provider.contents[i].pcm_channel_mask=masks[i];
        provider.contents[i].num_objects=3;
        memcpy(provider.contents[i].object_ids, objects[i], sizeof(objects[i]));
    }
    for (int i=0;i<5;i++) {
        provider.objects[i].object_id=i;
        provider.objects[i].pcm_channel_mask=i? 1u<<(i+11):0xfff;
    }
    strcpy(provider.objects[1].name, "AO_\"O1\\");
    for (int i=0;i<4;i++) {
        h.content_id=i;
        assert(arcdav3a_content_mask(&h,&mask,&applied)==0);
        assert(mask==masks[i] && applied==1);
        memset(source_gains,0,sizeof(source_gains));
        assert(arcdav3a_render_block(&ctx,&info,&spatial,mask,input,output)==0);
        for (int j=0;j<16;j++) assert(source_gains[j]==((mask>>j)&1));
        assert(arcdav3a_publish_contents(&h,applied)==0); puts(h.contents_json);
        char *unchanged=h.contents_json;
        assert(arcdav3a_publish_contents(&h,applied)==0 && h.contents_json==unchanged);
        assert(arcdav3a_append_spatial_frame(&h,mask,applied)==0);
    }
    for(int i=0;i<4;i++) assert(h.spatial_frames[i].pcm_mask==masks[i]);
    info.channel_gain_valid[0]=1; info.channel_gain_linear[0]=0.3f;
    spatial.objects[0].gain_valid=1; spatial.objects[0].gain_linear=0.4f;
    spatial.objects[1].muted=1;
    assert(arcdav3a_render_block(&ctx,&info,&spatial,masks[0],input,output)==0);
    assert(source_gains[0]==0.3f && source_gains[12]==0.4f && source_gains[13]==0);
    h.spatial_render=AV3A_RENDER_NATIVE; h.content_id=3;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==0 && mask==UINT32_MAX && !applied);
    assert(arcdav3a_publish_contents(&h,applied)==0); puts(h.contents_json);
    h.spatial_render=AV3A_RENDER_BINAURAL; h.content_id=-1;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==0 && mask==UINT32_MAX && !applied);
    h.content_id=3; provider.num_contents=3;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==AVERROR(EINVAL));
    provider.num_contents=4; provider.contents[3].pcm_channel_mask=1u<<30;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==AVERROR_INVALIDDATA);
    provider_ret=0; provider.available=0; provider.status=AVS3_CONTENTS_NO_METADATA;
    for(int i=0;i<64;i++) {
        assert(arcdav3a_content_mask(&h,&mask,&applied)==0 && mask==0 && !applied);
    }
    assert(arcdav3a_content_mask(&h,&mask,&applied)==AVERROR_INVALIDDATA);
    provider.status=AVS3_CONTENTS_INVALID;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==AVERROR_INVALIDDATA);
    h.content_id=-1;
    assert(arcdav3a_content_mask(&h,&mask,&applied)==0 && mask==UINT32_MAX);
    h.spatial_frame_count=h.spatial_frame_capacity;
    alloc_fail=1;
    assert(arcdav3a_append_spatial_frame(&h,0,0)==AVERROR(ENOMEM));
    h.contents_json[0]='x';
    assert(arcdav3a_publish_contents(&h,0)==AVERROR(ENOMEM));
    free(h.contents_json);free(h.spatial_frames);
    return 0;
}
'''

if __name__ == '__main__':
    run()
