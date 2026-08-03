# mpv 图形字幕 HDR 颜色修复

## 修复范围

`0001-vo_gpu_next-add-image-subtitle-colorspace-control.patch` 基于当前发行版
`mpv v0.41.0-846-g99b4c12cc`，只修改 `vo=gpu-next` 的
`SUBBITMAP_BGRA` overlay。它覆盖 PGS、VobSub、DVB 等图形字幕，不修改：

- 视频帧及 Dolby Vision Profile 5/7/8 处理；
- ASS、SSA、SRT 等文本字幕；
- OSD、音频、硬件解码、着色器或 HDR 显示切换。

## 新增选项

`image-subs-colorspace=<video|sdr|auto>`

- `video`：保留上游行为，图形字幕继承视频颜色空间。
- `sdr`：图形字幕始终按 SDR sRGB、203 nit 参考白解释。
- `auto`：HDR/PQ/HLG/Dolby Vision 视频使用 SDR sRGB；SDR 视频保留上游行为。

上游兼容默认值为 `video`。由于 PGS 码流没有可靠的 HDR/SDR 色彩元数据，
本配置包不再把所有 HDR 图形字幕固定到同一种解释方式，而由
`image-subs-brightness.lua` 在 `video` 与 `sdr` 之间自适应选择：

- UHD HDR/Dolby Vision 正片中的内封 PGS：使用 `video`，随视频进入同一 HDR 映射链；
- HDR 下的外置 PGS、VobSub、DVB：使用 `sdr`；
- SDR 视频：保持 `video` 上游行为。

右键菜单提供“自动判断 / 随视频（HDR 原生）/ SDR·sRGB”手动覆盖，处理
调色板制作不规范或封装来源不明的 DIY 字幕。

`image-subs-hdr-peak=<sdr|video|video-static|video-dynamic|10-10000>`

- `video` 路径必须使用 `video`，完整保留正片 HDR 元数据，不能再被
  203 nit 等 SDR 参考白覆盖。
- 在 `auto` 选择到 `sdr` 或手动 `sdr` 的 SDR sRGB 路径中，数值档位
  独立控制图形字幕参考白亮度。
- `sdr` 或 `203` 为标准 SDR 白；数值档位不会改变字幕色相、色域或视频输出。
- `video`、`video-static`、`video-dynamic` 在 SDR sRGB 路径中安全回退到 203 nit。

本配置包核心默认使用 `video`；脚本只在 SDR 图形字幕路径应用持久化的
150/203/250/300/400 nit 档位。该设置只影响 PGS、VobSub、DVB 等图形
字幕，不影响 ASS、文本字幕、OSD 或视频。

## 验收矩阵

| 场景 | 预期结果 |
| --- | --- |
| UHD HDR/Dolby Vision + 内封 PGS | 视频维持 `gpu-next`，PGS 随视频进入同一 HDR 映射链 |
| HDR + 外置/SDR 图形字幕 | 图形字幕按 SDR/sRGB 合成，必要时可手动覆盖 |
| HDR/Dolby Vision + PGS 亮度切换 | 色相保持不变，仅参考白亮度随档位变化 |
| Dolby Vision Profile 5 | 不切换 `vo=gpu`，视频不得绿/紫偏色 |
| SDR + PGS | 与上游现有显示一致 |
| HDR 转 SDR | 视频色调映射不变，内封 UHD PGS 与视频使用同一映射；SDR 图形字幕单独处理 |
| SDR 强制输出 HDR | 视频处理不变，图形字幕不继承伪造的 HDR 传输 |
| ASS/文本字幕 | 与当前已修复的 ASS 配置一致 |
| 无图形字幕 | 与未打补丁版本逐帧一致 |

## WASAPI 高度声道布局修复

`0002-ao-wasapi-preserve-height-channel-layouts.patch` 修复 mpv 的 Windows
WASAPI 后端在探测前把所有大于 8 声道的 PCM 布局无条件压成 7.1 的问题。

- 对可由 32 位 `WAVEFORMATEXTENSIBLE.dwChannelMask` 表达的 5.1.4、7.1.4
  等布局，先按原布局调用 `IAudioClient::IsFormatSupported`。
- 共享模式设备拒绝原布局时，仍使用既有的设备混音格式回退。
- 独占模式设备拒绝原布局时，仍使用既有的标准布局搜索回退。
- 只有声道掩码确实超出 `WAVEFORMATEXTENSIBLE` 表达范围时，才沿用旧的
  7.1 兜底。

该问题位于音频输出层，与 AV3A、Opus、WavPack 等编码格式无关。

`0003-sdl2-wasapi-spatial-speaker-mask.patch` 修复静态链接 SDL2 的 Windows
WASAPI 后端。SDL2 的公开音频接口只向 mpv 返回声道数，无法传递大于 8
声道的完整扬声器语义；本补丁在打开 10/12 声道端点时补全对应的
`WAVEFORMATEXTENSIBLE.dwChannelMask`：

