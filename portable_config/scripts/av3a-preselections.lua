local mp = require 'mp'
local utils = require 'mp.utils'
local msg = require 'mp.msg'

local MENU_TYPE = 'av3a_preselections'
local PROPERTY = 'audio-av3a-content-info'
local MAX_JSON = 16384
local MAX_ITEMS = 64
local timer, request, owned
local generation = 0
local last_track
local update_menu
local mode_page = false
local mode_request = 0
local MODE_OWNER = 'av3a_playback'

local mode_names = {auto = '自动兼容（默认）',
    native = '原生输出（高级）', explicit = '由参数指定'}

local function playback_state()
    local state = mp.get_property_native('user-data/av3a-playback')
    if type(state) ~= 'table' or state.version ~= 2
        or type(state.available) ~= 'boolean' or type(state.locked) ~= 'boolean'
        or not mode_names[state.policy] then return nil end
    return state
end

local function channel_label(params)
    if type(params) ~= 'table' or type(params.channels) ~= 'number'
        or params.channels < 1 or params.channels > 256
        or params.channels ~= math.floor(params.channels) then return '待确认' end
    return tostring(params.channels) .. 'CH'
end

local function mode_hint(state)
    if not state then return '状态暂不可用' end
    if state.pending then return '切换中…' end
    if state.reason == 'set-option-failed' then
        return '切换失败 · ' .. (mode_names[state.policy] or '待确认')
    end
    if state.reason == 'mode-unconfirmed' and not state.confirmed then
        local actual = {binaural = '双耳', native = '原生 PCM'}
        return '未确认 · 实际' .. (actual[state.actual_render] or '待确认')
    end
    return mode_names[state.policy] or '待确认'
end

local function integer(value, minimum, maximum)
    return type(value) == 'number' and value == math.floor(value)
        and value >= minimum and value <= maximum
end

local function copy_map(source)
    local result = {}
    for key, value in pairs(source) do result[key] = value end
    return result
end

local function selected_audio()
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'audio' and track.selected
            and track['main-selection'] == 0 then
            local codec = tostring(track.codec or ''):lower()
            return track.id, codec == 'av3a' or codec == 'avs3a'
                or codec == 'libarcdav3a'
        end
    end
end

local function text(value)
    if type(value) ~= 'string' then return '' end
    -- uosc escapes title/hint text for ASS. Never supply ass_safe_* fields.
    -- Reject excessively long names rather than cutting a UTF-8 sequence.
    if #value > 128 then return '' end
    return (value:gsub('[%z\1-\31\127]', ' '))
end

local function read_info()
    local _, av3a = selected_audio()
    if not av3a then return nil end
    local raw = mp.get_property(PROPERTY)
    if type(raw) ~= 'string' or #raw == 0 or #raw > MAX_JSON then return nil end
    local info = utils.parse_json(raw)
    if type(info) ~= 'table' or info.version ~= 1
        or (info.status ~= 'ok' and info.status ~= 'no-metadata'
            and info.status ~= 'invalid' and info.status ~= 'unsupported')
        or (info.render ~= 'native' and info.render ~= 'binaural')
        or not integer(info.selected, -1, 255)
        or type(info.applied) ~= 'boolean'
        or type(info.contents) ~= 'table' or #info.contents > MAX_ITEMS
        or type(info.objects) ~= 'table' or #info.objects > MAX_ITEMS then
        return nil
    end
    local object_ids, content_ids = {}, {}
    for _, object in ipairs(info.objects) do
        if type(object) ~= 'table' or not integer(object.id, 0, 255)
            or object_ids[object.id] then return nil end
        object_ids[object.id] = object
    end
    for _, content in ipairs(info.contents) do
        if type(content) ~= 'table' or not integer(content.id, 0, 255)
            or content_ids[content.id] or type(content.objects) ~= 'table'
            or #content.objects == 0 or #content.objects > MAX_ITEMS then
            return nil
        end
        content_ids[content.id] = content
        local seen = {}
        for _, id in ipairs(content.objects) do
            if not integer(id, 0, 255) or not object_ids[id] or seen[id] then
                return nil
            end
            seen[id] = true
        end
    end
    if info.applied and (info.status ~= 'ok' or info.render ~= 'binaural'
        or not content_ids[info.selected]) then return nil end
    info.object_ids, info.content_ids = object_ids, content_ids
    return info
end

local function publish(info)
    mp.set_property_native('user-data/av3a-preselections', {
        available = info ~= nil and info.status == 'ok' and #info.contents > 0,
        status = info and info.status or 'unavailable',
        native = info ~= nil and info.render == 'native',
        count = info and #info.contents or 0,
        selected = info and info.applied and info.selected or nil,
        requested = request and request.id or nil,
    })
