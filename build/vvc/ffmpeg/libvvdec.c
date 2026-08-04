/*
 * H.266 decoding using the VVdeC library
 *
 * Copyright (C) 2022, Thomas Siedel
 *
 * This file is part of FFmpeg.
 *
 * FFmpeg is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * FFmpeg is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with FFmpeg; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

#include <vvdec/vvdec.h>
#include <vvdec/version.h>

#include "libavutil/avutil.h"
#include "libavutil/common.h"
#include "libavutil/frame.h"
#include "libavutil/imgutils.h"
#include "libavutil/log.h"
#include "libavutil/mastering_display_metadata.h"
#include "libavutil/opt.h"
#include "libavutil/pixdesc.h"

#include "avcodec.h"
#include "cbs_h266.h"
#include "codec_internal.h"
#include "decode.h"
#include "internal.h"
#include "profiles.h"

#define VVDEC_VERSION_INT  AV_VERSION_INT(VVDEC_VERSION_MAJOR, \
                                          VVDEC_VERSION_MINOR, \
                                          VVDEC_VERSION_PATCH)

typedef struct VVdeCContext {
    AVClass      *av_class;
    vvdecDecoder *decoder;
    vvdecParams   params;
    bool          flush;
    AVBufferPool *pools[3];     /** Pools for each data plane. */
    int           pool_size[3];
    CodedBitstreamContext *cbc;
    CodedBitstreamFragment current_frame;
#if VVDEC_VERSION_INT > AV_VERSION_INT(2,3,0)
    bool          filmgrain;
#endif
} VVdeCContext;


static void vvdec_log_callback(void *avctx, int level, const char *fmt,
                               va_list args)
{
    vfprintf(level == 1 ? stderr : stdout, fmt, args);
}

static void *vvdec_buffer_allocator(void *ctx, vvdecComponentType comp,
                                    uint32_t size, uint32_t alignment,
                                    void **allocator)
{
    AVBufferRef *buf;
    VVdeCContext *s = ctx;
    int plane = (int)comp;
    uint32_t alignedsize = FFALIGN(size, alignment);

    if (plane < 0 || plane >= (int)FF_ARRAY_ELEMS(s->pools))
        return NULL;

    if (alignedsize != s->pool_size[plane]) {
        av_buffer_pool_uninit(&s->pools[plane]);
        s->pools[plane] = av_buffer_pool_init(alignedsize, NULL);
        if (!s->pools[plane]) {
            s->pool_size[plane] = 0;
            return NULL;
        }
        s->pool_size[plane] = alignedsize;
    }

    buf = av_buffer_pool_get(s->pools[plane]);
    if (!buf)
        return NULL;

    *allocator = (void *) buf;
    return buf->data;
}

static void vvdec_buffer_unref(void *ctx, void *allocator)
{
    AVBufferRef *buf = allocator;
    av_buffer_unref(&buf);
}

static void vvdec_printParameterInfo(AVCodecContext *avctx, vvdecParams *params)
{
    av_log(avctx, AV_LOG_DEBUG, "Version info: vvdec %s ( threads %d)\n",
           vvdec_get_version(), params->threads);
}

