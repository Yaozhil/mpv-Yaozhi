# 问题与风险

## 已知问题

- 当前已部署核心只有 FFmpeg 原生 `vvc` 软件解码，Tears of Steel VVC 样片效率偏低。
- 本机 `vvc_qsv` 探测失败，不能把硬解作为通用解决方案。

## 风险与待确认

- VVDEC 3.3.0-dev 与固定 MinGW 工具链的完整静态链接仍需远程构建确认。
- `libvvdec` wrapper 来自外部分支，已做边界、单一所有权清理、引用失败、空 decoder、时间戳和 HDR 元数据硬化，但仍需真实样片长时间播放验证。
- AVS2 修复尚未完成最终部署验收，VVC 改动不得绕过现有 AVS2/AVS3 回归。

## 失败尝试

- 本机缺少 CMake、Ninja 和交叉编译器，无法在 Windows 本地完成完整静态构建；改由固定 GitHub Actions 工具链验证。
- PowerShell `Invoke-WebRequest` 下载 FATE 样片时本机 TLS 失败，`curl.exe` 下载并校验 SHA-256 成功；GitHub Windows runner 仍使用现有已验证的 `Invoke-WebRequest` 路径。
- 通过把原生 `vvc` 标记为 experimental 来改变默认选择会同时破坏显式 `--vd=vvc` 回退；已改为仅调整注册顺序。
