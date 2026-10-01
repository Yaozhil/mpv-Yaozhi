-- modified from https://github.com/rkscv/danmaku/blob/main/danmaku.lua
local msg = require('mp.msg')
local utils = require("mp.utils")
local unpack = unpack or table.unpack
local Color = require("modules/color")
local color_revision = 0

local osd_width, osd_height, pause = 0, 0, true
local overlay_low = mp.create_osd_overlay('ass-events')
local overlay_high = mp.create_osd_overlay('ass-events')
local ass_track_path, ass_track_id = nil, nil
local ass_track_slot = 0
local previous_secondary_sid, previous_secondary_visibility, previous_secondary_ass_override = nil, nil, nil
local FULL_VIEWPORT_OPTION = "secondary-sub-ass-full-viewport"
local native_full_viewport_available = mp.get_property_native(FULL_VIEWPORT_OPTION) ~= nil
local previous_secondary_full_viewport = nil
local REFRESH_OPTION = 'secondary-sub-ass-refresh-rate'
local native_refresh_available = mp.get_property_native(REFRESH_OPTION) ~= nil
local native_refresh_ceiling = 240
if native_refresh_available then
    local info = mp.get_property_native('option-info/' .. REFRESH_OPTION)
    local ceiling = type(info) == 'table' and tonumber(info.max)
    if ceiling and ceiling > 0 and ceiling < math.huge then
        native_refresh_ceiling = ceiling
    end
end
local previous_secondary_refresh, sync_native_refresh
local native_replace_available = false
for _, command in ipairs(mp.get_property_native('command-list') or {}) do
    if command.name == 'secondary-ass-replace' then native_replace_available = true end
end
local native_full_viewport_active = false
local ass_track_dirty = true
local ass_track_failed = false
local fallback_notified = false
local changing_secondary = false
local active_render_mode = "overlay"
local overlay_render_timer = nil
local overlay_render_interval, overlay_render_deadline = nil, nil
local overlay_sleeping = false
local overlay_low_cache_data, overlay_low_cache_width, overlay_low_cache_height
local overlay_health_timer = nil
local overlay_health_last_drops, overlay_health_bad_samples = 0, 0
local overlay_health_good_seconds, overlay_health_ready_at = 0, 0
local overlay_health_drop_windows = 0
local overlay_adaptive_level, overlay_health_reason = 0, "native"
local overlay_health_publish_key = nil
local overlay_health_report_at, overlay_health_report_drops = 0, 0
local start_overlay_health_timer, stop_overlay_health_timer
local overlay_sync_profile_active, overlay_sync_external_override = false, false
local overlay_sync_profile_failed = false
local OVERLAY_SYNC_PROFILE = "danmaku-overlay-sync"
local ass_events_low, ass_events_high = {}, {}
local overlay_high_active, overlay_high_previous = {}, {}
local overlay_high_cache_valid = false
local overlay_high_cache_prefix, overlay_high_cache_width, overlay_high_cache_height = nil, nil, nil
local ass_prefix_cache_key, ass_prefix_cache_value = nil, nil
local overlay_clock_media, overlay_clock_wall, overlay_clock_speed = nil, nil, 1
local overlay_clock_seeking, overlay_clock_cache_paused = false, false
local overlay_clock_last, overlay_clock_seek_pending = nil, false
local hybrid_ass_parked = false
local overlay_timing_samples, overlay_timing_late_sum = 0, 0
local overlay_timing_late_max, overlay_timing_skipped = 0, 0
local overlay_timing_report_at = 0
local OVERLAY_TIMER_MIN_DELAY = 0.00025
local OVERLAY_WARM_PAYLOAD = "{\\alpha&HFF&\\bord0\\shad0\\pos(-200,-200)}."

-- Future comments are updated when they enter the visible window; a colour
-- change never walks a whole film's backlog on the overlay rendering thread.
local function update_event_color(event)
    if event._color_revision == color_revision then return end
    if Color.apply(event, options.smart_color, options.smart_color_percent,
        options.force_white) then
        overlay_high_cache_valid = false
    end
    event._color_revision = color_revision
end

local function is_ass_track_mode()
    return active_render_mode == "ass-track"
end

local function get_video_hdr_state()
    local gamma = mp.get_property("video-params/gamma")
    if gamma == nil or gamma == "" then return nil end
    gamma = tostring(gamma):lower()
    return gamma == "pq" or gamma == "hlg"
end

local published_render_mode_key = nil
local function publish_render_mode(mode, reason)
    mode = mode or active_render_mode or "overlay"
    reason = reason or "unknown"
    local hdr = get_video_hdr_state() == true
    local viewport = mode == "ass-track" and native_full_viewport_active and "full-output" or "video"
    local key = table.concat({mode, reason, hdr and "hdr" or "sdr", viewport}, ":")
    if key == published_render_mode_key then return end
    published_render_mode_key = key
    mp.set_property_native('user-data/uosc_danmaku/renderer', {
        mode = mode,
        reason = reason,
        hdr = hdr,
        viewport = viewport,
        native_full_viewport = mode == "ass-track" and native_full_viewport_active,
        fallback = mode == "overlay",
    })
    msg.info(string.format('danmaku renderer: %s (%s)', mode, reason))
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

-- Old cores retain the V19.5.8 hybrid fallback. Patched cores map only our
-- secondary ASS track into the output viewport; libass still owns its clock.

local function should_use_fullscreen_blackbar_overlay()
    if options.fullscreen_blackbar == false then return false end
    if mp.get_property_native('fullscreen') ~= true then return false end

    local width, _, picture_top = get_osd_vertical_geometry()
    if not width then return false end
    return picture_top >= 1
end

local function desired_render_mode()
    local requested = tostring(options.render_mode or "auto"):lower()

    if requested == "overlay" then return "overlay", "explicit-overlay" end

    if requested ~= "auto" and requested ~= "ass-track" then
        return "overlay", "invalid-render-mode"
    end
    if ass_track_failed then return "overlay", "ass-track-failed" end
    if has_external_secondary_subtitle() then return "overlay", "secondary-subtitle" end
    if should_use_fullscreen_blackbar_overlay() and native_full_viewport_available then
        return "ass-track", "native-ass-full-viewport"
    end
    if requested == "auto" and should_use_fullscreen_blackbar_overlay() then
        return "overlay", "fullscreen-blackbar"
    end

    -- V19.5: HDR/Dolby Vision is no longer a reason to force Lua/OSD overlay.
    -- A real ASS subtitle track lets mpv/libass own the animation timeline,
    -- avoiding the regular micro-jitter caused by a Windows/Lua software timer
    -- racing the display VBlank. HDR safety is preserved below: the legacy
    -- @danmaku fps video filter is never inserted while PQ/HLG (or unknown
    -- transfer metadata during startup) is active.
    local hdr_state = get_video_hdr_state()
    if hdr_state == true then return "ass-track", "native-ass-hdr" end
    if hdr_state == false then return "ass-track", "native-ass-sdr" end
    return "ass-track", "native-ass-pending"
end

-- libass scales glyphs from PlayResY, while positioned X coordinates follow
-- PlayResX. A fixed 1920-wide script on a portrait picture therefore compresses
-- lane clearance without shrinking the letters. Layout and rendering must use
-- the same viewport, including the optional full-output black-bar viewport.
local font_measure_overlay, font_measure_key, font_measure_height
local function measure_canvas_line_height(res_y, font_size, picture_height)
    local width, height = mp.get_osd_size()
    if not width or width <= 0 or not height or height <= 0 then return nil end
    local key = table.concat({options.fontname, string.format('%.3f', font_size),
        tostring(options.bold), tostring(options.outline), tostring(options.shadow),
        width, height, math.floor(picture_height + 0.5)}, ':')
    if key == font_measure_key then return font_measure_height end
    if not font_measure_overlay then
        font_measure_overlay = mp.create_osd_overlay('ass-events')
        font_measure_overlay.hidden, font_measure_overlay.compute_bounds = true, true
    end
    -- Match the native viewport's glyph scale in the full-output overlay.
    -- compute_bounds returns PlayRes coordinates, including bitmap padding.
    -- Subtract one identical line from two lines to measure font advance;
    -- the fixed raster padding must not become extra spacing in small windows.
    local measure_y = res_y * height / math.max(1, picture_height)
    font_measure_overlay.res_x, font_measure_overlay.res_y = measure_y * width / height, measure_y
    local sample = string.format(
        '{\\rDefault\\fn%s\\fs%d\\b%d\\bord%s\\shad%s\\q2\\an7\\pos(50,50)}弹幕 AgMWjpQ',
        options.fontname, font_size, options.bold and 1 or 0, options.outline, options.shadow)
    font_measure_overlay.data = sample
    local ok, bounds = pcall(font_measure_overlay.update, font_measure_overlay)
    font_measure_key, font_measure_height = key, nil
    if ok and type(bounds) == 'table' and bounds.y1 and bounds.y0 then
        font_measure_overlay.data = sample .. '\\N弹幕 AgMWjpQ'
        local two_ok, two_bounds = pcall(font_measure_overlay.update, font_measure_overlay)
        if two_ok and type(two_bounds) == 'table' and two_bounds.y1 and two_bounds.y0 then
            local advance = (two_bounds.y1 - two_bounds.y0) - (bounds.y1 - bounds.y0)
            if advance > 0 then font_measure_height = advance end
        end
    end
    return font_measure_height
