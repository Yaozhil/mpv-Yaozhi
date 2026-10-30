-- Runs the actual render module with controlled mpv properties and callbacks.
-- No player process, network, private config or production file writes.
local source = (arg and arg[1]) or os.getenv('DANMAKU_RECOVERY_SOURCE') or 'portable_config/scripts/uosc_danmaku/modules/render.lua'
local core = '1000'
local legacy = core == 'legacy'
local maximum = tonumber(core) or 240
local refresh = 'secondary-sub-ass-refresh-rate'
package.path = 'build/feedback/tests/fixtures/?.lua;portable_config/scripts/uosc_danmaku/?.lua;' .. package.path
local wall, next_id = 1, 40
local props = {['secondary-sid']='no', ['secondary-sub-visibility']='yes',
    ['secondary-sub-ass-override']='strip', ['fullscreen']=false,
    ['secondary-sub-ass-full-viewport']=false, ['track-list']={},
    ['osd-dimensions']={w=1920,h=1080,mt=0,mb=0},
    ['video-params/gamma']='bt.709', ['time-pos']=1, ['speed']=1,
    ['video-speed-correction']=1, ['display-fps']=144, ['estimated-vf-fps']=25,
    ['frame-drop-count']=0, ['pause']=true,
    ['command-list']={{name='secondary-ass-replace'}}}
if not legacy then props[refresh] = 37 end
if tonumber(core) then props['option-info/' .. refresh] = {max=maximum} end
local observers, hooks, events, timers, writes = {}, {}, {}, {}, {}
local noop = function() end
local logger = setmetatable({}, {__index=function() return noop end})
local function timer(timeout, fn, disabled)
    local value = {timeout=timeout, fn=fn, enabled=not disabled,
        kill=function(self) self.enabled=false end,
        resume=function(self) self.enabled=true end,
        is_enabled=function(self) return self.enabled end}
    timers[#timers+1]=value
    return value
end
mp = {get_time=function() return wall end, get_osd_size=function() return 1920,1080 end,
    get_property_native=function(key, default)
        if props[key] ~= nil then return props[key] end
        return default
    end,
    set_property_native=function(key, value)
        props[key]=value
        writes[#writes+1]={key=key,value=value}
    end,
    observe_property=function(key, _, fn) observers[key]=fn end,
    add_hook=function(key, _, fn) hooks[key]=fn end,
    register_event=function(key, fn) events[key]=fn end,
    register_script_message=noop, create_osd_overlay=function() return {update=noop,remove=noop} end,
    add_timeout=timer, add_periodic_timer=function(t, fn) return timer(t,fn,false) end,
    command_native=function() return 'fixture' end,
    commandv=function(command, value, _, title)
        if command=='sub-add' then
            next_id=next_id+1
            props['track-list'][#props['track-list']+1]={type='sub',id=next_id,
                title=title,external=true,codec='ass',['external-filename']=value}
        elseif command=='sub-remove' then
            for i=#props['track-list'],1,-1 do
                if props['track-list'][i].id==value then table.remove(props['track-list'],i) end
            end
        end
        return true
    end}
mp.get_property, mp.get_property_number = mp.get_property_native, mp.get_property_native
mp.set_property, mp.set_property_bool = mp.set_property_native, mp.set_property_native
package.loaded['mp.msg'] = logger
package.loaded['mp.utils'] = {join_path=function(a,b) return a .. '/' .. b end,
    file_info=function() return {is_dir=true} end}
options = {render_mode='auto',fullscreen_blackbar=true,fontsize=30,fontname='sans-serif',
    scrolltime=15,fixtime=5,opacity=1,outline=1,shadow=0,bold=false,displayarea=.11,
    smart_color=false,vf_fps=false,overlay_fps=0,overlay_display_sync=true,
    overlay_adaptive_fps=true}
ENABLED=true;PID=123;DANMAKU_PATH='fixture';HAS_DANMAKU='has';DANMAKU_COUNT='count'
DELAY_PROPERTY='delay';DELAY=0;DANMAKU={sources={},count=1}
local function comments()
    return {{text='{\\move(1920,20,-300,20)}test',move={1920,20,-300,20},
        start_time=0,end_time=20,layer=0,style='R2L'}}
end
COMMENTS=comments()
function file_exists() return false end
function get_danmaku_visibility() return true end
function set_danmaku_visibility() end
function refresh_danmaku_button() end
function binary_search() return 1 end
local f=assert(io.open(source,'rb'));local text=f:read('*a');f:close()
local probe=assert(loadstring(text .. [[
write_text_file = function() return true end
return {resolve=resolve_render_mode,attach=render_ass_track,health=monitor_overlay_health,
    sync=sync_overlay_display_mode,fps=get_overlay_fps,base=get_base_overlay_fps,
    ratio=overlay_render_ratio,level=function() return overlay_adaptive_level end,
    clock=function() return overlay_clock_media,overlay_clock_wall,overlay_render_deadline end,
    good=function() return overlay_health_good_seconds end,
    reset=function() reset_overlay_health_window(0) end}
]],'@' .. source))()
local checks, failures = 0, {}
local function check(value,label)
    checks=checks+1
    if not value then failures[#failures+1]=label end
end
local function near(actual,expected,label,tolerance)
    check(type(actual)=='number' and math.abs(actual-expected)<(tolerance or .00001),
        label .. ': got=' .. tostring(actual) .. ' expected=' .. tostring(expected))
end
local function external(key,value)
    props[key]=value
    if observers[key] then observers[key](key,value) end
end
check(probe.resolve()=='ass-track','native renderer selected')
check(probe.attach(),'native external track attached')
external('pause',false)


local scenarios = 0
local function step(count, drops)
    for i=1,count do
        props['frame-drop-count']=(props['frame-drop-count'] or 0)+(drops or 0)
        wall=wall+2
        probe.health()
    end
end
local function fresh()
    hooks.on_unload()
    COMMENTS=comments();ENABLED=true;DANMAKU={sources={},count=1}
    options.render_mode='auto';options.overlay_fps=0;options.overlay_adaptive_fps=true
    props['secondary-sid']='no';props['frame-drop-count']=0
    props['core-idle']=false
    external('display-fps',144);external('estimated-vf-fps',25)
    probe.resolve();check(probe.attach(),'attach fresh native fixture')
    external('pause',false);external('seeking',false);external('paused-for-cache',false)
    props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=20000000}}}
    wall=wall+30;probe.health();step(1)
    check(probe.level()==1,'known normal-rate pressure activates protection')
    near(props[refresh],48,'protection retains exact 144/3 display divisor')
    scenarios=scenarios+1
