-- modified from https://github.com/rkscv/danmaku/blob/main/danmaku.lua
local msg = require('mp.msg')
local utils = require("mp.utils")
local unpack = unpack or table.unpack

local osd_width, osd_height, pause = 0, 0, true
local overlay_low = mp.create_osd_overlay('ass-events')
local overlay_high = mp.create_osd_overlay('ass-events')
local ass_track_path, ass_track_id = nil, nil
local previous_secondary_sid, previous_secondary_visibility, previous_secondary_ass_override = nil, nil, nil
local ass_track_dirty = true
local ass_track_failed = false
local fallback_notified = false
local changing_secondary = false
local active_render_mode = "overlay"
local overlay_render_timer = nil
local ass_events_low, ass_events_high = {}, {}
local ass_prefix_cache_key, ass_prefix_cache_value = nil, nil

local function is_ass_track_mode()
    return active_render_mode == "ass-track"
end

local function is_disabled_sid(value)
    if value == nil or value == false then return true end
    local sid = tostring(value):lower()
    return sid == "" or sid == "no" or sid == "auto" or sid == "0" or sid == "false"
end

local function has_external_secondary_subtitle()
    local sid = mp.get_property_native("secondary-sid")
    if is_disabled_sid(sid) then return false end
    return not ass_track_id or tostring(sid) ~= tostring(ass_track_id)
end

local function get_osd_vertical_geometry()
    local width, height = mp.get_osd_size()
    if not width or width <= 0 or not height or height <= 0 then return nil end

    local dimensions = mp.get_property_native('osd-dimensions', {})
    if type(dimensions) ~= 'table' then return width, height, 0, height end
    local dimensions_height = tonumber(dimensions.h)
    local scale_y = dimensions_height and dimensions_height > 0 and height / dimensions_height or 1
    local top = math.max(0, math.min(height, (tonumber(dimensions.mt) or 0) * scale_y))
    local bottom = math.max(0, math.min(height, height - (tonumber(dimensions.mb) or 0) * scale_y))
    if bottom <= top then return width, height, 0, height end
    return width, height, top, bottom
end

local function get_overlay_font_height(width, height)
    local ratio = width / height
    local render_height = 1080
    local font_size = tonumber(options.fontsize) or 50
    if 1920 / 1080 < ratio then
        render_height = 1920 / ratio
        font_size = font_size - ratio * 2
    end
    return math.max(1, font_size * height / render_height)
end

local function should_use_fullscreen_blackbar_overlay()
    if options.fullscreen_blackbar == false then return false end
    if mp.get_property_native('fullscreen') ~= true then return false end

    local width, _, picture_top = get_osd_vertical_geometry()
    if not width then return false end
    return picture_top >= 1
end

local function desired_render_mode()
    local requested = tostring(options.render_mode or "auto"):lower()
    if requested == "overlay" then return "overlay" end
    if requested ~= "auto" and requested ~= "ass-track" then return "overlay" end
    if ass_track_failed or has_external_secondary_subtitle() then return "overlay" end
    if requested == "auto" and should_use_fullscreen_blackbar_overlay() then return "overlay" end
    return "ass-track"
end

local function resolve_render_mode()
    local requested = tostring(options.render_mode or "auto"):lower()
    active_render_mode = desired_render_mode()
    if requested ~= "overlay" and requested ~= "auto" and requested ~= "ass-track" then
        msg.warn("未知的 render_mode=" .. requested .. "，已使用 overlay")
    end
    return active_render_mode
end

local function clear_array(items)
    for i = #items, 1, -1 do
        items[i] = nil
    end
end

local function get_overlay_fps()
    local fps = math.max(20, math.min(60, tonumber(options.overlay_fps) or 60))
    local display_fps = mp.get_property_number("display-fps")
    if display_fps and display_fps > 0 then
        fps = math.min(fps, display_fps)
    end
    return math.max(1, fps)
end

local function stop_overlay_timer()
    if overlay_render_timer then
        overlay_render_timer:kill()
    end
end

local function start_overlay_timer()
    if pause or not ENABLED or COMMENTS == nil or is_ass_track_mode() then return end
    local interval = 1 / get_overlay_fps()
    if not overlay_render_timer then
        overlay_render_timer = mp.add_periodic_timer(interval, function()
            if ENABLED and COMMENTS ~= nil and not pause and not is_ass_track_mode() then
                render()
            end
        end)
    else
        overlay_render_timer.timeout = interval
        overlay_render_timer:resume()
    end
