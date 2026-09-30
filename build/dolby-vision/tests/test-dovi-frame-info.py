"""Compile the exact production side-data reader with minimal image containers."""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--include', type=Path, required=True)
parser.add_argument('--compiler', default='gcc')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
command = (args.source / 'player/command.c').read_text(encoding='utf-8')
start = command.index('static struct mp_dovi_metadata_info read_dovi_frame_info(')
end = command.index('\n}\n', start) + 3
reader = command[start:end]
group_start = command.rfind('    struct sh_stream *sh = track->stream;',
                           0, command.index('    struct sh_stream *dv_el ='))
group_end = command.index('\n\n', command.index('    bool dv_group =', group_start))
group_reader = 'static bool read_dovi_group(struct track *track) {\n' + command[group_start:group_end] + '\n    return dv_group;\n}\n'
header = (args.source / 'demux/stheader.h').read_text(encoding='utf-8')
start = header.index('static inline struct sh_stream *sh_stream_dependent_sibling(')
end = header.index('\n}\n', start) + 3
dependent_reader = header[start:end]
args.output.mkdir(parents=True, exist_ok=True)
source = args.output / 'frame-info-test.c'
source.write_text(r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "video/dovi_metadata.h"
#define MP_ARRAY_SIZE(s) (sizeof(s) / sizeof((s)[0]))
enum { AV_FRAME_DATA_DOVI_RPU_BUFFER, AV_FRAME_DATA_DOVI_METADATA };
struct AVBufferRef { unsigned char *data; size_t size; };
struct mp_ff_side_data { int type; struct AVBufferRef *buf; };
struct mp_image {
    struct mp_ff_side_data *ff_side_data;
    int num_ff_side_data;
    struct mp_image *enhancement_layer;
};
enum { STREAM_VIDEO, STREAM_AUDIO };
struct mp_codec_params {
    bool dovi_el_only, dv_config_present, dv_config_el_present;
    unsigned char dv_profile;
};
struct sh_stream;
struct sh_stream_group { struct sh_stream **members; int num_members; };
struct sh_stream {
    bool dependent_track, absent;
    int type;
    struct mp_codec_params *codec;
    struct sh_stream_group *group;
};
struct track { struct sh_stream *stream; };
''' + dependent_reader + '\n' + group_reader + '\n' + reader + r'''
struct sample {
    AVDOVIMetadata metadata;
    AVDOVIRpuDataHeader header;
    AVDOVIDataMapping mapping;
};
int main(void) {
    struct sample metadata = {0};
    metadata.metadata.header_offset = offsetof(struct sample, header);
    metadata.metadata.mapping_offset = offsetof(struct sample, mapping);
    metadata.header.rpu_type = 2;
    metadata.header.rpu_format = 18;
    metadata.header.vdr_rpu_profile = 1;
    metadata.header.vdr_bit_depth = 12;
    metadata.header.el_spatial_resampling_filter_flag = 1;
    metadata.header.coef_log2_denom = 23;
    metadata.mapping.nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    for (int c = 0; c < 3; c++)
        metadata.mapping.nlq[c].vdr_in_max = UINT64_C(1) << 23;
    struct AVBufferRef buffer = {(unsigned char *)&metadata, sizeof(metadata)};
    struct mp_ff_side_data side = {AV_FRAME_DATA_DOVI_METADATA, &buffer};
    struct mp_image base = {0}, el = {&side, 1, NULL};
    struct mp_dovi_metadata_info info = read_dovi_frame_info(&base);
    assert(!info.rpu_present && !info.el_type);
    base.enhancement_layer = &el;
    info = read_dovi_frame_info(&base);
    assert(info.rpu_present && strcmp(info.el_type, "MEL") == 0);
    metadata.mapping.nlq[2].linear_deadzone_slope = 1;
    info = read_dovi_frame_info(&base);
    assert(info.rpu_present && strcmp(info.el_type, "FEL") == 0);
    base.enhancement_layer = NULL;
    info = read_dovi_frame_info(&base);
    assert(!info.rpu_present && !info.el_type); // No sticky previous EL.
    base.ff_side_data = &side; base.num_ff_side_data = 1;
    info = read_dovi_frame_info(&base);
    assert(info.rpu_present && strcmp(info.el_type, "FEL") == 0);
    metadata.header.disable_residual_flag = 1;
    info = read_dovi_frame_info(&base);
    assert(info.rpu_present && !info.el_type); // RPU/P8 is not MEL.
    buffer.size = 0;
    info = read_dovi_frame_info(&base);
    assert(!info.rpu_present && !info.el_type);
    side.type = AV_FRAME_DATA_DOVI_RPU_BUFFER;
    buffer.size = 1;
    info = read_dovi_frame_info(&base);
    assert(info.rpu_present && !info.el_type); // Raw-only never guesses subtype.
    buffer.size = 0;
    info = read_dovi_frame_info(&base);
    assert(!info.rpu_present && !info.el_type);
    side.buf = NULL;
    info = read_dovi_frame_info(&base);
    assert(!info.rpu_present && !info.el_type);
    struct mp_codec_params codec = {0};
    struct sh_stream bs = {.type = STREAM_VIDEO};
    struct sh_stream es = {.type = STREAM_VIDEO, .dependent_track = true, .codec = &codec};
    struct sh_stream *members[] = {&bs, &es};
    struct sh_stream_group group = {members, 2};
    struct track track = {&bs};
    assert(!read_dovi_group(&track));
    bs.group = &group;
    assert(!read_dovi_group(&track)); // Ordinary dependent HEVC is not DV.
    codec.dovi_el_only = true;
    assert(read_dovi_group(&track)); // Explicit split/MP4/authored BD marker.
    codec.dovi_el_only = false;
    codec.dv_profile = 7;
    assert(!read_dovi_group(&track)); // P7 alone is insufficient.
    codec.dv_config_present = true;
    codec.dv_config_el_present = true;
    assert(read_dovi_group(&track)); // MKV's actual P7 EL record.
    es.absent = true;
    assert(!read_dovi_group(&track));
    es.absent = false;
    es.type = STREAM_AUDIO;
    assert(!read_dovi_group(&track));
    es.type = STREAM_VIDEO;
    group.num_members = 3;
    assert(!read_dovi_group(&track));
    group.num_members = 2;
    bs.dependent_track = true;
    assert(!read_dovi_group(&track));
    bs.dependent_track = false;
    codec.dv_config_el_present = false;
    assert(!read_dovi_group(&track));
    codec.dovi_el_only = true;
    assert(read_dovi_group(&track)); // Group overrides in-band config EL=false.
    track.stream = NULL;
    assert(!read_dovi_group(&track));
    puts("Production frame reader and explicit Dolby stream-group semantics PASS");
    return 0;
}
''', encoding='utf-8')
binary = args.output / 'frame-info-test.exe'
subprocess.run([args.compiler, '-Wall', '-Wextra', '-Werror',
                '-I' + str(args.source), '-I' + str(args.include),
                str(source), '-o', str(binary)], check=True)
run = subprocess.run([str(binary.resolve())], check=True, capture_output=True, text=True)
result = {'result': 'PASS', 'scope': 'exact production frame reader/group decision + actual metadata helper; image/stream containers only are stubbed',
          'stdout': run.stdout.strip()}
(args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result))
