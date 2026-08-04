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

## 已确认假设

- 固定 FFmpeg 基线的 `cbs_h266` 与 VVCEasy wrapper 所需接口兼容。
- `libvvdec.c` 使用现有 CBS H.266 解析，不需要 Martin 分支遗留的独立 VVC 参数集解析文件。