end

local function write_text_file(path, content)
    local file, err = io.open(path, "wb")
    if not file then
        msg.error("写入 ASS 弹幕文件失败: " .. tostring(err))
        return false
    end
    file:write(content)
    file:close()
    return true
end

local function ass_time(seconds)
    seconds = math.max(0, tonumber(seconds) or 0)
    local cs = math.floor(seconds * 100 + 0.5)
    local h = math.floor(cs / 360000)
    cs = cs - h * 360000
    local m = math.floor(cs / 6000)
    cs = cs - m * 6000
    local s = math.floor(cs / 100)
    cs = cs - s * 100
    return string.format("%d:%02d:%02d.%02d", h, m, s, cs)
end

local function ass_style_color(alpha, color)
    return string.format("&H%s%s&", alpha, color)
end

local function get_ass_track_path()
    local dir = nil
    if mp.command_native then
        dir = mp.command_native({ "expand-path", "~~/cache" })
    end
    dir = dir or DANMAKU_PATH or "."
    return utils.join_path(dir, string.format("uosc-danmaku-%s.ass", PID))
end

local function find_ass_track_id()
    local tracks = mp.get_property_native("track-list") or {}
    for _, track in ipairs(tracks) do
        if track.type == "sub" and (track.title == "uosc_danmaku"
        or track["external-filename"] == ass_track_path) then
            return track.id
        end
    end
    return nil
end

local function clear_saved_secondary_state()
    previous_secondary_sid = nil
    previous_secondary_visibility = nil
    previous_secondary_ass_override = nil
end

local function set_secondary_property(name, value, native)
    if value == nil then return end
    changing_secondary = true
    if native then
        mp.set_property_native(name, value)
    else
        mp.set_property(name, value)
    end
    changing_secondary = false
end

local function unload_ass_track(restore_secondary)
    local track_id = ass_track_id
    ass_track_id = nil
    if track_id then
        pcall(mp.commandv, "sub-remove", track_id)
    end
    if restore_secondary and previous_secondary_sid ~= nil then
        set_secondary_property("secondary-sid", previous_secondary_sid, true)
        set_secondary_property("secondary-sub-visibility", previous_secondary_visibility)
        set_secondary_property("secondary-sub-ass-override", previous_secondary_ass_override)
        clear_saved_secondary_state()
    end
    if ass_track_path and file_exists(ass_track_path) then
        os.remove(ass_track_path)
    end
    ass_track_path = nil
end

local function normalize_event_text(text)
    if not text then return nil end
    text = text:gsub("&#%d+;", "")
    text = text:gsub("\\fs(%d+)", function(size)
        local n = tonumber(size) or 0
        return string.format("\\fs%d", math.floor(n * 1.5))
    end)
    return "{\\an8}" .. text
end

local function event_in_display_area(event, displayarea)
    local y
    if event.move then
        y = event.move[2]
    elseif event.pos then
        y = event.pos[2]
    end
    return not y or tonumber(y) <= 1080 * displayarea
end

local function build_ass_track()
    if not COMMENTS or #COMMENTS == 0 then
        return nil
    end

    local opacity = tonumber(options.opacity)
    local alpha = string.format("%02X", (1 - (opacity or 0)) * 255)
    local bold = options.bold and "-1" or "0"
    local fontsize = tonumber(options.fontsize) or 50
    local outline = tonumber(options.outline) or 0
    local shadow = tonumber(options.shadow) or 0
    local displayarea = tonumber(options.displayarea) or 1

    local lines = {
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        string.format("Style: Default,%s,%d,%s,%s,&H00000000,&H00000000,%s,0,0,0,100,100,0,0,1,%.2f,%.2f,8,0,0,0,1",
            options.fontname, fontsize, ass_style_color(alpha, "FFFFFF"), ass_style_color(alpha, "FFFFFF"),
            bold, outline, shadow),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    }

    for _, event in ipairs(COMMENTS) do
        if event_in_display_area(event, displayarea) then
            local text = normalize_event_text(event.text)
            if text then
                table.insert(lines, string.format("Dialogue: %d,%s,%s,Default,,0,0,0,,%s",
                    tonumber(event.layer) or 0,
                    ass_time(event.start_time),
                    ass_time(event.end_time),
                    text))
            end
        end
    end

    return table.concat(lines, "\n") .. "\n"
