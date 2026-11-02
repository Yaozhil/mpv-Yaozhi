-- Detect letterboxing encoded in local video pixels without filtering, seeking,
-- downloading GPU frames from, or delaying the playing instance.
local M = {}

function M.measure(data, width, height)
    if type(data) ~= 'string' or #data ~= width * height then return nil end
    local function dark(y)
        -- Sample across the image, excluding only the outermost 2%.
        for i = 1, 64 do
            local x = math.floor(width * (0.02 + 0.96 * (i - 1) / 63))
            if data:byte(y * width + x + 1) > 18 then return false end
        end
        return true
    end
    local top, bottom, cap = 0, 0, math.floor(height * 0.24)
    while top < cap and dark(top) do top = top + 1 end
    while bottom < cap and dark(height - bottom - 1) do bottom = bottom + 1 end
    if top == cap or bottom == cap then return nil, 'dark-frame' end
    if top < height * 0.025 or bottom < height * 0.025
        or math.abs(top - bottom) > math.max(2, height * 0.003) then return nil end
    local geometry = {top = top, bottom = bottom, height = height}
    -- A dark scene is not a border. Require spatially broad, brighter content
    -- next to both edges, and later require agreement at separate timestamps.
    local function contrast(edge, direction)
        local bright, total = 0, 0
        for j = 1, 12 do
            local y = edge + direction * math.floor(j * height * 0.002)
            for i = 1, 32 do
                local x = math.floor(width * (0.03 + 0.94 * (i - 1) / 31))
                if data:byte(y * width + x + 1) > 32 then bright = bright + 1 end
                total = total + 1
            end
        end
        return bright / total >= 0.15
    end
    if not contrast(top, 1) or not contrast(height - bottom - 1, -1) then
        return nil, 'low-contrast', geometry
    end
    return geometry
end

function M.agree(samples)
    if #samples ~= 3 then return nil end
    local lo, hi = samples[1].top, samples[1].top
    local bottom, bottom_hi = samples[1].bottom, samples[1].bottom
    for _, s in ipairs(samples) do
        if s.height ~= samples[1].height then return nil end
        lo, hi, bottom = math.min(lo, s.top), math.max(hi, s.top), math.min(bottom, s.bottom)
        bottom_hi = math.max(bottom_hi, s.bottom)
    end
    if hi - lo > 2 or bottom_hi - bottom > 2 then return nil end
    return {top = lo / samples[1].height, bottom = bottom / samples[1].height}
end

