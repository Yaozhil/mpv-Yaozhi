/* Link against the exact candidate FFmpeg, then run on Windows (or native
 * FFmpeg with the same source). Callback counts catch the nested/custom IO
 * failure cleanup bug independently of mpv's public API version heuristic. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <libavformat/avformat.h>
#include <libavutil/error.h>
#include <libavutil/mem.h>

struct probe { int opens, closes, reads, offset, abort_read, valid; };
static const uint8_t wav[] = {
    'R','I','F','F',40,0,0,0,'W','A','V','E','f','m','t',' ',
    16,0,0,0,1,0,2,0,0x80,0xbb,0,0,0,0xee,2,0,4,0,16,0,
    'd','a','t','a',4,0,0,0,0,0,0,0
};

static int read_packet(void *opaque, uint8_t *buf, int size)
{
    struct probe *p = opaque;
    int len;
    p->reads++;
    if (p->abort_read)
        return AVERROR_EXIT;
    len = (int)sizeof(wav) - p->offset;
    if (len <= 0)
        return AVERROR_EOF;
    if (len > size)
        len = size;
    if (p->valid)
        memcpy(buf, wav + p->offset, len);
    else
        memset(buf, 0, len);
    p->offset += len;
    return len;
}

static int open_io(AVFormatContext *s, AVIOContext **pb, const char *url,
                   int flags, AVDictionary **options)
{
    struct probe *p = s->opaque;
    uint8_t *buffer = av_malloc(4096);
    (void)url; (void)flags; (void)options;
    if (!buffer)
        return AVERROR(ENOMEM);
    *pb = avio_alloc_context(buffer, 4096, 0, p, read_packet, NULL, NULL);
    if (!*pb) {
        av_free(buffer);
        return AVERROR(ENOMEM);
    }
    p->opens++;
    return 0;
}

static int close_io(AVFormatContext *s, AVIOContext *pb)
{
    struct probe *p = s->opaque;
    p->closes++;
    av_freep(&pb->buffer);
    avio_context_free(&pb);
    return 0;
}

static int test(const char *name, int abort_read, int valid, int provided)
{
    struct probe p = {0};
    AVFormatContext *s = avformat_alloc_context();
    AVIOContext *owned_pb = NULL;
    const AVInputFormat *format = av_find_input_format("wav");
    int ret, expected;
    if (!s || !format)
        return 2;
    p.abort_read = abort_read;
    p.valid = valid;
    s->opaque = &p;
    s->io_open = open_io;
    s->io_close2 = close_io;
    if (provided) {
        if (open_io(s, &owned_pb, "probe:provided", AVIO_FLAG_READ, NULL) < 0)
            return 3;
        s->pb = owned_pb;
    }
    ret = avformat_open_input(&s, "probe:custom", format, NULL);
    if (valid && !abort_read) {
        if (ret < 0 || !s)
            return 4;
        avformat_close_input(&s);
    } else if (ret >= 0 || s) {
        return 5;
    }
    expected = provided ? 0 : 1;
    if (p.opens != 1 || p.closes != expected || p.reads < 1 || s)
        return 6;
    if (owned_pb) {
        av_freep(&owned_pb->buffer);
        avio_context_free(&owned_pb);
    }
    printf("PASS %s opens=%d closes=%d reads=%d result=%d\n", name,
           p.opens, p.closes, p.reads, ret);
    return 0;
}

int main(void)
{
    int ret = 0;
    av_log_set_level(AV_LOG_QUIET);
    ret |= test("invalid-header-close-callback", 0, 0, 0);
    ret |= test("abort-read-close-callback", 1, 0, 0);
    ret |= test("normal-close-callback", 0, 1, 0);
    ret |= test("caller-owned-failure-retains-ownership", 0, 0, 1);
    ret |= test("caller-owned-abort-retains-ownership", 1, 0, 1);
    if (ret) {
        fprintf(stderr, "FAIL custom_io_cleanup code=%d\n", ret);
        return ret;
    }
    puts("PASS_CUSTOM_IO_CLEANUP_ALL_5");
    return 0;
}
