# 主核心与 Atmos 功能对齐候选

状态：已获用户授权推送候选并运行 CI，不发布 Release。正在编译验证；尚未替换 Atmos。根目录 `mpv-Atmos.exe` 是启动器，真实播放器在 `portable_config/experimental/omniphony/`。

目前侧车为 2026-08-20 的 v0.41.0-925，主核心为 2026-09-04 的 v0.41.0-1027。实际启用功能清单证实侧车缺少 VapourSynth、SMTC、libcurl 和 LuaJIT 等主核心能力，不能只升级版本字样。

候选使用同一个 c318236 基点、完整 17 项主核心补丁和原有依赖构建流程；Atmos 在其上增加官方 mpv-omniphony 的 0001–0028 补丁、orender 0.5.2 和 ASIO。蓝光扩展 IG PID 源码补丁同时用于两种核心。哈希、提交和来源见 `source-lock.json`。

上游 9001 音频重排补丁与主核心现有实现重叠。保留主核心同时处理 native_equal_layout 及输入/输出 unknown 布局的逻辑，避免只改一端布局引入声道交换。0012、0015 的临时回退枚举整合保留了主核心额外硬解表面控制项。

共同补丁 `0005-hdmv-overlay-video-ready.patch` 针对实测新按钮叠在旧片头/黑底的时序：动态 HDMV 菜单在跳转刷新与首帧未就绪时暂缓图形显示；不增加固定等待，不延迟导航输入，静帧和 BD-J 保留既有行为。源码应用检查通过，仍须新核心实盘验证后部署。

首轮 orender 构建因上游不含 Cargo.lock、直接 `--locked` 无法创建锁而失败。第二轮成功生成并构建；其 Cargo.lock 已固定为 orender-Cargo.lock，后续直接复制并锁定构建。已验证引擎 ABI0.7、现有桥v0.7.4、普通AC-3以及Dolby官方E-AC-3 JOC对象音频输出与重置；播放器整体验收仍待完成。

0005 已转换为实际构建器需要的 mailbox 格式，并在全新源码上按 CI 的 `git am --3way` 顺序验证（17主补丁、0005、Atmos delta）。普通 unified diff 的 `git apply` 成功不等于 mailbox 构建器可接收。

第三轮两个播放器构建都停在 libvpl：未定义 `_MSC_VER` 被误判为旧 MSVC，兼容宏破坏 MinGW 的 `stralign.h` 表达式。共同依赖固定为 `674d015bcb294bc39fa276e99a652ea045423e82`，仅将旧编译器宏限定到实际 MSVC；保留 Intel 硬解依赖。源码补丁应用与两个变体的依赖配置检查通过，待 CI 编译验证。失败后的缓存保存也已修正：`actions/cache` 不提供 `cache-primary-key` 输出，现与恢复步骤使用完全相同的显式键；之前两次保存实际未写入缓存。

构建完成后的最低安装条件：

- 两种变体均通过主核心原有完整功能门、AV3A/空间声道/FEL 验证。
- Atmos 额外检查 orender/ASIO、ABI 握手、缺引擎回退、旧桥接兼容与真实空间音频。
- 两种核心复测反馈 ISO 的按钮/章节/返回、HAG、普通文件、脚本与插件，以及菜单退出后的 SDR 状态。
- 使用独立候选目录和逐文件哈希预检安装，保留原主核心、侧车、引擎与启动器回滚；未完成这些步骤不更新现用 Atmos 或公告。

来源：[mpv-omniphony](https://github.com/mgth/mpv-omniphony/tree/6b474e387d30fabec8927880a25075f288d675d3)、[Omniphony v0.5.2](https://github.com/mgth/Omniphony/tree/f9a79721af64ad9c39042d4deded158b568fc598)、[ASIO SDK](https://github.com/audiosdk/asio/tree/496a0765b8bb9c26f764f22f9a9712a937177db2)。保留原作者版权和所需许可文本。