static int vvdec_set_pix_fmt(AVCodecContext *avctx, vvdecFrame *frame)
{
    if (NULL != frame->picAttributes && NULL != frame->picAttributes->vui &&
        frame->picAttributes->vui->colourDescriptionPresentFlag) {
        avctx->color_trc       = frame->picAttributes->vui->transferCharacteristics;
        avctx->color_primaries = frame->picAttributes->vui->colourPrimaries;
        avctx->colorspace      = frame->picAttributes->vui->matrixCoefficients;
    } else {
        avctx->color_primaries = AVCOL_PRI_UNSPECIFIED;
        avctx->color_trc       = AVCOL_TRC_UNSPECIFIED;
        avctx->colorspace      = AVCOL_SPC_UNSPECIFIED;
    }

    if (NULL != frame->picAttributes && NULL != frame->picAttributes->vui &&
        frame->picAttributes->vui->videoSignalTypePresentFlag) {
        avctx->color_range = frame->picAttributes->vui->videoFullRangeFlag ?
                             AVCOL_RANGE_JPEG : AVCOL_RANGE_MPEG;
    } else {
        avctx->color_range = AVCOL_RANGE_MPEG;
    }

    switch (frame->colorFormat) {
    case VVDEC_CF_YUV420_PLANAR:
    case VVDEC_CF_YUV400_PLANAR:
        if (frame->bitDepth == 8) {
            avctx->pix_fmt = frame->numPlanes == 1 ? AV_PIX_FMT_GRAY8 : AV_PIX_FMT_YUV420P;
            avctx->profile = AV_PROFILE_VVC_MAIN_10;
            return 0;
        } else if (frame->bitDepth == 10) {
            avctx->pix_fmt = frame->numPlanes == 1 ? AV_PIX_FMT_GRAY10 : AV_PIX_FMT_YUV420P10;
            avctx->profile = AV_PROFILE_VVC_MAIN_10;
            return 0;
        } else {
            return AVERROR_INVALIDDATA;
        }
    case VVDEC_CF_YUV422_PLANAR:
    case VVDEC_CF_YUV444_PLANAR:
        if (frame->bitDepth == 8) {
            avctx->pix_fmt = frame->colorFormat == VVDEC_CF_YUV444_PLANAR ?
                             AV_PIX_FMT_YUV444P : AV_PIX_FMT_YUV422P;
            if (avctx->profile != AV_PROFILE_VVC_MAIN_10_444)
                avctx->profile = AV_PROFILE_VVC_MAIN_10_444;
            return 0;
        } else if (frame->bitDepth == 10) {
            avctx->pix_fmt = frame->colorFormat == VVDEC_CF_YUV444_PLANAR ?
                             AV_PIX_FMT_YUV444P10 : AV_PIX_FMT_YUV422P10;
            if (avctx->profile != AV_PROFILE_VVC_MAIN_10_444)
                avctx->profile = AV_PROFILE_VVC_MAIN_10_444;
            return 0;
        } else {
            return AVERROR_INVALIDDATA;
        }
    default:
        return AVERROR_INVALIDDATA;
    }
}

static int set_side_data(AVCodecContext *avctx, AVFrame *avframe,
                         vvdecFrame *frame)
{
    vvdecSEI *sei;
    VVdeCContext *s = avctx->priv_data;

    sei = vvdec_find_frame_sei(s->decoder, VVDEC_MASTERING_DISPLAY_COLOUR_VOLUME, frame);
    if (sei) {
        /* VVC uses a g,b,r ordering, which we convert to a more natural r,g,b */
        const int mapping[3] = { 2, 0, 1 };
        const int chroma_den = 50000;
        const int luma_den = 10000;
        int i;
        vvdecSEIMasteringDisplayColourVolume *p;
        p = (vvdecSEIMasteringDisplayColourVolume *) (sei->payload);
        if (p) {
            AVMasteringDisplayMetadata *metadata =
                av_mastering_display_metadata_create_side_data(avframe);
            if (!metadata)
                return AVERROR(ENOMEM);
            for (i = 0; i < 3; i++) {
                const int j = mapping[i];
                metadata->display_primaries[i][0].num = p->primaries[j][0];
                metadata->display_primaries[i][0].den = chroma_den;
                metadata->display_primaries[i][1].num = p->primaries[j][1];
                metadata->display_primaries[i][1].den = chroma_den;
            }
            metadata->white_point[0].num = p->whitePoint[0];
            metadata->white_point[0].den = chroma_den;
            metadata->white_point[1].num = p->whitePoint[1];
            metadata->white_point[1].den = chroma_den;

            metadata->max_luminance.num = p->maxLuminance;
            metadata->max_luminance.den = luma_den;
            metadata->min_luminance.num = p->minLuminance;
            metadata->min_luminance.den = luma_den;
            metadata->has_luminance = 1;
            metadata->has_primaries = 1;

            av_log(avctx, AV_LOG_DEBUG, "Mastering Display Metadata:\n");
            av_log(avctx, AV_LOG_DEBUG,
                   "r(%5.4f,%5.4f) g(%5.4f,%5.4f) b(%5.4f %5.4f) wp(%5.4f, %5.4f)\n",
                   av_q2d(metadata->display_primaries[0][0]),
                   av_q2d(metadata->display_primaries[0][1]),
                   av_q2d(metadata->display_primaries[1][0]),
                   av_q2d(metadata->display_primaries[1][1]),
                   av_q2d(metadata->display_primaries[2][0]),
                   av_q2d(metadata->display_primaries[2][1]),
                   av_q2d(metadata->white_point[0]),
                   av_q2d(metadata->white_point[1]));
            av_log(avctx, AV_LOG_DEBUG, "min_luminance=%f, max_luminance=%f\n",
                   av_q2d(metadata->min_luminance),
                   av_q2d(metadata->max_luminance));
        }
    }

    sei = vvdec_find_frame_sei(s->decoder, VVDEC_CONTENT_LIGHT_LEVEL_INFO,
                               frame);
    if (sei) {
        vvdecSEIContentLightLevelInfo *p = NULL;
        p = (vvdecSEIContentLightLevelInfo *) (sei->payload);
        if (p) {
            AVContentLightMetadata *light =
                av_content_light_metadata_create_side_data(avframe);
            if (!light)
                return AVERROR(ENOMEM);
            light->MaxCLL  = p->maxContentLightLevel;
            light->MaxFALL = p->maxPicAverageLightLevel;

            av_log(avctx, AV_LOG_DEBUG, "Content Light Level Metadata:\n");
            av_log(avctx, AV_LOG_DEBUG, "MaxCLL=%d, MaxFALL=%d\n",
                   light->MaxCLL, light->MaxFALL);
        }
    }

    return 0;
}

