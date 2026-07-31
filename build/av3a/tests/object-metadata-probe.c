#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "avs3_decoder_interface.h"

#define OUTPUT_CAPACITY (4096U * 64U)

static int read_file(const char *path, unsigned char **data, size_t *size)
{
    FILE *file = fopen(path, "rb");
    long length;

    if (!file)
        return 0;
    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return 0;
    }
    length = ftell(file);
    if (length <= 0 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return 0;
    }
    *data = malloc((size_t)length);
    if (!*data) {
        fclose(file);
        return 0;
    }
    if (fread(*data, 1, (size_t)length, file) != (size_t)length) {
        free(*data);
        *data = NULL;
        fclose(file);
        return 0;
    }
    fclose(file);
    *size = (size_t)length;
    return 1;
}

static int float_changed(float a, float b)
{
    return !isfinite(a) || !isfinite(b) || fabsf(a - b) > 1.0e-6f;
}

static int object_changed(const AVS3SpatialObjectFrame *a,
                          const AVS3SpatialObjectFrame *b)
{
    return a->pcm_channel != b->pcm_channel ||
           a->position_valid != b->position_valid ||
           float_changed(a->x, b->x) ||
           float_changed(a->y, b->y) ||
           float_changed(a->z, b->z) ||
           a->gain_valid != b->gain_valid ||
           float_changed(a->gain_linear, b->gain_linear) ||
           a->muted != b->muted ||
           a->jump_position != b->jump_position ||
           float_changed(a->diffuse, b->diffuse) ||
           a->extent_valid != b->extent_valid ||
           float_changed(a->width, b->width) ||
           float_changed(a->height, b->height) ||
           float_changed(a->depth, b->depth) ||
           a->divergence_valid != b->divergence_valid ||
           float_changed(a->divergence, b->divergence) ||
           float_changed(a->divergence_azimuth_range,
                         b->divergence_azimuth_range) ||
           a->channel_lock_valid != b->channel_lock_valid ||
           a->channel_lock != b->channel_lock ||
           a->screen_ref_valid != b->screen_ref_valid ||
           a->screen_ref != b->screen_ref;
}

