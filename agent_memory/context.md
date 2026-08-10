# 项目上下文

## 项目概览

- 本仓库维护杳知版 Windows mpv 配置、补丁和可复现构建工作流。
- 当前维护分支为 `codex/hdr-pgs-core-fix`，固定使用带 AVS2/AVS3 与 AV3A 支持的 `llawsxx/FFmpeg`。

## 关键约定

- 不直接替换为其他完整 FFmpeg 分支；新增能力必须最小回移，保留 AVS2/AVS3、AV3A、HDR PGS、字幕与多声道补丁链。
- 新核心只有在 GitHub Actions 构建和 Windows 样片回归全部通过后才能部署到整合包根目录。
- VVC 默认软件解码器使用 `libvvdec`，FFmpeg 原生 `vvc` 必须保留为显式回退。

## 重要文件与入口

- `.github/workflows/build-mpv-hdr-pgs.yml`：Windows 静态 mpv 构建与回归入口。
- `build/vvc/`：VVDEC 构建配方、FFmpeg wrapper、默认选择补丁和 Windows 验收脚本。
- `build/av3a/`：AV3A、AVS2 及空间音频补丁链。
- `build/ffmpeg9/`：从 FFmpeg 9.0 定向回移的 Animated WebP、HE-AAC 960 补丁及 Windows 播放验收脚本；不代表整套基线升级到 libavcodec 63。
- `build/dolby-vision/`：单轨 FEL、MP4 双轨 FEL 及蓝光 ISO/BDMV Profile 7 BL/EL 配对补丁与验收脚本。

## 当前发布核心

- GitHub Actions Run `31328067629` 全绿，根目录已部署 `mpv v0.41.0-853-g413f9a86b`。
- `mpv.exe` / `mpv.com` SHA-256 为 `DD91331B157A4FC8791D26318AF4B6956D2D967D1D43AB738950D7CA018DF975`、`788B21D785369728D5F6E780EBB7962DF80C63B6905466BA21464B459F46FCFB`。
- 当前核心已支持单轨 FEL 和带 `vdep` 的 MP4 双轨 FEL；蓝光 ISO/BDMV 双轨 FEL 修复正在构建验收，尚未部署。

## 已确认假设

- 固定 FFmpeg 基线的 `cbs_h266` 与 VVCEasy wrapper 所需接口兼容。
- `libvvdec.c` 使用现有 CBS H.266 解析，不需要 Martin 分支遗留的独立 VVC 参数集解析文件。