static int set_pixel_format(AVCodecContext *avctx, const H266RawSPS *sps)
{
    enum AVPixelFormat pix_fmt = AV_PIX_FMT_NONE;
    const AVPixFmtDescriptor *desc;
    switch (sps->sps_bitdepth_minus8 + 8) {
    case 8:
        if (sps->sps_chroma_format_idc == 0)
            pix_fmt = AV_PIX_FMT_GRAY8;
        if (sps->sps_chroma_format_idc == 1)
            pix_fmt = AV_PIX_FMT_YUV420P;
        if (sps->sps_chroma_format_idc == 2)
            pix_fmt = AV_PIX_FMT_YUV422P;
        if (sps->sps_chroma_format_idc == 3)
            pix_fmt = AV_PIX_FMT_YUV444P;
        break;
    case 9:
        if (sps->sps_chroma_format_idc == 0)
            pix_fmt = AV_PIX_FMT_GRAY9;
        if (sps->sps_chroma_format_idc == 1)
            pix_fmt = AV_PIX_FMT_YUV420P9;
        if (sps->sps_chroma_format_idc == 2)
            pix_fmt = AV_PIX_FMT_YUV422P9;
        if (sps->sps_chroma_format_idc == 3)
            pix_fmt = AV_PIX_FMT_YUV444P9;
        break;
    case 10:
        if (sps->sps_chroma_format_idc == 0)
            pix_fmt = AV_PIX_FMT_GRAY10;
        if (sps->sps_chroma_format_idc == 1)
            pix_fmt = AV_PIX_FMT_YUV420P10;
        if (sps->sps_chroma_format_idc == 2)
            pix_fmt = AV_PIX_FMT_YUV422P10;
        if (sps->sps_chroma_format_idc == 3)
            pix_fmt = AV_PIX_FMT_YUV444P10;
        break;
    case 12:
        if (sps->sps_chroma_format_idc == 0)
            pix_fmt = AV_PIX_FMT_GRAY12;
        if (sps->sps_chroma_format_idc == 1)
            pix_fmt = AV_PIX_FMT_YUV420P12;
        if (sps->sps_chroma_format_idc == 2)
            pix_fmt = AV_PIX_FMT_YUV422P12;
        if (sps->sps_chroma_format_idc == 3)
            pix_fmt = AV_PIX_FMT_YUV444P12;
        break;
    default:
        av_log(avctx, AV_LOG_ERROR,
               "The following bit-depths are currently specified: 8, 9, 10 and 12 bits, "
               "sps_chroma_format_idc is %d, depth is %d\n",
               sps->sps_chroma_format_idc, sps->sps_bitdepth_minus8 + 8);
        return AVERROR_INVALIDDATA;
    }

    desc = av_pix_fmt_desc_get(pix_fmt);
    if (!desc)
        return AVERROR(EINVAL);

    avctx->pix_fmt = pix_fmt;

    return 0;
}

