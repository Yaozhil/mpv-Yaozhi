"""Compile the production replay/staging blocks with mocked libbluray position."""
import argparse
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--work',type=Path,required=True)
p.add_argument('--compiler',default='cc')
a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
s=(a.source/'stream/stream_bluray.c').read_text()
start=s.index('    if (b->jump_head_size > b->jump_head_offset)')
replay=s[start:s.index('    int idle_reads = 0;',start)]
start=s.index('                b->jump_head = talloc_realloc')
stage=s[start:s.index('                continue;',start)]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define MPMIN(a,b) ((a)<(b)?(a):(b))
#define talloc_realloc(ctx,ptr,type,n) ((type *)realloc(ptr,(n)*sizeof(type)))
#define MP_VERBOSE(...) ((void)0)
struct state {unsigned char *jump_head; int jump_head_size,jump_head_offset;
 uint64_t jump_head_end,next_read_pos,position;bool read_pos_known,data_delivered;void *bd;};
static uint64_t bd_tell(void *bd) {return ((struct state*)bd)->position;}
static int replay(struct state *b, void *buf,int len) {
REPLAY
return -1;
}
static void stage(struct state *b,void *buf,int n,uint64_t pos) {
STAGE
}
int main(void) {
struct state state={0},*b=&state;b->bd=b;
unsigned char input[131072],output[131072];
for(int i=0;i<131072;i++)input[i]=(unsigned char)(i%251);
b->position=572672;stage(b,input,131072,b->position);
int offset=0;
while(offset<131072) {int n=replay(b,output+offset,997);assert(n>0);offset+=n;}
assert(offset==131072 && memcmp(input,output,131072)==0);
assert(b->read_pos_known && b->next_read_pos==572672 && b->data_delivered);
assert(replay(b,output,997)==-1); // no duplicate prefix
stage(b,input,131072,b->position);assert(replay(b,output,11)==11);
b->position++;assert(replay(b,output,997)==-1); // superseded navigation
assert(b->jump_head_size==0 && b->jump_head_offset==0);
stage(b,input,131072,b->position);
b->jump_head_size=b->jump_head_offset=0; // explicit seek invalidation
assert(replay(b,output,997)==-1);
free(b->jump_head);puts("PASS: real Blu-ray head staging/replay blocks, partial reads, supersession, seek");
}
'''.replace('REPLAY',replay).replace('STAGE',stage)
f=a.work/'verify.c';f.write_text(code)
exe=a.work/'verify.exe'
subprocess.run([a.compiler,'-std=c11','-Wall','-Wextra','-Werror',str(f),'-o',str(exe)],check=True)
subprocess.run([str(exe.resolve())],check=True)
