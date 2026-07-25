# Yaozhil MPV 整合包

面向 Windows mpv 的自制 UI 整合包<br>基于 [dyphire/mpv-config](https://github.com/dyphire/mpv-config) 的配置结构继续整理<br>并加入个人维护的 uosc 布局、快捷键菜单、弹幕、片头片尾标记、AList/OpenList 网盘入口、起播格式徽章和中文统计信息体验

所有发布版都已做通用化处理。

> 上游参考：<br>
>`dyphire/mpv-config` 是 Windows下mpv 配置项目<br>
>`yosh-wang/mpv-stats.lua-zh-chinese-translation-` 提供中文版 stats.lua 思路与同步说明<br>
>`yosh-wang/auto_bluray-ISO-`提供圆盘ISO思路并深度优化

## UI 预览

![主界面标注](docs/images/ui-annotated.png)

### 底栏细节

![底栏细节](docs/images/player-bar-annotated.png)

### 网盘登录面板

![网盘登录面板](docs/images/alist-login-annotated.png)


### 杳知配置助手5.0

![杳知配置助手3.0](docs/images/%E6%9D%B3%E7%9F%A5%E9%85%8D%E7%BD%AE%E5%8A%A9%E6%89%8B3.0%E6%88%AA%E5%9B%BE.png)


## 新功能：专业起播格式徽章

> 像专业播放器一样，在起播阶段一眼确认片源规格。

播放器会在首帧和画面边界稳定后，自动识别画面标准与当前选中的音轨，并在实际视频画面的右上安全区短暂显示。默认淡入、停留 4 秒后淡出，不会变成常驻水印。

- **画面格式**：Dolby Vision、HDR10+、HDR10、HLG、SDR。
- **音频格式**：Dolby Atmos、DTS:X、Dolby TrueHD、DTS-HD、AC-4、MPEG-H，以及 FLAC、PCM、AAC 等常见格式。
- **智能定位**：适配上下/左右黑边，并识别蓝光 ISO 中编码进视频帧的黑边。
- **当前音轨优先**：多音轨文件按当前选中音轨识别；切换音轨后会重新显示，避免串标。
- **可自由控制**：右键菜单「其它 > 开/关 起播格式标签」可随时切换，状态会自动保存。

### 实际播放效果

![有字幕播放场景中的 Dolby Vision 和 Dolby Atmos 起播格式徽章](docs/images/startup-format-badges-playback.png)

### 起播画面与完整 UI

![绿色电影开头标场景中的 Dolby Vision 和 Dolby Atmos 起播格式徽章](docs/images/startup-format-badges-opening.png)

## 安装

1. 下载整合包：[mpv-yaozhi-2026.7.25.zip](https://github.com/Yaozhil/mpv-config/releases/download/%E6%9D%B3%E7%9F%A5mpv%E6%95%B4%E5%90%88%E5%8C%85/Yaozhi-mpv-2026.7.25.zip)，解压即可使用<br>

2. 打开配置助手，按需配置即可（会自动获取显卡信息）<br>

    注：整合内已有 `杳知配置助手5.0`


- 配置助手教程：把`杳知配置助手5.0（MPV）.exe` 放到 mpv 根目录，与 `mpv.exe` 同级即可<br>

- 配置助手下载：[杳知配置助手5.0（MPV）.zip](https://github.com/user-attachments/files/30345516/5.0.MPV.zip)

## 主要特色

- 新增专业起播格式徽章：自动识别画面标准与当前音轨，在实际画面安全区短暂显示。
- uosc 中文界面与菜单体验优化。
- 常用 UI 操作、播放控制、文件管理、字幕、音轨和播放列表快捷键整理。
- 集成弹幕相关配置。
- 新增片头片尾跳过。
- 新增纯本地化自定义片头片尾设置工具（剪刀图标）。
- 新增 AList/OpenList 登录弹窗和网盘图标（AList 相关适配）。
- 新增本地 ISO 视频格式播放。
- 重写文件浏览器鼠标操作，支持鼠标悬停高亮提示。
- 中文化 stats，方便查看解码、HDR、帧耗时和音频状态。

详细说明见 [独特功能说明](docs/unique-features.md)。

## 目录说明

```text
portable_config/
├─ mpv.conf              # mpv 主配置，通用硬件默认值
├─ input.conf            # 快捷键与菜单预设
├─ scripts/README.md     # 脚本同步说明
├─ script-opts/          # 脚本选项示例
├─ shaders/README.md     # shader 同步说明
└─ fonts/README.md       # 字体说明，不附带字体文件
docs/
├─ unique-features.md    # 本维护版特色说明
├─ release-check.md      # 发布前检查
└─ images/               # UI 展示图
```

## 许可与来源说明

本仓库整理自个人使用配置，并参考以下项目结构或思路：

- [dyphire/mpv-config](https://github.com/dyphire/mpv-config)
- [yosh-wang/mpv-stats.lua-zh-chinese-translation-](https://github.com/yosh-wang/mpv-stats.lua-zh-chinese-translation-)
- [yosh-wang/auto_bluray-ISO-](https://github.com/yosh-wang/auto_bluray-ISO-)
- mpv 社区脚本与相关开源项目

各脚本、shader 与第三方组件的版权和许可归原作者所有。

若上游项目自带 LICENSE / README，本仓库会尽量保留原始说明。

## 免责声明

本配置主要面向 Windows mpv 用户。不同 mpv 构建、显卡驱动、系统版本和脚本依赖环境可能导致体验不同。

建议直接使用整合包，解压即用。

如遇问题，反馈即可。
