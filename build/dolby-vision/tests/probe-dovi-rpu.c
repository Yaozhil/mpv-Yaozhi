// Links the exact player FFmpeg archives; does not generate or decode video.
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include <libavutil/mem.h>
#include <libavutil/avutil.h>
#include <libavcodec/avcodec.h>
#include "libavcodec/dovi_rpu.h"
#include "video/dovi_metadata.h"

int main(int argc, char **argv)
{
    if (argc != 3)
        return 2;
    FILE *input = fopen(argv[1], "rb");
    if (!input)
        return 3;
    uint8_t source[8192] = {0};
    size_t size = fread(source, 1, sizeof(source), input);
    int read_error = ferror(input) || size == sizeof(source);
    fclose(input);
    if (read_error || size < 5 || memcmp(source, "\0\0\0\1\x19", 5))
        return 4;

    // The upstream fixture is an escaped RPU with a four-byte start code.
    // FFmpeg's parser receives an unescaped payload starting with 0x19.
    uint8_t payload[8192 + AV_INPUT_BUFFER_PADDING_SIZE] = {0};
    size_t count = 0;
    for (size_t i = 4; i < size; i++) {
        if (i >= 6 && source[i] == 3 && !source[i - 1] && !source[i - 2] &&
            i + 1 < size && source[i + 1] <= 3)
            continue;
        payload[count++] = source[i];
    }

    DOVIContext context = {0};
    int result = ff_dovi_rpu_parse(&context, payload, count, 0);
    if (result < 0) {
        fprintf(stderr, "FFmpeg RPU parse failed: %d\n", result);
        ff_dovi_ctx_unref(&context);
        return 5;
    }
    AVDOVIMetadata *metadata = NULL;
    int metadata_size = ff_dovi_get_metadata(&context, &metadata);
    if (metadata_size <= 0 || !metadata) {
        ff_dovi_ctx_unref(&context);
        return 6;
    }
    struct mp_dovi_metadata_info info =
        mp_dovi_metadata_read(metadata, metadata_size);
    int profile = ff_dovi_guess_profile_hevc(av_dovi_get_header(metadata));
    int pass = info.rpu_present && profile == 7 && info.el_type &&
               strcmp(info.el_type, argv[2]) == 0;
    printf("{\"result\":\"%s\",\"el_type\":\"%s\","
           "\"rpu_present\":%s,\"profile\":%d,\"residual_disabled\":%s,"
           "\"codec_version\":%u,\"avutil_version\":%u}\n",
           pass ? "PASS" : "FAIL", info.el_type ? info.el_type : "unknown",
           info.rpu_present ? "true" : "false", profile,
           context.header.disable_residual_flag ? "true" : "false",
           avcodec_version(), avutil_version());
    av_free(metadata);
    ff_dovi_ctx_unref(&context);
    return pass ? 0 : 7;
}
