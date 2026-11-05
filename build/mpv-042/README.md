# mpv-Yaozhi 0.42 双核迁移输入

正式基底：mpv v0.42.0，`b0841e8c4d156b8403dc1876c4cbd9011eb583f3`。
本目录为独立候选构建资料，不会自动安装、改产品版本或发布发行包。

## 本轮收益与验收

| 范围 | 预期行为 | 交付门槛 |
| --- | --- | --- |
| 嵌套 HLS 失败清理 | 打开失败后正常恢复，避免旧核隔离测试的访问冲突 | 同次 FFmpeg 五回调 Windows probe，双核真实 HLS 失败／取消／拖动退出 |
| HTTP Range 重试 | 有传输进度时重置连续失败预算，同时保留无进度有限停止 | 同一个 oracle 验证 6 次请求完整 20603B、无进度 3 次停止 |
| HDR BT.2390 | 迁移新 gpu-next knee-offset 接口，延续原有调校 | 双核真实参数 apply／copy-equal restore／显式 CLI 优先；没有实屏对比不声称画质提升 |
| 原有自编能力 | 保 Native0065、AV3A 对象与四预选及输出、VC1、PGS、Disc／DV、Atmos／ASIO | 58／59 包逐项账本、832 原 hunk 对照、真实候选专项回归 |

不因升级启用新 scRGB／AMF／DoP、补帧或其它未验证默认设置。
能力保留属于防退化，不能算新优化；源码或编译检查也不能代替播放验收。

## 构建约束

- `migration-lock.json` 锁定完整源码树、整合 binary diff、旧补丁集合与全部输入。
- `prepare-winbuild.py` 先核旧完整 58／59 包，再替换为正式基底与精确源码层。
- 70 个依赖 overlay／核固定既有基线；保留私补，不跟踪今天的浮动分支。
- `cleanup` 的固定 pin 脚本只核祖先关系，不 fetch／reset，也不撤销 Git-am 私补。
- 真实 Ninja 图、MinGW 全部 13 个已确认生成文件（历史六项加当前 Autotools 新生成七项）和 fresh CRT、FFmpeg demux.o 与静态 archive、实际最终链接逐层绑定。
- 历史构建配方／门禁保持原件；使用新工作流和独立分支，构建非零退出即阻断。
- `package.py` 绑定本次 CI 的 variant、锁、source／dependency 收据及验证工具 SHA。打包状态仍明确未安装／未经过播放验收。

`migration-evidence/` 记完整账本；`cpu/` 只验真实生产头和提取调用算法，不声称物理显示通过。
本次 FFmpeg 单行修复保留 fork 的真实 `62.13.102`，避免丢失私有 DV API 能力识别。
