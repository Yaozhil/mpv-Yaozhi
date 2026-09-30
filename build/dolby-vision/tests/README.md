# Dolby Vision 元数据标识验证

`0032-dovi-rpu-enhancement-metadata.patch` 只读取已有解码帧的 side data，
不扫描电影文件、不运行外部探测播放器，也不修改 BL/EL 解码、渲染和时序。

- `video-frame-info/dolby-vision-rpu-present` 表示当前 VO 帧或已配对 EL
  中检测到解码 RPU 元数据或非空 raw RPU buffer；不代表最终应用成功。
- `video-frame-info/dolby-vision-el-type` 仅在有效 P7 header 和 NLQ 同时
  存在时返回 `MEL` / `FEL`，否则 unavailable。不能用 P7、文件名或轨道数
  判断类型，也不能用 `disable_residual_flag` 二分 MEL/FEL。
- `track-list/N/dolby-vision-config-{bl,el,rpu}-present` 是本 track 的真实
  configuration record 声明，无 record 则 unavailable，已知 false 会保留。
- `track-list/N/dolby-vision-group-{bl,el}-present` 在显式有效的双成员
  Dolby Vision group 上同时为 true，其余 unavailable；不把普通双 HEVC 当
  双层。整体 group 与单个 track 的 in-band config flags 分开解释。

判定按 FFmpeg 的 P7 header 约束和 dovi_tool 的 NLQ neutral 条件：三通道
offset/slope/threshold 全为 0、vdr_in_max 全为固定点 1 时是 MEL；其它
有效 NLQ 是 FEL。FFmpeg 将整数和小数部分合并，固定点 1 是
`1ULL << coef_log2_denom`，也适用于它转换后的 float 系数。

`test-dovi-metadata.c` 使用生产 helper 覆盖系数单位、每通道非中性 NLQ、
P5/P8/非 P7、缺失 mapping、截断/越界 offsets。`test-dovi-frame-info.py`
直接抽取生产 `read_dovi_frame_info` 编译，覆盖 BL/EL fallback、raw-only、
缺失 side data 和移除 EL 后无残留状态；只替代 image 容器，不复制判定实现。

`probe-dovi-rpu.c` 链接与核心相同的 FFmpeg 静态库，实际调用
`ff_dovi_rpu_parse` / `ff_dovi_get_metadata`，再调用生产 helper。
两种核心的 Windows CI 用 `verify-dovi-rpu.py` 分别核验四个 tiny RPU fixture，
同时绑定 fixture git blob / SHA256、probe SHA256、build commit 与 variant。
这里验证元数据解析和标识，不能替代实际电影的 EL 合成或画质验收。

fixture 取自 [quietvoid/dovi_tool](https://github.com/quietvoid/dovi_tool/tree/614c816b6446dcd1dbaf433403d499a6026fbb5a/assets/tests)，
固定 commit `614c816b6446dcd1dbaf433403d499a6026fbb5a`。四文件共 1156 字节，
无电影画面；原始 MIT 许可证保留在 `fixtures/LICENSE`。身份见 `manifest.json`。

依据：[FFmpeg header/profile inference](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavcodec/dovi_rpu.c)、
[FFmpeg RPU coefficient parser](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavcodec/dovi_rpudec.c)、
[dovi_tool MEL NLQ 判定](https://github.com/quietvoid/dovi_tool/blob/614c816b6446dcd1dbaf433403d499a6026fbb5a/dolby_vision/src/rpu/rpu_data_nlq.rs)。
