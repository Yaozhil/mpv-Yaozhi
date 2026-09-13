"""Compile the actual MKV open-time deferred-header traversal with instrumented IO."""
import argparse,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--compiler',default='cc');a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
s=(a.source/'demux/demux_mkv.c').read_text(encoding='utf-8')
start=s.index('    int only_cue = -1;');end=s.index('    if (!stream_seek(s, start_pos))',start)
body=s[start:end]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#define MATROSKA_ID_CUES 1
#define MATROSKA_ID_TAGS 2
#define MP_WARN(...)
#define MP_VERBOSE(...)
struct header_elem {int id; int64_t pos; bool parsed;};
struct opts {bool read_tail_tags;};
struct mkv {struct header_elem headers[8];int num_headers;bool probably_webm_dash_init,eof_warning;struct opts *opts;};
struct stream {bool seekable;};
struct demux {int unused;};
static int reads[8],nreads,fail;
static int read_deferred_element(struct demux *d,struct header_elem *e) {reads[nreads++]=e->id;e->parsed=true;return fail?-1:0;}
static int scan(struct mkv *mkv_d,struct stream *s,int64_t end) {
 struct demux d={0},*demuxer=&d;
BODY
 return 0;
}
static struct opts opts;
static struct stream stream;
static struct mkv m;
static void reset(bool tags) {m=(struct mkv){0};opts.read_tail_tags=tags;m.opts=&opts;stream.seekable=true;nreads=fail=0;}
static void add(int id,int pos) {m.headers[m.num_headers++]=(struct header_elem){id,pos,false};}
int main(void) {
 reset(true);add(1,100);add(2,110);assert(scan(&m,&stream,1000)==0);assert(nreads==2 && reads[0]==1 && reads[1]==2);
 reset(false);add(1,100);add(2,110);assert(scan(&m,&stream,1000)==0);assert(nreads==0 && !m.headers[0].parsed && m.headers[1].parsed);
 reset(false);add(2,110);add(1,100);scan(&m,&stream,1000);assert(nreads==0 && !m.headers[1].parsed);
 reset(true);add(1,100);scan(&m,&stream,1000);assert(nreads==0 && !m.headers[0].parsed);
 reset(false);add(2,100);scan(&m,&stream,1000);assert(nreads==0 && m.headers[0].parsed);
 reset(true);add(2,100);scan(&m,&stream,1000);assert(nreads==1);
 for(int id=3;id<=6;id++) {reset(false);add(1,100);add(2,110);add(id,90);scan(&m,&stream,1000);assert(nreads==2 && reads[0]==id && reads[1]==1);}
 reset(false);add(1,100);add(2,110);m.headers[1].parsed=true;scan(&m,&stream,1000);assert(nreads==0 && !m.headers[0].parsed);
 reset(false);add(1,100);add(2,110);stream.seekable=false;scan(&m,&stream,1000);assert(nreads==0 && m.headers[0].parsed);
 reset(false);add(1,1100);scan(&m,&stream,1000);assert(nreads==0 && m.eof_warning);
 reset(false);add(3,50);fail=1;assert(scan(&m,&stream,1000)==-1);
 puts("PASS: 14 real native header traversal cases; cues remain deferred and required metadata is retained");
}
'''.replace('BODY',body)
out=a.work/'verify.c';out.write_text(code,encoding='utf-8');exe=a.work/'verify.exe';subprocess.run([a.compiler,str(out),'-o',str(exe)],check=True);subprocess.run([str(exe.resolve())],check=True)