static void export_stream_params(AVCodecContext *avctx, const H266RawSPS *sps)
{
    avctx->coded_width  = sps->sps_pic_width_max_in_luma_samples;
    avctx->coded_height = sps->sps_pic_height_max_in_luma_samples;
    avctx->width        = sps->sps_pic_width_max_in_luma_samples -
                          sps->sps_conf_win_left_offset -
                          sps->sps_conf_win_right_offset;
    avctx->height       = sps->sps_pic_height_max_in_luma_samples -
                          sps->sps_conf_win_top_offset -
                          sps->sps_conf_win_bottom_offset;
    avctx->has_b_frames = sps->sps_max_sublayers_minus1 + 1;
    avctx->profile      = sps->profile_tier_level.general_profile_idc;
    avctx->level        = sps->profile_tier_level.general_level_idc;

    set_pixel_format( avctx, sps);

    avctx->color_range = sps->vui.vui_full_range_flag ? AVCOL_RANGE_JPEG :
                         AVCOL_RANGE_MPEG;

    if (sps->vui.vui_colour_description_present_flag) {
        avctx->color_primaries = sps->vui.vui_colour_primaries;
        avctx->color_trc       = sps->vui.vui_transfer_characteristics;
        avctx->colorspace      = sps->vui.vui_matrix_coeffs;
    } else {
        avctx->color_primaries = AVCOL_PRI_UNSPECIFIED;
        avctx->color_trc       = AVCOL_TRC_UNSPECIFIED;
        avctx->colorspace      = AVCOL_SPC_UNSPECIFIED;
    }

    avctx->chroma_sample_location = AVCHROMA_LOC_UNSPECIFIED;
    if (sps->sps_chroma_format_idc == 1) {
        if (sps->vui.vui_chroma_loc_info_present_flag) {
            if (sps->vui.vui_chroma_sample_loc_type_top_field <= 5)
                avctx->chroma_sample_location =
                    sps->vui.vui_chroma_sample_loc_type_top_field + 1;
        } else
            avctx->chroma_sample_location = AVCHROMA_LOC_LEFT;
    }

    if (sps->sps_timing_hrd_params_present_flag &&
        sps->sps_general_timing_hrd_parameters.num_units_in_tick &&
        sps->sps_general_timing_hrd_parameters.time_scale) {
        av_reduce(&avctx->framerate.den, &avctx->framerate.num,
                  sps->sps_general_timing_hrd_parameters.num_units_in_tick,
                  sps->sps_general_timing_hrd_parameters.time_scale, INT_MAX);
    }
}

static av_cold int vvdec_dec_init(AVCodecContext *avctx)
{
    int i, loglevel, ret;
    VVdeCContext *s = avctx->priv_data;

    vvdec_params_default(&s->params);
    s->params.logLevel = VVDEC_DETAILS;

    loglevel = av_log_get_level();
    if (loglevel >= AV_LOG_DEBUG)
        s->params.logLevel = VVDEC_DETAILS;
    else if (loglevel >= AV_LOG_VERBOSE)
        s->params.logLevel = VVDEC_INFO;
    else if (loglevel >= AV_LOG_INFO)
        s->params.logLevel = VVDEC_WARNING;
    else
        s->params.logLevel = VVDEC_SILENT;

    if (avctx->thread_count > 0)
        s->params.threads = avctx->thread_count;
    else
        s->params.threads = -1; /* get max cpus */

#if VVDEC_VERSION_INT > AV_VERSION_INT(2,3,0)
    s->params.filmGrainSynthesis = s->filmgrain;
#endif

    vvdec_printParameterInfo(avctx, &s->params);

    for (i = 0; i < FF_ARRAY_ELEMS(s->pools); i++) {
        s->pools[i] = NULL;
        s->pool_size[i] = 0;
    }

    /* using buffer allocation by using AVBufferPool */
    s->params.opaque = avctx->priv_data;
    s->decoder = vvdec_decoder_open_with_allocator(&s->params, vvdec_buffer_allocator, vvdec_buffer_unref);
    if (!s->decoder) {
        av_log(avctx, AV_LOG_ERROR, "cannot init vvdec decoder\n");
        return AVERROR_EXTERNAL;
    }

    vvdec_set_logging_callback(s->decoder, vvdec_log_callback);

    s->flush = false;

    ret = ff_cbs_init(&s->cbc, AV_CODEC_ID_VVC, avctx);
    if (ret)
        return ret;

    if (!avctx->internal->is_copy) {
        if (avctx->extradata_size > 0 && avctx->extradata) {
            const CodedBitstreamH266Context *h266 = s->cbc->priv_data;
            ff_cbs_fragment_reset(&s->current_frame);
            ret = ff_cbs_read_extradata_from_codec(s->cbc, &s->current_frame, avctx);
            if (ret < 0)
                return ret;

            if (h266->sps[0] != NULL)
                export_stream_params(avctx, h266->sps[0]);
        }
    }

    return 0;
}

