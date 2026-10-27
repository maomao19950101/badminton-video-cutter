# 🏸 Badminton Video Cutter (羽毛球实战视频智能精彩剪辑器)

<p align="center">
  <img src="https://img.shields.io/badge/version-v1.3.6-blue.svg?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10+-brightgreen.svg?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/ffmpeg-4K_UHD_StreamCopy-orange.svg?style=flat-square" alt="FFmpeg">
  <img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="License">
</p>

专为羽毛球业余/专业球友、俱乐部教练、视频创作者打造的**全自动化实战视频精彩高光提取与智能剪辑引擎**。基于**声光多模态击球感知（Acoustic-Optical Multimodal Perception）**与**物理运动学空间约束**，从数小时的 4K 60fps 原盘录像中毫秒级定位精彩回合，自动剔除捡球、走动、喝水等无效垃圾死球时间，无损直出转播级多拍集锦、接发秒杀大赏、慢动作回放与微信动态表情包！

---

## 🌟 核心功能亮点 (Key Features)

- 🏸 **纯多拍对攻拉锯集锦 (Multi-Shot Rallies)**
  - 自动识别激烈回合对攻，智能区分 5~15 秒【多拍激烈对攻】与 15 秒以上【超长高能拉锯】。
  - 单独输出独立精彩小视频，并一键无损缝合为整场比赛精选合集（`00_【纯多拍零死球合集】_全N段精选版.mp4`）。
- ⚡ **接发突击一拍定死大赏 (Serve-and-Kill Moments)**
  - 毫秒级捕捉发球被直接扑死（【发球被一拍定死】）与接发直接变线抽杀（【接发突击一拍定死】）。
  - **v1.3.5 落地保全与后续击球排他机制**：严格验证 $t_k + 3.2\text{s}$ 内无后续击球（排他性），并延展 $e_{\text{cut}} = t_k + 1.25\text{s}$ 完整记录羽毛球下坠砸地、触网反弹与死球全轨迹。
- 🛑 **落地即止与双侧攻防核验 (Ground-Landing Severing - v1.3.6)**
  - **同半场连续击球终结判定**：根据羽毛球跨网对攻规则，当一侧击球后对方半场处于休眠状态（`far_m < 5.2`）或球场进入走动捡球（`our_m < 8.8`），判定结分，球落地即刻切断，**彻底杜绝外场暴杀声混入、捡球走动粘连等假拉锯**。
- 🚫 **人员进出场与换人离场智能过滤**
  - 四锚点时序核验（20%, 40%, 60%, 80%），自动识别并剔除人员进出场、下场喝水、半场轮换等非实战镜头。
- 📹 **开机关机调试噪点智能排查 (Camera Match Window)**
  - 自动分析机位抖动，秒级锁定固定机位有效比赛时间窗（`stable_start ~ unstable_end`），彻底排除开机安装固定与关机收拾过程中的杂音。
- 📊 **转播级 HUD 焦点战术覆叠 (Broadcast Tactical HUD)**
  - 支持渲染奥运/世锦赛转播级 HUD：多拍拍数计数器（Rally Shots）、对攻持续时长（Duration）、高频攻防瞬时拍速（RPS, Hits/sec）与能量波形。
- 🎞️ **微信动态表情包自动制作 (WeChat GIF Stickers)**
  - 针对绝妙秒杀与高光绝杀，自动生成带有金色战术标语的 480P 12fps 微信表情包，大小控制在 1MB~5MB，即存即发！
- ⚡ **全流程 4K 极速无损流复制 (Lossless Stream Copy)**
  - 剪辑默认采用 `-c copy` 无损流切分，纯 4K 60fps UHD 画质原汁原味，处理耗时仅为传统重编码的 1/200！

---

## 🏗️ 算法架构与技术管线 (Architecture Pipeline)

```
                       [ 原始录像 4K 60fps MP4 ]
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
[ 提取单声道 WAV (16kHz) ]                       [ 视频帧多模态透视流 ]
         │                                                 │
[ 短时高通瞬态能量激增检测 ]                                 │
    (Dual-Contrast Acoustic)                               │
         │                                                 │
[ 击球候选点时间序列 t_hits ]                                │
         │                                                 │
         └────────────────────────┬────────────────────────┘
                                  ▼
               [ 机位实战时间窗校准 fast_camera_match_window ]
                                  │
               [ 邻场声学串扰抑制 & 走动捡球过滤 (v1.3.6) ]
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
[ 多拍聚类与双侧连续性核验 ]                     [ 接发秒杀多模态验证 ]
  - max_gap = 2.40s 物理上限                       - 严格发接发时序 (0.45s~1.70s)
  - 走动与捡球间歇强解耦                             - 后续击球排他窗口 [tk+0.25, tk+3.20]
  - 捞球连击消除 (Multi-Tap Prune)                  - 发球前蓄势静音核验
         │                                                 │
[ 落地即止强切断 (落地+0.50s) ]                   [ 落地轨迹保全 (tk+1.25s) ]
         │                                                 │
         └────────────────────────┬────────────────────────┘
                                  ▼
                     [ 多线程无损流复制 ffmpeg -c copy ]
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
[ 独立精彩多拍集锦 ]        [ 接发秒杀一拍定死 ]       [ 纯多拍零死球整场大合集 ]
(5~15s激烈 / >15s超长)    (发球被定死 / 接发突击)        (00_纯多拍合集.mp4)
```

