"""Compile the real libbluray filter and check authored still-menu PES bounds."""
import argparse, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
p.add_argument('--work',type=Path,required=True);p.add_argument('--compiler',default='cc')
a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
code=r'''
#include <assert.h>
#include <stdio.h>
#include "util/logging.h"
#undef BD_DEBUG
#define BD_DEBUG(...) ((void)0)
#include "libbluray/decoders/m2ts_filter.c"
static void packet(uint8_t *b, unsigned pid, uint64_t pts) {
    memset(b,0xff,6144);
    for (int i=0;i<32;i++) {uint8_t *t=b+i*192;t[4]=0x47;t[5]=0x1f;t[6]=0xff;t[7]=0x10;}
    b[5]=0x40|((pid>>8)&31);b[6]=pid&255;
    uint8_t *pes=b+8;pes[0]=pes[1]=0;pes[2]=1;pes[3]=0xbd;pes[4]=0;pes[5]=11;
    pes[6]=0x80;pes[7]=0x80;pes[8]=5;
    pes[9]=0x21|((pts>>29)&14);pes[10]=(pts>>22)&255;pes[11]=((pts>>14)&254)|1;
    pes[12]=(pts>>7)&255;pes[13]=((pts<<1)&254)|1;
    pes[14]=0x80;pes[15]=pes[16]=0; /* IG end-of-display segment */
}
static void check(unsigned pid,uint64_t pts,int still,int keep) {
    uint8_t b[6144];packet(b,pid,pts);
    M2TS_FILTER *p=m2ts_filter_init(54000000,54003752,pid==0x1011,pid==0x1100,pid==0x1400,pid==0x1200);assert(p);
    m2ts_filter_set_ig_still(p,still);assert(m2ts_filter(p,b)==0);
    unsigned actual=((b[5]&31)<<8)|b[6];assert(actual==(keep?pid:0x1fff));
    m2ts_filter_close(&p);assert(!p);
}
int main(void) {
    check(0x1400,54004305,0,0); /* Original truncation: beyond one-frame OUT */
    check(0x1400,54004305,1,1); /* Still menu objects and end marker survive */
    check(0x1400,53999999,1,0); /* Before IN remains excluded */
    check(0x1400,54000000,1,1);
    check(0x1200,54004305,1,0); /* PG remains clipped */
    check(0x1011,54004305,1,0); /* Video remains clipped */
    check(0x1100,54004305,1,0); /* Audio remains clipped */
    check(0x1011,54003752,1,1); /* Original inclusive video boundary */
    check(0x1400,54003752,0,0); /* Original exclusive IG boundary */
    m2ts_filter_set_ig_still(NULL,1);
    puts("PASS: real libbluray filter, still IG completion and unchanged A/V/PG/IN boundaries");
}
'''
f=a.work/'verify.c';f.write_text(code);exe=a.work/'verify.exe'
subprocess.run([a.compiler,'-std=c11','-Wall','-Wextra','-Werror','-I'+str((a.source/'src').resolve()),str(f),'-o',str(exe)],check=True)
subprocess.run([str(exe.resolve())],check=True)
