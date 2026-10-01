-- Runs the actual render module with controlled mpv properties and callbacks.
-- No player process, network, private config or production file writes.
local source = assert(arg[1])
local core = arg[2] or '1000'
local legacy = core == 'legacy'
local maximum = tonumber(core) or 240
local refresh = 'secondary-sub-ass-refresh-rate'
package.path = 'portable_config/scripts/uosc_danmaku/?.lua;' .. package.path
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
    clock=function() return overlay_clock_media,overlay_clock_wall,overlay_render_deadline end}
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

local hz_cases={{59.94,59.94},{60,60},{75,75},{90,90},{100,100},{119.88,119.88},
    {120,120},{120.2,120.2},{120.5,120.5},{120.5001,60.25005},{121,60.5},
    {143.999225,71.9996125},{144,72},{165,82.5},{179.82,89.91},
    {180,90},{200,100},{239.76,119.88},{240,120},{360,120},{480,120},{540,108},{600,120}}
for _,entry in ipairs(hz_cases) do
    local hz=entry[1]
    external('display-fps',hz)
    local expected=entry[2]
    near(probe.fps(),expected,'automatic target at ' .. hz)
    if not legacy then near(props[refresh],expected,'display observer updates selected native track at ' .. hz,.01) end
end

-- Source cadence must not become the redraw cadence while changing monitors.
external('display-fps',143.999225)
for _,fps in ipairs({12,23.976,24,25,29.97,30,50,60,120,240,480}) do
    external('estimated-vf-fps',fps)
    near(probe.fps(),71.9996125,'source fps does not cap native redraw at ' .. fps)
end
for _,invalid in ipairs({0,-1,math.huge,0/0}) do
    external('display-fps',invalid)
    near(probe.fps(),60,'unknown/invalid display rate uses bounded fallback')
    if not legacy then near(props[refresh],60,'invalid display fallback applied safely') end
end
external('display-fps',144)

-- Explicit user ceilings/adaptive preferences remain effective.
options.overlay_fps=90
probe.sync();near(probe.fps(),72,'manual ceiling uses integer display divisor')
options.overlay_fps=45
probe.sync();near(probe.fps(),36,'lower manual ceiling retained')
options.overlay_display_sync=false;options.overlay_fps=90
probe.sync();near(probe.fps(),90,'explicit asynchronous manual ceiling retained')
options.overlay_fps=0
probe.sync();near(probe.fps(),72,'automatic budget remains an exact divisor with pacing disabled')
options.overlay_display_sync=true
external('display-fps',360)
options.overlay_fps=360
probe.sync();near(probe.fps(),not legacy and maximum>=360 and 360 or 180,
    'explicit high-refresh native ceiling respects core range')
options.overlay_fps=0
external('display-fps',144)
options.overlay_adaptive_fps=false
props['vo-passes']={fresh={{avg=40000000}},redraw={{avg=8000000}}}
wall=100;probe.health();wall=102;probe.health()
near(probe.fps(),72,'disabled adaptive preference retains normal automatic budget')
options.overlay_adaptive_fps=true

if not legacy then
    external('estimated-vf-fps',25)
    props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=20000000}}}
    wall=140;probe.health();wall=142;probe.health()
    near(props[refresh],48,'real native budget pressure activates protection')
    check(probe.ratio()<.50 and probe.ratio(72)>.78,
        'fixture separates protected headroom from normal-rate overload')
    for i=1,40 do
        wall=wall+2;probe.health()
        near(props[refresh],48,'fixed overloaded normal cadence remains protected at sample ' .. i)
    end
    props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=100000}}}
    for i=1,25 do wall=wall+2;probe.health() end
    near(props[refresh],72,'sustained normal-rate headroom restores normal automatic cadence')
    -- Rich-budget output spikes do not trigger an arbitrary rate cut.
    for i=1,5 do
        props['frame-drop-count']=props['frame-drop-count']+10
        wall=wall+2;probe.health()
    end
    near(props[refresh],72,'drops without rendering pressure do not cut native cadence')
    props['vo-passes']={fresh={{avg=1000000}},redraw={{avg=20000000}}}
    wall=wall+30;probe.health();wall=wall+2;probe.health()
    near(props[refresh],48,'second workload can activate protection again')
    hooks.on_unload()
    check(probe.level()==0,'unload clears protection from previous workload')
    COMMENTS=comments();ENABLED=true;DANMAKU={sources={},count=1}
    external('display-fps',240)
    probe.resolve();check(probe.attach(),'new file attaches independent ASS track')
    near(props[refresh],120,'next light file starts at normal automatic cadence')
end

-- Explicit compatibility Overlay keeps its existing timer/work caps.
options.render_mode='overlay'
props['secondary-sid']='no'
options.overlay_adaptive_fps=false
probe.resolve()
for _,entry in ipairs({{144,72},{165,82.5},{240,120},{360,120},{480,120},{540,108}}) do
    external('display-fps',entry[1])
    near(probe.fps(),entry[2],'compatibility overlay retains budget at ' .. entry[1])
end
options.overlay_fps=360
external('display-fps',360)
near(probe.fps(),180,'compatibility overlay retains explicit 240 Hz ceiling')
print(string.format('NATIVE_CADENCE_%s core=%s checks=%d failures=%d',
    #failures==0 and 'PASS' or 'FAIL',core,checks,#failures))
for i=1,math.min(#failures,12) do print(failures[i]) end
if #failures>0 then os.exit(1) end
