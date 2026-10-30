"""Compile and execute the actual isolated core's cache helpers with small queues."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--compiler', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
source_path = args.source.resolve() / 'demux/demux.c'
source = source_path.read_text(encoding='utf-8')


def function(name):
    match = re.search(r"^static [^\n]*\b" + name + r"\([^;]*?\n\{", source, re.M)
    if not match:
        raise RuntimeError(name)
    start = match.start()
    brace = source.index("{", match.start())
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <math.h>
#define STREAM_VIDEO 0
#define STREAM_SUB 2
#define MP_NOPTS_VALUE (-1e20)
#define MP_PTS_MIN(a,b) ((a)==MP_NOPTS_VALUE ? (b) : (b)==MP_NOPTS_VALUE ? (a) : ((a)<(b)?(a):(b)))
#define MP_PTS_MAX(a,b) ((a)==MP_NOPTS_VALUE ? (b) : (b)==MP_NOPTS_VALUE ? (a) : ((a)>(b)?(a):(b)))
#define MPMIN(a,b) ((a)<(b)?(a):(b))
#define MP_ADD_PTS(a,b) ((a)==MP_NOPTS_VALUE ? MP_NOPTS_VALUE : (a)+(b))
#define MP_PTS_OR_DEF(a,b) ((a)==MP_NOPTS_VALUE ? (b) : (a))
#define MP_VERBOSE(...) ((void)0)
struct demux_internal;
struct demux_packet { struct demux_packet *next; uint64_t cum_pos; double pts, dts; };
struct index_entry { double pts; struct demux_packet *pkt; };
struct demux_stream {
    int type, index; bool cache_inactive, selected, eager, eof, need_wakeup, skip_to_keyframe;
    double back_seek_pos;
    struct demux_queue *queue;
    struct demux_internal *in;
    struct demux_packet *reader_head;
};
struct demux_queue {
    struct demux_stream *ds;
    struct demux_packet *head, *tail, *keyframe_first, *keyframe_latest;
    uint64_t tail_cum_pos;
    size_t index_size;
    double seek_start, seek_end, last_pruned, last_ts, last_dts;
    int64_t last_pos, last_pos_fixup;
    bool correct_dts, correct_pos, is_bof, is_eof, inactive_cache_discarded;
    struct index_entry *index;
};
struct demux_cached_range {
    struct demux_queue **streams; int num_streams;
    double seek_start, seek_end; bool is_bof, is_eof;
};
struct demux_internal {
    uint64_t max_bytes, total_bytes;
    struct demux_cached_range **ranges; int num_ranges;
    void *packet_pool;
    struct demux_cached_range *current_range;
    double ts_offset, demux_ts;
    bool back_demuxing, after_seek, after_seek_to_start;
    int num_streams;
    struct sh_stream **streams;
};
struct sh_stream { struct demux_stream *ds; int index; };
static void prune_metadata(struct demux_cached_range *r) { (void)r; }
static void free_index(struct demux_queue *q) {
    q->ds->in->total_bytes -= q->index_size * sizeof(q->index[0]);
    q->index_size = 0; free(q->index); q->index = NULL;
}
static void demux_packet_pool_prepend(void *pool, struct demux_packet *p,
                                      struct demux_packet *tail) {
    (void)pool; (void)tail;
    while (p) { struct demux_packet *next=p->next; free(p); p=next; }
}
static int refresh_count;
static void initiate_refresh_seek(struct demux_internal *in,
                                 struct demux_stream *ds, double pts) {
    (void)in; (void)ds; (void)pts; refresh_count++;
}
'''

tests = r'''
#define MiB (1024*1024ULL)
static struct demux_internal in;
static struct demux_stream ds[4];
static struct demux_queue q[8];
static struct demux_cached_range ranges[2];
static struct demux_queue *slots[2][4];
static struct demux_cached_range *range_ptrs[2];
static struct sh_stream sh[4];
static struct sh_stream *sh_ptrs[4];
static void setup(void) {
    in=(struct demux_internal){.max_bytes=256*MiB,.ranges=range_ptrs,.num_ranges=2,
        .current_range=&ranges[1],.num_streams=4,.streams=sh_ptrs};
    refresh_count=0;
    for(int n=0;n<4;n++) {
        ds[n]=(struct demux_stream){.type=STREAM_SUB,.cache_inactive=true,.in=&in,.index=n};
        sh[n]=(struct sh_stream){.ds=&ds[n],.index=n}; sh_ptrs[n]=&sh[n];
    }
    for(int r=0;r<2;r++) {
        ranges[r]=(struct demux_cached_range){.streams=slots[r],.num_streams=4};
        range_ptrs[r]=&ranges[r];
        for(int n=0;n<4;n++) {
            q[r*4+n]=(struct demux_queue){.ds=&ds[n],.seek_start=MP_NOPTS_VALUE,
                .seek_end=MP_NOPTS_VALUE,.last_pruned=MP_NOPTS_VALUE};
            slots[r][n]=&q[r*4+n];
            if(r==1) ds[n].queue=slots[r][n];
        }
    }
}
static void put(int r,int n,uint64_t bytes,bool index_only) {
    struct demux_queue *p=slots[r][n];
    if(index_only) {
        p->index_size=bytes/sizeof(p->index[0]);
        p->index=malloc(p->index_size*sizeof(p->index[0]));
    } else {
        p->head=p->tail=calloc(1,sizeof(*p->head));
        p->head->cum_pos=123; p->tail_cum_pos=123+bytes;
        if(r==1) ds[n].reader_head=p->head;
    }
    in.total_bytes+=queue_cached_bytes(p);
}
static void cleanup(void) {
    for(int r=0;r<2;r++) for(int n=0;n<4;n++) clear_queue(slots[r][n]);
    assert(in.total_bytes==0);
}
int main(void) {
    // Under-budget caches, reader pointer, and BOF coverage remain intact.
    setup(); put(1,0,MiB,false); q[4].is_bof=true;
    struct demux_packet *saved=ds[0].reader_head;
    assert(prune_inactive_subtitle_cache(&in,false)==0);
    assert(ds[0].reader_head==saved && q[4].is_bof); cleanup();

    // One queue above 4 MiB is completely discarded and its reader reset.
    setup(); put(1,0,5*MiB,false); q[4].is_bof=true;
    assert(prune_inactive_subtitle_cache(&in,false)==5*MiB);
    assert(q[4].inactive_cache_discarded && !q[4].head && !ds[0].reader_head);
    assert(!q[4].is_bof && in.total_bytes==0); cleanup();

    // The aggregate includes old ranges, rather than only the current range.
    setup(); in.max_bytes=8*MiB; // total budget 1 MiB, queue budget 256 KiB
    for(int r=0;r<2;r++) for(int n=0;n<4;n++) put(r,n,192*1024,false);
    assert(prune_inactive_subtitle_cache(&in,false)==3*192*1024);
    assert(q[0].inactive_cache_discarded && !q[3].inactive_cache_discarded);
    assert(ds[0].reader_head==q[4].head); // clearing an old queue preserves current reader
    assert(in.total_bytes<=MiB); cleanup();

    // Selected subtitles and non-subtitle streams are never reclaimed.
    setup(); ds[0].selected=true; ds[1].type=0;
    put(1,0,6*MiB,false); put(1,1,6*MiB,false); put(1,2,MiB,false);
    assert(prune_inactive_subtitle_cache(&in,true)==MiB);
    assert(q[4].head && q[5].head && !q[6].head); cleanup();

    // Index allocation counts even when there are no packet payloads.
    setup(); put(1,0,5*MiB,true);
    assert(prune_inactive_subtitle_cache(&in,false)==5*MiB);
    assert(!q[4].index_size && !q[4].index && !in.total_bytes); cleanup();

    // Tiny/zero budget and timestamp-less packets cannot bypass byte bounds.
    setup(); in.max_bytes=1; put(1,0,4096,false);
    assert(prune_inactive_subtitle_cache(&in,false)==4096); cleanup();

    // Cache coverage cannot be inferred from A/V when a selected queue has a gap.
    setup(); ds[0].selected=true; ds[0].eager=true;
    q[4].seek_start=0; q[4].seek_end=100;
    update_seek_ranges(&ranges[1]); assert(ranges[1].seek_start==0);
    q[4].inactive_cache_discarded=true;
    update_seek_ranges(&ranges[1]); assert(ranges[1].seek_start==MP_NOPTS_VALUE);
    clear_queue(&q[4]); assert(!q[4].inactive_cache_discarded);
    cleanup();

    // A discarded subtitle must refresh even immediately after a cached seek
    // when selected video would normally suppress refreshing another stream.
    setup(); ds[0].selected=true; ds[1].selected=true; ds[1].type=STREAM_VIDEO;
    in.after_seek=true; q[4].inactive_cache_discarded=true;
    ranges[1].seek_start=0; ranges[1].seek_end=100; in.demux_ts=100;
    refresh_track(&in,&sh[0],40);
    assert(refresh_count==1); cleanup();

    // An intact cached subtitle keeps the existing fast switch behavior.
    setup(); ds[0].selected=true; put(1,0,4096,false);
    q[4].head->pts=45; q[4].head->dts=MP_NOPTS_VALUE;
    ranges[1].seek_start=0; ranges[1].seek_end=100; in.demux_ts=100;
    refresh_track(&in,&sh[0],40);
    assert(refresh_count==0 && ds[0].reader_head==q[4].head); cleanup();
    puts("inactive subtitle cache: 9 executable contract cases passed");
}
'''

body = prefix + "\n" + "\n\n".join(function(name) for name in [
    "update_seek_ranges", "clear_queue", "ds_clear_reader_queue_state",
    "is_inactive_subtitle", "queue_cached_bytes", "prune_inactive_subtitle_cache",
    "refresh_track",
]) + tests
test_c = output / 'inactive_cache_contract.c'
test_c.write_text(body, encoding='utf-8')
exe = output / 'inactive_cache_contract.exe'
command = [args.compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
           str(test_c), '-o', str(exe)]
compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
(output / 'compile.stdout.log').write_text(compiled.stdout, encoding='utf-8')
(output / 'compile.stderr.log').write_text(compiled.stderr, encoding='utf-8')
report = {'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
          'translation_sha256': hashlib.sha256(test_c.read_bytes()).hexdigest(),
          'compile_command': command, 'compile_exit': compiled.returncode,
          'runtime_verified': False}
if compiled.returncode == 0:
    ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    report.update(exit=ran.returncode, stdout=ran.stdout, stderr=ran.stderr)
report['status'] = ('ACTUAL_DEMUX_CACHE_HELPERS_NINE_CONTRACT_CASES_PASS'
                    if report.get('exit') == 0 else 'DEMUX_CACHE_CONTRACT_FAILED')
(output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
if report.get('exit') != 0:
    raise SystemExit(1)
