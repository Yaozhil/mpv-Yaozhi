local source=arg[1] or 'portable_config/scripts/uosc_danmaku/modules/render.lua'
local available=arg[2]~='legacy'
local modern=arg[2]=='modern'
package.path='portable_config/scripts/uosc_danmaku/?.lua;'..package.path
local props={['secondary-sid']='no',['secondary-sub-visibility']='yes',
    ['secondary-sub-ass-override']='strip',['fullscreen']=false,
    ['video-params/gamma']='bt.709',['osd-dimensions']={w=1920,h=1080,mt=138,mb=138},
    ['track-list']={
        {type='sub',id=1,title='Embedded primary',external=false,selected=true},
        {type='sub',id=2,title='uosc_danmaku',external=true,['external-filename']='stale.ass'},
    },['sid']=1,['time-pos']=1,['pause']=true}
local flag='secondary-sub-ass-full-viewport'
if available then props[flag]=false end
local refresh='secondary-sub-ass-refresh-rate'
if modern then
    props[refresh]=37
    props['command-list']={{name='secondary-ass-replace'}}
end
local observers, adds, removes, checks={},0,0,0
local commands={}
local fail_add=false
local cache_exists=true
local wall=1
local function check(ok, why) checks=checks+1;assert(ok,why) end
local noop=function()end
local logger=setmetatable({},{__index=function()return noop end})
mp={msg=logger, get_time=function()return wall end,get_osd_size=function()return 1920,1080 end,
    register_event=noop,register_script_message=noop,add_hook=noop,
    observe_property=function(k,_,f)observers[k]=f end,
    get_property_native=function(k,d)if props[k]~=nil then return props[k] end return d end,
    set_property_native=function(k,v)props[k]=v end,
    create_osd_overlay=function()return {update=noop,remove=noop}end,
    add_timeout=function(t,fn,on)return {timeout=t,fn=fn,kill=noop,resume=noop,is_enabled=function()return false end}end,
    add_periodic_timer=function()return {kill=noop,resume=noop,is_enabled=function()return true end}end,
    command_native=function()return 'fixture' end,
    commandv=function(cmd,value,_,title)
        commands[#commands+1]={cmd,value,sid=props['secondary-sid']}
        if cmd=='sub-add' then
            if fail_add then return nil,'fixture open failure' end
            adds=adds+1;table.insert(props['track-list'],{type='sub',id=41+adds,title=title,external=true,['external-filename']=value})
        elseif cmd=='secondary-ass-replace' then
            if fail_add then return nil,'fixture replace failure' end
        elseif cmd=='sub-remove' then
            removes=removes+1
            for i=#props['track-list'],1,-1 do
                if props['track-list'][i].id==value then table.remove(props['track-list'],i) end
            end
        end
        return true
    end,
}
mp.get_property=mp.get_property_native;mp.get_property_number=mp.get_property_native
mp.set_property=mp.set_property_native;mp.set_property_bool=mp.set_property_native
package.loaded['mp.msg']=logger
package.loaded['mp.utils']={join_path=function(a,b)return a..'/'..b end,
    file_info=function()return cache_exists and {is_dir=true} or nil end}
options={render_mode='auto',fullscreen_blackbar=true,fontname='sans-serif',fontsize=30,
    scrolltime=15,fixtime=5,
    opacity=1,outline=1,shadow=0,bold=false,displayarea=1,smart_color=false,
    vf_fps=false,overlay_display_sync=false,overlay_adaptive_fps=true}
ENABLED=true;PID=123;DANMAKU_PATH='temporary-fixture';HAS_DANMAKU='has';DANMAKU_COUNT='count'
COMMENTS={{text='{\\move(1920,20,-300,20)}test',move={1920,20,-300,20},
    start_time=0,end_time=20,layer=0,style='R2L'}}
function file_exists()return false end
function write_text_file(_,text)check(text:find('\\move(1920,20,-300,20)',1,true),'move remains unchanged');return true end
function get_danmaku_visibility()return true end
function set_danmaku_visibility()end
function filter_state()return false end
function binary_search()return 1 end
local f=assert(io.open(source,'rb'));local text=f:read('*a');f:close()
local probe=assert(loadstring(text..[[
write_text_file = function(_, content)
    assert(content:find('\\move(1920,20,-300,20)',1,true), 'move remains unchanged')
    return true
end
return {desired=desired_render_mode,resolve=resolve_render_mode,attach=render_ass_track,
    layout=function()layout_mode_timer.fn()end,unload=unload_ass_track,
    fallback=function()switch_to_overlay(nil,true,false)end,
    health=monitor_overlay_health,fps=get_overlay_fps,path=get_ass_track_path}
]],'@'..source))()
check(probe.path()=='fixture/uosc-danmaku-123.ass','existing config cache is preferred')
cache_exists=false
check(probe.path()=='temporary-fixture/uosc-danmaku-123.ass','fresh config uses temporary directory')
cache_exists=true
check(probe.desired()=='ass-track','window uses native')
probe.resolve();check(probe.attach(),'native track loads')
check(props['secondary-sid']==42,'new external track selected, embedded and stale tracks ignored')
check(props.sid==1,'embedded primary selection unchanged')
if available then
    for _,hz in ipairs({59.94,60,75,90,100,119.88,120,144,165,240}) do
        props['display-fps']=hz
        props.fullscreen=true;probe.layout()
        check(props[flag]==true,'full viewport enabled at '..hz)
        check(props['user-data/uosc_danmaku/renderer'].viewport=='full-output','full viewport telemetry')
        props.fullscreen=false;probe.layout()
        check(props[flag]==false,'window video viewport restored')
        if modern then
            local expected=({[144]=72,[165]=82.5,[240]=120})[hz] or hz
            check(props[refresh]==expected,'native automatic refresh follows monitor divisor')
        end
    end
    check(adds==1 and removes==0,'all geometry switches retain one track')
    props.fullscreen=true;probe.layout()
    for i=1,4 do
        local old=props['secondary-sid'];local first=#commands+1
        check(probe.attach(),'live replacement opens')
        if modern then
            check(#commands==first and commands[first][1]=='secondary-ass-replace','live update uses one in-place operation')
            check(props['secondary-sid']==old and adds==1 and removes==0,'live decoder and track retained')
        else
            check(commands[first][1]=='sub-add' and commands[first].sid==old,'old track stays selected during replacement preparation')
            local last=commands[#commands]
            check(last[1]=='sub-remove' and last[2]==old and last.sid~=old,'old track removed only after replacement selection')
        end
        check(#props['track-list']==3 and props[flag]==true,'replacement preserves preexisting tracks and keeps full viewport')
    end
    local old=props['secondary-sid'];local removed=removes
    fail_add=true
    check(not probe.attach(),'failed replacement reported')
    check(props['secondary-sid']==old and removes==removed and #props['track-list']==3,'failed open preserves existing subtitle output')
    fail_add=false
    if modern then
        props['display-fps']=144;props['estimated-vf-fps']=25;props['frame-drop-count']=0
        props['vo-passes']={fresh={{avg=35000000}},redraw={{avg=1000000}}}
        options.overlay_display_sync=true
        props.pause=false;observers.pause('pause',false)
        wall=20;probe.health();wall=22;probe.health()
        check(props[refresh]==48,'native cadence guard includes redraw GPU cost')
        props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=100000}}}
        for i=1,20 do wall=wall+2;probe.health() end
        check(props[refresh]==72,'native cadence recovers after sustained headroom')
    end
    props['secondary-sid']=7;probe.fallback()
    check(props[flag]==false and props['secondary-sid']==7,'ordinary secondary selection restored without override')
    check(props['secondary-sub-ass-override']=='strip','ordinary secondary style restored')
    if modern then check(props[refresh]==37,'ordinary secondary refresh setting restored') end
else
    props.fullscreen=true
    local mode,reason=probe.desired()
    check(mode=='overlay' and reason=='fullscreen-blackbar','legacy core blackbar fallback preserved')
end
options.render_mode='overlay'
check(probe.desired()=='overlay','explicit overlay fallback remains selectable')
if available then
    props['secondary-sid']='no';props['display-fps']=144
    props['estimated-vf-fps']=24;props['frame-drop-count']=0
    props['vo-passes']={fresh={{avg=40000000}}}
    options.overlay_fps=0;options.overlay_display_sync=true
    props.pause=false;observers.pause('pause',false)
    wall=wall+20;probe.health();wall=wall+2;probe.health()
    check(probe.fps()==48,'sustained rendering pressure still activates fallback guard')
    props['vo-passes']={fresh={{avg=1000000}}}
    for i=1,20 do wall=wall+2;probe.health() end
    check(probe.fps()==72,'fallback guard recovers after stable headroom')
end
print('PASS: '..checks..' viewport checks ('..(available and 'capable' or 'legacy')..')')
