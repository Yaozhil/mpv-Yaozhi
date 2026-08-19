# 问题与风险

## 多字幕轨切换即时生效（2026-08-19）

- 现象：普通本地片源切换字幕后约 20 至 30 秒才显示，手动拖动进度条会立即显示；ISO/BD 会出现约 3 至 4 秒刷新暂停。
- 根因：现有 `cache-inactive` 仅避免丢弃字幕包，未让本地或光盘 demux 启用 seekable packet cache；disc wrapper 子 lavf demux 又在打开后才知道字幕轨数量。
- 风险控制：缓存只在两条以上非封面内嵌字幕时启用，且沿用 mpv 已有缓存上限；不模拟 seek，不改 PGS 色彩/HDR/FEL/音频直通链。
- 构建失败记录：Run `32209935162` 的 `git am --3way` 会尝试下载补丁索引指定的浅克隆外 blob；去掉 `0013` 的 `index` 行后，本地 `git am --3way` 已成功。Run `32209935152` 的 `code.videolan.org` 被 runner 拒绝连接；已改用可固定的 GitHub 镜像，依赖构建脚本对两个固定提交均有三次浅拉取重试。

---

## 已知问题

- 蓝光 FEL ISO 的 libbluray DV BL/EL 依赖关系已由 v854 修复并部署；真实 ISO、正式配置入口与固定 SDR 画面对照均通过。
- VVC 默认 `libvvdec`，原生 `vvc` 保留为显式回退。
- 本机 `vvc_qsv` 探测失败，不能把硬解作为通用解决方案。

## 风险与待确认

- 蓝光 FEL 已稳定产生 `[el_pair]` 并从 EL 帧继承 Dolby Vision 元数据；后续风险仅剩不同客户显卡上的性能与硬解资源覆盖。
- 任意裸 `.m2ts` 不含 MPLS authored relation，修复范围是经 libbluray 打开的 ISO/BDMV；不会对裸 M2TS 做启发式误配。
- 尚未取得可公开复现的 HE-AAC 960 / DAB+ 样片；当前验证覆盖官方补丁完整回移、15-slot SBR 路径、最终二进制旧拒绝字符串消失和 Windows 编译链接。
- FFmpeg 9.0 能力采用定向回移；不要把当前 `libavcodec 62` 基线误记为已整体升级 FFmpeg 9.0 ABI。

## 失败尝试

- 本机缺少 CMake、Ninja 和交叉编译器，无法在 Windows 本地完成完整静态构建；改由固定 GitHub Actions 工具链验证。
- PowerShell `Invoke-WebRequest` 下载 FATE 样片时本机 TLS 失败，`curl.exe` 下载并校验 SHA-256 成功；GitHub Windows runner 仍使用现有已验证的 `Invoke-WebRequest` 路径。
- 通过把原生 `vvc` 标记为 experimental 来改变默认选择会同时破坏显式 `--vd=vvc` 回退；已改为仅调整注册顺序。
- FFmpeg 9.0 首轮 Run `30915256699` 因安装后源码被构建系统自动还原，新增源码检查误报失败；实际二进制已包含两项能力，门禁改为补丁预检、最终二进制断言和 Windows 实播后，Run `30917292112` 全绿。
- GitHub Raw HTTPS 在候选验收时多次被对端重置，旧核心同端点也复现；Microsoft HTTPS 端点在候选和部署后均由 libcurl/Schannel 成功播放到 EOF。