end
local function low_budget()
    props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=100000}}}
end

-- The reported self-lock: independently sourced output drops persist while
-- measured normal-rate work is small. Both zero and large drop rates recover.
for _,drop_rate in ipairs({0,1,24,200}) do
    fresh();low_budget();step(17,drop_rate)
    check(probe.level()==0,'known headroom recovers despite global VO drops='..drop_rate)
    near(props[refresh],72,'recovery restores automatic 144/2 cadence')
    step(30,drop_rate)
    check(probe.level()==0,'low-cost output drops do not flap back to protection')
end

-- Protected cost fitting is insufficient: projection at base cadence stays
-- overloaded, with or without global drops. This must never recover.
for _,drop_rate in ipairs({0,24}) do
    fresh()
    check(probe.ratio()<.50 and probe.ratio(72)>.78,'fixed native fixture models expensive base cadence')
    step(120,drop_rate)
    check(probe.level()==1,'normal-rate predicted pressure remains protected')
    near(props[refresh],48,'high pressure retains reduced cadence across 240 seconds')
end

-- A middling projected budget also cannot count as sustained recovery.
fresh();props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=14000000}}}
step(60,1)
check(probe.level()==1,'50-78 percent normal-rate projection stays protected')

-- Missing/invalid timing data must not relax the conservative zero-drop rule.
for _,passes in ipairs({{}, {fresh={{avg=0}},redraw={{avg=100000}}}}) do
    fresh();props['vo-passes']=passes
    step(60,24)
    check(probe.level()==1,'unknown budget with continued drops stays protected')
    step(20,0)
    check(probe.level()==0,'unknown budget can still recover using stable zero-drop fallback')
end

-- Stable headroom remains a twenty-second condition after the twelve-second
-- hold. One light sample must not undo protection.
fresh();low_budget();step(7,24)
check(probe.level()==1,'short headroom period does not immediately recover')
local hold_good=probe.good()
check(hold_good>0 and hold_good<20,'headroom stability counter is accumulating')
props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=20000000}}}
step(1,24)
check(probe.good()==0,'known heavy sample resets headroom stability immediately')
low_budget();step(9,24)
check(probe.level()==1,'nineteen or fewer post-pressure seconds cannot recover')
step(1,24)
check(probe.level()==0,'full twenty seconds stable normal-rate headroom recovers')

-- Pause does not count toward stability and starts a fresh warmup window;
-- it cannot recover in the background. Existing observer resets are retained.
fresh();low_budget();step(8,24)
external('pause',true)
local before_pause=probe.good()
step(30,24)
check(probe.level()==1,'paused time cannot restore cadence')
check(probe.good()==before_pause,'idle health timer does not add recovery time')
external('pause',false);step(2,24)
check(probe.level()==1,'post-pause warmup does not immediately recover')
step(16,24)
check(probe.level()==0,'playing stable headroom eventually recovers after pause')

-- Compatibility Overlay retains its zero-drop recovery requirement; the
-- native-only exemption does not silently change its behavior.
fresh();low_budget();options.render_mode='overlay';probe.resolve();probe.reset()
step(60,24)
check(probe.level()==1,'compatibility Overlay with global drops does not use native exemption')
options.render_mode='auto';probe.resolve()

-- New files do not inherit the previous workload or its reduced refresh.
fresh();hooks.on_unload()
check(probe.level()==0,'unload removes previous workload protection')
COMMENTS=comments();ENABLED=true;DANMAKU={sources={},count=1};props['secondary-sid']='no'
low_budget();probe.resolve();check(probe.attach(),'next file attaches')
near(props[refresh],72,'next file starts at automatic normal cadence')

if #failures>0 then error(table.concat(failures,'\n')) end
return string.format('NATIVE_RECOVERY_PASS scenarios=%d checks=%d',scenarios,checks)
