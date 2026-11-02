# Rendering dependency identity gate

本轮保持已安装核心报告的 libplacebo `c9076f7cba48443ef51638361bddd5165e9a596c`。glad `0a7cf1af…` 与 fast_float `0de7a21d…` 是按上一 CI 网络更新截止时间 `2026-10-23T16:13:49Z` 从官方历史解析的本轮新冻结身份。上一轮没有保存两外部源的完整身份，因此不宣称与旧二进制精确相同。

`dependency-lock.json` 独立于历史 `source-lock.json`，固定三个完整提交、Git tree、原始构建配方 SHA、显式 Meson 选项与允许的两个子模块链接替换；不添加 libplacebo 功能补丁。其它 package/toolchain Git 依赖的有效配方、完整 SHA pin 状态和可取得的实际 HEAD/tree/status 都在每核最终回执中盘点。它们没有被冒称为“全部已固定”或“与上一核完全相同”。

执行顺序：

1. frozen round-two/network prepare 结束后调用 `prepare-dependency-lock.py --winbuild … --variant main|atmos`。它拒绝未审配方，加入固定提交、取消三个浮动 force-update hook，保留源码和构建目录，插入 before/after 编译门。
2. 缓存只使用锁文件摘要与 variant 对应的精确 key，没有旧 generation 或跨 variant restore 前缀。cache phase 拒绝无身份旧缓存或异锁/异核 marker，并强制重建三个源/prefix 和 libplacebo 静态库；workflow 全局 `PYTHONDONTWRITEBYTECODE=1`，源码门拒绝 ignored/untracked 字节码及其它额外输入。
3. before 核对实际三个 Git base/tree/逐字节源码，唯一允许 LP 的 glad/fast_float gitlink 替换成指向已锁外部源的链接；同时核实际 Meson source/build 目录、Windows x86_64 machine、cross file、编译器目标、static archive target 和每个 compile command 的来源/输出归属。保存三源完整输入包、清单、差异和构建配置。
4. after 重新核源码及编译配置，要求新编译与安装的 `libplacebo.a` 字节一致，保留真实静态库与 Ninja/安装日志。
5. final 复核上述输入和同次 invocation，确认唯一 `-o mpv.exe` link 命令和该 target 的直接输入均引用已验 `.a`；绑定新 mpv.exe/mpv.com SHA，上传 `mpv-dependency-identity-main|atmos`。这说明实际构建来源与产物的关系，不代替播放/色彩/性能回归。

`test-dependency-build-gate.py --output …` 用隔离临时仓库验证错误 base/tree、dirty/staged/untracked/ignored/链接、配置与机器归属、错误缓存、陈旧/异源静态库、错误目标链接、陈旧二进制和证据篡改拒绝。该合同中的模拟编译产物不是实际上游编译证据；真实构建必须运行 before/after/final 门并通过 Windows 播放回归后才可部署。
