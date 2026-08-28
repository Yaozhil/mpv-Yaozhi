<div align="center">

<h1>mpv-Yaozhi</h1>

**面向 Windows 的高画质、原盘导航、沉浸声与中文交互一体化 mpv 播放方案**

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D4?logo=windows11&logoColor=white)](https://github.com/Yaozhil/mpv-Yaozhi/releases/latest)
[![Architecture](https://img.shields.io/badge/Architecture-x86--64-4C8BF5)](https://github.com/Yaozhil/mpv-Yaozhi/releases/latest)
[![mpv](https://img.shields.io/badge/mpv-0.41.0--1017--g5290a1925-691B9A?logo=mpv&logoColor=white)](https://github.com/mpv-player/mpv)
[![Core](https://img.shields.io/badge/Core-Yaozhi%20Custom-7C3AED)](https://github.com/Yaozhil/mpv-Yaozhi/tree/codex/hdr-pgs-core-fix)
[![License](https://img.shields.io/badge/License-See%20details-2EA44F)](#来源与许可)

[下载最新版本](https://github.com/Yaozhil/mpv-Yaozhi/releases/latest) · [近期更新](#近期更新) · [界面预览](#界面预览) · [主要功能](#主要功能) · [快速开始](#快速开始) · [问题反馈](#问题反馈)

</div>

mpv-Yaozhi 基于 [mpv](https://github.com/mpv-player/mpv) 与 [dyphire/mpv-config](https://github.com/dyphire/mpv-config) 持续维护，将自编译播放器核心、Windows 便携配置和中文交互整合在同一个解压即用的发行包中。

项目重点覆盖 HDR / Dolby Vision、蓝光与 DVD 原盘菜单、图形字幕、AV3A / Audio Vivid、Dolby Atmos 源码直通、多声道 PCM、AI 超分与补帧、AList/OpenList 以及日常播放体验。

> 本项目是社区维护的第三方发行方案，并非 mpv 官方版本。

**交流群：** [Telegram · mpv_Yaozhi](https://t.me/mpv_Yaozhi)

## 近期更新

- **蓝光 / DVD 原盘菜单**：本地目录、光驱与 ISO 可自动进入光盘导航，同时支持 HDMV 与 BD-J Java 菜单；完整包已内置匹配播放器核心的 Java 运行环境。
- **Dolby Vision P7 / FEL**：改善频繁精确跳转后的增强层恢复，保持基础层、EL/FEL 与 RPU 的正确配对。
- **HDR Vivid 识别**：在原生、软件解码及硬件帧回读路径中保持帧元数据识别，格式标签不会因解码路径变化误退成 HDR10。
- **中文轨道选择**：视频与音频菜单直接打开完整轨道列表，确认选择后才切换；当前轨道、语言、编码、声道和分辨率信息一目了然。
- **快捷键管理**：通过“杳知 > 快捷键绑定列表”用中文搜索、修改和恢复常用快捷键，不直接改写原始 `input.conf`。
- **智能画质保护**：RIFE 补帧不再以降低片源分辨率或原有超分质量为代价；不满足安全条件时自动保留原画质并回到原生平滑。

## 界面预览

![mpv-Yaozhi 主界面](docs/images/ui-annotated.png)

<details>
<summary>查看更多界面与配置助手</summary>

### 杳知功能菜单

![杳知功能菜单](docs/images/yaozhi-menu-showcase.png)

### 杳知配置助手

![杳知配置助手](docs/images/config-assistant.png)

</details>

## 主要功能

| 分类 | 支持内容 |
| --- | --- |
| 播放核心 | 自维护 Windows x86-64 mpv；D3D11、`gpu-next`、Schannel/libcurl 与定制补丁链 |
| 画面格式 | HDR10、HDR10+、HLG、Dolby Vision P5 / P7 MEL/FEL / P8.1 / P8.4、HDR Vivid 元数据识别 |
| 视频解码 | H.264、HEVC、AV1、VVC / H.266、AVS2、AVS3、Animated WebP 等 |
| 图形字幕 | UHD HDR/DV 内封 PGS 与 SDR 图形字幕分别处理；支持手动色彩覆盖及 150–400 nits 独立亮度 |
| 原盘导航 | 本地蓝光 / DVD / ISO 自动进入原盘导航；支持 HDMV、BD-J Java 菜单与中文操作入口 |
| 沉浸声音频 | AV3A / Audio Vivid / AVS3 Audio 解码，对象与 HOA 双耳渲染，5.1.4 至 9.1.6 PCM 高度声道 |
| 音频源码直通 | AC-3、E-AC-3、Dolby TrueHD、DTS、DTS-HD HRA/MA，以及相应载荷中的 Dolby Atmos / DTS:X |
| 超分与补帧 | FSRCNNX、SSim、RIFE v4.6 Vulkan，可选 NVIDIA TensorRT FP16 扩展与实时安全回退 |
| 中文交互 | 深度定制 uosc、中文媒体信息、轨道选择、快捷键管理、弹幕、片头片尾、音乐模式、播放历史与格式标签 |
| 网络播放 | AList/OpenList、WebDAV、HTTPS 媒体直链、Windows 系统证书链、ZIP/RAR 内视频播放与远程蓝光 ISO 主标题模式 |

## 蓝光 / DVD 原盘菜单

本地蓝光目录、光驱与 ISO 会在建立播放链时启用光盘导航；如果 First Play 直接进入正片，播放器会在合适时机请求一次原盘主菜单。普通用户无需预先安装 Java，也不需要手动修改环境变量。

- 支持蓝光 HDMV 菜单、BD-J Java 动态菜单与 DVD 菜单。
- `杳知 > 蓝光圆盘菜单` 提供返回菜单根目录、标题菜单、播放快捷菜单和上一级等中文入口。
- 正片或分段播放时可使用 `Home` / `Ctrl+m` 返回蓝光菜单根目录，`Ctrl+M` 显示或隐藏弹出菜单。
- AList/OpenList 远程蓝光 ISO 继续使用主标题模式，不启动菜单 VM，避免额外的网络随机读取和起播等待。

<p align="center">
  <img src="docs/images/bluray-menu-showcase-1.png" alt="蓝光原盘菜单播放展示" width="960">
</p>

<details>
<summary>查看另一种原盘菜单效果</summary>

<p align="center">
  <img src="docs/images/bluray-menu-showcase-2.png" alt="蓝光原盘菜单播放展示" width="960">
</p>

</details>

> 菜单画面、语言、动画、弹出菜单和可选项目由原盘自身决定；没有制作菜单的镜像不会由播放器生成菜单。

## Dolby Vision、HDR 与图形字幕

- Dolby Vision 支持 P5、P7 MEL/FEL、P8.1 与 P8.4，由播放器内部完成解码、重塑和显示适配。
- P7/FEL 播放会保留基础层、增强层与 RPU 的关联；快速精确跳转时会过滤已损坏的增强层恢复帧，避免短暂叠入正常画面。
- `gpu-next` 路径会区分 UHD HDR/DV 内封 PGS 与外置或 SDR 图形字幕：前者可随视频进入 HDR 映射链，后者保守按 SDR/sRGB 处理。
- `杳知 > HDR 图形字幕色彩与亮度` 提供自动判断、随视频、SDR·sRGB 三种模式，以及 150 / 203 / 250 / 300 / 400 nits 图形字幕亮度。
- 图形字幕设置不改变视频、ASS/文本字幕和 OSD 的色彩处理。

## 超分与补帧

“杳知 > 超分与补帧”统一管理空间增强与时间平滑，两项功能默认关闭，可独立启用并保存选择。

- 自动模式会根据显卡档位、片源分辨率、帧率、输出负载和当前画面格式选择合适方案。
- 通用空间增强以 SSim 与 FSRCNNX 为主；Anime4K、NNEDI3、RAVU 等保持手动选择。
- RIFE v4.6 使用随包提供的 Vulkan 运行环境；安装完整高端扩展后，兼容的 NVIDIA RTX 显卡可以选择 TensorRT FP16 后端。
- RIFE 只在可以保持片源分辨率和原有超分质量时建立 AI 2× 链路；无法实时运行时自动回退，不先降采样再补帧。
- HDR10 / HDR10+ 可使用保留 PQ、BT.2020 与逐帧信息的安全路径；Dolby Vision、HLG、HDR Vivid、光盘和 VFR 等场景保持原始色彩链与原生平滑。
- 暂停、跳转和播放恢复期间优先复用现有滤镜图，减少重复初始化和额外等待。

## 沉浸声与多声道音频

### AV3A / Audio Vivid

- 支持 AV3A（Audio Vivid / AVS3 Audio）常规多声道、对象音频和 HOA 内容。
- `native` 模式保留可用的传输声道与 PCM；`binaural` 模式将对象、床层加对象及 HOA 内容渲染为双声道耳机输出。
- AV3A / Audio Vivid 是播放器解码后的 PCM 输出，不属于 S/PDIF 源码直通格式。

### 高度声道 PCM

| 布局 | 声道顺序 |
| --- | --- |
| 5.1.4（10ch） | `FL-FR-FC-LFE-SL-SR-TFL-TFR-TBL-TBR` |
| 7.1.4（12ch） | `FL-FR-FC-LFE-BL-BR-SL-SR-TFL-TFR-TBL-TBR` |
| 9.1.4（14ch） | `FL-FR-FC-LFE-BL-BR-SL-SR-TFL-TFR-TBL-TBR-TSL-TSR` |
| 9.1.6（16ch） | `FL-FR-FC-LFE-BL-BR-SL-SR-TFL-TFR-TBL-TBR-TSL-TSR-WL-WR` |

播放器会为 Windows 输出具名扬声器布局与匹配的 speaker mask，避免高度声道退化为未知通道。5.1.4 / 7.1.4 已覆盖 Windows 设备打开与实机声道路由，9.1.4 / 9.1.6 已覆盖软件声道顺序与 PCM 保序；最终扬声器输出仍取决于声卡、驱动、Windows 音频接口、HDMI/eARC 链路和终端设备。

### 音频源码直通

- 支持 Dolby Digital、Dolby Digital Plus、Dolby TrueHD、DTS 与 DTS-HD HRA/MA。
- Dolby Atmos 可随 E-AC-3 / TrueHD 载荷传输，DTS:X 可随 DTS-HD 载荷传输。
- 提供全部直通、仅 Dolby、仅 DTS、关闭直通四种模式。
- 设备拒绝当前码流时会退出不兼容状态并恢复 PCM，避免后续播放持续无声或卡住。
- **菜单路径：** `杳知 > 音频直通`

根目录的 `mpv-Atmos.exe` 是独立实验入口，用于尝试对象音频软件解码与状态展示；它不替换正式 `mpv.exe`，组件不可用时会回到普通播放路径。

## 专业起播格式标签

播放器会在画面信息就绪时识别当前画面标准与选中音轨，并在真实视频画面的安全区短暂显示。多音轨切换后会自动刷新，编码黑边识别在后台完成，不阻塞首个可呈现画面。

- **画面标签：** Dolby Vision、HDR Vivid、HDR10+、HDR10、HLG、SDR
- **音频标签：** Audio Vivid、Dolby Atmos、DTS:X、TrueHD、DTS-HD、AC-4、MPEG-H、DRA、APE、FLAC、PCM、AAC 等
- **显示样式：** 彩色徽章或透明白图标
- **菜单路径：** `杳知 > 起播格式标签`

![HDR Vivid 与 Audio Vivid 起播格式标签](docs/images/startup-format-badges-vivid-dual.png)

## 中文播放与网络体验

- 使用统一的 uosc 主菜单、右键菜单、播放列表、轨道列表和字幕内容搜索。
- 底栏直接显示解码方式、画面规格、编码、音频、码率和网络状态。
- 支持中文弹幕搜索与加载、片头片尾查询/手动标记、章节显示和自动跳过。
- 音乐模式提供列表循环、单曲循环、随机防重复以及最小化继续播放。
- 最近播放支持本地文件、网盘和签名 URL；临时离线不会批量清除历史记录。
- AList/OpenList 浏览支持刷新、排序、长路径适配及 ZIP/RAR 内视频直接播放，不在界面中展示账号、密码和签名参数。

## 快速开始

### 系统要求

- Windows 10 / 11 64 位
- 支持 Direct3D 11 的显卡与较新的显卡驱动
- HDR、源码直通和 5.1.4 至 9.1.6 输出需要相应显示器、声卡、Windows 音频接口、HDMI/eARC 设备或功放支持

### 安装

1. 前往 [Releases](https://github.com/Yaozhil/mpv-Yaozhi/releases/latest) 下载最新整合包。
2. 将压缩包完整解压到可写目录，不要直接在压缩软件中运行。
3. 双击 `mpv.exe`，或者把媒体文件拖入播放器。
4. 按需运行与 `mpv.exe` 同级的“杳知配置助手”，让程序识别硬件并选择适合的配置。
5. 如需双击媒体文件直接播放，可运行根目录的“注册视频文件关联”脚本；文件关联只写入当前用户。

> 完整整合包已包含播放器核心、便携配置与 BD-J Java 运行环境。普通用户无需另外安装 mpv 或 Java。

## 兼容性说明

| 功能 | 当前边界 |
| --- | --- |
| Dolby Vision | 由播放器内部处理并输出适合显示设备的 HDR10/PQ 或 SDR；不作为原生 Dolby Vision 元数据透传方案 |
| HDR Vivid | 支持帧元数据识别与界面标识；当前不包含专用动态色调映射或显示端透传 |
| Dolby Atmos / DTS:X | 普通入口支持源码直通，依赖原始音轨、Windows 默认输出设备及回音壁或功放；`mpv-Atmos.exe` 属于独立实验入口 |
| AV3A / Audio Vivid | 支持解码与 PCM 输出；当前明确提供的对象/HOA 空间渲染模式为双耳输出 |
| 5.1.4 至 9.1.6 PCM | 5.1.4 / 7.1.4 已验证 Windows 设备打开与实机声道路由；9.1.4 / 9.1.6 已验证软件声道顺序与 PCM 保序，终端设备仍须支持对应布局 |
| 蓝光 / DVD 菜单 | 本地介质由原盘自身导航数据驱动；远程蓝光 ISO 使用主标题模式，不进入菜单 VM |
| AI 超分与补帧 | 只在当前硬件和片源满足安全条件时启用；触发保护后保留原画质并回到普通播放 |

## 问题反馈

提交 [Issue](https://github.com/Yaozhil/mpv-Yaozhi/issues) 时，建议提供：

- Windows 版本、显卡型号与驱动版本
- 播放器版本，可运行 `mpv.com --version` 查看
- 音频设备、连接方式及 Windows 扬声器布局
- 可复现的文件格式、音视频编码和操作步骤
- `portable_config/files/mpv.log` 中与问题相关的片段

请勿公开包含网盘账号、签名 URL、访问令牌或私人文件路径的完整日志。

## 支持项目

如果 mpv-Yaozhi 有幸改善了你的播放体验，也欢迎在方便的情况下自愿赞赏。你的支持会帮助我更好的持续投入测试、维护与后续开发，非常感谢。

<p align="center">
  <a href="docs/images/赞赏码.png">
    <img src="docs/images/赞赏码.png" alt="支持 mpv-Yaozhi" width="760">
  </a>
</p>

</details>

## 来源与许可

本项目参考或集成了以下项目及社区成果：

- [mpv-player/mpv](https://github.com/mpv-player/mpv)
- [dyphire/mpv-config](https://github.com/dyphire/mpv-config)
- [yosh-wang/mpv-stats.lua-zh-chinese-translation-](https://github.com/yosh-wang/mpv-stats.lua-zh-chinese-translation-)
- [yosh-wang/auto_bluray-ISO-](https://github.com/yosh-wang/auto_bluray-ISO-)
- uosc、FFmpeg、libplacebo、SDL2、libbluray 及其他随项目保留来源说明的开源组件

公开仓库中由 Yaozhi 独立创作并由仓库许可证明确覆盖的代码与文档采用 [MIT License](https://github.com/Yaozhil/mpv-Yaozhi/blob/main/LICENSE.md)。
