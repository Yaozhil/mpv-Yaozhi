# 蓝光标题与音轨修复验证

2026-09-08 候选以已通过 CI 34054633292 的双核心为基础，不改变 Omniphony、bridge、libbluray 或其他功能依赖。

- `0006-bluray-title-resync-hdmv-context.patch`：直达标题模式公布已有的重同步边界，使临时 EOF 得到应答、重建 lavf；最后一个真实标题不再误当作菜单占位。仅已知 Blu-ray 后端向 MPEG-TS 传入格式上下文。
- `ffmpeg-9005-bluray-hdmv-context.patch`：可选 `force_hdmv` 在节目注册缺失时使用现有完整 HDMV 类型处理。默认关闭，不覆盖显式节目注册，不按文件名、PID 或单一音频编码猜测。
- `verify-hdmv-context.py`：现场生成 48 kHz 双声道和 96 kHz 六声道蓝光 PCM，去掉 PMT 的 HDMV 注册并重算 CRC。默认模式必须仍无法识别，显式上下文必须解码出与正常样本逐字节一致的音频，其他显式注册不得被覆盖；同时检查每个 mpv 的实际音频文件输出。

合成用例不包含用户视频。真实 ISO 标题切换、菜单转正片、音轨切换、字幕及正常 EOF 需在独立候选进程实测；编译成功和合成测试不等于这些实盘项目全部通过。不发布 Release。
