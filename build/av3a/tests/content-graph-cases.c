#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "avs3_stat_dec.h"
#include "avs3_decoder_interface.h"
#include "avs3_spatial_contents.h"

static AVS3Decoder decoder;
static Avs3DecMetadata metadata;
static AVS3SpatialContents result;
static int cases;
#include "sample_fixture.inc"

static Avs3BasicL1 *reset(void)
{
    memset(&decoder, 0, sizeof(decoder));
    memset(&metadata, 0, sizeof(metadata));
    decoder.hMetadataDec = &metadata;
    decoder.numChansOutput = 16;
    decoder.numObjsOutput = 4;
    decoder.avs3CodecFormat = AVS3_MIX_FORMAT;
    decoder.isMixedContent = 1;
    decoder.soundBedType = 1;
    sample_fixture(&metadata.avs3MetaData.avs3MetaDataStatic.avs3BasicL1);
    memset(&result, 0xA5, sizeof(result));
    result.struct_size = sizeof(result);
    return &metadata.avs3MetaData.avs3MetaDataStatic.avs3BasicL1;
}

static void expect(int success, int status)
{
    assert(avs3_get_spatial_contents(&decoder, &result) == success);
    assert(result.struct_size == sizeof(result));
    assert(result.abi_version == AVS3_SPATIAL_CONTENTS_ABI_VERSION);
    if (result.status != status)
        fprintf(stderr,"case %d: expected status %d, got %d\n",cases+1,status,result.status);
    assert(result.status == status);
    assert(result.available == success);
    if (!success) {
        assert(!result.num_contents && !result.num_objects);
        for (int i=0; i<AVS3_CONTENT_MAX_CONTENTS; i++)
            assert(!result.contents[i].pcm_channel_mask);
    }
    cases++;
}

static void verify_real_sample(void)
{
    static const uint32_t masks[] = {0x3fffU,0x5fffU,0x6fffU,0x9fffU};
    reset(); expect(1, AVS3_CONTENTS_OK);
    assert(result.total_channels==16 && result.num_contents==4 && result.num_objects==5);
    for (int i=0; i<4; i++) {
        assert(result.contents[i].content_id==i);
        assert(result.contents[i].pcm_channel_mask==masks[i]);
        assert(result.contents[i].num_objects==3);
        assert(result.objects[i+1].object_id==i+1);
        assert(result.objects[i+1].pcm_channel_mask==(UINT32_C(1)<<(12+i)));
    }
    assert(!strcmp(result.objects[1].name,"AO_O1"));
    assert(!strcmp(result.objects[4].name,"AO_O4"));
}

#define BAD(label, mutation, status) do { \
    Avs3BasicL1 *b=reset(); (void)b; mutation; expect(0,status); \
    puts(label); \
} while (0)

