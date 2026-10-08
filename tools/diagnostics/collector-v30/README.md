# V30 独立 PresentMon 启动缓冲区诊断构建准备

## 当前结论与边界

本目录只准备本任务诊断工具，未编译、未远程 dispatch、未启动 ETW/GPU/播放器；不修改产品核心、config-v29、旧采集器或任何现有会话。原因是旧采集器第一次 QUERY 前已丢 1,898 个事件，运行后增加 MaximumBuffers 无法补回已缺失的事件。原失败证据保持。

官方源固定为 `GameTechDev/PresentMon` 的 `v2.3.1`，完整提交 `717c5bf14e80a4a06b70cd16415ae8d40a7ce201`。本机下载的[官方 release 页面](https://github.com/GameTechDev/PresentMon/releases/tag/v2.3.1)实际包含该完整 commit 链接；full-commit raw 源与此前 tag raw 源 SHA 一致。未认证 API 遇到限流、本机 `git ls-remote` 无输出后取消，均未用作成功证据。runner 仍须独立检查 `HEAD` 和 `refs/tags/v2.3.1^{commit}`。

唯一代码补丁在 [`PresentData/PresentMonTraceSession.cpp`](https://github.com/GameTechDev/PresentMon/blob/717c5bf14e80a4a06b70cd16415ae8d40a7ce201/PresentData/PresentMonTraceSession.cpp) 的实时会话分支、`StartTraceW` 调用前新增：

```cpp
sessionProps.MinimumBuffers = 128;
sessionProps.MaximumBuffers = 512;
```

原 `BufferSize=0`、QPC clock、provider/filter、Ready/Display 解释与 CSV 全部保持。`start-buffers-only.patch` 是 +2/-0；去除这两行后完整源字节与原文件一致。原 cpp SHA 为 `e4dfe92174d0ee5d2f3bef139722f0c1a92d19e3f2060658aee1f66fa1fb7c06`；补丁 SHA 为 `d82ee11f068957c419473083a861c4282d6ab0be8abee8d31bd2aafd4a756f8b`。

## 文件与构建方式

- `source-pins.json`：官方下载源、release 页面、补丁前后 SHA。
- `apply-start-buffers.py`：拒绝任意原源变动、重复 patch、补丁字节变动；只写新 runner 的隔离源目录。
- `build-collector-v30.ps1`：一次新的 Windows x64、VS2022 CPU 构建，输出到新 WorkRoot，已有目录拒绝使用。
- `build-collector-v30.yml`：仅供 root 审核的个人仓库 workflow 草案，尚未放入 `.github/workflows/`。
- `verify-start-props.cpp`、`verify-compiled-probes.py`：编译后的真实属性构造与 CLI 检查，尚未实际执行。
- `owned-capture-contract.json`：后续 root OwnJob 实采的接口边界，不是可运行采集入口。
- `cpu-preparation.json`：本轮本地准备结果，明确编译/实采仍 pending。

[官方 BUILDING](https://github.com/GameTechDev/PresentMon/blob/717c5bf14e80a4a06b70cd16415ae8d40a7ce201/BUILDING.md)称 console-only 可用 `PresentMon/ConsoleApplication.sln`、只需 VS。但该 tag 的 PresentMon/PresentData 工程实际引用整个 CommonUtilities，后者引入 vcpkg 的广泛依赖；本准备包没有据此修改官方工程或拉取 GUI/service。隔离构建直接编译两个官方工程的全部源单元，外加它们实际使用的官方 `Hash.cpp` 实现：5 个 PresentData、7 个 console、1 个 Hash；原文件与项目保持。使用 Release 级 `/O2 /MT`、原 console C++17/PresentData C++latest、原 Win32 target definitions，记录完整命令。此构建策略尚待 runner 的 MSVC 实编验证，不能称官方发布二进制的构建参数完全一致。

`Launch-VsDevShell.ps1 -Arch amd64 -HostArch amd64 -SkipAutomaticLocation` 来自[微软官方开发 shell 文档](https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell?view=vs-2022)。不安装 SDK/CMake/Node/WiX/vcpkg，不注册 service 或证书。

## root 审核后的可逆路径

1. 将本目录工具文件作为独立临时 tools commit 的 `tools/diagnostics/collector-v30/`，草案放独立构建分支 workflow；不修改冻结 config-v29，不创建 PR 或 formal release。
2. root 审核完整 tools SHA 后自行 dispatch。`tools_ref` 必须是 40 位 SHA，仓库必须是 `Yaozhil/mpv-Yaozhi`；read-only GitHub 权限，无凭据持久化。
3. runner 新目录是 `${RUNNER_TEMP}/collector-v30-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`。先下载官方 tag，完整 commit/clean 源检查，应用两行 patch，再 MSVC 构建。失败日志照常上传，不能用只有 artifact 存在来宣布构建成功。
4. 预期成功 artifact 内有独立 `PresentMon-2.3.1-v30-buffers-x64.exe`、两只 props probe、`patch-receipt.json`、`compiled-check.json`、`build-receipt.json` 与所有日志。root 下载到新的任务工具目录，核 SHA 后再准备独立采集 runner；旧 `PresentMon-2.3.1-x64.exe` 不替换。
5. 本轮没有本机安装或会话需要回滚。远程临时分支/工作流和 artifact 均可由 root 事后移除；本地新增目录也只包含工具与证据。本脚本不执行递归删除，runner 临时目录由独立 job 生命周期释放。

## 编译后应实际验证的内容

官方 `--help` 在 parser 阶段打印 `PresentMon 2.3.1`，退出码 1；该 tag **没有 `--version`**，运行它应保留“unrecognized option”和同版本 banner，退出码 1，不增造新 CLI。两者都在原 `PMTraceSession::Start` 前退出，源码路径已读核；实际二进制行为仍 pending。

props probe 包含真正的官方 `PMTraceSession::Start` 源码，分别用原源和改源。只在独立 probe 翻译单元将首次 `StartTraceW` 重定向到 hook，复制属性并返回 `ERROR_ACCESS_DENIED`；后续 provider/trace/Stop 代码不会执行。不是手写镜像属性构造，也没有给生产诊断 exe 增加 hook。实编后的期望：WNODE 48 字节、EVENT_TRACE_PROPERTIES 120 字节、属性含 session name 总分配 640 字节；两次原始 120 字节比较仅 offset 52/56 的两个 ULONG 从 0/0 改为 128/512，其余逐字节相同。

本机当前只有 Python/PowerShell AST 与真实 patch 源检查通过；没有 MSVC/Windows SDK，因此不能在此宣布 probe、编译或 ETW 实机通过。

## 后续实采边界与未验证风险

root 独立核工件后，仍使用一个新的 OwnJob player PID、fresh UUID4 session、32 秒 capture、2 秒 flush、45 秒父 job 绝对界；argv 除新 binary SHA/path 和 session 前缀外沿用旧采集参数，继续保留 `--no_track_input`，不改变 Display/GPU tracking 或 CSV。禁止任何 stop/terminate-existing、restart-as-admin、UPDATE、其它 PID 或产品交付。

128/512 是调用时请求值，Windows 可以按系统条件调整实际池；必须只 QUERY 自有 UUID/handle，记录实际 Minimum/Maximum/NumberOfBuffers、mode/clock 和 startup/exit 的 EventsLost/LogBuffersLost/RealTimeBuffersLost。未知 flags 或仍丢事件应如实保留失败，不能修改 CSV 或阈值补救；本准备包不处理现有 helper 身份与 effective-mode 守卫，root 需在新采集器派生目录独立审查。

扩大池可能增加 ETW 内存开销；当前保留 `BufferSize=0`，实际每 buffer 大小未知，不能承诺已消除丢事件。是否仍有 collector loss、32 秒是否完整、真实 Ready/Display 身份关联、frame pacing/phase 是否达原验收线，都须新独立实机证据。本工具构建成功也不等于播放器流畅通过，不触发 V29/V30 用户入口或公告交付。
