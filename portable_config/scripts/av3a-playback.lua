local mp = require 'mp'
local msg = require 'mp.msg'
local utils = require 'mp.utils'

-- Only this script owns av3a_render. Content selection owns av3a_content.
-- All changes are file-local; explicit decoder options remain authoritative.
local active, file_has_av3a, announced = false, false, false
local owned, pending, request, request_timer
local policy, reason, external = 'auto', 'idle', false
local decode_serial, request_serial = 0, 0

local function copy_map(source)
    local result = {}
    for key, value in pairs(source) do result[key] = value end
    return result
end

local function is_av3a(track)
    if not track then return false end
    local codec = tostring(track.codec or ''):lower()
    return codec == 'av3a' or codec == 'avs3a' or codec == 'libarcdav3a'
end

local function selected_audio()
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'audio' and track.selected
            and track['main-selection'] == 0 then
            return track.id, is_av3a(track)
        end
    end
end

local function contains_av3a()
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'audio' and is_av3a(track) then return true end
    end
    return false
end

local function diagnostic_output()
    if mp.get_property('options/o', '') ~= '' then return true end
    local ao = mp.get_property('options/ao', ''):lower()
    for item in ao:gmatch('[^,]+') do
        if item:match('^%s*([%w_-]+)') == 'pcm' then return true end
    end
    return mp.get_property('options/audio-device', ''):lower():match('^pcm/') ~= nil
end

local function channel_params(name)
    local params = mp.get_property_native(name)
    if type(params) ~= 'table' then return nil end
    local count = params['channel-count']
    if type(count) ~= 'number' or count < 1 or count > 256
        or count ~= math.floor(count) then return nil end
    local layout = type(params.channels) == 'string' and params.channels or nil
    if layout and #layout > 128 then layout = nil end
    return {channels = count, layout = layout}
end

local function actual_render()
    local _, av3a = selected_audio()
    if not av3a then return nil end
    local raw = mp.get_property('audio-av3a-content-info')
    if type(raw) ~= 'string' or #raw > 16384 then return nil end
    local info = utils.parse_json(raw)
    if type(info) == 'table' and info.version == 1
        and (info.render == 'native' or info.render == 'binaural') then
        return info.render
    end
end

local function publish()
    local track, av3a = selected_audio()
    local render = actual_render()
    local current = mp.get_property_native('options/ad-lavc-o', {})
    local mode = policy == 'auto' and owned and 'binaural-if-spatial'
        or owned and owned.value or external and current.av3a_render or 'native'
    mp.set_property_native('user-data/av3a-playback', {
        version = 2, mode = mode, policy = external and 'explicit' or policy,
        reason = reason, actual_render = render, available = active and av3a or false,
        confirmed = render ~= nil and channel_params('audio-params') ~= nil
            and (not owned or render == owned.value),
        locked = external or diagnostic_output(),
        capabilities = {binaural = true, native = true, speaker = false},
        track = track, decoded = av3a and channel_params('audio-params') or nil,
        output = av3a and channel_params('audio-out-params') or nil,
        pending = request ~= nil, requested = request and request.policy or nil,
        request_id = request and request.id or nil,
        preselections = 'unavailable',
    })
end

local function stop_request()
    if request_timer then request_timer:kill(); request_timer = nil end
    request = nil
    request_serial = request_serial + 1
end

local function write_avopts(value)
    local ok, err = mp.set_property_native('file-local-options/ad-lavc-o', value)
    if not ok then
        msg.warn('AV3A 播放策略未生效：' .. tostring(err))
        reason = 'set-option-failed'
    end
    return ok
end

local function check_request(serial)
    if not request or serial ~= request_serial then return end
    request_timer = nil
    local track, av3a = selected_audio()
    if not active or not av3a or track ~= request.track or external then
        stop_request(); reason = 'request-cancelled'; publish(); return
    end
    if actual_render() == request.render and channel_params('audio-params')
        and (request.same_render or decode_serial > request.serial) then
        stop_request(); reason = 'mode-confirmed'; publish()
        mp.osd_message('AV3A 输出模式已生效', 2)
        return
    end
    if request.remaining <= 0 then
        stop_request(); reason = 'mode-unconfirmed'; publish()
        mp.osd_message('AV3A 模式尚未确认；暂停时请继续播放后查看状态', 4)
        return
    end
    request.remaining = request.remaining - 1
    publish()
    request_timer = mp.add_timeout(0.2, function() check_request(serial) end)
