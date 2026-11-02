"""Run actual FFmpeg output/graph transition functions and two red mutants.

The SDK neural decoder is replaced by bounded input/output fixtures. This proves
pending PCM, per-block masks, graph snapshots and exported state ownership; it
does not test codec acoustics or a complete linked player.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk-source',type=Path,required=True)
parser.add_argument('--ffmpeg-source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cc',default='cc')
args=parser.parse_args()
runner=HERE/'verify-preselections-contract.py'
spec=importlib.util.spec_from_file_location('contracts',runner)
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
sdk=args.sdk_source/'av3adecoder/avs3Decoder/include'
headers=(sdk/'avs3_spatial_contents.h').read_text()+'\n'+(sdk/'avs3_spatial_metadata.h').read_text()
source_path=args.ffmpeg_source/'libavcodec/libarcdav3a.c'
source=source_path.read_text(encoding='utf-8')
actual='\n'.join(contract.function(source,n) for n in ['arcdav3a_content_mask','arcdav3a_json_add','arcdav3a_publish_contents','arcdav3a_stream_config_changed','arcdav3a_recreate_decoder','arcdav3a_preserve_input_from','arcdav3a_append_spatial_frame','dav3a_decode_frame'])
fake=contract.FAKE.replace('int content_id, spatial_render;',r'''
    int content_id, spatial_render;
    bool m_bFirstFrame;
    int have_last_stream_info;
    AVS3SpatialStreamInfo last_stream_info;
    unsigned long m_dwDataLen,m_dwBufferSize,m_dwErrorCounter;
    uint8_t *m_pBuffer;
''')
fake+=r'''
#define MAX_VIVID_SIZE (4096U*64U)
#define AV_LOG_DEBUG 0
#define AV_LOG_WARNING 1
#define AV_LOG_ERROR 2
#define av_log(...) ((void)0)
#define AVERROR_BUFFER_TOO_SMALL (-1004)
#define AVS3_DECODER_NEED_MORE_DATA 2
static void *av_realloc(void *p,size_t n){return realloc(p,n);}
static void avs3_destroy_decoder(void *p){(void)p;}
static void *avs3_create_decoder(void){return (void *)1;}
static void arcdav3a_destroy_renderer(arcdav3a_context *h){(void)h;}
static int header_calls;
static int parse_header(void *d,uint8_t *p,int len,int first,int *consumed,void *crc)
{(void)d;(void)p;(void)len;(void)first;(void)crc; ++header_calls;*consumed=1;return 1;}
static int avs3_get_spatial_stream_info(void *d,AVS3SpatialStreamInfo *info)
{
    (void)d;memset(info,0,sizeof(*info));
    info->struct_size=sizeof(*info);info->abi_version=AVS3_SPATIAL_ABI_VERSION;
    info->format=AVS3_SPATIAL_FORMAT_BED_OBJECTS;
    info->sample_rate=header_calls==1?48000:44100;
    info->total_channels=16;info->bed_channels=12;info->object_channels=4;
    info->frame_length=1;info->bit_depth=16;return 1;
}
static int avs3_decode(void *d,uint8_t *p,int len,uint8_t *out,int *outlen,int *consumed)
{(void)d;(void)p;(void)len;memset(out,1,32);*outlen=32;*consumed=1;return 1;}
'''
out_type=r'''
typedef struct AVS3DecoderOutput {
    uint8_t *pOutData;
    unsigned long nlen,nChannel,nSamplerate,nBits,nChCfg;
    AVS3SpatialStreamInfo spatial_info;
    int have_spatial_info;
} AVS3DecoderOutput;
'''
test=r'''
int main(void)
{
    arcdav3a_context h={0};AVCodecContext ctx={&h};
    AVS3DecoderOutput out={0};unsigned long consumed=0;
    uint8_t input[4]={1,2,3,4};
    h.m_hAvs3=(void*)1;h.m_bFirstFrame=true;
    h.content_id=0;h.spatial_render=AV3A_RENDER_BINAURAL;
    out.pOutData=malloc(MAX_VIVID_SIZE);
    provider.struct_size=sizeof(provider);provider.abi_version=AVS3_SPATIAL_CONTENTS_ABI_VERSION;
    provider.available=1;provider.status=AVS3_CONTENTS_OK;
    provider.total_channels=16;provider.num_contents=1;provider.num_objects=3;
    provider.contents[0].content_id=0;provider.contents[0].num_objects=3;
    provider.contents[0].pcm_channel_mask=0x3fff;
    for(int i=0;i<3;i++){provider.contents[0].object_ids[i]=i;provider.objects[i].object_id=i;}
    int ret=dav3a_decode_frame(&ctx,input,4,&consumed,&out);
    assert(ret==0 && out.nlen==32 && out.nSamplerate==48000);
    assert(h.spatial_frame_count==1 && h.spatial_frames[0].pcm_mask==0x3fff && h.spatial_frames[0].content_applied);
    assert(h.m_dwDataLen==2 && h.m_bFirstFrame);
    /* This is the exact publish argument for a successfully rendered block. */
    ret=arcdav3a_publish_contents(&h,h.spatial_frames[h.spatial_frame_count-1].content_applied);
    assert(ret==0);puts(h.contents_json);
    /* A consumer must never see applied=true for a reset or unrelated graph. */
    memset(&h.contents,0,sizeof(h.contents));h.contents.status=AVS3_CONTENTS_NO_METADATA;
    assert(arcdav3a_publish_contents(&h,1)==0);puts(h.contents_json);
    h.contents=provider;h.spatial_render=AV3A_RENDER_NATIVE;
    assert(arcdav3a_publish_contents(&h,1)==0);puts(h.contents_json);
    h.spatial_render=AV3A_RENDER_BINAURAL;h.content_id=1;
    assert(arcdav3a_publish_contents(&h,1)==0);puts(h.contents_json);
    h.content_id=-1;
    assert(arcdav3a_publish_contents(&h,1)==0);puts(h.contents_json);
    free(h.contents_json);free(h.m_pBuffer);free(h.spatial_frames);free(out.pOutData);
    return 0;
}
'''
args.output.mkdir(parents=True,exist_ok=False)
def run_case(label,functions):
    generated=contract.PREFIX+'\n#include <limits.h>\n'+headers+out_type+fake+functions+test
    c=args.output/(label+'.c');c.write_text(generated,encoding='utf-8')
    exe=args.output/(label+('.exe' if os.name=='nt' else ''))
    p=subprocess.run([args.cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-sign-compare',str(c),'-o',str(exe),'-lm'],capture_output=True,timeout=30)
    (args.output/(label+'-compile.log')).write_bytes(p.stdout+p.stderr)
    p.check_returncode()
    p=subprocess.run([str(exe)],capture_output=True,timeout=5,
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (args.output/(label+'-stdout.jsonl')).write_bytes(p.stdout)
    (args.output/(label+'-stderr.log')).write_bytes(p.stderr)
    p.check_returncode()
    rows=[json.loads(line) for line in p.stdout.splitlines()]
    assert len(rows)==5, 'Unexpected output graph contract fixture'
    return rows

def receipt_valid(rows):
    return (rows[0]['status']=='ok' and rows[0]['applied'] is True
            and rows[0]['selected']==0 and len(rows[0]['contents'])==1
            and rows[0]['contents'][0]['id']==0
            and rows[0]['contents'][0]['mask']==0x3fff
            and all(row['applied'] is False for row in rows[1:]))

baseline=run_case('actual-functions',actual)
assert receipt_valid(baseline), 'Output metadata does not belong to pending PCM or applied flag is false'
snapshot='\th->contents = output_contents;'
assert actual.count(snapshot)==1, 'Review a changed output snapshot implementation'
without_snapshot=actual.replace(snapshot,'\t(void)output_contents;',1)
snapshot_red=run_case('mutant-no-output-snapshot',without_snapshot)
assert not receipt_valid(snapshot_red), 'Removing graph snapshot must fail the contract'
guard=r'\tapplied = applied && table->available && table->status == AVS3_CONTENTS_OK &&\s*h->spatial_render == AV3A_RENDER_BINAURAL && selected_present;'
without_guard,count=re.subn(guard,'\t(void)selected_present;',actual,count=1)
assert count==1, 'Review a changed applied-state guard implementation'
guard_red=run_case('mutant-no-applied-guard',without_guard)
assert not receipt_valid(guard_red), 'Removing applied-state guard must fail the contract'
receipt={'status':'PASS_ACTUAL_AV3A_OUTPUT_GRAPH_CONTRACT','source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
         'actual_functions':8,'pending_pcm_preserved':True,'per_block_mask_preserved':True,
         'output_graph_matches_pending_pcm':True,'invalid_native_unselected_all_never_claim_applied':True,
         'mutants_rejected':['remove-output-graph-snapshot','remove-applied-state-guard'],
         'nn_decoder_exercised':False,'full_player_exercised':False}
(args.output/'report.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2))