function M.measure_batch(data, width, height)
    local size = width * height
    if type(data) ~= 'string' or #data < size * 3 or #data > size * 5
        or #data % size ~= 0 then return nil, 'incomplete' end
    local samples, edges = {}, {}
    for offset = 1, #data, size do
        local measured, reason, weak = M.measure(data:sub(offset, offset + size - 1), width, height)
        local edge = measured or weak
        if edge then edges[#edges + 1] = edge end
        if measured then samples[#samples + 1] = measured
        elseif reason ~= 'low-contrast' and reason ~= 'dark-frame' then return nil, 'no-border' end
    end
    -- Check every observed edge, including dim samples and later keyframes.
    -- All independent samples retain the same geometry/contrast requirements.
    for _, edge in ipairs(edges) do
        for _, other in ipairs(edges) do
            if math.abs(edge.top - other.top) > 2 or math.abs(edge.bottom - other.bottom) > 2 then
                return nil, 'changing-geometry'
            end
        end
    end
    if #samples < 3 then return nil, 'low-contrast' end
    return M.agree({samples[1], samples[2], samples[3]})
end

function M.new(mp, utils, changed)
    local self = {value = nil}
    local generation, serial, request, timer, deadline = 0, 0
    local started, samples, cache, cache_order = false, {}, {}, {}
    local retries = 0
    local function status(state, reason)
        mp.set_property_native('user-data/uosc_danmaku/blackbar-status',
            {state = state, reason = reason, attempt = retries + 1})
    end
    local function publish(value)
        self.value = value
        mp.set_property_native('user-data/uosc_danmaku/embedded-blackbar', value or {})
        changed()
    end
    function self.reset()
        generation = generation + 1
        if timer then timer:kill(); timer = nil end
        if deadline then deadline:kill(); deadline = nil end
        if request then mp.abort_async_command(request); request = nil end
        started, samples, retries = false, {}, 0
        status('idle')
        publish(nil)
    end
    function self.start(retry)
        if started then return end
        local path = mp.get_property('path')
        local info = path and utils.file_info(path)
        local p = mp.get_property_native('video-out-params', {})
        local duration = mp.get_property_number('duration', 0)
        local position = mp.get_property_number('time-pos', 0)
        local h, w = tonumber(p.h), tonumber(p.w)
        local filters = mp.get_property_native('vf', {})
        local vid = mp.get_property_native('vid')
        -- Only bounded local files with ordinary unrotated geometry. Optical
        -- probes never open URLs, discs, devices, or another subtitle stream.
        if not info or not info.is_file or not h or not w or h < 100 or h > 8640
            or w / h > 2.1 or duration < 6 or position + 3 >= duration
            or (p.rotate or 0) ~= 0 or (p['crop-h'] or h) ~= h
            or (p['crop-w'] or w) ~= w or #filters > 0 then return end
        started = true
        local key = table.concat({path, info.size or 0, info.mtime or 0, w, h}, ':')
        if cache[key] ~= nil then status('cached'); publish(cache[key] or nil); return end
        status('pending')
        local token, index, geometry = generation, 0, nil
        -- Launch the native process directly so cancellation owns the decoder,
        -- including installations whose public EXE is now a launcher.
        local exe = mp.command_native({'expand-path', '~~/../core-builds/current/Yaoplayer.exe'})
        if not utils.file_info(exe) then
            exe = mp.command_native({'expand-path', '~~/../Yaoplayer.exe'})
        end
        if not utils.file_info(exe) then return end
        local function finish(value, reason)
            if token ~= generation then return end
            -- An inconclusive scene is not a persistent "no border" result.
            if value then
                if #cache_order >= 8 then cache[table.remove(cache_order, 1)] = nil end
                cache[key] = value; cache_order[#cache_order + 1] = key
            end
            status(value and 'confirmed' or 'unconfirmed', reason)
            publish(value)
        end
        local function retry_batch(reason)
            if token ~= generation then return end
            -- Startup I/O and the first scene can be inconclusive. Retry once
            -- at the current position, without changing contrast/agreement
            -- thresholds or extending a decoder's five-second lifetime.
            if retries >= 1 then finish(nil, reason); return end
            retries = retries + 1
            status('retry-pending', reason)
            timer = mp.add_timeout(1, function()
                timer = nil
                if token ~= generation then return end
                started = false
                self.start(true)
            end)
        end
        local function probe(batch)
            if token ~= generation then return end
            index, serial = index + 1, serial + 1
            local target = utils.join_path(os.getenv('TEMP') or '/tmp',
                string.format('uosc-blackbar-%d-%d.gray', utils.getpid(), serial))
            status('probing')
            local args = {exe, '--no-config', '--load-scripts=no', '--load-stats-overlay=no',
                '--load-auto-profiles=no', '--load-console=no', '--load-select=no',
                '--load-positioning=no', '--load-commands=no', '--load-context-menu=no',
                '--osc=no', '--ytdl=no', '--media-controls=no', '--audio=no', '--sub=no',
                '--hwdec=no', '--vd-lavc-threads=2', '--priority=belownormal',
                '--demuxer-readahead-secs=0', '--demuxer-max-bytes=1MiB',
                '--demuxer-max-back-bytes=0',
                '--start=' .. string.format('%.3f', position + (index - 1) * 1.5),
                '--frames=1', '--ovc=rawvideo', '--of=rawvideo',
                '--vf=scale=192:ih,format=gray', '--o=' .. target, '--terminal=no',
                '--msg-level=all=no', '--', path}
            if batch then
                -- One demuxer/decoder, only independent pictures. The select
                -- filter enforces distinct source times at least 1.5s apart,
                -- also for all-intra sources; never copies of one frame.
                for i, arg in ipairs(args) do
                    if arg == '--frames=1' then args[i] = '--frames=3' end
                    if arg:sub(1, 5) == '--vf=' then
                        args[i] = "--vf=lavfi=[select='isnan(prev_selected_t)+gte(t-prev_selected_t,1.5)'],scale=192:ih,format=gray"
                    end
                end
                for _, arg in ipairs({'--vd-lavc-o=skip_frame=nokey', '--hr-seek=no', '--length=30'}) do
                    table.insert(args, #args - 1, arg)
                end
            end
            if tonumber(vid) and tonumber(vid) > 0 then
                table.insert(args, #args - 1, '--vid=' .. tostring(vid))
            end
            local expired = false
            request = mp.command_native_async({name = 'subprocess', args = args,
                playback_only = true, capture_stdout = false, capture_stderr = false},
                function(ok, result)
                    local data
                    local f = io.open(target, 'rb')
                    if f then data = f:read(192 * h * (batch and 5 or 1) + 1); f:close() end
                    os.remove(target)
                    if token ~= generation then return end
                    request = nil
                    if deadline then deadline:kill(); deadline = nil end
                    if batch then
                        -- Do not add another decoding pass after exhausting
                        -- the time budget while playback is under pressure.
                        if expired then retry_batch('timeout'); return end
                        local value, reason
                        if not expired and ok and result and result.status == 0 then
                            value, reason = M.measure_batch(data, 192, h)
                        end
                        if value or reason == 'no-border' or reason == 'changing-geometry' then finish(value); return end
                        if reason == 'low-contrast' then retry_batch(reason); return end
                        -- Codecs without keyframe skipping or short remaining
                        -- segments retain the original bounded sampling path.
                        index = 0
                        timer = mp.add_timeout(0.15, function() probe(false) end)
                        return
                    end
                    if expired or not ok or not result or result.status ~= 0 then
                        finish(nil); return
                    end
                    local measured, reason, weak_geometry = M.measure(data, 192, h)
                    local candidate = measured or weak_geometry
                    if candidate then
                        -- Even a dim edge must agree with the other observed
                        -- edges. Never discard conflicting geometry as jitter.
                        if geometry then
                            geometry.top_min = math.min(geometry.top_min, candidate.top)
                            geometry.top_max = math.max(geometry.top_max, candidate.top)
                            geometry.bottom_min = math.min(geometry.bottom_min, candidate.bottom)
                            geometry.bottom_max = math.max(geometry.bottom_max, candidate.bottom)
                            if geometry.top_max - geometry.top_min > 2
                                or geometry.bottom_max - geometry.bottom_min > 2 then
                                finish(nil); return
                            end
                        else
                            geometry = {top_min=candidate.top, top_max=candidate.top,
                                bottom_min=candidate.bottom, bottom_max=candidate.bottom}
                        end
                    end
                    if measured then samples[#samples + 1] = measured
                    elseif reason ~= 'low-contrast' and reason ~= 'dark-frame' then
                        finish(nil); return
                    end
                    if #samples == 3 then finish(M.agree(samples))
                    elseif index < 5 and position + index * 1.5 < duration then
                        timer = mp.add_timeout(0.15, probe)
                    else finish(nil) end
                end)
            deadline = mp.add_timeout(5, function()
                expired = true
                if request then mp.abort_async_command(request) end
            end)
        end
        timer = mp.add_timeout(retry == true and 0 or 0.75, function() probe(true) end)
    end
    return self
end

return M
