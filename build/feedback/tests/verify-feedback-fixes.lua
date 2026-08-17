package.path = 'portable_config/script-modules/?.lua;' .. package.path

local url_list = require 'url-list'
local bounds = require 'startup-logo-bounds'
local media_format = require 'media-format-info'

local function assert_equal(actual, expected, label)
    if actual ~= expected then
        error(string.format('%s: expected %s, got %s', label, tostring(expected), tostring(actual)))
    end
end

local single = assert(url_list.parse('https://example.com/a.m3u8'))
assert_equal(#single, 1, 'single URL count')

local playlist = assert(url_list.parse('\239\187\191#EXTM3U\r\n#EXTINF:-1,A\r\nhttps://example.com/a\r\nhttps://example.com/b\r\nhttps://example.com/a'))
assert_equal(#playlist, 2, 'M3U URL count')
assert_equal(playlist[2], 'https://example.com/b', 'M3U order')

local invalid, invalid_error = url_list.parse('https://example.com/a\nlocal-file.mkv')
assert_equal(invalid, nil, 'mixed invalid URL list')
assert(invalid_error:find('非 HTTP%(S%)'))

local hls, hls_error = url_list.parse('#EXTM3U\n#EXT-X-TARGETDURATION:6\nsegment001.ts')
assert_equal(hls, nil, 'HLS manifest body')
assert(hls_error:find('HLS'))

local function make_frame(width, height, top, bottom, left, right)
    local rows = {}
    local black = string.char(0, 0, 0, 0)
    local bright = string.char(96, 112, 128, 0)
    for y = 0, height - 1 do
        local row = {}
        for x = 0, width - 1 do
            local is_bar = y < top or y >= height - bottom or x < left or x >= width - right
            row[#row + 1] = is_bar and black or bright
        end
        rows[#rows + 1] = table.concat(row)
    end
    return {format = 'bgr0', w = width, h = height, stride = width * 4, data = table.concat(rows)}
end

local letterbox, letterbox_meaningful, letterbox_coverage = bounds.detect(
    make_frame(640, 360, 70, 70, 0, 0), 16
)
assert(letterbox)
assert_equal(letterbox_meaningful, true, 'letterbox meaningful frame')
assert(letterbox_coverage > 0.40)
assert(math.abs(letterbox.top - 70 / 360) < 0.004)
assert(math.abs(letterbox.bottom - 70 / 360) < 0.004)

local pillarbox = assert(bounds.detect(make_frame(640, 360, 0, 0, 90, 90), 16))
assert(math.abs(pillarbox.left - 90 / 640) < 0.004)
assert(math.abs(pillarbox.right - 90 / 640) < 0.004)

local no_bars, full_meaningful, full_coverage = bounds.detect(
    make_frame(640, 360, 0, 0, 0, 0), 16
)
assert_equal(no_bars, nil, 'no encoded bars')
assert_equal(full_meaningful, true, 'full-frame content meaningful')
assert(full_coverage > 0.95)

local black_bars, black_meaningful, black_coverage = bounds.detect(
    make_frame(640, 360, 360, 0, 0, 0), 16
)
assert_equal(black_bars, nil, 'full black frame')
assert_equal(black_meaningful, false, 'full black frame ambiguous')
assert_equal(black_coverage, 0, 'full black coverage')
assert_equal(bounds.detect(make_frame(640, 360, 70, 0, 0, 0), 16), nil, 'asymmetric dark edge')

local function make_sparse_frame(width, height, x1, y1, x2, y2)
    local rows = {}
    local black = string.char(0, 0, 0, 0)
    local bright = string.char(96, 112, 128, 0)
    for y = 0, height - 1 do
        local row = {}
        for x = 0, width - 1 do
            local is_detail = x >= x1 and x < x2 and y >= y1 and y < y2
            row[#row + 1] = is_detail and bright or black
        end
        rows[#rows + 1] = table.concat(row)
    end
    return {format = 'bgr0', w = width, h = height, stride = width * 4, data = table.concat(rows)}
end

local sparse_insets, sparse_meaningful, sparse_coverage = bounds.detect(
    make_sparse_frame(640, 360, 220, 100, 420, 260), 16
)
assert(sparse_insets, 'sparse centered logo can geometrically resemble black bars')
assert_equal(sparse_meaningful, false, 'sparse centered logo must not move the badge')
assert(sparse_coverage < 0.28)

local merged = assert(bounds.merge({
    {left = 0, top = 0.10, right = 0, bottom = 0.10},
    {left = 0, top = 0.12, right = 0, bottom = 0.12},
    {left = 0, top = 0.50, right = 0, bottom = 0.50},
}))
assert_equal(merged.top, 0.12, 'multi-frame median')

assert_equal(bounds.merge_stable({
    {left = 0, top = 0.10, right = 0, bottom = 0.10},
}, 2, 0.012), nil, 'single probe cannot lock badge anchor')

local stable = assert(bounds.merge_stable({
    {left = 0, top = 0.100, right = 0, bottom = 0.100},
    {left = 0, top = 0.106, right = 0, bottom = 0.106},
    {left = 0, top = 0.180, right = 0, bottom = 0.180},
}, 2, 0.012))
assert(math.abs(stable.top - 0.103) < 0.001, 'two consistent probes lock their median')

assert_equal(bounds.merge_stable({
    {left = 0, top = 0.10, right = 0, bottom = 0.10},
    {left = 0, top = 0.18, right = 0, bottom = 0.18},
}, 2, 0.012), nil, 'conflicting probes cannot lock badge anchor')

local progressive = media_format.from_snapshot({
    video_params = {w = 1920, h = 1080},
    video_frame_info = {interlaced = false},
})
assert_equal(progressive.resolution_long, '1080P', '1080 progressive label')

local interlaced = media_format.from_snapshot({
    video_params = {w = 1920, h = 1080},
    video_frame_info = {interlaced = true},
})
assert_equal(interlaced.resolution_long, '1080i', '1080 interlaced label')

print('feedback Lua regression checks passed')
if mp and mp.commandv then mp.commandv('quit') end