int main(int argc, char **argv)
{
    AVS3DecoderHandle decoder = NULL;
    unsigned char *input = NULL;
    unsigned char *output = NULL;
    size_t input_size = 0;
    size_t offset = 0;
    AVS3SpatialFrame previous = {0};
    int have_previous = 0;
    int object_changes[AVS3_SPATIAL_MAX_OBJECTS] = {0};
    int first = 1;
    int frames = 0;
    int dynamic_frames = 0;
    int changed_frames = 0;
    float first_object_x = 0.0f;
    float last_object_x = 0.0f;
    int result = 1;

    if (argc != 2 || !read_file(argv[1], &input, &input_size))
        return 2;
    output = malloc(OUTPUT_CAPACITY);
    decoder = avs3_create_decoder();
    if (!output || !decoder)
        goto done;

    while (offset < input_size) {
        AVS3SpatialStreamInfo info = {0};
        AVS3SpatialFrame spatial = {0};
        int consumed = 0;
        int output_size = 0;
        int frame_changed = 0;
        int ret;
        int i;

        ret = parse_header(decoder, input + offset,
                           (int)(input_size - offset), first,
                           &consumed, NULL);
        if (ret == AVS3_DECODER_NEED_MORE_DATA)
            break;
        if (ret != AVS3_DECODER_SUCCESS || consumed <= 0)
            goto done;
        offset += (size_t)consumed;

        info.struct_size = sizeof(info);
        if (avs3_get_spatial_stream_info(decoder, &info) !=
                AVS3_DECODER_SUCCESS)
            goto done;
        if (info.abi_version != AVS3_SPATIAL_ABI_VERSION ||
            info.format != AVS3_SPATIAL_FORMAT_BED_OBJECTS ||
            info.sample_rate != 48000 ||
            info.frame_length != 1024 ||
            info.bit_depth != 16 ||
            info.total_channels != 3 ||
            info.bed_channels != 2 ||
            info.object_channels != 1) {
            fprintf(stderr,
                    "unexpected stream info: abi=%u format=%d rate=%d "
                    "frame_length=%d bit_depth=%d total=%d bed=%d objects=%d\n",
                    info.abi_version, info.format, info.sample_rate,
                    info.frame_length, info.bit_depth, info.total_channels,
                    info.bed_channels, info.object_channels);
            goto done;
        }

        ret = avs3_decode(decoder, input + offset,
                          (int)(input_size - offset), output,
                          &output_size, &consumed);
        if (ret != AVS3_DECODER_SUCCESS || consumed <= 0 ||
            output_size <= 0 || output_size > (int)OUTPUT_CAPACITY)
            goto done;
        offset += (size_t)consumed;

        spatial.struct_size = sizeof(spatial);
        if (avs3_get_spatial_frame(decoder, &spatial) !=
                AVS3_DECODER_SUCCESS)
            goto done;
        if (spatial.abi_version != AVS3_SPATIAL_ABI_VERSION ||
            spatial.object_count != info.object_channels ||
            spatial.objects[0].pcm_channel != 2 ||
            !spatial.objects[0].position_valid ||
            !isfinite(spatial.objects[0].x) ||
            !isfinite(spatial.objects[0].y) ||
            !isfinite(spatial.objects[0].z) ||
            !isfinite(spatial.objects[0].gain_linear) ||
            fabsf(spatial.objects[0].gain_linear - 1.0f) > 1.0e-6f ||
            spatial.objects[0].muted ||
            spatial.objects[0].jump_position) {
            fprintf(stderr,
                    "unexpected object frame: abi=%u objects=%d channel=%d "
                    "position_valid=%d pos=%.6f,%.6f,%.6f gain_valid=%d "
                    "gain=%.6f mute=%d jump=%d\n",
                    spatial.abi_version, spatial.object_count,
                    spatial.objects[0].pcm_channel,
                    spatial.objects[0].position_valid,
                    spatial.objects[0].x, spatial.objects[0].y,
                    spatial.objects[0].z, spatial.objects[0].gain_valid,
                    spatial.objects[0].gain_linear,
                    spatial.objects[0].muted,
                    spatial.objects[0].jump_position);
            goto done;
        }

        if (!have_previous)
            first_object_x = spatial.objects[0].x;
        last_object_x = spatial.objects[0].x;

        if (spatial.has_dynamic_metadata)
            dynamic_frames++;
        if (have_previous) {
            for (i = 0; i < spatial.object_count; i++) {
                if (object_changed(&previous.objects[i],
                                   &spatial.objects[i])) {
                    object_changes[i]++;
                    frame_changed = 1;
                }
            }
            if (frame_changed)
                changed_frames++;
        }

        if (frames < 3 || frame_changed) {
            printf("frame=%d dynamic=%d", frames,
                   spatial.has_dynamic_metadata);
            for (i = 0; i < spatial.object_count; i++) {
                const AVS3SpatialObjectFrame *object =
                    &spatial.objects[i];
                printf(" obj%d[ch=%d pos=%.6f,%.6f,%.6f "
                       "gain=%.6f mute=%d jump=%d]",
                       i + 1, object->pcm_channel,
                       object->x, object->y, object->z,
                       object->gain_linear, object->muted,
                       object->jump_position);
            }
            putchar('\n');
        }

        previous = spatial;
        have_previous = 1;
        frames++;
        first = 0;
    }

    printf("summary frames=%d dynamic_frames=%d changed_frames=%d "
           "transport_channel=2 first_x=%.6f last_x=%.6f",
           frames, dynamic_frames, changed_frames,
           first_object_x, last_object_x);
    for (int i = 0; i < previous.object_count; i++)
        printf(" object%d_changes=%d", i + 1, object_changes[i]);
    putchar('\n');

    result = frames > 0 &&
             dynamic_frames == frames &&
             changed_frames > 0 &&
             fabsf(first_object_x - last_object_x) > 1.8f ? 0 : 1;

done:
    if (decoder)
        avs3_destroy_decoder(decoder);
    free(output);
    free(input);
    return result;
}