static av_cold int vvdec_dec_close(AVCodecContext *avctx)
{
    VVdeCContext *s = avctx->priv_data;

    for (int i = 0; i < FF_ARRAY_ELEMS(s->pools); i++) {
        av_buffer_pool_uninit(&s->pools[i]);
        s->pool_size[i] = 0;
    }

    ff_cbs_fragment_free(&s->current_frame);
    ff_cbs_close(&s->cbc);

    s->flush = false;

    if (s->decoder) {
        int close_ret = vvdec_decoder_close(s->decoder);
        s->decoder = NULL;
        if (close_ret)
            return AVERROR_EXTERNAL;
    }

    return 0;
}

static av_cold int vvdec_dec_frame(AVCodecContext *avctx, AVFrame *data,
                                   int *got_frame, AVPacket *avpkt)
{
    VVdeCContext *s = avctx->priv_data;
    AVFrame *avframe = data;
    AVBufferRef *plane_bufs[3] = { NULL };

    int ret = 0;
    vvdecFrame *frame = NULL;

    if (!s->decoder) {
        av_log(avctx, AV_LOG_ERROR, "vvdec decoder is unavailable\n");
        return AVERROR_EXTERNAL;
    }

    if (avframe) {
        if (!avpkt->size && !s->flush)
            s->flush = true;

        if (s->flush)
            ret = vvdec_flush(s->decoder, &frame);
        else {
            vvdecAccessUnit accessUnit;
            vvdec_accessUnit_default(&accessUnit);
            accessUnit.payload = avpkt->data;
            accessUnit.payloadSize = avpkt->size;
            accessUnit.payloadUsedSize = avpkt->size;

            accessUnit.cts = avpkt->pts;
            accessUnit.ctsValid = avpkt->pts != AV_NOPTS_VALUE;
            accessUnit.dts = avpkt->dts;
            accessUnit.dtsValid = avpkt->dts != AV_NOPTS_VALUE;

            ret = vvdec_decode(s->decoder, &accessUnit, &frame);
        }

        if (ret < 0) {
            if (ret == VVDEC_EOF)
                s->flush = true;
            else if (ret != VVDEC_TRY_AGAIN) {
                av_log(avctx, AV_LOG_ERROR, "error in vvdec_decode - ret:%d - %s %s\n", ret,
                       vvdec_get_last_error(s->decoder), vvdec_get_last_additional_error( s->decoder));
                ret = AVERROR_EXTERNAL;
                goto fail;
            }
        } else if (NULL != frame) {
            const uint8_t *src_data[4] = { frame->planes[0].ptr,
                                           frame->planes[1].ptr,
                                           frame->planes[2].ptr, NULL
                                         };
            const int src_linesizes[4] = { (int) frame->planes[0].stride,
                                           (int) frame->planes[1].stride,
                                           (int) frame->planes[2].stride, 0
                                         };

            if ((ret = vvdec_set_pix_fmt(avctx, frame)) < 0) {
                av_log(avctx, AV_LOG_ERROR, "Unsupported output colorspace (%d) / bit_depth (%d)\n",
                       frame->colorFormat, frame->bitDepth);
                goto fail;
            }

            if ((int) frame->width != avctx->width ||
                (int) frame->height != avctx->height) {
                av_log(avctx, AV_LOG_INFO, "dimension change! %dx%d -> %dx%d\n",
                       avctx->width, avctx->height, frame->width, frame->height);

                ret = ff_set_dimensions(avctx, frame->width, frame->height);
                if (ret < 0)
                    goto fail;
            }

            for (int i = 0; i < FF_ARRAY_ELEMS(plane_bufs); i++) {
                if (!frame->planes[i].allocator)
                    continue;

                plane_bufs[i] =
                    av_buffer_ref((AVBufferRef *) frame->planes[i].allocator);
                if (!plane_bufs[i]) {
                    ret = AVERROR(ENOMEM);
                    goto fail;
                }
            }

            for (int i = 0; i < FF_ARRAY_ELEMS(plane_bufs); i++) {
                avframe->buf[i] = plane_bufs[i];
                plane_bufs[i] = NULL;
            }

            for (int i = 0; i < 4; i++) {
                avframe->data[i] = (uint8_t *) src_data[i];
                avframe->linesize[i] = src_linesizes[i];
            }

            ret = ff_decode_frame_props(avctx, avframe);
            if (ret < 0)
                goto fail;

            if (frame->picAttributes) {
                if (frame->picAttributes->isRefPic)
                    avframe->flags |= AV_FRAME_FLAG_KEY;
                else
                    avframe->flags &= ~AV_FRAME_FLAG_KEY;

                avframe->pict_type = (frame->picAttributes->sliceType != VVDEC_SLICETYPE_UNKNOWN) ?
                                     frame->picAttributes->sliceType + 1 : AV_PICTURE_TYPE_NONE;
            }

            if (frame->ctsValid)
                avframe->pts = frame->cts;

            ret = set_side_data(avctx, avframe, frame);
            if (ret < 0)
                goto fail;

            if (0 != vvdec_frame_unref(s->decoder, frame))
                av_log(avctx, AV_LOG_ERROR, "cannot free picture memory\n");

            *got_frame = 1;
        }
    }

    return avpkt->size;

fail:
    for (int i = 0; i < FF_ARRAY_ELEMS(plane_bufs); i++)
        av_buffer_unref(&plane_bufs[i]);

    av_frame_unref(avframe);

    if (frame) {
        if (vvdec_frame_unref(s->decoder, frame))
            av_log(avctx, AV_LOG_ERROR, "cannot free picture memory after decode failure\n");
    }
    return ret;
}