end

function get_danmaku_canvas(mode)
    mode = mode or desired_render_mode()
    local width, height = mp.get_osd_size()
    width, height = tonumber(width) or 0, tonumber(height) or 0
    if width <= 0 or height <= 0 then width, height = 1920, 1080 end
    if mode == "ass-track" and not (native_full_viewport_available
        and should_use_fullscreen_blackbar_overlay()) then
        local d = mp.get_property_native('osd-dimensions', {})
        if type(d) == 'table' then
            local dw, dh = tonumber(d.w) or width, tonumber(d.h) or height
            local picture_width = dw - (tonumber(d.ml) or 0) - (tonumber(d.mr) or 0)
            local picture_height = dh - (tonumber(d.mt) or 0) - (tonumber(d.mb) or 0)
            if dw > 0 and dh > 0 and picture_width > 0 and picture_height > 0 then
                width, height = picture_width * width / dw, picture_height * height / dh
            end
        end
    end
    local ratio = width / height
    local res_x, res_y = 1920, 1080
    local font_size = math.max(1, tonumber(options.fontsize) or 50)
    if ratio < 1920 / 1080 then
        res_x = math.max(1, math.floor(1080 * ratio + 0.5))
    elseif mode == 'overlay' then
        -- Preserve the established ultrawide overlay scale.
        res_y = 1920 / ratio
        font_size = math.max(1, font_size - ratio * 2)
    end
    local line_height = math.ceil(font_size * 1.2
        + 2 * math.max(0, tonumber(options.outline) or 0)
        + math.max(0, tonumber(options.shadow) or 0) + 1)
    local measured = measure_canvas_line_height(res_y, font_size, height)
    if measured then line_height = math.max(line_height, math.ceil(measured + 2)) end
    local width_padding = math.max(0, line_height - math.ceil(font_size * 1.2 + 2))
    return {width=res_x, height=res_y, font_size=font_size, line_height=line_height,
        width_padding=width_padding,
        key=string.format('%d:%.2f:%.2f:%d', res_x, res_y, font_size, line_height)}
end

local function resolve_render_mode()
    local requested = tostring(options.render_mode or "auto"):lower()
    local mode, reason = desired_render_mode()
    active_render_mode = mode
    publish_render_mode(mode, reason)
    if requested ~= "overlay" and requested ~= "auto" and requested ~= "ass-track" then
        msg.warn("未知的 render_mode=" .. requested .. "，已使用 overlay")
    end
    return active_render_mode
end

local published_layout_key
local function publish_danmaku_layout()
    local width, height, top, bottom = get_osd_vertical_geometry()
    if not width then return end
    local visible = HAS_DANMAKU and mp.get_property_native(HAS_DANMAKU) == true
    local occupied = 0
    if visible then
        local area = math.max(0, math.min(1, tonumber(options.displayarea) or 0))
        if is_ass_track_mode() then
            -- The black-bar track starts at the output's top, not the
            -- picture's top. Publish the same viewport used to draw it.
            local canvas_top = native_full_viewport_active and 0 or top
            local canvas_height = native_full_viewport_active and height or (bottom - top)
            occupied = canvas_top + canvas_height * area
                + (tonumber(options.fontsize) or 50) * canvas_height / 1080
        else
            occupied = height * area + get_overlay_font_height(width, height)
        end
    end
    local fraction = math.max(0, math.min(1, occupied / height))
    local key = tostring(visible)..':'..string.format('%.5f', fraction)
    if key == published_layout_key then return end
    published_layout_key = key
    mp.set_property_native('user-data/uosc_danmaku/layout', {visible=visible, top=fraction})
end

local function clear_array(items)
    for i = #items, 1, -1 do
        items[i] = nil
    end
end

local function invalidate_overlay_high_cache()
    overlay_high_cache_valid = false
    overlay_high_cache_prefix, overlay_high_cache_width, overlay_high_cache_height = nil, nil, nil
    clear_array(overlay_high_active)
    clear_array(overlay_high_previous)
end

local function remove_overlay_high()
    overlay_high:remove()
    invalidate_overlay_high_cache()
end

local function get_danmaku_display_fps()
    local value = tonumber(mp.get_property_number('display-fps'))
    if value and value > 0 and value < math.huge then return value end
end

local function get_automatic_overlay_divisor(display_fps, ceiling)
    -- Automatic rates follow an exact monitor divisor with a 120 Hz budget.
    -- Avoid making compatibility Overlay more expensive than Native ASS.
    -- A half-Hz tolerance covers normal 120 Hz mode-reporting drift.
    if not display_fps or display_fps <= 0 then return 1 end
    return math.max(1, math.ceil(display_fps / (ceiling or 120.5)))
end

local function get_base_overlay_fps()
    local display_fps = get_danmaku_display_fps()
    local native = is_ass_track_mode() and native_refresh_available
    local configured_fps = tonumber(options.overlay_fps)
    local automatic = not configured_fps or configured_fps <= 0
    local fps

    if automatic then
        if display_fps then
            -- Core range matters for native refresh properties. Both paths
            -- retain the automatic budget; an explicit user ceiling below can
            -- opt into faster redraws without changing the video/audio clock.
            local ceiling = native and math.min(120.5, native_refresh_ceiling) or 120.5
            fps = display_fps / get_automatic_overlay_divisor(display_fps, ceiling)
        else
            fps = 60
        end
    else
        fps = math.max(20, math.min(native and native_refresh_ceiling or 240, configured_fps))
        if display_fps and display_fps > 0 then
            fps = math.min(fps, display_fps)
            if options.overlay_display_sync then
                -- Manual values are ceilings, not arbitrary asynchronous
                -- clocks. Snap down to an exact display divisor.
                local divisor = math.max(1, math.ceil(display_fps / fps - 0.001))
                fps = display_fps / divisor
            end
        end
    end

    return math.max(1, fps)
end

local function remove_overlay_low()
    overlay_low:remove()
    overlay_low_cache_data, overlay_low_cache_width, overlay_low_cache_height = nil, nil, nil
end

-- V19.5.8: keep both OSD/libass overlay contexts warm while Native ASS is
-- visible. This removes the one-time font/libass construction stall from the
-- fullscreen handoff without drawing anything on screen. Full hide/unload still
-- uses remove_overlay_* and releases the overlays normally.
local function park_overlay_renderers()
    overlay_low.res_x, overlay_low.res_y, overlay_low.z = 1920, 1080, 0
    overlay_low.data = OVERLAY_WARM_PAYLOAD
    overlay_low:update()
    overlay_low_cache_data = OVERLAY_WARM_PAYLOAD
    overlay_low_cache_width, overlay_low_cache_height = 1920, 1080

    overlay_high.res_x, overlay_high.res_y, overlay_high.z = 1920, 1080, 1
    overlay_high.data = OVERLAY_WARM_PAYLOAD
    overlay_high:update()
    overlay_high_cache_valid = false
    overlay_high_cache_prefix = nil
    overlay_high_cache_width, overlay_high_cache_height = 1920, 1080
    clear_array(overlay_high_active)
    clear_array(overlay_high_previous)