end

local function render_ass_track()
    unload_ass_track(false)
    if not COMMENTS or #COMMENTS == 0 then
        ass_track_dirty = false
        return true
    end

    local content = build_ass_track()
    if not content then return true end

    ass_track_path = get_ass_track_path()
    if not write_text_file(ass_track_path, content) then
        ass_track_path = nil
        return false, "write-failed"
    end

    if previous_secondary_sid == nil then
        previous_secondary_sid = mp.get_property_native("secondary-sid") or "no"
        previous_secondary_visibility = mp.get_property("secondary-sub-visibility", "yes")
        previous_secondary_ass_override = mp.get_property("secondary-sub-ass-override", "strip")
    end

    local command_ok, command_err = pcall(mp.commandv, "sub-add", ass_track_path, "auto", "uosc_danmaku")
    if not command_ok then
        unload_ass_track(false)
        return false, command_err or "sub-add-failed"
    end
    ass_track_id = find_ass_track_id()
    if ass_track_id then
        set_secondary_property("secondary-sub-visibility", "yes")
        set_secondary_property("secondary-sub-ass-override", "no")
        set_secondary_property("secondary-sid", ass_track_id, true)
        ass_track_dirty = false
        msg.verbose("ASS 弹幕轨已加载: " .. ass_track_path)
        return true
    else
        unload_ass_track(false)
        return false, "track-not-found"
    end
end

local function switch_to_overlay(reason, preserve_current_secondary)
    ass_track_failed = true
    active_render_mode = "overlay"
    stop_overlay_timer()

    if preserve_current_secondary then
        local visibility = previous_secondary_visibility
        local ass_override = previous_secondary_ass_override
        unload_ass_track(false)
        set_secondary_property("secondary-sub-visibility", visibility)
        set_secondary_property("secondary-sub-ass-override", ass_override)
        clear_saved_secondary_state()
    else
        unload_ass_track(true)
    end

    if reason then
        msg.warn("ASS 弹幕轨不可用，已自动切换到兼容渲染: " .. tostring(reason))
        if not fallback_notified and show_message then
            show_message("弹幕已自动切换兼容模式", 3)
            fallback_notified = true
        end
    end
end

local function get_overlay_event_text(event)
    if event._overlay_text then return event._overlay_text end
    local text = (event.text or ""):gsub("\\move%(.-%)", "")
    text = text:gsub("&#%d+;", "")
    text = text:gsub("\\fs(%d+)", function(size)
        local n = tonumber(size) or 0
        return string.format("\\fs%d", math.floor(n * 1.5))
    end)
    event._overlay_text = text
    return text
end

local function get_ass_prefix(fontname, fontsize, alpha)
    local key = table.concat({
        tostring(fontname), tostring(fontsize), tostring(alpha),
        tostring(options.outline), tostring(options.shadow), tostring(options.bold)
    }, "\0")
    if key ~= ass_prefix_cache_key then
        ass_prefix_cache_key = key
        ass_prefix_cache_value = string.format(
            "{\\rDefault\\fn%s\\fs%d\\c&HFFFFFF&\\alpha&H%s\\bord%s\\shad%s\\b%s\\q2}",
            fontname, fontsize, alpha, options.outline, options.shadow,
            options.bold and "1" or "0")
    end
    return ass_prefix_cache_value
end

local function realtime_position_text(event, pos, displayarea)
    local event_text = get_overlay_event_text(event)
    if not event.move then
        local _, current_y = unpack(event.pos or {})
        if not current_y or tonumber(current_y) > displayarea then return end
        if event.style ~= "SP" and event.style ~= "MSG" then
            return "{\\an8}" .. event_text
        else
            return "{\\an7}" .. event_text
        end
    end

    local x1, y1, x2, y2 = unpack(event.move)
    -- 计算移动的时间范围
    local duration = math.max(0.001, event.end_time - event.start_time)  --mean: options.scrolltime
    local progress = (pos - event.start_time) / duration  -- 移动进度 [0, 1]

    -- 计算当前坐标
    local current_x = tonumber(x1 + (x2 - x1) * progress)
    local current_y = tonumber(y1 + (y2 - y1) * progress)

    -- 移除 \move 标签并应用当前坐标
    if current_y > displayarea then return end
    if event.style ~= "SP" and event.style ~= "MSG" then
        return string.format("{\\pos(%.1f,%.1f)\\an8}%s", current_x, current_y, event_text)
    else
        return string.format("{\\pos(%.1f,%.1f)\\an7}%s", current_x, current_y, event_text)
    end
