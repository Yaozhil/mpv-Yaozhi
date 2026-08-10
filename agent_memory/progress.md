# 当前任务进度

## 蓝光 ISO/BDMV Dolby Vision Profile 7 FEL（2026-08-10，构建前验证完成）

- 用户样片 `C:\Users\杳知\Desktop\FEL RPU_EL测试.iso` 已确认是 UHD Blu-ray：主视频 PID `0x1011` 为 HEVC HDR10/BT.2020 BL，`dv_streams[]` 中 PID `0x1015` 为 HEVC Dolby Vision EL；现有 MPEG-TS 层未形成 stream group，所以只选择 BL 并显示 HDR10。
- 历史核心 `v0.41.0-847` 至当前 `v0.41.0-853` 对同一 ISO 均未暴露 Profile 7，排除“最近双轨 MP4 补丁破坏 ISO”的回归；问题是蓝光结构关系一直没有接入 mpv。
- 方案固定为 libbluray 1.5.1 官方 `dv_streams[]` 声明，不使用分辨率、PID 范围或轨道顺序猜测。只有唯一 HEVC DV EL 与唯一 HEVC HDR10/BT.2020 主视频时才建组，歧义内容保持原行为。
- 已新增 `mpv-bluray-dovi-pair.patch`，在蓝光 stream control 暴露 BL/EL PID 关系，并在 disc demux 层建立 dependent group、标注 Profile 7；现有 MP4 stream group 路径保持不变。
- 构建固定 libbluray `065247e5ef40ccf39857db81e2c1368354a23ef8`（1.5.1），并强制清理其缓存前缀；最终二进制门禁检查 libbluray 版本和蓝光配对日志字符串。
- 已通过精确 mpv 基线 `99b4c12cccb4d8d3f72b41944cb6c640e2156650` 的补丁顺序应用、`git diff --check`、PowerShell AST 和工作流关键断言检查。

## 下一步（蓝光 FEL）

- 提交并推送 `codex/hdr-pgs-core-fix`，等待 GitHub Actions 完整交叉构建。
- 下载候选核心后先用 ISO 执行 `verify-fel.ps1 -BluRayIsoPath`，再回归三份既有 FEL 样片、普通 HDR10/SDR/音频/字幕与网络路径。
- 全部通过后备份并部署根目录核心，最后更新桌面公告；未通过前不替换正式核心。

## FFmpeg 9.0 播放能力定向回移（2026-08-04，已完成）

- 范围固定为 Animated WebP 解码/解封装和 HE-AAC 960（DAB+）解码，不迁移 FFmpeg 9.0 ABI，不引入 AMF FRC、`dovi_split` 或 SMPTE 2094-50 UI。
- 已从 FFmpeg 官方提交提取并重做 `build/ffmpeg9/ffmpeg-animated-webp-backport.patch` 与 `build/ffmpeg9/ffmpeg-he-aac-960-backport.patch`；两者在固定 `llawsxx/FFmpeg@18c01ad424ca7712ef9a9d46953308efc75c4776` 上单独及完整补丁链顺序均通过 `git apply --check`。
- Animated WebP 回归使用内嵌 188 字节、三帧 RGBA WebP：旧核心稳定因 `ANIM/ANMF` unsupported 失败；候选必须由 FFmpeg `webp_anim` demux/decoder 和 mpv 各自解出 3/3 帧。
- HE-AAC 960 门禁要求 SBR 传播 `fl960`、使用 15 个 QMF time slots，并在源代码及最终 FFmpeg 二进制中移除旧的 `SBR with 960 frame length` 未实现路径。
- 工作流已接入补丁复制/应用、二进制断言、Windows 专项脚本、Artifact 清单和缓存键；本地 PowerShell AST、YAML、完整补丁链及旧核心负对照通过。
- 首轮 CI `30915256699` 已成功编译含 `webp_anim` 且移除旧 HE-AAC 960 拒绝路径的二进制，但构建系统安装后自动还原源码，导致构建后源码检查误报；删除无效检查后，Run `30917292112` 的 `build` 与 `validate-windows` 均成功。
- 最终核心为 `mpv v0.41.0-852-g8d504e9c0`；`mpv.exe` / `mpv.com` SHA-256 分别为 `96C67204828E96C0C5823B608BFDBF9B319E71877F4559CCE4D7BE3EEC6068AD`、`275C8CC28AC7C05DEDED009B48CE75C42F92E7B5BD753BEDE299FCC76753E351`。
- 候选与部署后均通过 Animated WebP 3/3 帧、AVS2 关闭 16/16、用户 AVS2/AVS3/VVC 实片、VVC 三解码路径、AV3A native/binaural/HOA/移动对象、5.1.4 至 9.1.6 多声道及完整配置 HTTPS 回归。
- 根目录已部署新核心，旧核心备份在 `.codex-build/backups/pre-run-30917292112-core-20260804-223831/`；桌面公告已新增 `2026.8.4-3 更新`。
- 当前没有可公开取得的独立 HE-AAC 960 / DAB+ 运行时样片；现有门禁覆盖官方上游实现的完整回移、15 个 QMF time slots、最终二进制移除旧拒绝路径和编译链接，不宣称完成第三方 DAB+ 样片实播。

## 成功标准

- 静态构建固定版本 VVDEC，并由 FFmpeg 注册 `libvvdec`。
- VVC 默认选择 `libvvdec`；显式 `--vd=libvvdec` 和 `--vd=vvc` 都能解码。
- AVS2/AVS3、AV3A、HDR Vivid/PGS、字幕、多声道和网络能力回归继续通过。

## 范围边界

- 不更换现有 FFmpeg、mpv 或其他依赖分支。
- 不在完整远程构建和 Windows 验收前替换正式播放器核心。

## 当前状态

- 已新增 VVDEC 静态构建配方、最小 FFmpeg 注册/默认选择补丁和 wrapper 生命周期硬化。
- 已接入工作流依赖、缓存清理、构建断言、产物检查与三路径 VVC Windows 验收。
- 代码审查发现并修复原生回退被 experimental 阻断、allocator 双重释放、plane 引用失败悬空和 flush 重建失败后空指针调用。
- 默认选择改为调整 FFmpeg 解码器注册顺序；`libvvdec` 排在原生 `vvc` 前，两个解码器都保持可正常打开。
- 本地已通过干净固定基线补丁应用、解码器顺序、`configure` Bash 语法、YAML、嵌入 Bash/PowerShell、PowerShell 验收脚本和工作流变换模拟。

## 下一步

- 提交并推送当前分支，等待 GitHub Actions 完整交叉构建。
- 根据失败日志修正直至 build 与 validate-windows 全绿。
- 使用用户的 Tears of Steel VVC、AVS2 和 AVS3 样片做本机最终验收后再部署核心。

## 验证方式

- GitHub Actions：`Build mpv HDR PGS + AV3A + VVDEC`。
- Windows VVC：官方 FATE `CodingToolsSets_A_2.bit` 固定 SHA-256。
- 本机样片：`C:\Users\杳知\Desktop\测试视频`。