end

local function get_pressure_overlay_fps(base_fps)
    local display_fps = get_danmaku_display_fps()
    if not display_fps or display_fps <= 0 then return math.min(base_fps, 60) end

    -- Pressure mode moves exactly one display divisor lower than normal.
    -- Below the automatic budget this means, for example:
    -- 120->60, 144:72->48, 165:82.5->55, 240:120->80, 360:120->90.
    -- This is temporary protection; low-refresh displays retain a useful floor.
    local base_divisor = math.max(1, math.floor(display_fps / base_fps + 0.5))
    local fps = display_fps / (base_divisor + 1)
    if fps < 47.5 or fps >= base_fps - 0.5 then return base_fps end
    return fps
end

local function overlay_adaptive_enabled()
    local configured_fps = tonumber(options.overlay_fps)
    return options.overlay_adaptive_fps == true
        and (not configured_fps or configured_fps <= 0)
end

local function get_overlay_fps()
    local base_fps = get_base_overlay_fps()
    if overlay_adaptive_level > 0 and overlay_adaptive_enabled() then
        return get_pressure_overlay_fps(base_fps)
    end
    return base_fps
end

local function publish_overlay_health(state)
    local base_fps = get_base_overlay_fps()
    local effective_fps = get_overlay_fps()
    local current_state = state or (overlay_adaptive_level > 0 and "protected" or "native")
    local key = table.concat({current_state, string.format("%.3f", base_fps),
        string.format("%.3f", effective_fps), overlay_health_reason}, ":")
    if key == overlay_health_publish_key then return end
    overlay_health_publish_key = key
    mp.set_property_native('user-data/uosc_danmaku/overlay-cadence', {
        state = current_state,
        base_fps = base_fps,
        effective_fps = effective_fps,
        reason = overlay_health_reason,
    })
end

local function clear_overlay_clock()
    overlay_clock_media = nil
    overlay_clock_wall = nil
    overlay_clock_speed = 1
    overlay_clock_last = nil
end

local function get_overlay_clock_speed()
    local speed = mp.get_property_number('speed', 1) or 1
    local correction = mp.get_property_number('video-speed-correction', 1) or 1
    if correction <= 0 then correction = 1 end
    return speed * correction
end

local function reset_overlay_clock(media_time)
    overlay_clock_media = media_time or mp.get_property_number('time-pos')
    overlay_clock_wall = mp.get_time()
    overlay_clock_speed = get_overlay_clock_speed()
    overlay_clock_last = overlay_clock_media
    return overlay_clock_media
end

local function hold_overlay_clock()
    -- Freeze the position actually submitted to libass. time-pos may still
    -- describe the preceding 24/30 fps video frame and move comments backwards.
    if overlay_sleeping and overlay_clock_media ~= nil and overlay_clock_wall ~= nil
        and not pause and not overlay_clock_cache_paused then
        -- During an empty interval there is no visible position to freeze.
        -- Preserve elapsed playback time, not the preceding idle probe time.
        overlay_clock_media = overlay_clock_media
            + (mp.get_time() - overlay_clock_wall) * overlay_clock_speed
        overlay_clock_last = overlay_clock_media
    else
        overlay_clock_media = overlay_clock_last or overlay_clock_media or mp.get_property_number('time-pos')
    end
    overlay_clock_wall = mp.get_time()
    overlay_clock_speed = get_overlay_clock_speed()
end

local function resume_overlay_clock()
    if overlay_clock_media == nil then return reset_overlay_clock() end
    overlay_clock_wall = mp.get_time()
    overlay_clock_speed = get_overlay_clock_speed()
end

local function rebase_overlay_clock(speed)
    local now = mp.get_time()
    if overlay_clock_media ~= nil and overlay_clock_wall ~= nil
    and not pause and not overlay_clock_seeking and not overlay_clock_cache_paused then
        overlay_clock_media = overlay_clock_media
            + (now - overlay_clock_wall) * overlay_clock_speed
    elseif overlay_clock_media == nil then
        overlay_clock_media = mp.get_property_number('time-pos')
    end
    overlay_clock_wall = now
    overlay_clock_speed = tonumber(speed) or get_overlay_clock_speed()
end

local function get_overlay_media_time(sample_wall)
    local media_time = mp.get_property_number('time-pos')
    if media_time == nil then
        clear_overlay_clock()
        return nil
    end

    local speed = get_overlay_clock_speed()
    if overlay_clock_media == nil or overlay_clock_wall == nil then
        return reset_overlay_clock(media_time)
    end

    if speed ~= overlay_clock_speed then
        rebase_overlay_clock(speed)
    end

    if overlay_clock_seeking then
        return reset_overlay_clock(media_time)
    end
    if pause or overlay_clock_cache_paused then return overlay_clock_media end

    -- time-pos is quantized to decoded video frames.  Extrapolate from a
    -- monotonic playback anchor so a 60 Hz OSD overlay does not repeat the
    -- same coordinate two or three times on 24/30 fps sources.  Seeking,
    -- pausing, cache stalls and speed changes explicitly rebase this clock.
    local position = overlay_clock_media + ((sample_wall or mp.get_time()) - overlay_clock_wall) * overlay_clock_speed
    overlay_clock_last = position
    return position
end

local function stop_overlay_timer(keep_native_health)
    if overlay_render_timer then
        overlay_render_timer:kill()
    end
    overlay_render_interval, overlay_render_deadline = nil, nil
    overlay_sleeping = false
    if not keep_native_health and stop_overlay_health_timer then stop_overlay_health_timer() end
end

local function run_overlay_timer()
    if pause or not ENABLED or COMMENTS == nil or is_ass_track_mode() then
        stop_overlay_timer()
        return
    end

    -- V19.5.8: keep the absolute cadence, but never discard an upcoming slot
    -- merely because it is less than 1 ms away. At 144 Hz that old 1 ms guard
    -- was ~14% of a refresh interval and could create a regular hold/catch-up
    -- pulse. Only deadlines that are already expired are skipped. Position
    -- sampling remains deadline-based so callback jitter is not copied directly
    -- into the danmaku's spatial step.
    local started = mp.get_time()
    local raw_lateness = math.max(0, started - overlay_render_deadline)
    local skipped = 0
    if raw_lateness >= overlay_render_interval then
        skipped = math.floor(raw_lateness / overlay_render_interval)
        overlay_render_deadline = overlay_render_deadline + skipped * overlay_render_interval
    end
    local residual_lateness = math.max(0, started - overlay_render_deadline)
    overlay_timing_samples = overlay_timing_samples + 1
    overlay_timing_late_sum = overlay_timing_late_sum + residual_lateness
    overlay_timing_late_max = math.max(overlay_timing_late_max, residual_lateness)
    overlay_timing_skipped = overlay_timing_skipped + skipped

    local was_sleeping = overlay_sleeping
    local position = get_overlay_media_time(overlay_render_deadline)
    local idle_until = render(position)
    overlay_sleeping = idle_until ~= nil
    if overlay_sleeping then
        -- No live events: wake at the next event boundary, with a bounded
        -- one-second fallback for external updates. Keep the media anchor.
        local delay = math.min(1, math.max(overlay_render_interval,
            (idle_until - position) / math.max(get_overlay_clock_speed(), 0.01)))
        overlay_render_deadline = started + delay
        overlay_render_timer.timeout = math.max(OVERLAY_TIMER_MIN_DELAY, overlay_render_deadline - mp.get_time())
        overlay_render_timer:resume()
        if stop_overlay_health_timer then stop_overlay_health_timer() end
        return
    end
    if was_sleeping and start_overlay_health_timer then start_overlay_health_timer() end

    -- Anchor updates to an absolute cadence. mpv's periodic timers schedule
    -- from the actual (possibly late) callback time, so occasional delays can
    -- permanently shift the following frames and make horizontal motion feel
    -- uneven. Skip expired slots, but keep the next valid display deadline.
    local now = mp.get_time()
    repeat
        overlay_render_deadline = overlay_render_deadline + overlay_render_interval
    until overlay_render_deadline > now
    overlay_render_timer.timeout = math.max(OVERLAY_TIMER_MIN_DELAY, overlay_render_deadline - now)
    overlay_render_timer:resume()

    if overlay_timing_report_at == 0 then overlay_timing_report_at = now end
    if now - overlay_timing_report_at >= 30 and overlay_timing_samples > 0 then
        local avg_ms = overlay_timing_late_sum / overlay_timing_samples * 1000
        local max_ms = overlay_timing_late_max * 1000
        mp.set_property_native('user-data/uosc_danmaku/overlay-timing', {
            avg_late_ms = avg_ms,
            max_late_ms = max_ms,
            skipped_slots = overlay_timing_skipped,
            cadence = get_overlay_fps(),
        })
        msg.verbose(string.format('overlay timing: avg-late=%.3fms max-late=%.3fms skipped=%d cadence=%.3f',
            avg_ms, max_ms, overlay_timing_skipped, get_overlay_fps()))
        overlay_timing_samples, overlay_timing_late_sum = 0, 0
        overlay_timing_late_max, overlay_timing_skipped = 0, 0
        overlay_timing_report_at = now
    end