end

function render(pos_arg)
    if COMMENTS == nil then return end
    if is_ass_track_mode() then
        if ass_track_dirty or not ass_track_id then
            local ok, reason = render_ass_track()
            if ok then return end
            switch_to_overlay(reason, false)
        else
            return
        end
    end

    local pos, err
    if pos_arg == nil then
        pos, err = mp.get_property_number('time-pos')
        if err ~= nil then
            return msg.error(err)
        end
    else
        pos = pos_arg
    end

    if not pos then
        overlay_low:remove()
        overlay_high:remove()
        return
    end

    local fontname = options.fontname
    local fontsize = options.fontsize
    local opacity = tonumber(options.opacity)
    local alpha = string.format("%02X", (1 - (opacity or 0)) * 255)

    local width, height = 1920, 1080
    local ratio = osd_width / osd_height
    if width / height < ratio then
        height = width / ratio
        fontsize = options.fontsize - ratio * 2
    end

    clear_array(ass_events_low)
    clear_array(ass_events_high)
    local max_display = math.max(options.scrolltime, options.fixtime)
    local window_start = pos - max_display

    -- 跳过已结束的弹幕
    local lo = binary_search(COMMENTS, window_start, function(item) return item.start_time end)

    local ass_prefix = get_ass_prefix(fontname, fontsize, alpha)

    for i = lo, #COMMENTS do
        local event = COMMENTS[i]
        if not event then break end

        if event.start_time > pos then break end  -- 后续弹幕提前退出
        if event.end_time >= pos then
            local text = realtime_position_text(event, pos, height * options.displayarea)

            -- 构建 ASS 字符串
            local ass_text = text and (ass_prefix .. text)
            if ass_text then
                if event.layer == nil or tonumber(event.layer) == 0 then
                    table.insert(ass_events_low, ass_text)
                else
                    table.insert(ass_events_high, ass_text)
                end
            end
        end
    end

    -- 写入低层（滚动）和高层（顶/底）overlay，并设置 z 值以控制堆叠
    overlay_low.res_x = width
    overlay_low.res_y = height
    overlay_low.z = 0
    overlay_low.data = table.concat(ass_events_low, '\n')
    overlay_low:update()

    overlay_high.res_x = width
    overlay_high.res_y = height
    overlay_high.z = 1
    overlay_high.data = table.concat(ass_events_high, '\n')
    overlay_high:update()
end

function render_danmaku(from_menu, no_osd)
    if ENABLED and (from_menu or get_danmaku_visibility()) then
        ass_track_dirty = true
        if not no_osd then
            show_loaded(true)
        end
        toggle_danmaku_switch("on")
        show_danmaku_func()
    else
        show_message("")
        hide_danmaku_func()
    end
end

local function filter_state(label, name)
    local filters = mp.get_property_native("vf") or {}
    for _, filter in pairs(filters) do
        if filter.label == label or filter.name == name
        or (name and filter.params and filter.params[name] ~= nil) then
            return true
        end
    end
    return false
end