static av_cold void vvdec_dec_flush(AVCodecContext *avctx)
{
    VVdeCContext *s = avctx->priv_data;

    if (s->decoder && 0 != vvdec_decoder_close(s->decoder))
        av_log(avctx, AV_LOG_ERROR, "cannot close during flush\n");
    s->decoder = NULL;
    s->flush = false;

    s->decoder = vvdec_decoder_open_with_allocator(&s->params, vvdec_buffer_allocator, vvdec_buffer_unref);
    if (!s->decoder) {
        av_log(avctx, AV_LOG_ERROR, "cannot reinit during flush\n");
        return;
    }

    vvdec_set_logging_callback(s->decoder, vvdec_log_callback);
}

static const enum AVPixelFormat pix_fmts_vvdec[] = {
    AV_PIX_FMT_GRAY8,
    AV_PIX_FMT_GRAY10,
    AV_PIX_FMT_YUV420P,
    AV_PIX_FMT_YUV422P,
    AV_PIX_FMT_YUV444P,
    AV_PIX_FMT_YUV420P10,
    AV_PIX_FMT_YUV422P10,
    AV_PIX_FMT_YUV444P10,
    AV_PIX_FMT_NONE
};

#if VVDEC_VERSION_INT > AV_VERSION_INT(2,3,0)

#define OFFSET(x) offsetof(VVdeCContext, x)
#define VE AV_OPT_FLAG_VIDEO_PARAM | AV_OPT_FLAG_DECODING_PARAM
static const AVOption options[] = {
    { "filmgrain",    "set usage of filemgrain SEI", OFFSET(filmgrain), AV_OPT_TYPE_BOOL, {.i64 = 1},  0, 1, VE},
    {NULL}
};

#endif

static const AVClass class = {
    .class_name = "libvvdec",
    .item_name  = av_default_item_name,
#if VVDEC_VERSION_INT > AV_VERSION_INT(2,3,0)
    .option     = options,
#endif
    .version    = LIBAVUTIL_VERSION_INT,
};

const FFCodec ff_libvvdec_decoder = {
    .p.name         = "libvvdec",
    CODEC_LONG_NAME("libvvdec H.266 / VVC"),
    .p.type         = AVMEDIA_TYPE_VIDEO,
    .p.id           = AV_CODEC_ID_VVC,
    .p.capabilities = AV_CODEC_CAP_DELAY | AV_CODEC_CAP_OTHER_THREADS,
    .p.profiles     = NULL_IF_CONFIG_SMALL(ff_vvc_profiles),
    .p.priv_class   = &class,
    .p.wrapper_name = "libvvdec",
    .priv_data_size = sizeof(VVdeCContext),
    CODEC_PIXFMTS_ARRAY(pix_fmts_vvdec),
    .init           = vvdec_dec_init,
    FF_CODEC_DECODE_CB(vvdec_dec_frame),
    .close          = vvdec_dec_close,
    .flush          = vvdec_dec_flush,
    .bsfs           = "vvc_mp4toannexb",
    .caps_internal  = FF_CODEC_CAP_AUTO_THREADS | FF_CODEC_CAP_INIT_CLEANUP,
};
