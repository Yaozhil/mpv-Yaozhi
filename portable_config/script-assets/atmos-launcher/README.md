# mpv-Yaozhi Atmos 实验启动器

根目录的 `mpv-Atmos.exe` 是独立实验入口，不替换普通 `mpv.exe`。

- 首次启动由用户确认后，从上游 GitHub Releases 直接获取固定版本组件。
- 下载文件必须通过内置 SHA-256 校验才会解压。
- 组件安装到 `portable_config/experimental/omniphony/`，与主播放器隔离。
- 启动时显式把 `--ad-orender-library` 固定到侧车自己的 `orender.dll`，不会误用
  Omniphony Studio 或系统目录中的另一版引擎。
- 启动前会检查侧车核心同时具备 Omniphony 与本项目 HDR/PGS 定制能力，再加载
  引擎并检查 liborender ABI；命令行不能覆盖引擎或解码桥路径。通用上游包、
  版本、ABI、下载或启动任一门禁失败都会回退根目录 `mpv.exe`。
- 下载、校验、部署或启动失败时，自动使用根目录原生 `mpv.exe` 打开相同参数。
- 普通播放器不启用 `ad_orender`，也不会显示 Atmos 菜单。
- 根目录 `mpv.exe` 已适配 AV3A / Audio Vivid；`mpv-Atmos.exe` 仍使用独立的
  Omniphony 侧车，不能把根目录 `mpv.exe` 或其 DLL 直接复制覆盖到侧车目录。
- AV3A、HOA 和对象音频使用普通 `mpv.exe`；Atmos 实验内容使用
  `mpv-Atmos.exe`。两条路径分别保留各自的解码/渲染 ABI，避免互相破坏。

固定版本：

- `mgth/mpv-omniphony`：`mpv-v0.4.2-fel-beta.1`
- `mgth/Omniphony` / `liborender`：`v0.4.2`
- `harletty/harletty-bridge`：`v0.7.3`

`beta.1` 是跟随 mpv master 的 FEL 预发布线，已加入 liborender 运行时 ABI
握手和不可用时的原生解码回退。旧 `beta.6 + bridge v0.7.1` 目录不覆盖、
不删除，只作为本机可回滚侧车保留。

播放器及 `orender.dll` 由上游按 GPL-3.0-or-later 发布，压缩包内含相应许可与第三方声明。
解码桥由启动器在用户明确进入实验模式时从其上游项目直接获取，不随 mpv-Yaozhi
发布包再分发。

如 GitHub 自动下载失败，可手动把以下两个**未经改名**的官方压缩包放进
`portable_config/cache/atmos-components/`，启动器仍会执行同样的 SHA-256 校验：

- `mpv-omniphony-fel-windows-x86_64.zip`
- `harletty-bridge-v0.7.3-windows-x86_64.zip`
