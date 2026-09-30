// Compile against the production helper and matching libavutil headers.
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "video/dovi_metadata.h"

struct sample {
    AVDOVIMetadata metadata;
    AVDOVIRpuDataHeader header;
    AVDOVIDataMapping mapping;
};

static struct sample mel_sample(unsigned denom)
{
    struct sample sample = {0};
    sample.metadata.header_offset = offsetof(struct sample, header);
    sample.metadata.mapping_offset = offsetof(struct sample, mapping);
    sample.header.rpu_type = 2;
    sample.header.rpu_format = 18;
    sample.header.vdr_rpu_profile = 1;
    sample.header.vdr_bit_depth = 12;
    sample.header.el_spatial_resampling_filter_flag = 1;
    sample.header.coef_log2_denom = denom;
    sample.mapping.nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    for (int c = 0; c < 3; c++)
        sample.mapping.nlq[c].vdr_in_max = UINT64_C(1) << denom;
    return sample;
}

static void check_type(struct sample *sample, const char *type)
{
    struct mp_dovi_metadata_info info = mp_dovi_metadata_read(sample, sizeof(*sample));
    assert(info.rpu_present);
    assert(type ? info.el_type && strcmp(info.el_type, type) == 0 : !info.el_type);
}

int main(void)
{
    // Fixed and originally floating coefficients use the same decoded units.
    for (unsigned denom = 13; denom <= 32; denom++) {
        struct sample sample = mel_sample(denom);
        check_type(&sample, "MEL");
        sample.header.coef_data_type = 1;
        check_type(&sample, "MEL");
        for (int c = 0; c < 3; c++) {
            sample = mel_sample(denom);
            sample.mapping.nlq[c].nlq_offset = 1;
            check_type(&sample, "FEL");
            sample = mel_sample(denom);
            sample.mapping.nlq[c].vdr_in_max++;
            check_type(&sample, "FEL");
            sample = mel_sample(denom);
            sample.mapping.nlq[c].linear_deadzone_slope = 1;
            check_type(&sample, "FEL");
            sample = mel_sample(denom);
            sample.mapping.nlq[c].linear_deadzone_threshold = 1;
            check_type(&sample, "FEL");
        }
    }

    struct sample sample = mel_sample(23);
    sample.header.disable_residual_flag = 1; // P8/no EL is not MEL.
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.header.vdr_rpu_profile = 0; // P5.
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.header.vdr_bit_depth = 10; // P4.
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.header.el_spatial_resampling_filter_flag = 0;
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.header.rpu_format |= 0x100;
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.mapping.nlq_method_idc = AV_DOVI_NLQ_NONE;
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.header.coef_log2_denom = 64;
    check_type(&sample, NULL); // No undefined shift.

    assert(!mp_dovi_metadata_read(NULL, sizeof(sample)).rpu_present);
    assert(!mp_dovi_metadata_read(&sample, sizeof(AVDOVIMetadata) - 1).rpu_present);
    sample = mel_sample(23);
    sample.metadata.header_offset = SIZE_MAX;
    assert(!mp_dovi_metadata_read(&sample, sizeof(sample)).rpu_present);
    sample = mel_sample(23);
    sample.metadata.header_offset = sizeof(sample) - 1;
    assert(!mp_dovi_metadata_read(&sample, sizeof(sample)).rpu_present);
    sample = mel_sample(23);
    sample.metadata.header_offset++;
    assert(!mp_dovi_metadata_read(&sample, sizeof(sample)).rpu_present);
    sample = mel_sample(23);
    sample.metadata.header_offset = 0;
    assert(!mp_dovi_metadata_read(&sample, sizeof(sample)).rpu_present);
    sample = mel_sample(23);
    sample.header.rpu_type = 0;
    assert(!mp_dovi_metadata_read(&sample, sizeof(sample)).rpu_present);
    sample = mel_sample(23);
    sample.metadata.mapping_offset = SIZE_MAX;
    check_type(&sample, NULL);
    sample = mel_sample(23);
    sample.metadata.mapping_offset++;
    check_type(&sample, NULL);
    sample = mel_sample(23);
    struct mp_dovi_metadata_info truncated =
        mp_dovi_metadata_read(&sample, offsetof(struct sample, mapping));
    assert(truncated.rpu_present && !truncated.el_type);
    puts("Decoded DOVI metadata identification and bounds PASS");
    return 0;
}