end

local function stop_request()
    if timer then timer:kill(); timer = nil end
    request = nil
    generation = generation + 1
end

local function menu_is_open()
    return mp.get_property_native('user-data/uosc/menu/type') == MENU_TYPE
end

local function refresh_menu(info)
    publish(info)
    if menu_is_open() then update_menu(info, true) end
end

local function content_hint(info, content)
    local names = {}
    for _, id in ipairs(content.objects) do
        local name = text(info.object_ids[id].name)
        if name ~= '' then names[#names + 1] = name end
    end
    return #names > 0 and table.concat(names, ' + ')
        or ('对象 ID：' .. table.concat(content.objects, ', '))
end

update_menu = function(info, update)
    local items, selected_index = {}, 1
    local state = playback_state()
    local enabled = state and state.available and not state.locked and not state.pending
    if mode_page then
        items[#items + 1] = {title = '返回内容预选', value = 'back'}
        local descriptions = {auto = '对象/HOA 双耳输出；纯声道保持原布局',
            native = '保留运输 PCM；不是 7.1.4 对象扬声器渲染'}
        for _, mode in ipairs({'auto', 'native'}) do
            items[#items + 1] = {title = mode_names[mode], hint = descriptions[mode],
                value = 'mode:' .. mode, active = state and state.policy == mode
                    and state.confirmed and not state.pending,
                selectable = enabled or false, muted = not enabled}
        end
        if state and state.locked then
            items[#items + 1] = {title = '当前由显式参数或导出设置指定',
                hint = '保留原参数；移除 av3a_render 参数后可在此切换',
                selectable = false, muted = true, interaction_role = 'status'}
        end
    else
    items[#items + 1] = {title = '输出模式', value = 'modes',
        hint = mode_hint(state)}
    items[#items + 1] = {title = '解码 ' .. channel_label(state and state.decoded)
        .. ' → 输出 ' .. channel_label(state and state.output),
        selectable = false, muted = true, interaction_role = 'status'}
    if not info or info.status ~= 'ok' or #info.contents == 0 then
        local labels = {
            ['no-metadata'] = '正在等待音轨内容元数据',
            invalid = '音轨内容元数据无效',
            unsupported = '该音轨的内容选择暂不支持',
        }
        items[#items + 1] = {title = labels[info and info.status]
            or '当前音轨没有可用的 AVS3A 内容预选',
            selectable = false, muted = true, interaction_role = 'status'}
    else
        local native = info.render == 'native'
        if native then
            items[#items + 1] = {title = '当前为手动原生模式，预选未应用',
                hint = '切回双耳模式后可选择', selectable = false,
                muted = true, interaction_role = 'status'}
        end
        items[#items + 1] = {title = '默认：全部对象', value = -1,
            hint = info.selected == -1 and '当前默认策略' or '恢复原播放策略',
            selectable = not native, muted = native}
        for index, content in ipairs(info.contents) do
            local active = info.applied and info.selected == content.id
            items[#items + 1] = {title = string.format('预选 %d', index),
                hint = content_hint(info, content), value = content.id,
                active = active, selectable = not native, muted = native}
            if active then selected_index = #items end
        end
    end
    end
    mp.commandv('script-message-to', 'uosc', update and 'update-menu' or 'open-menu',
        utils.format_json({type = MENU_TYPE, title = mode_page and 'AV3A · 输出模式' or 'AV3A',
            min_width = 420, search_style = 'disabled', fixed_columns = true,
            uniform_title_size = true, selected_index = selected_index,
            callback = {mp.get_script_name(), 'menu-event'}, items = items,
            footnote = mode_page and '仅对当前文件生效 · 输出为播放器音频格式，不代表实体扬声器验证'
                or '内容预选与输出模式独立 · 对象名称来自音轨元数据'}))
end

local function open_menu()
    mode_page = false
    local info = read_info()
    publish(info)
    update_menu(info, menu_is_open())
end

local function poll_selection(serial)
    if not request or serial ~= generation then return end
    timer = nil
    local track_id, av3a = selected_audio()
    if not av3a or track_id ~= request.track then
        stop_request()
        refresh_menu(read_info())
        return
    end
    local info = read_info()
    local applied = info and info.status == 'ok' and info.render == 'binaural'
        and info.selected == request.id
        and (request.id == -1 or info.applied)
    if applied then
        local id = request.id
        stop_request()
        refresh_menu(info)
        mp.osd_message(id == -1 and '已恢复 AVS3A 全部对象'
            or 'AVS3A 内容预选已应用', 2)
        return
    end
    local failed = info and (info.render == 'native'
        or info.status == 'invalid' or info.status == 'unsupported')
    if failed or request.remaining <= 0 then
        stop_request()
        refresh_menu(info)
        mp.osd_message('AVS3A 内容预选未确认生效，请检查音轨元数据和渲染模式', 4)
        return
    end
    request.remaining = request.remaining - 1
    refresh_menu(info)
    timer = mp.add_timeout(0.2, function() poll_selection(serial) end)
end

local function choose(id)
    if not integer(id, -1, 255) then return end
    local info = read_info()
    if not info or info.status ~= 'ok' or #info.contents == 0
        or (id ~= -1 and not info.content_ids[id]) then
        mp.osd_message('该 AVS3A 内容预选已不可用', 3)
        return
    end
    local current = mp.get_property_native('options/ad-lavc-o')
    if type(current) ~= 'table' then return end
    if info.render ~= 'binaural' or current.av3a_render ~= 'binaural' then
        mp.osd_message('当前为手动原生模式，内容预选需要双耳渲染；原生设置已保留', 4)
        return
    end
    if info.selected == id and ((id >= 0 and info.applied
        and tostring(current.av3a_content) == tostring(id))
        or (id == -1 and (current.av3a_content == nil
            or tostring(current.av3a_content) == '-1'))) then
        mp.osd_message(id == -1 and '当前已是 AVS3A 全部对象'
            or '当前 AVS3A 内容预选已应用', 2)
        return
    end
    local track_id = selected_audio()
    if not owned or tostring(current.av3a_content) ~= owned.value then
        owned = {previous = current.av3a_content, track = track_id}
    end
    local next_options = copy_map(current)
    next_options.av3a_content = tostring(id)
    local ok, err = mp.set_property_native('file-local-options/ad-lavc-o', next_options)
    if not ok then
        msg.warn('AVS3A 内容预选设置失败：' .. tostring(err))
        mp.osd_message('AVS3A 内容预选设置失败', 3)
        return
    end
    owned.value = tostring(id)
    stop_request()
    request = {id = id, track = track_id, remaining = 39}
    publish(info)
    local serial = generation
    timer = mp.add_timeout(0.2, function() poll_selection(serial) end)
end

local function release_owned()
    if owned then
        local current = mp.get_property_native('options/ad-lavc-o')
        if type(current) == 'table' and tostring(current.av3a_content) == owned.value then
            if current.av3a_content ~= owned.previous then
                local restored = copy_map(current)
                restored.av3a_content = owned.previous
                mp.set_property_native('file-local-options/ad-lavc-o', restored)
            end
        end
        owned = nil
    end
end

local function tracks_changed()
    local track_id = selected_audio()
    if last_track == track_id then return end
    last_track = track_id
    stop_request()
    if owned and owned.track ~= track_id then release_owned() end
    refresh_menu(read_info())
end

local function clear()
    stop_request()
    owned, last_track, mode_page = nil, nil, false
    -- The core restores file-local options. Writing on end-file would alter
    -- the following file's baseline options.
    publish(nil)
    if menu_is_open() then
        mp.commandv('script-message-to', 'uosc', 'close-menu', MENU_TYPE)
    end
end

mp.register_script_message('open', open_menu)
mp.add_key_binding(nil, 'open', open_menu)
mp.register_script_message('select', function(value) choose(tonumber(value)) end)
mp.register_script_message('menu-event', function(raw)
    local event = utils.parse_json(raw)
    if type(event) == 'table' and event.type == 'activate' and not event.action then
        if event.value == 'modes' then
            mode_page = true; update_menu(read_info(), true)
        elseif event.value == 'back' then
            mode_page = false; update_menu(read_info(), true)
        elseif type(event.value) == 'string' and event.value:match('^mode:') then
            local mode = event.value:sub(6)
            local state = playback_state()
            if state and state.available and not state.locked and not state.pending
                and (mode == 'auto' or mode == 'native') then
                stop_request()
                mode_request = mode_request + 1
                mp.commandv('script-message-to', MODE_OWNER, 'set-mode', mode,
                    tostring(mode_request))
            end
        else choose(event.value) end
    end
end)
mp.register_event('start-file', clear)
mp.register_event('end-file', clear)
-- on_unload blocks teardown before core option restoration. Restore only our
-- still-owned key here; end-file may already refer to the following file.
mp.add_hook('on_unload', 50, function()
    stop_request()
    release_owned()
    clear()
end)
mp.register_event('file-loaded', tracks_changed)
mp.observe_property('track-list', 'native', tracks_changed)
mp.observe_property('user-data/av3a-playback', 'native', function()
    if menu_is_open() then update_menu(read_info(), true) end
end)
