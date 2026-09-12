"""Compile actual changed C functions against small deterministic state fixtures."""
import argparse
from pathlib import Path
import subprocess
import json

p=argparse.ArgumentParser()
p.add_argument('--mpv-source',type=Path,required=True)
p.add_argument('--bd-source',type=Path,required=True)
p.add_argument('--cc',default='cc')
p.add_argument('--zig',action='store_true')
p.add_argument('--work',type=Path,required=True)
a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
def function(text, signature):
    start=text.index(signature);brace=text.index('{',start);depth=1;i=brace+1
    while depth:
        depth+=(text[i]=='{')-(text[i]=='}');i+=1
    return text[start:i]
load=(a.mpv_source/'player/loadfile.c').read_text(encoding='utf-8')
bd=(a.bd_source/'src/libbluray/hdmv/hdmv_vm.c').read_text(encoding='utf-8')
video=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define MP_NOPTS_VALUE -1e20
#define STREAM_VIDEO 0
#define MP_VERBOSE(...) ((void)0)
struct sh_stream { bool selected, absent; struct sh_stream *el; };
struct track { struct sh_stream *stream; void *demuxer; };
struct vo { void *filter; };
struct MPContext { struct vo *vo_chain; struct track *current_track[1][1]; };
static int selections,pairs;static struct sh_stream *paired;
static bool demux_stream_is_selected(struct sh_stream *s) {return s->selected;}
static struct sh_stream *sh_stream_dependent_sibling(struct sh_stream *s) {
 return s && s->el && !s->el->absent ? s->el : NULL;
}
static void demuxer_select_track(void *d,struct sh_stream *s,double t,bool on) {
 assert(d && t==MP_NOPTS_VALUE && on);s->selected=on;selections++;
}
static void mp_output_chain_set_el_stream(void *f,struct sh_stream *el) {
 assert(f);pairs++;paired=el;
}
'''+function(load,'void update_vo_chain_el_pair(')+r'''
int main(void) {
 struct sh_stream el={0},bl={.selected=true};
 struct track track={.stream=&bl,.demuxer=&bl};
 struct vo vo={.filter=&bl};struct MPContext c={.vo_chain=&vo,.current_track={{&track}}};
 update_vo_chain_el_pair(&c);assert(!paired && !selections);
 bl.el=&el;update_vo_chain_el_pair(&c);assert(paired==&el && el.selected && selections==1);
 update_vo_chain_el_pair(&c);assert(selections==1);
 el.absent=true;update_vo_chain_el_pair(&c);assert(!paired && selections==1);
 el.absent=false;el.selected=false;update_vo_chain_el_pair(&c);assert(el.selected && selections==2);
 bl.selected=false;el.selected=false;update_vo_chain_el_pair(&c);assert(!el.selected && selections==2);
 c.current_track[0][0]=NULL;update_vo_chain_el_pair(&c);assert(!paired);
 c.current_track[0][0]=&track;track.stream=NULL;update_vo_chain_el_pair(&c);assert(!paired);
 int before=pairs;c.vo_chain=NULL;update_vo_chain_el_pair(&c);assert(pairs==before);
 c.vo_chain=&vo;vo.filter=NULL;update_vo_chain_el_pair(&c);assert(pairs==before);
 puts("video selection: 10 cases PASS");return 0;
}
'''
vm=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#define BD_DEBUG(...) ((void)0)
#define MAX_LOOP 1000
enum {HDMV_EVENT_NONE,HDMV_EVENT_PLAY_PI,HDMV_EVENT_PLAY_PM,HDMV_EVENT_END,HDMV_EVENT_IG_END};
typedef struct {int event,param;} HDMV_EVENT;
typedef struct {uint32_t num_cmds;} OBJECT;
typedef struct {OBJECT *object,*ig_object;uint32_t pc;HDMV_EVENT pending;int kind,value,jumps,freed;} HDMV_VM;
static void _queue_event(HDMV_VM *p,int event,int param) {assert(!p->pending.event);p->pending=(HDMV_EVENT){event,param};}
static int _get_event(HDMV_VM *p,HDMV_EVENT *ev) {
 *ev=p->pending;p->pending=(HDMV_EVENT){0};return ev->event ? 0 : -1;
}
static void _free_ig_object(HDMV_VM *p) {p->ig_object=NULL;p->freed++;}
'''+function(bd,'static int _link_at(')+r'''
static int _hdmv_step(HDMV_VM *p) {
 if (!p->pc) _link_at(p,p->kind==1?p->value:-1,p->kind==2?p->value:-1);
 else p->jumps++;
 p->pc++;return 0;
}
'''+function(bd,'static int _vm_run(')+r'''
int main(void) {
 for(int kind=1;kind<=2;kind++) for(int value=0;value<3;value++) {
  OBJECT obj={2};HDMV_VM p={.object=&obj,.ig_object=&obj,.kind=kind,.value=value};HDMV_EVENT ev={0};
  assert(_vm_run(&p,&ev)==0 && ev.event==(kind==1?HDMV_EVENT_PLAY_PI:HDMV_EVENT_PLAY_PM) && ev.param==value);
  assert(_vm_run(&p,&ev)==0 && ev.event==HDMV_EVENT_IG_END && !p.jumps && p.freed==1);
 }
 OBJECT obj={2};HDMV_VM p={.object=&obj};
 assert(_link_at(&p,1,-1)==-1 && !p.pc && !p.pending.event);
 assert(_link_at(&p,-1,1)==-1 && !p.pc && !p.pending.event);
 puts("HDMV command termination: 8 cases PASS");return 0;
}
'''
results=[]
for name,code in [('video',video),('hdmv',vm)]:
    src=a.work/(name+'.c');src.write_text(code,encoding='utf-8')
    exe=a.work/(name+'.exe')
    cmd=[a.cc]+(['cc'] if a.zig else [])+['-std=c11','-O0',str(src),'-o',str(exe)]
    subprocess.run(cmd,check=True,timeout=180)
    proc=subprocess.run([str(exe.resolve())],capture_output=True,text=True,timeout=10)
    results.append({'name':name,'exit':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    print(proc.stdout,proc.stderr)
(a.work/'result.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(r['exit']==0 for r in results),results
