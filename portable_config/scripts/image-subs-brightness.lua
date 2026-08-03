local mp = require 'mp'
local msg = require 'mp.msg'
local options = require 'mp.options'

local o = {
    mode = 'auto',
    peak = 203,
}
options.read_options(o, 'image_subs_brightness')

local config_path = mp.command_native({
    'expand-path',
    '~~/script-opts/image_subs_brightness.conf',
})

local apply_timer

local function normalize_peak(value)
    local peak = tonumber(value)
    if not peak then return nil end
    return math.floor(math.max(10, math.min(10000, peak)) + 0.5)
end

local function normalize_mode(value)
    value = tostring(value or ''):lower()
    if value == 'auto' or value == 'video' or value == 'sdr' then return value end
    return nil
end

local function label_for_peak(peak)
    if peak == 150 then return '柔和 · 150 nits' end
    if peak == 203 then return '标准 · 203 nits' end
    if peak == 250 then return '明亮 · 250 nits' end
    if peak == 300 then return '高亮 · 300 nits' end
    if peak == 400 then return '较强 · 400 nits' end
    return string.format('%d nits', peak)
end

local function label_for_mode(mode)
    if mode == 'video' then return '随视频（HDR 原生）' end
    if mode == 'sdr' then return 'SDR / sRGB' end
    return '自动判断'
end

local function core_supported()
    return mp.get_property('image-subs-colorspace', '') ~= ''
end

local function selected_track(track_type)
    for _, track in ipairs(mp.get_property_native('track-list') or {}) do
        if track.type == track_type and track.selected then return track end
    end
end

local function image_subtitle_kind(track)
    local codec = tostring(track and track.codec or ''):lower()
    if codec:find('pgs', 1, true) or codec == 'hdmv_pgs_subtitle' then return 'PGS' end
    if codec:find('vobsub', 1, true) or codec == 'dvd_subtitle' then return 'VobSub' end
    if codec:find('dvb', 1, true) then return 'DVB' end
end

local function source_is_hdr(video_track)
    local gamma = mp.get_property('video-params/gamma', ''):lower()
    if gamma == 'pq' or gamma == 'hlg' then return true end

    local profile = tonumber(video_track and video_track['dolby-vision-profile'])
    return profile ~= nil and profile > 0
end

local function source_is_uhd(video_track)
    local width = tonumber(mp.get_property_native('video-params/w'))
        or tonumber(video_track and video_track['demux-w'])
        or 0
    local height = tonumber(mp.get_property_native('video-params/h'))
        or tonumber(video_track and video_track['demux-h'])
        or 0
    return width >= 3000 and height >= 1600
end

local function resolve_mode()
    local requested = normalize_mode(o.mode) or 'auto'
    if requested ~= 'auto' then
        return requested, '手动指定'
    end

    local subtitle = selected_track('sub')
    local kind = image_subtitle_kind(subtitle)
    local video = selected_track('video')
    local hdr = source_is_hdr(video)

    -- PGS 没有可供播放器可靠判断 HDR/SDR 的标准色彩元数据。
    -- UHD HDR/DV 正片中的内封 PGS 通常按正片 PQ/BT.2020 调色板制作，
    -- 应随视频进入同一色彩管理链；外置 PGS、VobSub 与 DVB 则保守按 SDR 处理。
    if hdr and kind == 'PGS' and subtitle and not subtitle.external and source_is_uhd(video) then
        return 'video', 'UHD HDR/DV 内封 PGS'
    end
    if hdr and kind then
        return 'sdr', (subtitle and subtitle.external and 'HDR 外置 ' or 'HDR ') .. kind
    end

    return 'video', kind and ('SDR ' .. kind) or '非 HDR 或无图形字幕'
end