end

local function start_overlay_timer()
    if pause or overlay_clock_cache_paused or overlay_clock_seeking
        or not ENABLED or COMMENTS == nil then return end
    if is_ass_track_mode() then
        if native_refresh_available and start_overlay_health_timer then start_overlay_health_timer() end
        return
    end
    local interval = 1 / get_overlay_fps()
    -- A style change or incoming live batch must not rewind the media clock
    -- or shift an already running cadence. Re-arm only when it really stopped.
    if overlay_render_timer and overlay_render_timer:is_enabled() and not overlay_sleeping
        -- Drivers can report the same refresh rate with tiny decimal drift
        -- (for example 143.999 -> 144.001). Treat that as the same cadence so
        -- property notifications cannot repeatedly move the timer phase.
        and math.abs(overlay_render_interval - interval)
            <= math.max(0.000001, overlay_render_interval * 0.005) then
        if start_overlay_health_timer then start_overlay_health_timer() end
        return
    end
    if overlay_clock_media == nil then reset_overlay_clock() end
    overlay_sleeping = false
    overlay_render_interval = interval
    overlay_render_deadline = mp.get_time() + overlay_render_interval
    if not overlay_render_timer then
        overlay_render_timer = mp.add_timeout(overlay_render_interval, run_overlay_timer, true)
    end
    overlay_render_timer:kill()
    overlay_render_timer.timeout = overlay_render_interval
    overlay_render_timer:resume()
    if start_overlay_health_timer then start_overlay_health_timer() end
end

local function overlay_render_ratio(target_fps)
    local fps = mp.get_property_number('estimated-vf-fps', 0) or 0
    if fps <= 0 then fps = mp.get_property_number('container-fps', 0) or 0 end
    fps = fps * math.max(mp.get_property_number('speed', 1) or 1, 0.01)
    if fps <= 0 then return nil end

    local passes = mp.get_property_native('vo-passes')
    local fresh = type(passes) == 'table' and passes.fresh or nil
    if type(fresh) ~= 'table' or #fresh == 0 then return nil end
    local total = 0
    for _, pass in ipairs(fresh) do
        total = total + (tonumber(pass.avg) or tonumber(pass.last) or 0)
    end
    if total <= 0 then return nil end
    local budget = total * fps
    if is_ass_track_mode() and native_refresh_available then
        local redraw = type(passes.redraw) == 'table' and passes.redraw or {}
        local extra = 0
        for _, pass in ipairs(redraw) do
            extra = extra + (tonumber(pass.avg) or tonumber(pass.last) or 0)
        end
        budget = budget + extra * math.max(0, (target_fps or get_overlay_fps()) - fps)
    end
    return budget / 1000000000
end

local function reset_overlay_health_window(delay, keep_recovery)
    overlay_health_last_drops = mp.get_property_number('frame-drop-count', 0) or 0
    overlay_health_bad_samples = 0
    overlay_health_drop_windows = 0
    if not keep_recovery then
        overlay_health_good_seconds = 0
    end
    overlay_health_ready_at = mp.get_time() + math.max(0, delay or 0)
    overlay_health_report_at, overlay_health_report_drops = mp.get_time(), 0
end

local function change_overlay_adaptive_level(level, reason)
    level = math.max(0, math.min(1, tonumber(level) or 0))
    if level > 0 and get_pressure_overlay_fps(get_base_overlay_fps()) >= get_base_overlay_fps() - 0.5 then
        return false
    end
    local old_fps = get_overlay_fps()
    overlay_adaptive_level = level
    overlay_health_reason = reason or (level > 0 and 'render-pressure' or 'recovered')
    local new_fps = get_overlay_fps()
    publish_overlay_health()
    -- Protected cadence is visibly softer on high-refresh panels, so keep a
    -- short anti-flap hold instead of V19.3's long recovery delay.
    reset_overlay_health_window(level > 0 and 12 or 20)
    if math.abs(old_fps - new_fps) < 0.5 then return false end

    msg.info(string.format('overlay cadence %s: %.3f -> %.3f Hz (%s)',
        level > 0 and 'protected' or 'recovered', old_fps, new_fps,
        overlay_health_reason))
    -- Re-arm only the cadence. The monotonic media clock remains untouched, so
    -- the first protected frame cannot jump backwards or restart a comment.
    if is_ass_track_mode() and sync_native_refresh then
        sync_native_refresh()
    else
        start_overlay_timer()
    end
    return true
end

local function monitor_overlay_health()
    local drops = mp.get_property_number('frame-drop-count', 0) or 0
    if not overlay_adaptive_enabled() or pause or overlay_clock_cache_paused
        or overlay_clock_seeking or mp.get_property_native('core-idle')
        or not ENABLED or COMMENTS == nil or not get_danmaku_visibility()
        or (is_ass_track_mode() and not native_refresh_available) then
        -- 暂停或无弹幕期间不测量，但保留已累积的稳定时长：暂停本身不构成渲染
        -- 压力，不应让一次暂停抵消此前的恢复进度。
        reset_overlay_health_window(8, true)
        publish_overlay_health('idle')
        return
    end

    local now = mp.get_time()
    if drops < overlay_health_last_drops or now < overlay_health_ready_at then
        overlay_health_last_drops = drops
        return
    end

    local drop_delta = math.max(0, drops - overlay_health_last_drops)
    overlay_health_last_drops = drops
    local ratio = overlay_render_ratio()
    overlay_health_report_drops = overlay_health_report_drops + drop_delta
    if now - overlay_health_report_at >= 30 then
        -- Bounded summaries support long-play diagnosis without per-frame log I/O.
        msg.info(string.format('overlay health: window=%.1fs drops=%d render-ratio=%.3f cadence=%.3f',
            now - overlay_health_report_at, overlay_health_report_drops,
            ratio or -1, get_overlay_fps()))
        overlay_health_report_at, overlay_health_report_drops = now, 0
    end
    local over_budget = ratio and ratio >= 0.78
    -- 渲染预算充足时，丢帧不是弹幕造成的：显示合成、解码、显卡降频都会让
    -- 输出丢帧，而降弹幕刷新率既救不回这些帧，还白白牺牲滚动流畅度（用户
    -- 感受为周期性顿感）。因此只有弹幕自身吃掉了可观预算时，丢帧才作为
    -- 收紧节奏的依据。预算读不到时保留原有判定。
    local pace_budget_spent = ratio == nil or ratio >= 0.50
    -- 单个采样窗口里的丢帧尖峰常来自一次性的 OSD 重排（打开统计面板、切换
    -- 菜单等），它不代表持续的渲染压力；只有丢帧连续跨越多个窗口才收紧。
    overlay_health_drop_windows = drop_delta >= 2
        and (overlay_health_drop_windows + 1) or 0
    local bad = over_budget
        or (pace_budget_spent and overlay_health_drop_windows >= 3)
    -- Reduced native redraw cost is not proof that the normal cadence fits.
    -- Predict that cost before recovering, otherwise a fixed load can bounce
    -- between (for example) 240 and 120 Hz every protection/recovery window.
    local recovery_ratio = ratio
    if overlay_adaptive_level > 0 and is_ass_track_mode() and native_refresh_available then
        recovery_ratio = overlay_render_ratio(get_base_overlay_fps())
    end
    local good = drop_delta == 0 and (not recovery_ratio or recovery_ratio <= 0.50)

    if bad then
        overlay_health_bad_samples = overlay_health_bad_samples + 1
        -- 持续超出预算时立即归零；孤立尖峰只扣减，避免一次操作抵消全部恢复进度
        overlay_health_good_seconds = over_budget and 0
            or math.max(0, overlay_health_good_seconds - 6)
    else
        overlay_health_bad_samples = 0
        overlay_health_good_seconds = good
            and (overlay_health_good_seconds + 2) or 0
    end

    if overlay_adaptive_level == 0 and overlay_health_bad_samples >= 2 then
        local reason = over_budget and 'render-pressure' or 'output-drops'
        change_overlay_adaptive_level(1, reason)
    elseif overlay_adaptive_level > 0 and overlay_health_good_seconds >= 20 then
        change_overlay_adaptive_level(0, 'stable-headroom')
    else
        publish_overlay_health()
    end