function show_danmaku_func()
    mp.set_property_bool(HAS_DANMAKU, type(COMMENTS) == "table" and #COMMENTS > 0)
    set_danmaku_visibility(true)
    resolve_render_mode()
    render()
    if is_ass_track_mode() then
        stop_overlay_timer()
        overlay_low:remove()
        overlay_high:remove()
    elseif not pause then
        start_overlay_timer()
    end
    if options.vf_fps then
        local display_fps = mp.get_property_number('display-fps')
        local video_fps = mp.get_property_number('estimated-vf-fps')
        if (display_fps and display_fps < 58) or (video_fps and video_fps > 58) then
            return
        end
        if not filter_state("danmaku", "fps") then
            mp.commandv("vf", "append", string.format("@danmaku:fps=fps=%s", options.fps))
        end
    end
end

function hide_danmaku_func()
    stop_overlay_timer()
    unload_ass_track(true)
    mp.set_property_bool(HAS_DANMAKU, false)
    set_danmaku_visibility(false)
    overlay_low:remove()
    overlay_high:remove()
    if filter_state("danmaku") then
        mp.commandv("vf", "remove", "@danmaku")
    end
end

function refresh_danmaku_renderer()
    ass_track_dirty = true
    ass_track_failed = false
    fallback_notified = false
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        show_danmaku_func()
    end
end

local layout_mode_timer = mp.add_timeout(0.08, function()
    if not ENABLED or COMMENTS == nil or not get_danmaku_visibility() then return end
    local next_mode = desired_render_mode()
    if next_mode == active_render_mode then return end

    stop_overlay_timer()
    if next_mode == "overlay" then
        unload_ass_track(true)
        active_render_mode = "overlay"
        render()
        if not pause then start_overlay_timer() end
        msg.verbose("检测到全屏顶部黑边，已切换到 overlay 连续布局")
    else
        overlay_low:remove()
        overlay_high:remove()
        active_render_mode = "ass-track"
        ass_track_dirty = true
        render()
        msg.verbose("已恢复原生 ASS 弹幕布局")
    end
end, true)

local function schedule_layout_mode_refresh()
    layout_mode_timer:kill()
    layout_mode_timer:resume()
end

local message_overlay = mp.create_osd_overlay('ass-events')
message_overlay.z = 2100
local active_message = nil
local message_timer = mp.add_timeout(3, function()
    active_message = nil
    message_overlay:remove()
end, true)

local function clamp_number(value, minimum, maximum)
    return math.max(minimum, math.min(maximum, value))
end

local function get_video_bounds(width, height)
    local dimensions = mp.get_property_native('osd-dimensions', {})
    if type(dimensions) ~= 'table' then return 0, 0, width, height end

    local dimensions_width = tonumber(dimensions.w)
    local dimensions_height = tonumber(dimensions.h)
    local scale_x = dimensions_width and dimensions_width > 0 and width / dimensions_width or 1
    local scale_y = dimensions_height and dimensions_height > 0 and height / dimensions_height or 1
    local left = clamp_number((tonumber(dimensions.ml) or 0) * scale_x, 0, width)
    local top = clamp_number((tonumber(dimensions.mt) or 0) * scale_y, 0, height)
    local right = clamp_number(width - (tonumber(dimensions.mr) or 0) * scale_x, 0, width)
    local bottom = clamp_number(height - (tonumber(dimensions.mb) or 0) * scale_y, 0, height)
    if right <= left or bottom <= top then return 0, 0, width, height end
    return left, top, right, bottom
end

local function count_message_lines(text)
    local _, ass_breaks = tostring(text):gsub('\\N', '')
    local _, plain_breaks = tostring(text):gsub('\n', '')
    return math.max(1, 1 + ass_breaks + plain_breaks)
end

local function layout_message(text)
    local width, height = mp.get_osd_size()
    if not width or width <= 0 or not height or height <= 0 then
        width, height = math.max(osd_width, 1280), math.max(osd_height, 720)
    end
    local dpi_scale = mp.get_property_number('display-hidpi-scale', 1)
    local canvas_scale = math.min(width / 1280, height / 720)
    local visual_scale = math.max(dpi_scale, canvas_scale)
    local font_size = math.max(18, math.floor(17 * visual_scale + 0.5))
    local x = math.floor(options.message_x * visual_scale + 0.5)
    local y = math.floor(options.message_y * visual_scale + 0.5)
    local displayarea = tonumber(options.displayarea) or 0
    if displayarea > 0 then
        local fullscreen = mp.get_property_native('fullscreen') == true
        local top_aligned = tonumber(options.message_anlignment) and tonumber(options.message_anlignment) >= 7
        if fullscreen and top_aligned then
            local picture_left, picture_top, _, picture_bottom = get_video_bounds(width, height)
            local picture_height = picture_bottom - picture_top
            local picture_gap = math.max(6, math.floor(8 * visual_scale + 0.5))
            local lane_gap = math.max(6, math.floor(8 * visual_scale + 0.5))

            -- Anchor status messages to the real picture. If overlay danmaku
            -- continues past the top black bar, stay below its final lane.
            x = math.max(x, math.floor(picture_left + picture_gap + 0.5))
            y = math.floor(picture_top + picture_gap + 0.5)
            if desired_render_mode() == "overlay" then
                local lane_bottom = height * displayarea + get_overlay_font_height(width, height)
                y = math.max(y, math.floor(lane_bottom + lane_gap + 0.5))
            else
                local lane_font_height = (tonumber(options.fontsize) or 50) * picture_height / 1080
                local lane_bottom = picture_top + picture_height * displayarea + lane_font_height
                y = math.max(y, math.floor(lane_bottom + lane_gap + 0.5))
            end
        else
            -- Preserve the established windowed and overlay-mode placement.
            y = math.max(y, math.floor(height * displayarea + 32 * visual_scale + 0.5))
        end
    end
    local border = math.max(2, math.floor(2.4 * visual_scale + 0.5))
    local message_height = count_message_lines(text) * font_size + border * 2
    local edge_inset = math.max(4, math.floor(6 * visual_scale + 0.5))
    y = clamp_number(y, edge_inset, math.max(edge_inset, height - message_height - edge_inset))

    return width, height, font_size, x, y, border
end

local function render_active_message()
    if not active_message then return end
    local width, height, font_size, x, y, border = layout_message(active_message)
    local message = string.format(
        "{\\an%d\\pos(%d,%d)\\fs%d\\fn%s\\b1\\c&HF2E655&"
            .. "\\3c&H160B04&\\3a&H00&\\bord%d\\blur0.35\\shad0\\q2}%s",
        options.message_anlignment, x, y, font_size, options.fontname, border, active_message
    )
    message_overlay.res_x = width
    message_overlay.res_y = height
    message_overlay.data = message
    message_overlay:update()
end

function show_message(text, time)
    message_timer.timeout = time or 3
    message_timer:kill()
    message_overlay:remove()
    active_message = nil
    if not text or text == '' or time == 0 then return end

    active_message = text
    render_active_message()
    message_timer:resume()
end

mp.observe_property('osd-width', 'number', function(_, value)
    osd_width = value or osd_width
    render_active_message()
    schedule_layout_mode_refresh()
end)
mp.observe_property('osd-height', 'number', function(_, value)
    osd_height = value or osd_height
    render_active_message()
    schedule_layout_mode_refresh()
end)
mp.observe_property('osd-dimensions', 'native', function()
    render_active_message()
    schedule_layout_mode_refresh()
end)
mp.observe_property('fullscreen', 'bool', function()
    render_active_message()
    schedule_layout_mode_refresh()
end)
mp.observe_property('display-hidpi-scale', 'number', function() render_active_message() end)
mp.observe_property('pause', 'bool', function(_, value)
    if value ~= nil then
        pause = value
    end
    if ENABLED then
        if pause then
            stop_overlay_timer()
        elseif COMMENTS ~= nil and not is_ass_track_mode() then
            render()
            start_overlay_timer()
        end
    end
end)

mp.observe_property('secondary-sid', 'native', function(_, value)
    if changing_secondary or not ass_track_id or not is_ass_track_mode() then return end
    if tostring(value) == tostring(ass_track_id) then return end

    switch_to_overlay(nil, true)
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        msg.verbose("检测到用户选择第二字幕，弹幕已切换到 overlay")
        render()
        start_overlay_timer()
        show_message("检测到双字幕，弹幕已切换兼容模式", 3)
    end
end)

mp.register_event('playback-restart', function(event)
    if event.error then
        return msg.error(event.error)
    end
    if ENABLED and COMMENTS ~= nil then
        if not is_ass_track_mode() then
            render()
        end
    end
end)

mp.add_hook("on_unload", 50, function()
    COMMENTS, DELAY = nil, 0
    stop_overlay_timer()
    unload_ass_track(true)
    ass_track_dirty = true
    ass_track_failed = false
    fallback_notified = false
    active_render_mode = "overlay"
    ass_prefix_cache_key, ass_prefix_cache_value = nil, nil
    clear_array(ass_events_low)
    clear_array(ass_events_high)
    overlay_low:remove()
    overlay_high:remove()
    mp.set_property_bool(HAS_DANMAKU, false)
    mp.set_property_native(DELAY_PROPERTY, 0)
    if filter_state("danmaku") then
        mp.commandv("vf", "remove", "@danmaku")
    end

    local files_to_remove = {
        file1 = utils.join_path(DANMAKU_PATH, "temp-" .. PID .. ".mp4"),
        file2 = get_ass_track_path(),
    }

    if options.save_danmaku then
        save_danmaku(true)
    end

    for _, file in pairs(files_to_remove) do
        if file_exists(file) then
            os.remove(file)
        end
    end

    DANMAKU = {sources = {}, count = 1}
    mp.set_property_native(DANMAKU_COUNT, 0)
    refresh_danmaku_button()
end)