end

local function release_owned()
    if not owned then return true end
    local current = mp.get_property_native('options/ad-lavc-o')
    if type(current) == 'table' and current.av3a_render == owned.value then
        local restored = copy_map(current)
        restored.av3a_render = owned.previous
        if not write_avopts(restored) then return false end
    end
    owned = nil
    return true
end

local function refresh()
    if not active then publish(); return end
    local current = mp.get_property_native('options/ad-lavc-o')
    if type(current) ~= 'table' then
        reason = 'avoptions-unavailable'; publish(); return
    end
    -- Removing/changing a key we inserted is an explicit external override.
    if owned and current.av3a_render ~= owned.value then
        owned = nil; external = true; stop_request()
    end
    local wanted = file_has_av3a and not diagnostic_output() and not external
    if owned and not wanted then
        release_owned()
        current = mp.get_property_native('options/ad-lavc-o', {})
    end
    if not owned and current.av3a_render ~= nil then
        external = true
        reason = 'explicit-decoder-option'
    elseif not wanted then
        reason = diagnostic_output() and 'diagnostic-output'
            or external and 'user-override' or 'non-av3a-file'
    elseif not owned then
        local options = copy_map(current)
        options.av3a_render = policy == 'native' and 'native' or 'binaural'
        -- Mark ownership before writing: option observers may fire immediately.
        owned = {previous = current.av3a_render, value = options.av3a_render}
        if not write_avopts(options) then owned = nil; publish(); return end
        reason = 'device-playback-compatibility'
        if not announced then
            msg.info('AV3A 对象/HOA 默认双耳立体声；纯声道保留原布局。')
            announced = true
        end
    end
    publish()
end

local function schedule_refresh()
    if not active or pending then return end
    pending = mp.add_timeout(0, function() pending = nil; refresh() end)
end

local function choose_mode(value, token)
    if value ~= 'auto' and value ~= 'native' then return end
    if type(token) ~= 'string' or #token > 64 then return end
    local track, av3a = selected_audio()
    if not active or not av3a then return end
    refresh()
    if external or diagnostic_output() then
        mp.osd_message('AV3A 输出由显式参数或导出设置指定，未覆盖原设置', 4)
        return
    end
    local current = mp.get_property_native('options/ad-lavc-o')
    if type(current) ~= 'table' then return end
    local target = value == 'native' and 'native' or 'binaural'
    local same_render = actual_render() == target
    local serial_before_write = decode_serial
    local options = copy_map(current)
    options.av3a_render = target
    local previous = owned
    owned = {previous = current.av3a_render, value = target}
    if previous then owned.previous = previous.previous end
    if current.av3a_render ~= target and not write_avopts(options) then
        owned = previous; publish(); return
    end
    policy = value
    stop_request()
    request = {id = token, policy = value, render = target, track = track,
        serial = serial_before_write, same_render = same_render, remaining = 39}
    reason = 'mode-requested'
    publish()
    local serial = request_serial
    request_timer = mp.add_timeout(0.2, function() check_request(serial) end)
end

local function clear_state()
    if pending then pending:kill(); pending = nil end
    stop_request()
    active, file_has_av3a, announced = false, false, false
    owned, external, policy, reason = nil, false, 'auto', 'idle'
    decode_serial = 0
    publish()
end

mp.register_script_message('set-mode', choose_mode)
mp.add_hook('on_load', 60, clear_state)
mp.add_hook('on_loaded', 60, function()
    file_has_av3a = contains_av3a(); active = true; refresh()
end)
mp.add_hook('on_unload', 60, function() release_owned(); clear_state() end)
mp.register_event('end-file', clear_state)
mp.observe_property('track-list', 'native', function()
    local track, av3a = selected_audio()
    if request and (not av3a or track ~= request.track) then stop_request() end
    schedule_refresh()
end)
mp.observe_property('options/ad-lavc-o', 'native', schedule_refresh)
mp.observe_property('options/ao', 'string', schedule_refresh)
mp.observe_property('options/audio-device', 'string', schedule_refresh)
mp.observe_property('audio-params', 'native', function()
    decode_serial = decode_serial + 1; publish()
end)
mp.observe_property('audio-out-params', 'native', publish)
mp.observe_property('audio-av3a-content-info', 'string', publish)
