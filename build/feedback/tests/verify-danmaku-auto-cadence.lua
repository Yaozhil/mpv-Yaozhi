-- Deterministic real render.lua exercise with a quantized 24 fps media clock.
-- No external processes, network or player configuration writes.
local source=assert(arg[1]);local mode=arg[2] or 'verify'
local media_fps=tonumber(arg[3]) or 24
package.path='portable_config/scripts/uosc_danmaku/?.lua;'..package.path
local wall=0;local props={['time-pos']=0,['speed']=1,['display-fps']=60,['video-speed-correction']=1,
    ['video-params/gamma']='bt.709',['secondary-sid']='no'}
local observers,events,overlays={},{},{}
mp={}
function mp.get_time()return wall end
function mp.get_property_native(k,d)if props[k]~=nil then return props[k] end return d end
mp.get_property_number=mp.get_property_native;mp.get_property=mp.get_property_native
function mp.set_property_native(k,v)props[k]=v end
mp.set_property_bool=mp.set_property_native
function mp.observe_property(k,_,f)observers[k]=f end
function mp.register_event(k,f)events[k]=f end
function mp.register_script_message()end
function mp.add_hook()end
function mp.get_osd_size()return 1920,1080 end
function mp.commandv()end
function mp.create_osd_overlay()
    local o={update=function()end,remove=function()end};overlays[#overlays+1]=o;return o
end
function mp.add_timeout(t,f,disabled)
    return {timeout=t,fn=f,on=not disabled,kill=function(self)self.on=false end,
        resume=function(self)self.on=true end,is_enabled=function(self)return self.on end}
end
package.preload['mp.msg']=function()return {info=function()end,warn=function()end,verbose=function()end,error=function()end}end
package.preload['mp.utils']=function()return {}end
options={render_mode='overlay',fontname='Microsoft YaHei',fontsize=30,opacity=.88,outline=.5,
    shadow=0,bold=true,scrolltime=20,fixtime=5,displayarea=.3,overlay_fps=60,
    overlay_display_sync=false,vf_fps=false,smart_color=false,smart_color_percent=25}
ENABLED=true;HAS_DANMAKU='has';DANMAKU_COUNT='count';DANMAKU_PATH='.';PID=42
function get_danmaku_visibility()return true end
function set_danmaku_visibility()end
function filter_state()return false end
function binary_search()return 1 end
COMMENTS={{text='{\\move(1920,20,-300,20)}运动连续性',move={1920,20,-300,20},
    start_time=0,end_time=20,layer=0,style='R2L'}}
local f=assert(io.open(source,'rb'));local content=f:read('*a');f:close()
local probe=assert(loadstring(content..[[
return {time=get_overlay_media_time,start=start_overlay_timer,stop=stop_overlay_timer,
    fps=get_overlay_fps,sync=sync_overlay_display_mode,clear=clear_overlay_clock,clock=function()return overlay_clock_media,overlay_clock_wall,overlay_render_deadline end}
]],'@'..source))()
local checks,failures,backsteps=0,{},{}
local function check(v,label)checks=checks+1;if not v then failures[#failures+1]=label end end
local function property(k,v)props[k]=v;if observers[k]then observers[k](k,v)end end
property('osd-width',1920);property('osd-height',1080);property('pause',false)
show_danmaku_func()
local function x()
    render()
    return assert(tonumber(overlays[1].data:match('\\pos%(([%d%.%-]+),')))
end
local previous=x()
for i=1,240 do
    wall=i/60;props['time-pos']=math.floor(wall*media_fps)/media_fps
    local before=x()
    check(before<=previous+.001,'normal movement reversed')
    if i%7==0 then
        local a,b,deadline=probe.clock()
        refresh_danmaku_renderer()
        local after=x()
        if after>before+.001 then backsteps[#backsteps+1]=after-before end
        check(after<=before+.001,'style/live refresh moved backwards')
        local aa,bb,dd=probe.clock()
        check(a==aa and b==bb and deadline==dd,'refresh restarted cadence')
        previous=after
    else previous=before end
end
local before=x()
property('paused-for-cache',true)
check(x()==before,'cache entry jumps')
wall=wall+3;check(x()==before,'cached pause moves')
property('paused-for-cache',false)
check(x()==before,'cache resume jumps')
events['playback-restart']({})
check(x()==before,'restart event jumps')
wall=wall+.03;local pre_pause=x();property('pause',true)
check(x()==pre_pause,'pause entry jumps')
wall=wall+2;check(x()==pre_pause,'pause moves')
property('pause',false);check(x()==pre_pause,'pause resume jumps')
-- A real explicit backward seek must remain immediate.
property('seeking',true);props['time-pos']=1;property('seeking',false)
events['playback-restart']({});check(math.abs(probe.time()-1)<.001,'backward seek rejected')
local origin=x();property('speed',2)
check(x()==origin,'speed change jumps')
wall=wall+.1;check(math.abs(x()-(origin-22.2))<.11,'2x movement incorrect')
local speed_origin=x();property('video-speed-correction',1.001)
check(x()==speed_origin,'speed correction jumps')
for i=1,80 do
    wall=wall+1/60
    local a=x()
    property('video-speed-correction',i%2==0 and 1.0002 or .9998)
    check(x()==a,'frequent correction changes position')
    local b,c,d=probe.clock();probe.start()
    local bb,cc,dd=probe.clock();check(b==bb and c==cc and d==dd,'running timer reanchored')
end
local held=x();property('pause',true);property('paused-for-cache',true)
wall=wall+1;check(x()==held,'overlapping stops move')
property('pause',false);wall=wall+1;check(x()==held,'cache stop lost when pause released')
property('paused-for-cache',false);check(x()==held,'overlapping resume jumps')

-- A settings/live update between ticks must not submit an early movement.
local stable=x();local a,b,deadline=probe.clock();wall=wall+.005
refresh_danmaku_renderer()
local repainted=tonumber(overlays[1].data:match('\\pos%(([%d%.%-]+),'))
check(repainted==stable,'refresh moved between scheduled frames')
local aa,bb,dd=probe.clock();check(a==aa and b==bb and deadline==dd,'refresh changed phase')
-- Keep the overlay cadence on an integer divisor of the display refresh,
-- with display-paced OSD while preserving explicit user synchronization.
options.overlay_display_sync=true;options.overlay_fps=0
props['video-sync']='audio'
for _,case in ipairs({{60,60},{75,75},{120,120},{144,72},{165,82.5},{240,120},{59.94,59.94}})do
 props['display-fps']=case[1]
 check(math.abs(probe.fps()-case[2])<.001,'unequal display cadence '..case[1])
end
options.overlay_fps=45;props['display-fps']=144
check(probe.fps()==36,'manual ceiling not honoured')
options.overlay_fps=0;props['speed']=1;props['estimated-vf-fps']=60;props['video-sync']='audio'
local applied,restored=0,0
mp.commandv=function(cmd,name,action)
 if cmd=='apply-profile' then
  if action=='restore' then restored=restored+1;if props['video-sync']=='display-vdrop'then props['video-sync']='audio'end
  else applied=applied+1;props['video-sync']='display-vdrop'end
 end
end
local anchor_media,anchor_wall=probe.clock();probe.sync()
local new_media,new_wall=probe.clock()
check(applied==0 and restored==0 and props['video-sync']=='audio','renderer must not take over video-sync')
check(anchor_media==new_media and anchor_wall==new_wall,'sync changed playback clock')
check(probe.fps()==72,'budgeted automatic cadence not applied')
local jitter_media,jitter_wall,jitter_deadline=probe.clock()
property('display-fps',143.9992);probe.start()
local jitter_media_after,jitter_wall_after,jitter_deadline_after=probe.clock()
check(jitter_media==jitter_media_after and jitter_wall==jitter_wall_after
    and jitter_deadline==jitter_deadline_after,'minor refresh drift restarted cadence')
probe.sync();check(applied==0,'overlay applied a sync profile')
props['video-sync']='display-resample';probe.sync()
check(props['video-sync']=='display-resample','overrode user sync')
props['video-sync']='audio';probe.sync();check(applied==0 and props['video-sync']=='audio','overrode explicit audio sync')
options.overlay_fps=90;options.overlay_display_sync=false;probe.sync()
check(probe.fps()==90,'disabled display pacing ignored')

print(string.format('MOTION_%s checks=%d failures=%d refreshBacksteps=%d maxBackstep=%.3fpx',
    #failures==0 and 'PASS' or 'FAIL',checks,#failures,#backsteps,math.max(0,unpack(backsteps))))
for i=1,math.min(6,#failures)do print(failures[i])end
if mode~='baseline' then assert(#failures==0,'motion continuity failed')end
