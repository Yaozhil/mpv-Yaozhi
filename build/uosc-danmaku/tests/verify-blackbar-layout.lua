package.path = 'portable_config/scripts/uosc_danmaku/?.lua;' .. package.path

local state = {
    width = 1920,
    height = 1080,
    fullscreen = true,
    dpi = 1,
    secondary_sid = 'no',
    secondary_visibility = 'yes',
    secondary_ass_override = 'strip',
    track_adds = 0,
    track_removes = 0,
    dimensions = {w = 1920, h = 1080, ml = 0, mr = 0, mt = 138, mb = 138},
}

local overlays = {}
local observers = {}
local timers = {}

package.preload['mp.msg'] = function()
    return setmetatable({}, {__index = function() return function() end end})
end
package.preload['mp.utils'] = function()
    return {join_path = function(a, b) return a .. '/' .. b end}
end

mp = {}

function mp.create_osd_overlay()
    local overlay = {data = ''}
    function overlay:update() end
    function overlay:remove() self.data = '' end
    overlays[#overlays + 1] = overlay
    return overlay
end

function mp.add_timeout(timeout, callback, disabled)
    local timer = {
        timeout = timeout,
        callback = callback,
        enabled = not disabled,
        kill = function(self) self.enabled = false end,
        resume = function(self) self.enabled = true end,
        is_enabled = function(self) return self.enabled end,
    }
    timers[#timers + 1] = timer
    return timer
end

function mp.add_periodic_timer()
    return {kill = function() end, resume = function() end, is_enabled = function() return false end}
end

function mp.observe_property(name, _, callback)
    observers[name] = callback
end

function mp.get_osd_size()
    return state.width, state.height
end

function mp.get_time() return 1 end

function mp.get_property_number(name, default)
    if name == 'display-hidpi-scale' then return state.dpi end
    if name == 'time-pos' then return 1 end
    return default
end

function mp.get_property_native(name, default)
    if name == 'fullscreen' then return state.fullscreen end
    if name == 'osd-dimensions' then return state.dimensions end
    if name == 'secondary-sid' then return state.secondary_sid end
    if name == 'secondary-sub-visibility' then return state.secondary_visibility end
    if name == 'secondary-sub-ass-override' then return state.secondary_ass_override end
    if name == 'vf' then return {} end
    if name == 'track-list' then
        if state.track_added then
            return {{type = 'sub', title = 'uosc_danmaku', id = 7,
                external = true, ['external-filename'] = state.track_path}}
        end
        return {}
    end
    return default
end

function mp.get_property(name, default) return mp.get_property_native(name, default) end
function mp.set_property_native(name, value)
    if name == 'secondary-sid' then state.secondary_sid = value end
    if name == 'secondary-sub-visibility' then state.secondary_visibility = value end
    if name == 'secondary-sub-ass-override' then state.secondary_ass_override = value end
end
mp.set_property = mp.set_property_native
function mp.command_native() return 'build/uosc-danmaku/tests' end
function mp.commandv(command, value)
    if command == 'sub-add' then
        state.track_added = true
        state.track_path = value
        state.track_adds = state.track_adds + 1
    end
    if command == 'sub-remove' then
        state.track_added = false
        state.track_removes = state.track_removes + 1
    end
end

setmetatable(mp, {__index = function() return function() end end})

options = {
    render_mode = 'auto',
    fullscreen_blackbar = true,
    overlay_fps = 60,
    message_x = 30,
    message_y = 48,
    message_anlignment = 7,
    displayarea = 0.11,
    fontsize = 30,
    fontname = 'Microsoft YaHei',
    scrolltime = 20,
    fixtime = 5,
    opacity = 0.88,
    outline = 0.5,
    shadow = 0,
    bold = true,
    vf_fps = false,
}

ENABLED = false
COMMENTS = nil
HAS_DANMAKU = 'user-data/test/has-danmaku'
DELAY_PROPERTY = 'user-data/test/delay'
DANMAKU_PATH = 'build/uosc-danmaku/tests'
PID = 1
get_danmaku_visibility = function() return true end
set_danmaku_visibility = function() end
toggle_danmaku_switch = function() end
refresh_danmaku_button = function() end
binary_search = function() return 1 end
file_exists = function(path)
    local file = io.open(path, 'rb')
    if not file then return false end
    file:close()
    return true
end

assert(loadfile('portable_config/scripts/uosc_danmaku/modules/render.lua'))()

local message_overlay = assert(overlays[3], 'message overlay missing')
local message = 'line one\\Nline two'

local function parse_position()
    local x, y = message_overlay.data:match([=[\pos%((%d+),(%d+)%)]=])
    return assert(tonumber(x), message_overlay.data), assert(tonumber(y), message_overlay.data)
end

local function expect_message(name, expected_x, expected_y)
    show_message(message, 3)
    local actual_x, actual_y = parse_position()
    assert(actual_x == expected_x and actual_y == expected_y,
        string.format('%s: expected (%d,%d), got (%d,%d)',
            name, expected_x, expected_y, actual_x, actual_y))
    print(string.format('PASS %-38s x=%d y=%d', name, actual_x, actual_y))
end

local function set_geometry(width, height, top, bottom)
    state.width = width
    state.height = height
    state.dimensions = {
        w = width,
        h = height,
        ml = 0,
        mr = 0,
        mt = top,
        mb = bottom or top,
    }
end

local function expect_overlay_mode(name, expected)
    state.track_added = false
    show_danmaku_func()
    local actual = overlays[1].data:find('overlay lane probe', 1, true) ~= nil
    assert(actual == expected,
        string.format('%s: expected overlay=%s, got overlay=%s',
            name, tostring(expected), tostring(actual)))
    if expected then
        assert(state.track_added ~= true, name .. ': native ASS track unexpectedly loaded')
    else
        assert(state.track_added == true, name .. ': native ASS track was not loaded')
    end
    print(string.format('PASS %-38s overlay=%s', name, tostring(actual)))
end

expect_message('fullscreen status below overlay lanes', 45, 161)

state.width = 1536
state.height = 864
state.dpi = 1.25
state.dimensions = {w = 1536, h = 864, ml = 0, mr = 0, mt = 110, mb = 110}
expect_message('125pct DPI status below overlay lanes', 38, 129)

state.width = 1920
state.height = 1080
state.dpi = 1
state.dimensions = {w = 1920, h = 1080, ml = 0, mr = 0, mt = 0, mb = 0}
expect_message('fullscreen status below picture lanes', 45, 161)

state.fullscreen = false
state.dimensions = {w = 1920, h = 1080, ml = 0, mr = 0, mt = 138, mb = 138}
expect_message('windowed placement unchanged', 45, 167)

state.fullscreen = true
state.dimensions = {w = 1920, h = 1080, ml = 240, mr = 240, mt = 0, mb = 0}
expect_message('pillarbox status follows picture left', 252, 161)

state.dimensions = {w = 1920, h = 1080, ml = 0, mr = 0, mt = 138, mb = 138}

state.fullscreen = true
observers['osd-width']('osd-width', state.width)
observers['osd-height']('osd-height', state.height)
COMMENTS = {{
    start_time = 0,
    end_time = 20,
    style = 'R2L',
    text = '{\\move(2100,30,-300,30)}overlay lane probe',
    move = {2100, 30, -300, 30},
    layer = 0,
}}
ENABLED = true
expect_overlay_mode('large blackbar displayarea 0.11', true)
assert(overlays[1].data:find('\\pos', 1, true), 'overlay event was not positioned from OSD top')
-- This is the existing production canvas scale, before the clock/cadence fix.
-- Keep the baseline visible here; changing font policy is outside this fix.
local canvas = get_danmaku_canvas('overlay')
assert(math.abs(canvas.font_size - (30 - 2 * 1920 / 1080)) < 1e-9,
    'existing overlay canvas font scale changed')
assert(overlays[1].data:find('\\fs26', 1, true), 'overlay prefix differs from the existing canvas scale')

options.displayarea = 0.2
expect_overlay_mode('large blackbar displayarea 0.20', true)

options.displayarea = 0.3
expect_overlay_mode('partial blackbar displayarea 0.30', true)
expect_message('partial blackbar status below lanes', 45, 366)

options.displayarea = 0.5
expect_overlay_mode('partial blackbar displayarea 0.50', true)
expect_message('half-screen status below lanes', 45, 582)

set_geometry(1920, 1080, 24, 24)
options.displayarea = 0.3
expect_overlay_mode('small blackbar displayarea 0.30', true)
expect_message('small blackbar status below lanes', 45, 366)

set_geometry(1920, 1080, 0, 0)
expect_overlay_mode('no blackbar keeps native ASS', false)

state.fullscreen = false
timers[1].callback()
assert(state.track_added == true, 'leaving fullscreen did not restore native ASS track')
for _, overlay in ipairs({overlays[1], overlays[2]}) do
    assert(not overlay.data:find('overlay lane probe', 1, true),
        'native mode left comments visible in an overlay')
    assert(overlay.data == '' or overlay.data:find('\\alpha&HFF&', 1, true),
        'native mode left a visible warm overlay')
end
print('PASS leaving fullscreen restored native ASS mode')

state.fullscreen = true
set_geometry(1920, 1080, 138, 138)
timers[1].callback()
assert(state.track_added == true, 'fullscreen fallback detached the parked native ASS track')
assert(state.secondary_visibility == 'no', 'fullscreen fallback did not hide the parked track')
assert(overlays[1].data:find('overlay lane probe', 1, true), 'entering fullscreen did not restore overlay')
print('PASS entering fullscreen restored blackbar overlay')

local adds, removes = state.track_adds, state.track_removes
state.fullscreen = false
timers[1].callback()
assert(state.track_added and state.secondary_visibility == 'yes',
    'leaving fullscreen did not resume the parked native ASS track')
assert(state.track_adds == adds and state.track_removes == removes,
    'fullscreen handoff reloaded the native ASS track')
print('PASS fullscreen handoff resumes the same external track')

hide_danmaku_func()
os.remove('build/uosc-danmaku/tests/uosc-danmaku-1.ass')
print('all blackbar layout tests passed')