---

## 📋 羽毛球精彩集锦八大执行铁律 (The 8 Mandatory Rules)

1. **绝对零死球截断规范与球落地即止原则**：片头紧随发球引拍（$t_{\text{serve}} - 0.70\text{s}$），片尾严格终结于羽毛球触地/挂网瞬间（$t_{\text{last}} + 0.50\text{s}$），严禁包含球员捡球、擦汗、发呆。
2. **绝对严禁未死球提前截断**：长达 2.40 秒的底线高远球空中航迹必须 100% 完整保留，不漏球、不切碎。
3. **机位调试与非比赛镜头 100% 排除**：开机关机、拿在手上调整机位等非打球片段坚决剔除。
4. **人员进出场与换人离场严格过滤**：严禁替补进出、喝水走动等镜头进入集锦。
5. **默认纯净原画无遮挡直出**：视频默认不压印任何字幕或贴纸，保持场地、球路视线清晰。
6. **双轨分类存储架构**：多拍拉锯与接发秒杀分门别类，绝不混淆。
7. **整场无损缝合大合集**：全场精彩无缝拼接，零死球连贯播放。
8. **微信动态表情包即发规格**：专为移动端社交传播设计的微型动图。

---

## 🚀 快速上手 (Quickstart)

### 1. 环境准备 (Requirements)

- **Python**: 3.10+ (推荐使用 [uv](https://github.com/astral-sh/uv) 极速管理环境)
- **FFmpeg**: 需支持 HEVC/H.264 解码与无损封装
- **Python 依赖**: `opencv-python-headless`, `numpy`, `scipy`

```bash
# 使用 uv 运行（无需繁琐配置虚拟环境）
uv run --with opencv-python-headless --with numpy --with scipy python scripts/badminton_cutter.py --help
```

### 2. 命令行基础用法 (Basic Usage)

```bash
# 1. 剪辑指定比赛目录下的所有视频（提取多拍 + 秒杀 + 合集）
python scripts/badminton_cutter.py --dir /path/to/videos --mode all

# 2. 仅提取多拍拉锯集锦并生成全场纯多拍合集
python scripts/badminton_cutter.py --dir /path/to/videos --mode duopai

# 3. 仅提取接发秒杀一拍定死高光时刻
python scripts/badminton_cutter.py --dir /path/to/videos --mode serve_kill

# 4. 生成带转播级 HUD 焦点战术特效的小视频
python scripts/badminton_cutter.py --dir /path/to/videos --mode all --hud

# 5. 生成接发秒杀微信动态表情包 (GIF)
python scripts/badminton_cutter.py --dir /path/to/videos --mode serve_kill --gif
```

---

## 📂 输出目录组织结构 (Output Directory Structure)

剪辑完成后，将自动在指定输出目录下按场次规范分类：

```text
📁 1026羽毛球精彩多拍集锦/
├── 📁 01_场次一_双打实战_049/
│   ├── 🎬 00_【01_场次一_纯多拍零死球合集】_全38段精选版.mp4  <-- 全场精选大合集
│   ├── 🎬 多拍01_02分15秒至02分28秒_【多拍激烈对攻】_13秒.mp4
│   ├── 🎬 多拍02_04分10秒至04分32秒_【超长高能拉锯】_22秒.mp4
│   ├── 📁 接发秒杀一拍定死/
│   │   ├── 🎬 秒杀01_01分44秒至01分49秒_【接发突击一拍定死】_5秒.mp4
│   │   └── 🎬 秒杀02_08分12秒至08分16秒_【发球被一拍定死】_4秒.mp4
│   ├── 📁 转播级HUD特效/
│   │   └── 🎬 HUD_多拍02_04分10秒至04分32秒_【超长高能拉锯】_22秒.mp4
│   └── 📁 微信动态表情包/
│       └── 🖼️ 表情包_秒杀01_接发突击一拍定死.gif
└── 📁 02_场次二_双打实战_050/
    └── ...
```

---

## 🏷️ 版本历史 (Release History)

查看完整的版本迭代记录：[CHANGELOG.md](CHANGELOG.md)

- **v1.3.6 (2026-10-27)**：同半场连续击球终结判定与双侧攻防核验，落地即止强切断机制，彻底根除捡球走动与相邻场地杀球声串扰粘连。
- **v1.3.5 (2026-10-27)**：接发秒杀落地即止保全（$t_k+1.25\text{s}$），后续击球严格排他窗口（3.2秒静默），发球前蓄势静音核验。
- **v1.3.4 (2026-10-26)**：中途死球动量骤降解耦与静止场区声学串扰清洗。
- **v1.3.3 (2026-10-26)**：双重声学标定与多点航迹高远球保全。
- **v1.3.0 ~ v1.3.2 (2026-10-26)**：零死球解耦引擎、人员进出场过滤与轻吊搓放捕捉。

---

## 🤝 贡献与持续更新 (Continuous Delivery & Contribution)

本项目持续维护，针对各类场馆声学环境（吸音馆、铁皮馆、高挑空大馆）、多机位角度（后场高机位、侧面网口、低三脚架）以及双打/单打场景持续优化模型参数。

欢迎提交 Issue 和 Pull Request！

```bash
# 提交并推送至 GitHub
git add .
git commit -m "feat: your new feature"
git push origin main --tags
```

---

## 📄 开源许可证 (License)

本项目基于 [MIT License](LICENSE) 开源。