int main(void)
{
    verify_real_sample();
    assert(!avs3_get_spatial_contents(NULL, NULL)); cases++;
    reset();
    assert(!avs3_get_spatial_contents(&decoder, NULL)); cases++;
    result.struct_size=sizeof(result);
    assert(!avs3_get_spatial_contents(NULL,&result));
    assert(result.status==AVS3_CONTENTS_NO_METADATA && !result.available); cases++;
    {
        AVS3SpatialContents original;
        reset(); result.struct_size=sizeof(result)-1; original=result;
        assert(!avs3_get_spatial_contents(&decoder,&result));
        assert(!memcmp(&result,&original,sizeof(result))); cases++;
        result.struct_size=0; original=result;
        assert(!avs3_get_spatial_contents(&decoder,&result));
        assert(!memcmp(&result,&original,sizeof(result))); cases++;
    }
    {
        struct {AVS3SpatialContents out; unsigned char guard[32];} oversized;
        reset(); memset(&oversized,0xA7,sizeof(oversized));
        oversized.out.struct_size=sizeof(oversized);
        assert(avs3_get_spatial_contents(&decoder,&oversized.out));
        for (int i=0;i<32;i++) assert(oversized.guard[i]==0xA7);
        assert(oversized.out.struct_size==sizeof(AVS3SpatialContents)); cases++;
    }
    BAD("fresh decoder unavailable", memset(b,0,sizeof(*b)), AVS3_CONTENTS_NO_METADATA);
    BAD("missing metadata handle", decoder.hMetadataDec=NULL, AVS3_CONTENTS_NO_METADATA);
    BAD("channel total zero", decoder.numChansOutput=0, AVS3_CONTENTS_INVALID);
    BAD("channel total too large", decoder.numChansOutput=33, AVS3_CONTENTS_INVALID);
    BAD("negative dynamic object count", decoder.numObjsOutput=-1, AVS3_CONTENTS_INVALID);
    BAD("object count beyond transport", decoder.numObjsOutput=17, AVS3_CONTENTS_INVALID);
    BAD("channel-only header unsupported", decoder.avs3CodecFormat=AVS3_MC_FORMAT, AVS3_CONTENTS_UNSUPPORTED);
    BAD("HOA header with stale objects unsupported", decoder.avs3CodecFormat=AVS3_HOA_FORMAT, AVS3_CONTENTS_UNSUPPORTED);
    BAD("non-mixed header unsupported", decoder.isMixedContent=0, AVS3_CONTENTS_UNSUPPORTED);
    BAD("no object header unsupported", decoder.numObjsOutput=0, AVS3_CONTENTS_UNSUPPORTED);
    BAD("unknown soundbed type unsupported", decoder.soundBedType=2, AVS3_CONTENTS_UNSUPPORTED);
    BAD("pure object count mismatch", decoder.soundBedType=0, AVS3_CONTENTS_INVALID);
    BAD("bed object header with no bed", decoder.numObjsOutput=16, AVS3_CONTENTS_INVALID);
    BAD("negative content count", b->numOfContents=-1, AVS3_CONTENTS_INVALID);
    BAD("content count overflow", b->numOfContents=5, AVS3_CONTENTS_INVALID);
    BAD("object count overflow", b->numOfObjects=9, AVS3_CONTENTS_INVALID);
    BAD("pack count overflow", b->numOfPacks=9, AVS3_CONTENTS_INVALID);
    BAD("channel count overflow", b->numOfChannels=33, AVS3_CONTENTS_INVALID);
    BAD("programme count zero", b->audioProgrammeMeta.numContents=0, AVS3_CONTENTS_INVALID);
    BAD("programme count overflow", b->audioProgrammeMeta.numContents=5, AVS3_CONTENTS_INVALID);
    BAD("unknown programme content", b->audioProgrammeMeta.refContentIdx[0]=7, AVS3_CONTENTS_INVALID);
    BAD("duplicate programme content", b->audioProgrammeMeta.refContentIdx[1]=0, AVS3_CONTENTS_INVALID);
    BAD("duplicate content definition", b->audioContentData[1].contentIdx=0, AVS3_CONTENTS_INVALID);
    BAD("negative content ID", b->audioContentData[0].contentIdx=-1, AVS3_CONTENTS_INVALID);
    BAD("content ID overflow", b->audioContentData[0].contentIdx=4, AVS3_CONTENTS_INVALID);
    BAD("unknown content object", b->audioContentData[0].refObjectIdx[1]=7, AVS3_CONTENTS_INVALID);
    BAD("duplicate content object", b->audioContentData[0].refObjectIdx[1]=0, AVS3_CONTENTS_INVALID);
    BAD("content object count overflow", b->audioContentData[0].numObjects=9, AVS3_CONTENTS_INVALID);
    BAD("empty content object count", b->audioContentData[0].numObjects=0, AVS3_CONTENTS_INVALID);
    BAD("complementary groups unsupported", b->audioContentData[0].hasNumComplementaryObjectGroup=1, AVS3_CONTENTS_UNSUPPORTED);
    BAD("duplicate object ID", b->audioObjectData[1].objectIdx=0, AVS3_CONTENTS_INVALID);
    BAD("object ID overflow", b->audioObjectData[1].objectIdx=8, AVS3_CONTENTS_INVALID);
    BAD("unknown pack reference", b->audioObjectData[1].refPackFormatIdx[0]=7, AVS3_CONTENTS_INVALID);
    BAD("object pack count overflow", b->audioObjectData[1].numPacks=9, AVS3_CONTENTS_INVALID);
    BAD("duplicate pack reference", b->audioObjectData[1].numPacks=2; b->audioObjectData[1].refPackFormatIdx[1]=1, AVS3_CONTENTS_INVALID);
    BAD("duplicate pack definition", b->audioPackFormatData[1].packFormatIdx=0, AVS3_CONTENTS_INVALID);
    BAD("pack ID overflow", b->audioPackFormatData[1].packFormatIdx=8, AVS3_CONTENTS_INVALID);
    BAD("matrix pack unsupported", b->audioPackFormatData[1].typeLabel=2, AVS3_CONTENTS_UNSUPPORTED);
    BAD("HOA pack unsupported", b->audioPackFormatData[1].typeLabel=4, AVS3_CONTENTS_UNSUPPORTED);
    BAD("pack channel count overflow", b->audioPackFormatData[0].numChannels=33, AVS3_CONTENTS_INVALID);
    BAD("unknown channel reference", b->audioPackFormatData[1].refChannelIdx[0]=31, AVS3_CONTENTS_INVALID);
    BAD("duplicate channel reference", b->audioPackFormatData[0].refChannelIdx[1]=0, AVS3_CONTENTS_INVALID);
    BAD("negative pack start", b->audioPackFormatData[0].packFormatStartIdx=-1, AVS3_CONTENTS_INVALID);
    BAD("pack range beyond transport", b->audioPackFormatData[1].packFormatStartIdx=16, AVS3_CONTENTS_INVALID);
    BAD("invalid reuse flag", b->audioPackFormatData[1].hasChannelReuse=2, AVS3_CONTENTS_INVALID);
    BAD("negative reuse channel", b->audioPackFormatData[1].hasChannelReuse=1; b->audioPackFormatData[1].transChRef[0]=-1, AVS3_CONTENTS_INVALID);
    BAD("reuse channel beyond transport", b->audioPackFormatData[1].hasChannelReuse=1; b->audioPackFormatData[1].transChRef[0]=16, AVS3_CONTENTS_INVALID);
    BAD("duplicate channel definition", b->audioChannelFormatData[1].channelFormatIdx=0, AVS3_CONTENTS_INVALID);
    BAD("negative channel ID", b->audioChannelFormatData[1].channelFormatIdx=-1, AVS3_CONTENTS_INVALID);
    BAD("channel ID overflow", b->audioChannelFormatData[1].channelFormatIdx=32, AVS3_CONTENTS_INVALID);
    BAD("name code overflow", b->audioObjectData[1].ObjectName[0]=256, AVS3_CONTENTS_INVALID);
    BAD("negative name code", b->audioObjectData[1].ObjectName[0]=-1, AVS3_CONTENTS_INVALID);
    BAD("ambiguous object reuse", b->audioPackFormatData[2].packFormatStartIdx=12, AVS3_CONTENTS_UNSUPPORTED);
    BAD("object alias across disjoint contents", b->audioContentData[0].numObjects=2; b->audioContentData[1].numObjects=2; b->audioContentData[1].refObjectIdx[1]=2; b->audioProgrammeMeta.numContents=2; b->audioObjectData[2].refPackFormatIdx[0]=1, AVS3_CONTENTS_UNSUPPORTED);
    BAD("spatial pack mapped into bed", b->audioPackFormatData[1].packFormatStartIdx=11, AVS3_CONTENTS_UNSUPPORTED);
    BAD("channel format identity differs from PCM", b->audioPackFormatData[0].refChannelIdx[0]=1; b->audioPackFormatData[0].refChannelIdx[1]=0, AVS3_CONTENTS_UNSUPPORTED);
    {
        reset(); Avs3MetaData *meta=&metadata.avs3MetaData;
        meta->hasDynamicMeta=1; meta->avs3MetaDataDynamic.numDmChans=4;
        for (int i=0;i<4;i++) meta->avs3MetaDataDynamic.transChRef[i]=12+i;
        expect(1,AVS3_CONTENTS_OK);
        for (int i=0;i<4;i++) meta->avs3MetaDataDynamic.transChRef[i]=15-i;
        expect(1,AVS3_CONTENTS_OK);
        meta->avs3MetaDataDynamic.transChRef[0]=14;
        expect(0,AVS3_CONTENTS_INVALID);
        meta->avs3MetaDataDynamic.transChRef[0]=11;
        expect(0,AVS3_CONTENTS_UNSUPPORTED);
        meta->avs3MetaDataDynamic.transChRef[0]=32;
        expect(0,AVS3_CONTENTS_INVALID);
        meta->avs3MetaDataDynamic.transChRef[0]=15;
        meta->avs3MetaDataDynamic.numDmChans=3;
        expect(0,AVS3_CONTENTS_INVALID);
        meta->avs3MetaDataDynamic.numDmChans=4;
        meta->avs3MetaDataDynamic.dmLevel=2;
        expect(0,AVS3_CONTENTS_UNSUPPORTED);
    }
    {
        Avs3BasicL1 *b=reset();
        for (int i=0;i<b->numOfPacks;i++) {
            AudioPackFormat *pack=&b->audioPackFormatData[i];
            pack->hasChannelReuse=1;
            for (int j=0;j<pack->numChannels;j++) pack->transChRef[j]=pack->packFormatStartIdx+j;
            pack->packFormatStartIdx=-32000;
        }
        expect(1,AVS3_CONTENTS_OK); assert(result.contents[3].pcm_channel_mask==0x9fffU);
    }
    {
        Avs3BasicL1 *b=reset();
        for (int i=0;i<2;i++) {
            AudioContent t=b->audioContentData[i]; b->audioContentData[i]=b->audioContentData[3-i]; b->audioContentData[3-i]=t;
        }
        for (int i=0;i<2;i++) {
            AudioObject t=b->audioObjectData[i]; b->audioObjectData[i]=b->audioObjectData[4-i]; b->audioObjectData[4-i]=t;
            AudioPackFormat p=b->audioPackFormatData[i]; b->audioPackFormatData[i]=b->audioPackFormatData[4-i]; b->audioPackFormatData[4-i]=p;
        }
        for (int i=0;i<8;i++) {
            AudioChannelFormat t=b->audioChannelFormatData[i]; b->audioChannelFormatData[i]=b->audioChannelFormatData[15-i]; b->audioChannelFormatData[15-i]=t;
        }
        expect(1,AVS3_CONTENTS_OK);
        assert(result.contents[0].content_id==0 && result.contents[0].pcm_channel_mask==0x3fffU);
        assert(result.contents[3].content_id==3 && result.contents[3].pcm_channel_mask==0x9fffU);
    }
    {
        Avs3BasicL1 *b=reset(); memset(b,0,sizeof(*b)); decoder.numChansOutput=32; decoder.numObjsOutput=1;
        b->audioProgrammeMeta.numContents=1; b->audioProgrammeMeta.refContentIdx[0]=3;
        b->numOfContents=1; b->audioContentData[0].contentIdx=3;
        b->audioContentData[0].numObjects=1; b->audioContentData[0].refObjectIdx[0]=7;
        b->numOfObjects=1; b->audioObjectData[0].objectIdx=7;
        b->audioObjectData[0].numPacks=1; b->audioObjectData[0].refPackFormatIdx[0]=7;
        b->numOfPacks=1; b->audioPackFormatData[0].packFormatIdx=7;
        b->audioPackFormatData[0].typeLabel=3; b->audioPackFormatData[0].numChannels=1;
        b->audioPackFormatData[0].refChannelIdx[0]=31; b->audioPackFormatData[0].packFormatStartIdx=31;
        b->numOfChannels=1; b->audioChannelFormatData[0].channelFormatIdx=31;
        expect(1,AVS3_CONTENTS_OK); assert(result.contents[0].pcm_channel_mask==UINT32_C(0x80000000));
    }
    {
        reset(); AVS3SpatialContents prior;
        expect(1,AVS3_CONTENTS_OK); prior=result;
        metadata.avs3MetaData.hasStaticMeta=0;
        expect(1,AVS3_CONTENTS_OK); assert(!memcmp(&prior,&result,sizeof(prior)));
        memset(&metadata,0,sizeof(metadata)); expect(0,AVS3_CONTENTS_NO_METADATA);
    }
    {
        Avs3BasicL1 *b=reset(); memset(b,0,sizeof(*b));
        decoder.numChansOutput=1; decoder.numObjsOutput=1; decoder.soundBedType=0;
        b->audioProgrammeMeta.numContents=1; b->audioProgrammeMeta.refContentIdx[0]=3;
        b->numOfContents=1; b->audioContentData[0].contentIdx=3;
        b->audioContentData[0].numObjects=1; b->audioContentData[0].refObjectIdx[0]=7;
        b->numOfObjects=1; b->audioObjectData[0].objectIdx=7;
        b->audioObjectData[0].numPacks=1; b->audioObjectData[0].refPackFormatIdx[0]=7;
        b->numOfPacks=1; b->audioPackFormatData[0].packFormatIdx=7;
        b->audioPackFormatData[0].typeLabel=3; b->audioPackFormatData[0].numChannels=1;
        b->audioPackFormatData[0].refChannelIdx[0]=0; b->audioPackFormatData[0].packFormatStartIdx=0;
        b->numOfChannels=1; b->audioChannelFormatData[0].channelFormatIdx=0;
        expect(1,AVS3_CONTENTS_OK); assert(result.contents[0].pcm_channel_mask==1);
    }
    printf("{\"cases\":%d,\"passed\":true,\"scope\":\"real getter + real SDK headers, sample-derived fixture and invalid graphs; no media/NN/AO/GPU\"}\n",cases);
    return 0;
}