end

stop_overlay_health_timer = function()
    if overlay_health_timer then overlay_health_timer:kill() end
    reset_overlay_health_window(8)
    publish_overlay_health('idle')
end

start_overlay_health_timer = function()
    if not overlay_adaptive_enabled() then
        if overlay_health_timer then overlay_health_timer:kill() end
        overlay_adaptive_level, overlay_health_reason = 0, 'manual'
        publish_overlay_health('manual')
        return
    end
    if overlay_health_timer and overlay_health_timer:is_enabled() then
        publish_overlay_health()
        return
    end
    reset_overlay_health_window(8)
    if not overlay_health_timer then
        overlay_health_timer = mp.add_periodic_timer(2, monitor_overlay_health)
    end
    overlay_health_timer:resume()
    publish_overlay_health()
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
    -- A fresh/isolated config may not have a cache directory yet. Native ASS
    -- should still work using the existing temporary directory in that case.
    if dir and utils.file_info then
        local info = utils.file_info(dir)
        if not info or not info.is_dir then dir = nil end
    end
    dir = dir or DANMAKU_PATH or "."
    return utils.join_path(dir, string.format("uosc-danmaku-%s.ass", PID))
end

local function find_ass_track_id(existing_ids, path)
    local tracks = mp.get_property_native("track-list") or {}
    for _, track in ipairs(tracks) do
        -- Embedded subtitles have no external-filename. Never compare their
        -- nil filename with the not-yet-assigned ass_track_path (also nil).
        -- Only claim a newly added external track; a stale same-title track
        -- from an earlier load must not win either.
        if track.type == "sub" and track.external and not existing_ids[track.id]
        and (track.title == "uosc_danmaku"
            or (path and track["external-filename"] == path)) then
            return track.id
        end
    end
    return nil
end

local function clear_saved_secondary_state()
    previous_secondary_sid = nil
    previous_secondary_visibility = nil
    previous_secondary_ass_override = nil
    previous_secondary_full_viewport = nil
    previous_secondary_refresh = nil
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

local function restore_native_viewport()
    if previous_secondary_refresh ~= nil then
        set_secondary_property(REFRESH_OPTION, previous_secondary_refresh, true)
    end
    if previous_secondary_full_viewport ~= nil then
        set_secondary_property(FULL_VIEWPORT_OPTION, previous_secondary_full_viewport, true)
    end
    native_full_viewport_active = false
end

sync_native_refresh = function()
    if not native_refresh_available or not ass_track_id then return end
    if has_external_secondary_subtitle() then return end
    local rate = is_ass_track_mode() and get_overlay_fps() or 0
    if math.abs((mp.get_property_number(REFRESH_OPTION, 0) or 0) - rate) > 0.01 then
        set_secondary_property(REFRESH_OPTION, rate, true)
    end
end

local function sync_native_viewport()
    sync_native_refresh()
    if not native_full_viewport_available or not ass_track_id then return end
    if has_external_secondary_subtitle() then return end
    local enabled = is_ass_track_mode() and should_use_fullscreen_blackbar_overlay()
    if mp.get_property_native(FULL_VIEWPORT_OPTION) ~= enabled then
        set_secondary_property(FULL_VIEWPORT_OPTION, enabled, true)
    end
    native_full_viewport_active = enabled
end

local function unload_ass_track(restore_secondary)
    -- Restore before removing the track so a replacement secondary subtitle
    -- never inherits our full-output setting from this handoff.
    restore_native_viewport()
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

-- V19.5.8 seamless hybrid handoff. For fullscreen letterbox only, keep the
-- Native ASS track attached but temporarily hidden while the black-bar Overlay
-- path is active. Returning to windowed mode then becomes a visibility handoff
-- instead of sub-remove/sub-add, so the comments do not visibly reload.
local function park_native_ass_track()
    if not ass_track_id then return false end
    if tostring(mp.get_property_native("secondary-sid")) ~= tostring(ass_track_id) then return false end
    set_secondary_property("secondary-sub-visibility", "no")
    hybrid_ass_parked = true
    return true
end

local function resume_parked_native_ass_track()
    if not hybrid_ass_parked or not ass_track_id then return false end
    if has_external_secondary_subtitle() then return false end
    set_secondary_property("secondary-sid", ass_track_id, true)
    sync_native_viewport()
    set_secondary_property("secondary-sub-ass-override", "no")
    set_secondary_property("secondary-sub-visibility", "yes")
    hybrid_ass_parked = false
    return true
end

local function detach_parked_native_ass_track_for_external_secondary()
    if not hybrid_ass_parked or not ass_track_id then return false end
    local track_id = ass_track_id
    restore_native_viewport()
    ass_track_id = nil
    pcall(mp.commandv, "sub-remove", track_id)
    if previous_secondary_visibility ~= nil then
        set_secondary_property("secondary-sub-visibility", previous_secondary_visibility)
    end
    if previous_secondary_ass_override ~= nil then
        set_secondary_property("secondary-sub-ass-override", previous_secondary_ass_override)
    end
    clear_saved_secondary_state()
    hybrid_ass_parked = false
    ass_track_dirty = true
    return true
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
    local canvas = COMMENTS and COMMENTS.canvas
    return not y or tonumber(y) <= (canvas and canvas.height or 1080) * displayarea
end