- 10 声道：`FL FR FC LFE SL SR TFL TFR TBL TBR`；
- 12 声道：`FL FR FC LFE BL BR SL SR TFL TFR TBL TBR`。

`0005-ao-sdl-preserve-spatial-channel-layouts.patch` 补齐 mpv 的 SDL 输出协商：
显式允许上述 10/12 声道布局，避免 mpv 先把空间声道折叠成 7.1、SDL 再按
设备声道数扩展，造成高度声道落入基础层或后顶声道静音。该补丁与 SDL2
扬声器掩码补丁配套，保证 5.1.4/7.1.4 PCM 从音频滤镜到 Windows 端点按
同一 `WAVEFORMATEXTENSIBLE` 顺序传递。

`0006-sdl2-allow-spatial-channel-counts.patch` 补齐 SDL2 公共音频入口：只放行
本项目已定义扬声器语义的 10/12 声道，避免 `prepare_audiospec()` 在进入
WASAPI 前以 `Unsupported number of audio channels` 拒绝；其他大于 8 声道
的非标准数量仍保持上游拒绝策略。

`0007-swresample-use-native-canonical-input-layout.patch` 修复多声道 planar PCM
转 packed PCM 时的通道语义丢失。旧逻辑只要输入输出布局相同，就先把双方
改成 `unknownN`；随后 libswresample 收到“未知输入 + native 输出”，可能按
另一套默认布局解释输入平面，导致 WV/Opus 等 planar 解码输出错位、静音或
初始化失败。

- 5.1.4、7.1.4、9.1.4 等 FFmpeg 标准位序布局使用 native mask；
- 输入输出相同的非标准位序布局继续使用输入/输出对称的 unspecified layout，
  按位置保序，避免没有前方声道的 custom 布局触发 libswresample 重矩阵失败；
- 只有确实需要改变位序时才沿用既有 custom layout 与标签重排路径；
- 对象、HOA、`NA` 和真正未知的 transport channels 同样使用输入/输出对称的
  unspecified layout，不再伪造默认 native 输出 mask；
- 逻辑只依据解码后的声道标签，不按 WV、WAV、Opus、AV3A 等格式名写死。

项目把 9.1.6 作为扬声器集合基准，并按标签做子集：

| 布局 | 扬声器集合 |
| --- | --- |
| 9.1.6 | `FL FR FC LFE BL BR SL SR TFL TFR TBL TBR TSL TSR WL WR` |
| 9.1.4 | 9.1.6 移除 `WL WR` |
| 7.1.4 | 9.1.6 移除 `TSL TSR WL WR` |
| 5.1.4 | `FL FR FC LFE SL SR TFL TFR TBL TBR` |

该表用于集合适配，不用于假定所有容器和 API 的物理索引。FFmpeg/native mask
会按扬声器 ID 排序，例如 9.1.6 的 native PCM 位序中 `WL WR` 位于
`TSL TSR` 之前；代码必须按标签映射，不能按“第 13/14/15/16 声道”做减法。

Windows `WAVEFORMATEXTENSIBLE.dwChannelMask` 只有 32 位，无法精确表达
`TSL/TSR`。因此 9.1.4/9.1.6 当前保证解码、滤镜和 `ao=pcm` 导出阶段保序，
但不伪装成可无歧义路由的普通 WASAPI/HDMI 扬声器布局；5.1.4/7.1.4 则继续
由现有 WASAPI/SDL 补丁精确输出。Opus mapping family 255 同样只有位置顺序、
没有扬声器语义，必须由容器或用户显式提供布局，禁止仅凭 10/12/14/16 声道数
自动猜测。

WavPack v4 的高位 speaker metadata 也有同类限制：5.1.4/7.1.4 可保存精确
布局，但包含 `TSL/TSR` 的 14/16 声道文件可能被 FFmpeg 解释为带
`FLC/FRC` 的默认 9.1.4/9.1.6 别名，或只保留“未分配声道”。播放器会按文件
实际声明保序，不会把错误/缺失元数据自动猜成项目布局；这类文件需要在制作时
保留可靠布局元数据，或由用户显式提供通道解释。

12 声道路由不再由 Lua 改成 10 声道，也不执行额外的 `ao-reload`。输入 PCM
按上述 12 个位置原样交给端点；若设备或驱动拒绝该格式，由 AO 自身按既有
规则回退，而不是静默改变声道数量。

## HDR Vivid 元数据识别

`0004-video-expose-hdr-vivid-metadata.patch` 保留 FFmpeg 已解析并附加到解码帧的
`AV_FRAME_DATA_DYNAMIC_HDR_VIVID` 存在状态，并将其公开为只读的
`video-params/hdr-vivid` 属性。起播格式标签和 uosc 媒体参数据此识别
HDR Vivid，不再只依赖文件名猜测。

该属性只表示当前解码帧携带 HDR Vivid 动态元数据；本补丁不实现动态元数据
渲染、色调映射或显示端透传。
