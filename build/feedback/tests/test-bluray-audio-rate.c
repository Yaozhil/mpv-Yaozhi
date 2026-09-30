// Compile against the real libbluray header and the production helper:
// cc -std=c11 -Wall -Wextra -Werror -I MPV_SOURCE -I LIBBLURAY_INCLUDE
//    test-bluray-audio-rate.c -o test-bluray-audio-rate
#include <stdio.h>
#include "stream/bluray_audio_rate.h"

struct rate_case {
    int coding_type, rate;
    const char *codec;
    int expected;
};

int main(void)
{
    // Rates 12/14 describe different HD and compatibility presentations; in
    // particular the 192 kHz DTS core is ambiguous and must remain unknown.
    const struct rate_case cases[] = {
        {0x86, 4, "dts", 96000}, // Pretty Crazy DISC1 full DTS-HD MA
        {0x80, 4, "pcm_bluray", 96000},
        {0x81, 1, "ac3", 48000},
        {0x86, 1, "dts", 48000},
        {0x86, 5, "dts", 192000},
        {0x85, 14, "dts", 96000},
        {0x86, 14, "dts", 96000},
        {0xa2, 14, "dts", 96000},
        {0x85, 12, "dts", 192000},
        {0x86, 12, "dts", 192000},
        {0xa2, 12, "dts", 192000},
        {0x82, 14, "dts", 48000},
        {0x82, 12, "dts", 0},
        {0x82, 4, "dts", 96000},
        {0x83, 1, "truehd", 48000},
        {0x83, 4, "truehd", 96000},
        {0x83, 5, "truehd", 192000},
        {0x83, 14, "truehd", 96000},
        {0x83, 12, "truehd", 192000},
        {0x83, 1, "ac3", 48000},
        {0x83, 4, "ac3", 48000},
        {0x83, 5, "ac3", 48000},
        {0x83, 14, "ac3", 48000},
        {0x83, 12, "ac3", 48000},
        {0x84, 1, "eac3", 48000},
        {0xa1, 1, "eac3", 48000},
        {0x80, 1, "pcm_bluray", 48000},
        {0x80, 5, "pcm_bluray", 192000},
        {0x86, 0, "dts", 0},
        {0x83, 0, "truehd", 0}, // existing unknown-rate fallback stays usable
        {0x83, 0, "ac3", 0},
        {0x86, 15, "dts", 0},
        {0x86, 4, "ac3", 0},
        {0x83, 4, "dts", 0},
        {0x80, 4, "truehd", 0},
        {0x84, 1, "ac3", 0},
        {0x81, 1, "eac3", 0},
        {0x82, 1, "truehd", 0},
        {0xff, 4, "dts", 0},
        {0x86, 4, NULL, 0},
    };
    int count = sizeof(cases) / sizeof(cases[0]);
    for (int i = 0; i < count; i++) {
        const struct rate_case *c = &cases[i];
        int got = mp_bluray_audio_sample_rate(c->coding_type, c->rate, c->codec);
        if (got != c->expected) {
            fprintf(stderr, "case %d: coding=0x%x rate=%d codec=%s: %d != %d\n",
                    i, c->coding_type, c->rate, c->codec ? c->codec : "NULL",
                    got, c->expected);
            return 1;
        }
    }
    printf("BLURAY_AUDIO_RATE_PASS %d cases\n", count);
    return 0;
}