local function build_ass_track()
    if not COMMENTS or #COMMENTS == 0 then
        return nil
    end

    local opacity = tonumber(options.opacity)
    local alpha = string.format("%02X", (1 - (opacity or 0)) * 255)
    local bold = options.bold and "-1" or "0"
    local canvas = COMMENTS.canvas or get_danmaku_canvas('ass-track')
    local fontsize = canvas.font_size
    local outline = tonumber(options.outline) or 0
    local shadow = tonumber(options.shadow) or 0
    local displayarea = tonumber(options.displayarea) or 1

    local lines = {
        "[Script Info]",
        "ScriptType: v4.00+",
        string.format("PlayResX: %d", canvas.width),
        string.format("PlayResY: %d", math.floor(canvas.height + 0.5)),
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
            update_event_color(event)
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
    if not COMMENTS or #COMMENTS == 0 then
        unload_ass_track(false)
        ass_track_dirty = false
        return true
    end

    local content = build_ass_track()
    if not content then return true end

    -- Live batches must not detach the visible track while the replacement
    -- file is written/probed. Keep the current libass output until selection
    -- of the fully opened replacement, then retire only our previous track.
    local old_id, old_path = ass_track_id, ass_track_path
    local next_slot = old_id and (1 - ass_track_slot) or 0
    local next_path = get_ass_track_path()
    if next_slot == 1 then next_path = next_path:gsub('%.ass$', '-next.ass') end
    if not write_text_file(next_path, content) then
        return false, "write-failed"
    end

    if old_id and native_replace_available and not has_external_secondary_subtitle() then
        local ok, result, err = pcall(mp.commandv, 'secondary-ass-replace', old_id, next_path)
        if ok and result ~= false and not (result == nil and err) then
            -- Keep the original backing filename current for explicit reloads.
            if old_path ~= next_path then write_text_file(old_path, content); pcall(os.remove, next_path) end
            ass_track_dirty = false
            sync_native_viewport()
            return true
        end
        msg.warn('原生弹幕原位更新失败，保留画面并尝试备用更新')
    end

    if previous_secondary_sid == nil then
        previous_secondary_sid = mp.get_property_native("secondary-sid") or "no"
        previous_secondary_visibility = mp.get_property("secondary-sub-visibility", "yes")
        previous_secondary_ass_override = mp.get_property("secondary-sub-ass-override", "strip")
        if native_full_viewport_available then
            previous_secondary_full_viewport = mp.get_property_native(FULL_VIEWPORT_OPTION)
        end
        if native_refresh_available then
            previous_secondary_refresh = mp.get_property_native(REFRESH_OPTION)
        end
    end

    local existing_ids = {}
    for _, track in ipairs(mp.get_property_native("track-list") or {}) do
        if track.type == "sub" then existing_ids[track.id] = true end
    end
    local command_ok, result, command_err = pcall(mp.commandv, "sub-add", next_path, "auto", "uosc_danmaku")
    if not command_ok or result == false or (result == nil and command_err) then
        if next_path ~= old_path then pcall(os.remove, next_path) end
        return false, command_err or result or "sub-add-failed"
    end
    ass_track_id = find_ass_track_id(existing_ids, next_path)
    if ass_track_id then
        ass_track_path, ass_track_slot = next_path, next_slot
        set_secondary_property("secondary-sub-visibility", "yes")
        set_secondary_property("secondary-sub-ass-override", "no")
        set_secondary_property("secondary-sid", ass_track_id, true)
        sync_native_viewport()
        if native_refresh_available then start_overlay_health_timer() end
        if old_id then pcall(mp.commandv, "sub-remove", old_id) end
        if old_path and old_path ~= next_path then pcall(os.remove, old_path) end
        local _, reason = desired_render_mode()
        publish_render_mode("ass-track", reason)
        hybrid_ass_parked = false
        ass_track_dirty = false
        msg.verbose("ASS 弹幕轨已加载: " .. ass_track_path)
        -- Prime the Overlay/libass contexts invisibly while the Native ASS track
        -- is already on screen. The first fullscreen switch then does not pay
        -- the font/provider construction cost in the click-to-fullscreen path.
        park_overlay_renderers()
        return true
    else
        ass_track_id, ass_track_path = old_id, old_path
        if next_path ~= old_path then pcall(os.remove, next_path) end
        return false, "track-not-found"
    end
end

local function switch_to_overlay(reason, preserve_current_secondary, mark_failed)
    -- Only an actual ASS track construction/load failure should poison the
    -- native path. Temporary compatibility fallbacks (for example a user
    -- selecting a second subtitle) must be able to return to Native ASS later.
    ass_track_failed = mark_failed == true
    hybrid_ass_parked = false
    active_render_mode = "overlay"
    if COMMENTS and COMMENTS.canvas and COMMENTS.canvas.key ~= get_danmaku_canvas('overlay').key
        and DANMAKU and type(DANMAKU.sources) == 'table' then
        convert_danmaku_to_ass_events(true)
    end
    publish_render_mode("overlay", reason and ("ass-track-fallback:" .. tostring(reason)) or "compatibility-fallback")
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

    if event._overlay_motion_x == nil then
        local x1, y1, x2, y2 = unpack(event.move)
        event._overlay_motion_x = x1
        event._overlay_motion_y = y1
        event._overlay_motion_dx = x2 - x1
        event._overlay_motion_dy = y2 - y1
        event._overlay_motion_inv_duration = 1 /
            math.max(0.001, event.end_time - event.start_time)
    end
    local progress = (pos - event.start_time) * event._overlay_motion_inv_duration

    -- 计算当前坐标
    local current_x = event._overlay_motion_x + event._overlay_motion_dx * progress
    local current_y = event._overlay_motion_y + event._overlay_motion_dy * progress

    -- 移除 \move 标签并应用当前坐标
    if current_y > displayarea then return end
    if event.style ~= "SP" and event.style ~= "MSG" then
        return string.format("{\\pos(%.2f,%.2f)\\an8}%s", current_x, current_y, event_text)
    else
        return string.format("{\\pos(%.2f,%.2f)\\an7}%s", current_x, current_y, event_text)
    end
end

local function static_overlay_ass(event, ass_prefix, displayarea)
    local _, current_y = unpack(event.pos or {})
    if not current_y or tonumber(current_y) > displayarea then return end
    if event._overlay_static_prefix ~= ass_prefix then
        local alignment = (event.style ~= "SP" and event.style ~= "MSG")
            and "{\\an8}" or "{\\an7}"
        event._overlay_static_prefix = ass_prefix
        event._overlay_static_ass = ass_prefix .. alignment .. get_overlay_event_text(event)
    end
    return event._overlay_static_ass
end

function render(pos_arg)
    if COMMENTS == nil then return end
    if is_ass_track_mode() then
        if ass_track_dirty or not ass_track_id then
            local ok, reason = render_ass_track()
            if ok then return end
            switch_to_overlay(reason, false, true)
        else
            return
        end
    end

    local pos
    if pos_arg == nil then
        pos = get_overlay_media_time()
    else
        pos = pos_arg
    end

    if not pos then
        remove_overlay_low()
        remove_overlay_high()
        return
    end

    local fontname = options.fontname
    local canvas = COMMENTS.canvas or get_danmaku_canvas('overlay')
    local fontsize = canvas.font_size
    local opacity = tonumber(options.opacity)
    local alpha = string.format("%02X", (1 - (opacity or 0)) * 255)

    local width, height = canvas.width, canvas.height

    clear_array(ass_events_low)
    clear_array(ass_events_high)
    clear_array(overlay_high_active)
    local max_display = math.max(options.scrolltime, options.fixtime)
    local window_start = pos - max_display

    -- 跳过已结束的弹幕
    local lo = binary_search(COMMENTS, window_start, function(item) return item.start_time end)

    local ass_prefix = get_ass_prefix(fontname, fontsize, alpha)
    local active_events, next_event_time = 0, math.huge

    for i = lo, #COMMENTS do
        local event = COMMENTS[i]
        if not event then break end

        if event.start_time > pos then
            next_event_time = event.start_time
            break
        end
        if event.end_time >= pos then
            active_events = active_events + 1
            update_event_color(event)
            if event.layer == nil or tonumber(event.layer) == 0 then
                local text = realtime_position_text(event, pos, height * options.displayarea)
                if text then
                    ass_events_low[#ass_events_low + 1] = ass_prefix .. text
                end
            else
                local ass_text = static_overlay_ass(event, ass_prefix, height * options.displayarea)
                if ass_text then
                    overlay_high_active[#overlay_high_active + 1] = event
                end
            end
        end
    end

    -- 写入低层（滚动）和高层（顶/底）overlay，并设置 z 值以控制堆叠
    overlay_low.res_x = width
    overlay_low.res_y = height
    overlay_low.z = 0
    local low_data = table.concat(ass_events_low, '\n')
    if low_data ~= overlay_low_cache_data or width ~= overlay_low_cache_width
        or height ~= overlay_low_cache_height then
        overlay_low.data = low_data
        overlay_low:update()
        overlay_low_cache_data, overlay_low_cache_width, overlay_low_cache_height = low_data, width, height
    end

    local high_changed = not overlay_high_cache_valid
        or overlay_high_cache_prefix ~= ass_prefix
        or overlay_high_cache_width ~= width
        or overlay_high_cache_height ~= height
        or #overlay_high_active ~= #overlay_high_previous
    if not high_changed then
        for i = 1, #overlay_high_active do
            if overlay_high_active[i] ~= overlay_high_previous[i] then
                high_changed = true
                break
            end
        end
    end
    if high_changed then
        clear_array(ass_events_high)
        clear_array(overlay_high_previous)
        for i = 1, #overlay_high_active do
            local event = overlay_high_active[i]
            ass_events_high[i] = event._overlay_static_ass
            overlay_high_previous[i] = event
        end
        overlay_high.res_x = width
        overlay_high.res_y = height
        overlay_high.z = 1
        overlay_high.data = table.concat(ass_events_high, '\n')
        overlay_high:update()
        overlay_high_cache_valid = true
        overlay_high_cache_prefix = ass_prefix
        overlay_high_cache_width = width
        overlay_high_cache_height = height
    end

    -- Overlay mode rebuilds the moving ASS payload at its display cadence.  A small
    -- incremental collection here prevents those short-lived strings from
    -- accumulating into a larger, visible collection pause every few seconds.
    collectgarbage('step', 32)
    if active_events == 0 then return next_event_time end
end

function render_danmaku(from_menu, no_osd)
    if ENABLED and type(COMMENTS) == 'table' and #COMMENTS > 0
        and (from_menu or get_danmaku_visibility()) then
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

local function has_moving_danmaku()
    if type(COMMENTS) ~= "table" then return false end
    for _, event in ipairs(COMMENTS) do
        if event and event.move then return true end
    end
    return false
end

local function restore_overlay_display_sync(reset_override)
    if overlay_sync_profile_active then
        local ok, err = pcall(mp.commandv, "apply-profile", OVERLAY_SYNC_PROFILE, "restore")
        if not ok then
            msg.warn("恢复弹幕 overlay 显示同步失败: " .. tostring(err))
        end
        overlay_sync_profile_active = false
    end
    if reset_override then
        overlay_sync_external_override = false
    end
end

local function overlay_sync_session_active()
    return options.overlay_display_sync == true
        and ENABLED and type(COMMENTS) == "table" and #COMMENTS > 0
        and get_danmaku_visibility() and not is_ass_track_mode()
        and has_moving_danmaku()
end

local function overlay_display_sync_eligible()
    if not overlay_sync_session_active() or filter_state("danmaku") then return false end

    local display_fps = mp.get_property_number("display-fps")
    local video_fps = mp.get_property_number("estimated-vf-fps")
    if not display_fps or display_fps < 58 or not video_fps or video_fps <= 0 then
        return false
    end

    -- A 60 fps source on a 144 Hz monitor also needs display-paced redraws.
    -- Comparing against the overlay's 60 Hz ceiling excluded this common case.
    if video_fps >= display_fps - 1 then return false end

    -- Avoid fighting the existing speed-dependent video-sync auto profile.
    local speed = mp.get_property_number("speed", 1) or 1
    return speed >= 0.96 and speed <= 1.04
end

local overlay_enhancement_sync_generation = nil

local function update_overlay_display_mode()
    -- V19.3: overlay timing never owns the video's presentation clock.
    -- The old path applied danmaku-overlay-sync and changed video-sync to
    -- display-vdrop. On 60 fps + high-refresh displays that could enter a
    -- long-play cadence oscillation. Smoothness is now handled solely by the
    -- exact display-divisor overlay timer above.
    overlay_sync_profile_active = false
    overlay_sync_external_override = false
    overlay_sync_profile_failed = false
end

local function sync_overlay_display_mode()
    update_overlay_display_mode()
    sync_native_refresh()
    -- Monitor/sync changes can select a different integer refresh divisor.
    -- Re-arm its cadence only; keep the current playback anchor intact.
    if overlay_render_timer and overlay_render_timer:is_enabled() then
        start_overlay_timer()
    end
end

local function remove_danmaku_fps_filter()
    if filter_state("danmaku") then
        mp.commandv("vf", "remove", "@danmaku")
    end
end

local function sync_danmaku_fps_filter()
	-- Overlay mode owns its own render cadence and must never alter the video
	-- frame rate. Keep this hard guard even if a stale config still says yes.
	if not is_ass_track_mode() then
		remove_danmaku_fps_filter()
		return
	end

    -- V19.5: Native ASS does not require changing the video pipeline. Keep the
    -- legacy fps helper strictly SDR-only. While transfer metadata is unknown,
    -- or once PQ/HLG is confirmed (including Dolby Vision output through PQ),
    -- never insert @danmaku:fps. This avoids the historical HDR/gamma/filter
    -- side effects and keeps RIFE/AI/video-sync ownership outside the danmaku.
    if not options.vf_fps or get_video_hdr_state() ~= false then
        remove_danmaku_fps_filter()
        return
    end

    local display_fps = mp.get_property_number('display-fps')
    -- container-fps is not changed by our own fps filter. Falling back keeps
    -- streams without a nominal rate compatible with the previous behavior.
    local video_fps = mp.get_property_number('container-fps')
        or mp.get_property_number('estimated-vf-fps')
    if (display_fps and display_fps < 58) or (video_fps and video_fps > 58) then
        remove_danmaku_fps_filter()
        return
    end

    if not filter_state("danmaku", "fps") then
        mp.commandv("vf", "append", string.format("@danmaku:fps=fps=%s", options.fps))
    end
end

local function repaint_danmaku()
    -- A live batch or a settings edit may arrive between scheduled frames.
    -- Repaint its content at the last submitted position; moving early here
    -- creates an extra short step followed by a long one on the display.
    local position
    if not is_ass_track_mode() and overlay_render_timer
        and overlay_render_timer:is_enabled() and not overlay_sleeping then position = overlay_clock_last end
    render(position)
end

function show_danmaku_func()
    mp.set_property_bool(HAS_DANMAKU, type(COMMENTS) == "table" and #COMMENTS > 0)
    set_danmaku_visibility(true)
    resolve_render_mode()
    repaint_danmaku()
    if is_ass_track_mode() then
        stop_overlay_timer(native_refresh_available)
        if native_refresh_available then start_overlay_health_timer() end
        park_overlay_renderers()
    elseif not pause then
        start_overlay_timer()
    end
    sync_danmaku_fps_filter()
    sync_overlay_display_mode()
    publish_danmaku_layout()
end

function hide_danmaku_func()
    restore_overlay_display_sync(true)
    stop_overlay_timer()
    unload_ass_track(true)
    hybrid_ass_parked = false
    mp.set_property_bool(HAS_DANMAKU, false)
    set_danmaku_visibility(false)
    publish_danmaku_layout()
    remove_overlay_low()
    remove_overlay_high()
    if filter_state("danmaku") then
        mp.commandv("vf", "remove", "@danmaku")
    end
end

function refresh_danmaku_colors()
    color_revision = color_revision + 1
    ass_track_dirty = true
    overlay_high_cache_valid = false
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        -- Keep the current clock, timer deadline, visibility and sync profile.
        repaint_danmaku()
    end
end

function refresh_danmaku_renderer()
    ass_track_dirty = true
    -- An explicit style/colour change must repaint fixed comments even when
    -- the active event objects and their positions did not change.
    overlay_high_cache_valid = false
    ass_track_failed = false
    fallback_notified = false
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        show_danmaku_func()
    end
end

function reset_danmaku_association_render()
    COMMENTS = {}
    stop_overlay_timer()
    unload_ass_track(true)
    clear_overlay_clock()
    clear_array(ass_events_low)
    clear_array(ass_events_high)
    remove_overlay_low()
    remove_overlay_high()
    ass_track_dirty, ass_track_failed = true, false
    hybrid_ass_parked = false
    overlay_timing_samples, overlay_timing_late_sum = 0, 0
    overlay_timing_late_max, overlay_timing_skipped, overlay_timing_report_at = 0, 0, 0
    mp.set_property_bool(HAS_DANMAKU, false)
    mp.set_property_native(DANMAKU_COUNT, 0)
    publish_danmaku_layout()
end

local LAYOUT_MODE_DEBOUNCE = 0.015
local layout_mode_timer = mp.add_timeout(LAYOUT_MODE_DEBOUNCE, function()
    if not ENABLED or COMMENTS == nil or not get_danmaku_visibility() then return end
    local next_mode, next_reason = desired_render_mode()
    local canvas = get_danmaku_canvas(next_mode)
    local old_canvas = COMMENTS.canvas
    if old_canvas and old_canvas.key ~= canvas.key
        and DANMAKU and type(DANMAKU.sources) == 'table' then
        convert_danmaku_to_ass_events(true)
        ass_track_dirty = true
        invalidate_overlay_high_cache()
    end
    if next_mode == active_render_mode then
        sync_native_viewport()
        publish_render_mode(next_mode, next_reason)
        if ass_track_dirty then repaint_danmaku() end
        publish_danmaku_layout()
        return
    end

    stop_overlay_timer()
    if next_mode == "overlay" then
        if next_reason == "fullscreen-blackbar" and ass_track_id then
            -- Build and submit the first black-bar Overlay frame while Native ASS
            -- is still visible, then hide (not unload) the ASS track. This makes
            -- window -> fullscreen a continuous handoff instead of a reload.
            active_render_mode = "overlay"
            publish_render_mode("overlay", next_reason)
            reset_overlay_clock(mp.get_property_number('time-pos'))
            render(get_overlay_media_time(mp.get_time()))
            park_native_ass_track()
            if not pause then start_overlay_timer() end
            msg.verbose("检测到全屏黑边布局，弹幕已无缝切换 overlay 兼容渲染")
        else
            unload_ass_track(true)
            hybrid_ass_parked = false
            active_render_mode = "overlay"
            publish_render_mode("overlay", next_reason)
            reset_overlay_clock(mp.get_property_number('time-pos'))
            render(get_overlay_media_time(mp.get_time()))
            if not pause then start_overlay_timer() end
            if next_reason == "secondary-subtitle" then
                msg.verbose("检测到第二字幕占用，弹幕已切换 overlay 兼容渲染")
            else
                msg.verbose("弹幕已切换 overlay 兼容渲染: " .. tostring(next_reason))
            end
        end
    else
        active_render_mode = "ass-track"
        publish_render_mode("ass-track", next_reason)

        local resumed = false
        if ass_track_id and hybrid_ass_parked and not ass_track_dirty then
            resumed = resume_parked_native_ass_track()
        end
        if not resumed then
            ass_track_dirty = true
            render()
        end
        -- Keep the Overlay contexts warm but invisible for the next fullscreen
        -- handoff. Do not remove them here; remove is reserved for true hide/unload.
        park_overlay_renderers()
        if next_reason == "native-ass-hdr" then
            msg.verbose("HDR/DV 弹幕已无缝恢复原生 ASS 时间轴渲染")
        else
            msg.verbose("已无缝恢复原生 ASS 弹幕布局")
        end
    end
    -- Gamma/layout changes can switch renderer asynchronously. Reconcile the
    -- optional legacy SDR fps helper only after the target mode is active.
    sync_danmaku_fps_filter()
    sync_overlay_display_mode()
    publish_danmaku_layout()
end, true)

local function schedule_layout_mode_refresh()
    layout_mode_timer:kill()
    layout_mode_timer.timeout = LAYOUT_MODE_DEBOUNCE
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
    publish_danmaku_layout()
end)
mp.observe_property('video-out-params', 'native', schedule_layout_mode_refresh)
mp.observe_property('video-rotate', 'number', schedule_layout_mode_refresh)
mp.observe_property('video-aspect-override', 'number', schedule_layout_mode_refresh)
mp.observe_property('fullscreen', 'bool', function()
    render_active_message()
    schedule_layout_mode_refresh()
end)
mp.observe_property('video-params/gamma', 'string', function()
    local active = ENABLED and COMMENTS ~= nil and get_danmaku_visibility()
    if active then
        sync_danmaku_fps_filter()
        schedule_layout_mode_refresh()
    elseif get_video_hdr_state() ~= false then
        remove_danmaku_fps_filter()
    end
    sync_overlay_display_mode()
end)
mp.observe_property('user-data/video-enhancement/sync-managed', 'native', function() sync_overlay_display_mode() end)
mp.observe_property('user-data/video-enhancement/sync-generation', 'native', function() sync_overlay_display_mode() end)
mp.observe_property('display-fps', 'number', function() sync_overlay_display_mode() end)
mp.observe_property('video-sync', 'string', function() sync_overlay_display_mode() end)
mp.observe_property('estimated-vf-fps', 'number', function() sync_overlay_display_mode() end)
mp.observe_property('container-fps', 'number', function()
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        sync_danmaku_fps_filter()
    end
end)
mp.observe_property('display-hidpi-scale', 'number', function() render_active_message() end)
mp.observe_property('pause', 'bool', function(_, value)
    if value == nil or value == pause then return end
    if value then hold_overlay_clock() else resume_overlay_clock() end
    pause = value
    if ENABLED then
        if pause then
            stop_overlay_timer()
        elseif COMMENTS ~= nil then
            if not is_ass_track_mode() then render() end
            start_overlay_timer()
        end
    end
end)

mp.observe_property('speed', 'number', function(_, value)
    if value ~= nil then
        rebase_overlay_clock()
    end
    sync_overlay_display_mode()
end)

mp.observe_property('video-speed-correction', 'number', function(_, value)
    if value ~= nil then
        rebase_overlay_clock()
        if overlay_sleeping then start_overlay_timer() end
    end
end)

mp.observe_property('seeking', 'bool', function(_, value)
    local seeking = value == true
    if seeking == overlay_clock_seeking then return end
    overlay_clock_seeking = seeking
    overlay_clock_seek_pending = true
    reset_overlay_clock()
    if seeking then stop_overlay_timer() else start_overlay_timer() end
end)

mp.observe_property('paused-for-cache', 'bool', function(_, value)
    local stalled = value == true
    if stalled == overlay_clock_cache_paused then return end
    if stalled then hold_overlay_clock() else resume_overlay_clock() end
    overlay_clock_cache_paused = stalled
    if stalled then stop_overlay_timer() else start_overlay_timer() end
end)

mp.observe_property('secondary-sid', 'native', function(_, value)
    if changing_secondary then return end

    if ass_track_id and hybrid_ass_parked and tostring(value) ~= tostring(ass_track_id) then
        -- Fullscreen hybrid keeps Native ASS attached but hidden. If the user
        -- selects a real second subtitle, release the parked danmaku track and
        -- restore the user's secondary-subtitle properties without overriding
        -- the newly selected track.
        detach_parked_native_ass_track_for_external_secondary()
        if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
            publish_render_mode("overlay", "secondary-subtitle")
            schedule_layout_mode_refresh()
        end
        return
    end

    if ass_track_id and is_ass_track_mode() then
        if tostring(value) == tostring(ass_track_id) then return end

        -- The user selected a real second subtitle. This is a compatibility
        -- fallback, not a Native ASS failure; once the external second subtitle
        -- is disabled, auto mode is allowed to return to the ASS timeline.
        switch_to_overlay(nil, true, false)
        publish_render_mode("overlay", "secondary-subtitle")
        if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
            msg.verbose("检测到用户选择第二字幕，弹幕已切换到 overlay")
            sync_overlay_display_mode()
            render()
            start_overlay_timer()
            show_message("检测到双字幕，弹幕已切换兼容模式", 3)
        end
        return
    end

    -- While already in compatibility overlay, track selection can change again
    -- (e.g. secondary-sid -> no). Re-evaluate so auto mode can recover Native
    -- ASS immediately instead of remaining stuck in overlay for the whole file.
    if ENABLED and COMMENTS ~= nil and get_danmaku_visibility() then
        schedule_layout_mode_refresh()
    end
end)

mp.register_event('playback-restart', function(event)
    if event.error then
        return msg.error(event.error)
    end
    if ENABLED and COMMENTS ~= nil then
        if not is_ass_track_mode() then
            if overlay_clock_seek_pending or overlay_clock_media == nil then reset_overlay_clock() end
            overlay_clock_seek_pending = false
            render()
            start_overlay_timer()
        end
    end
end)

mp.add_hook("on_unload", 50, function()
    COMMENTS, DELAY = nil, 0
    -- Protection belongs to the current workload, not the next video's first
    -- seconds. Every new file starts at its normal rate and is measured again.
    overlay_adaptive_level, overlay_health_reason = 0, 'native'
    restore_overlay_display_sync(true)
    stop_overlay_timer()
    unload_ass_track(true)
    ass_track_dirty = true
    ass_track_failed = false
    fallback_notified = false
    hybrid_ass_parked = false
    overlay_timing_samples, overlay_timing_late_sum = 0, 0
    overlay_timing_late_max, overlay_timing_skipped, overlay_timing_report_at = 0, 0, 0
    active_render_mode = "overlay"
    published_render_mode_key = nil
    mp.set_property_native('user-data/uosc_danmaku/renderer', {mode="idle", reason="unload", hdr=false})
    clear_overlay_clock()
    overlay_clock_seeking, overlay_clock_cache_paused = false, false
    overlay_clock_seek_pending = false
    ass_prefix_cache_key, ass_prefix_cache_value = nil, nil
    clear_array(ass_events_low)
    clear_array(ass_events_high)
    remove_overlay_low()
    remove_overlay_high()
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
