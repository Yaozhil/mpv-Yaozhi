# 当前任务进度

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