local function publish_state(supported, peak, requested, effective, reason)
    local effective_peak = effective == 'video' and 'video' or tostring(peak)
    mp.set_property('user-data/image-subs-brightness/supported', supported and 'yes' or 'no')
    mp.set_property_number('user-data/image-subs-brightness/peak', peak)
    mp.set_property('user-data/image-subs-brightness/label', label_for_peak(peak))
    mp.set_property('user-data/image-subs-brightness/mode', requested)
    mp.set_property('user-data/image-subs-brightness/mode-label', label_for_mode(requested))
    mp.set_property('user-data/image-subs-brightness/effective-mode', effective)
    mp.set_property('user-data/image-subs-brightness/effective-label', label_for_mode(effective))
    mp.set_property('user-data/image-subs-brightness/effective-peak', effective_peak)
    mp.set_property('user-data/image-subs-brightness/reason', reason or '')
end

local function persist_settings()
    local file = config_path and io.open(config_path, 'wb')
    if not file then
        msg.error('无法保存图形字幕设置：' .. tostring(config_path))
        return false
    end
    file:write(
        '# HDR 图形字幕色彩与参考白；仅影响 PGS/VobSub/DVB，不影响视频、ASS 或 OSD。\n'
            .. '# mode=auto 自动区分 UHD HDR/DV 内封 PGS 与 SDR 图形字幕；必要时可在菜单手动覆盖。\n'
            .. '# 通过“杳知 > HDR 图形字幕色彩与亮度”维护。\n'
            .. string.format('mode=%s\n', normalize_mode(o.mode) or 'auto')
            .. string.format('peak=%d\n', normalize_peak(o.peak) or 203)
    )
    file:close()
    return true
end

local function apply_settings(show_osd)
    local peak = normalize_peak(o.peak) or 203
    local requested = normalize_mode(o.mode) or 'auto'
    o.peak = peak
    o.mode = requested

    local supported = core_supported()
    local effective, reason = resolve_mode()

    if supported then
        local color_ok, color_err = pcall(mp.set_property, 'image-subs-colorspace', effective)
        local effective_peak = effective == 'video' and 'video' or tostring(peak)
        local peak_ok, peak_err = pcall(mp.set_property, 'image-subs-hdr-peak', effective_peak)
        if not color_ok or not peak_ok then
            supported = false
            msg.error('无法应用图形字幕设置：' .. tostring(color_err or peak_err))
        end
    end

    publish_state(supported, peak, requested, effective, reason)
    if show_osd then
        if supported then
            local mode_text = requested == 'auto'
                and string.format('自动 → %s（%s）', label_for_mode(effective), reason)
                or label_for_mode(effective)
            local peak_text = effective == 'video' and '峰值随视频' or label_for_peak(peak)
            mp.osd_message(string.format('HDR 图形字幕：%s；%s', mode_text, peak_text), 3)
        else
            mp.osd_message('当前 mpv 核心不支持独立图形字幕色彩管理', 3)
        end
    end
end

local function schedule_apply()
    if not apply_timer then
        apply_timer = mp.add_timeout(0.05, function()
            apply_timer = nil
            apply_settings(false)
        end)
    else
        apply_timer:kill()
        apply_timer:resume()
    end
end

mp.register_script_message('set', function(value)
    local peak = normalize_peak(value)
    if not peak then
        mp.osd_message('无效的图形字幕亮度', 2)
        return
    end
    o.peak = peak
    persist_settings()
    apply_settings(true)
end)

mp.register_script_message('set-mode', function(value)
    local mode = normalize_mode(value)
    if not mode then
        mp.osd_message('无效的图形字幕色彩模式', 2)
        return
    end
    o.mode = mode
    persist_settings()
    apply_settings(true)
end)

mp.observe_property('track-list', 'native', schedule_apply)
mp.observe_property('video-params', 'native', schedule_apply)
mp.register_event('file-loaded', schedule_apply)
mp.register_event('playback-restart', schedule_apply)

mp.add_timeout(0, function()
    apply_settings(false)
end)
