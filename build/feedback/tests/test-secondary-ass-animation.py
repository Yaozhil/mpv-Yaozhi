"""Compile the actual decoder animation helpers with small ASS event fixtures."""
from pathlib import Path
import argparse
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--compiler', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
source = (args.source/'sub/sd_ass.c').read_text(encoding='utf-8')
helpers = source[source.index('static bool is_animated('):source.index('// Note: pkt is not necessarily')]
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <limits.h>
#include <string.h>
#include <stdio.h>
#define MPMIN(a,b) ((a)<(b)?(a):(b))
typedef struct { long long Start, Duration; char *Effect, *Text; } ASS_Event;
typedef struct { int n_events; ASS_Event *events; } ASS_Track;
struct sd_ass_priv {
    bool animation_valid, animation_active;
    long long animation_from, animation_until;
};
'''
test = r'''
int main(void) {
    struct sd_ass_priv c={0};
    ASS_Event e[]={
        {0,10000,"","{\\pos(300,30)}static"},
        {1000,2000,"","{\\move(1800,70,-200,70)}moving"},
        {4000,1000,"","{\\fad(100,100)}fade"},
        {6000,1000,"","{\\k10}karaoke"},
        {8000,1000,"Banner;1;0;50","effect"},
    };
    ASS_Track t={5,e};
    for (int i=0;i<10000;i++) {
        bool expected=(i>=1000&&i<3000)||(i>=4000&&i<5000)||
                      (i>=6000&&i<7000)||(i>=8000&&i<9000);
        assert(secondary_has_animation(&c,&t,i)==expected);
    }
    // Backward seek must not reuse the later static interval.
    assert(secondary_has_animation(&c,&t,1500));
    assert(!secondary_has_animation(&c,&t,999));
    // Live replacement can retain event count and timestamps but change tags.
    e[0].Text="{\\t(\\fs60)}transform"; c.animation_valid=false;
    assert(secondary_has_animation(&c,&t,999));
    e[0].Text="{\\pos(300,30)}static"; c.animation_valid=false;
    assert(!secondary_has_animation(&c,&t,999));
    e[0].Duration=0; c.animation_valid=false;
    assert(!secondary_has_animation(&c,&t,0));
    assert(is_animated("{\\K10}upper karaoke"));
    assert(is_animated("{\\fade(255,0,255,0,100,900,1000)}fade"));
    assert(!is_animated("{\\p1}m 0 0 l 10 10"));
    assert(!is_animated("plain move words"));
    puts("PASS 10000 timestamps, static/move/fade/karaoke/Effect, backward seek, replacement");
}
'''
args.output.mkdir(parents=True, exist_ok=True)
file = args.output/'animation.c'
exe = args.output/'animation.exe'
file.write_text(prefix+helpers+test, encoding='utf-8')
subprocess.run([str(args.compiler), str(file), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
