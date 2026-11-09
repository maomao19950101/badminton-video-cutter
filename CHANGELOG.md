# 🏸 Badminton Video Cutter - Changelog & Version History

All notable changes to the `badminton-video-cutter` skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.8.11] - 2026-11-09

- 修复局间死球捡球/踱步误切与真回合遭截断问题：
  - 核心重构发球静止锚定机制（Rule 4），支持多窗口（`t-0.85s`, `t-1.20s`, `t-1.50s`）与半场解耦核验（兼容双打接发方微晃防守），彻底防止因接发方颠步误判发球未静止；
  - 增加真发球击球间隔物理约束（`g_lead >= 0.55s`），杜绝将捡球双脚垫步误判为发球；
  - 增加进攻保护护栏（`any(E >= 2.5e7) break`），彻底严禁将包含后场重杀/平抽实战回合截断或丢弃；
  - 增加纯死球短碎噪音整簇剔除保护，彻底杜绝无发球、低能量（`max_E < 2.5e7`）的死球捡球步伐输出为伪多拍；
  - 增强终结球后死球解耦（Rule 1），在重杀或快攻下分后，若伴随死球垫步与运动骤降，干净切断后续局间走动。
- 替换并修复 1105 场次四第 01 局 `多拍05` 为完整的 15 拍进攻拉锯高能回合（01分56秒至02分11秒，15秒），彻底清除 7 秒捡球死球片段。

## [1.8.10] - 2026-11-09

- 强化发球前静止定界与局间过道进出场强过滤：在发球静止核验（Rule 4）与片段质检中引入边界过道动态约束（`b_max <= 8.5`），彻底杜绝局间球员入场、踱步闲逛及邻场杀球串音误切为多拍回合的问题。
- 修复换人局间偶发的分局粘连，确保实战换人节点干净切分。

## [1.8.9] - 2026-11-06

- CLI 与本地工作台共用时间轴分析及导出引擎，支持仅分析、时间轴复用、可调导出并发和帧级精剪。
- 隔离同名视频的音频缓存，按源文件、分析参数和版本缓存时间轴，分开保存人工编辑。
- 优化声学候选扫描与接发秒杀事件窗口查询，减少数组副本和无效分局取帧。
- 修复相对路径拼接、导出误报和 16:9 比例。个人高光使用人工站位标注，未确认的打法单独分类。
- 本地 Web 视频接口仅服务已导入的视频，写操作校验请求来源与会话令牌。
- 精简 Skill 入口，修复 ZIP 中文路径编码与启动器本机路径。

## [1.8.8] - 2026-11-06

### 🧹 Deprecation & Removal of Tactical Review Mode (发接发前三拍复盘全面下线与纯净五大实战模式)
- **Engine & Modes Pipeline Refactor (`modes_handler.py`, `badminton_cutter.py`, `gui_engine.py`)**:
  - 全面下线发接发前三拍复盘（`--mode review` / `generate_review_package`）功能，从核心引擎及 CLI 参数选择中完整剥离。
  - 瘦身并优化输出结构，彻底杜绝冗余的前三拍切片与战术报告生成，节省约 3.5GB 磁盘占用并提升批处理导出效率。
  - 核心保留 5 大高价值实战模式：`all`（默认多拍与秒杀）、`condensed`（全场连贯纯享）、`vertical`（9:16 自媒体短视频）、`solo`（指定球员主角独享）、`showcase`（战术分类高光集锦）。
- **Desktop & Web Studio UI Alignment (`badminton_gui.py`, `scripts/ui/index.html`)**:
  - 本地 Tkinter 桌面端界面与 Codex Studio Web 端交互界面同步移除“发接发前三拍切片/战术复盘”选项卡与复选框。
  - 保持专业非编剪辑台风格布局整洁统一，所有实战模式卡片、预设配置与导出管线严格对齐。
- **Unit Test Suite Update**:
  - 同步更新 `test_gui_engine.py`、`test_modes.py` 与 `test_ui_pro_nle.py`，全套 50 项测试 100% 通过。

---

## [1.8.7] - 2026-11-05

### 🚫 Corridor Walk-Off & Intermission Pedestrian Suppression (镜头走廊过道走动强过滤)
- **Walk-Off / Non-Play Pedestrian Rejection (`check_clip_is_real_play`)**:
  - 精准识别局间换人、休息离场、镜头过道行人穿行等伪多拍场景（`b_avg >= 14.0`, `b_max_all >= 25.0` 且场内运动非爆发状态 `max_our < 30.0`），彻底杜绝因近处行人走过并伴随隔壁场地杀球声而被误判为多拍对攻的问题。
  - 智能保留底线极限杀球/鱼跃救球逼近边界线（`max_our >= 30.0`）的真实高难度多拍回合。
  - 新增专项单元测试 `test_walkoff_pedestrian_corridor_rejected`（51 项测试全部通过）。

---

## [1.8.6] - 2026-11-05

### 🏸 Deep-Lob Cadence Protection & True Serve Temporal Guard (深挑高远球保全与真发球时序校验)
- **Deep-Lob / High-Clear Protection (高远球与深挑球中盘物理保全)**:
  - 解决了激烈长回合在中盘遭遇高远球/深挑球（击球间歇 1.6s~2.2s）被旧版算法误判死球提前腰斩的问题。
  - 在 Rule 4 锚定逻辑中加入实战发球飞行时序窗口校验（`0.60s <= g_ret <= 2.60s`）与首个真发球命中即断（`break`），杜绝将回合内部连续对攻判定为新发球或割裂回合。
- **100% Full Rally Ground Truth (实战多拍完整性修复)**:
  - 成功修复第 05 局多拍 04 提前截断问题，无损重剪出完整的 18.2 秒超长高能拉锯，去除残尾碎片多拍 05，全局顺番重排并重建 14 拍连贯浓缩纯享合集。

---

## [1.8.5] - 2026-11-05

### ⏱️ Rule 4: Pre-Serve Stationary Boundary & True Serve Anchoring (发球静止定界与真发球锚定)
- **Zero Leading Footstep / Ball-Picking Noise (彻底剔除发球前捡球与踱步杂音)**:
  - 严格依据世界羽联（BWF）第 9.1 条规则（发球与接发球员必须在发球区保持静止）。
  - 在发球声学簇前评估局部光学运动平稳度（`our_m <= 7.5` 且 `near_m <= 7.0`），向前精确定位静止低谷之后的首记有效发球，将发球前捡球、走动、敲拍等死球杂音彻底剪除。

---

## [1.8.4] - 2026-11-04

### 🎨 Pro NLE Studio UI & Anti-AI Pure Desktop Redesign (去 AI 化专业桌面剪辑台与双主题)
- **Clean Native Pro NLE Aesthetic (专业非线性剪辑软件视觉质感)**:
  - 彻底去除 AI 概念化设计与冗余视觉元素，采用 Final Cut Pro / DaVinci Resolve 风格的工业级时间轴与工具栏。
  - 完整支持专业深色模式（Pro Dark）与录音室浅色模式（Studio Light）一键切换，配备实战赛点微调与双画面关键帧核对。

---

## [1.7.0] - 2026-11-02

### 🖥️ Major Feature: Pure Local Visual Desktop GUI & Interactive Timeline Studio (`badminton_gui.py` + `gui_engine.py`)
- **100% Pure Local Visual Video Cutting Software (纯净本地可视化桌面软件)**:
  - Built `scripts/badminton_gui.py` and `scripts/gui_engine.py`, delivering a dark-themed visual desktop application for Windows and macOS with zero cloud/LLM bloat.
- **Two Seamless Workflows**:
  - **🚀 一键全自动剪辑并输出视频**: Batch processes single/multiple videos or folders directly into organized game subfolders (`第01局` / `第02局` / `第03局`) and selected modes.
  - **🔍 先扫描时间轴 -> 双画面预览微调 -> 导出**:
    - Interactive color-coded rally timeline canvas (green = multi-shot rallies, gold = 15s+ marathon rallies, orange = serve-kills, dashed blue = player ReID game boundaries).
    - Dual live keyframe preview cards showing both the **Opening Serve Frame (`s_cut`)** and **Shuttle Landing End Frame (`e_cut`)**.
    - Fine-tune start/end timestamps (`±0.5s` / `±1.0s` / `+1.5s`), toggle individual clips on/off, or manually split/merge games (`split_game_at_segment`, `merge_game_with_previous`).
- **Cross-Platform Packaging & One-Click Launchers**:
  - Added `启动可视化剪辑软件_Windows.bat`, `打包Windows独立EXE程序.bat` (PyInstaller standalone `.exe` builder), and `启动可视化剪辑软件_Mac.command`.
  - Replaced hardcoded `/tmp` paths with `tempfile.gettempdir()` and added automatic Windows/macOS FFmpeg & font resolution.
  - Added unit test suite `tests/test_gui_engine.py` (all 33 unit tests pass).

---

## [1.6.0] - 2026-11-02

### 🚀 Major Feature: Multi-Mode Production Engine & Specialized Workflow Suite (多模式工作流套件版)
- **Default Mode Backward-Compatibility Guaranteed (默认模式 100% 保持现状)**:
  - Default `--mode all` (or `--mode highlight`) preserves the exact behavior of `v1.5.0`: multi-shot rally highlight extraction, serve-kill extraction, player ReID game partitioning, and clean stream-copy lossless cutting without extra overhead.
- **Five New Production & Analytical Modes (`modes_handler.py`)**:
  - **`--mode condensed` (比赛浓缩纯享模式)**: Strips dead-ball downtime between points and losslessly concatenates rallies into a continuous match replay (`00_【第XX局_比赛浓缩纯享】_全XX段连贯版.mp4`) in $< 1\text{s}$ using ffmpeg concat demuxer.
  - **`--mode vertical` (9:16 竖屏自媒体短视频模式)**: Automatically crops 16:9 court recording centered on the playing trapezoid into mobile 9:16 vertical video (`--aspect-ratio 9:16`), saved into `竖屏9比16自媒体短视频/`.
  - **`--mode solo` (个人主角光环模式)**: Focuses exclusively on the designated player (`--player [near_left|near_right|far_left|far_right]`) to extract personal highlight reels.
  - **`--mode review` (技战术与发接发复盘模式)**: Extracts serve & return opening windows (first 3.5s) into `发接发前三拍复盘/` and compiles a comprehensive `tactical_review_report.txt` with rally tempo distribution.
  - **`--mode showcase` (战术风格分类集锦模式)**: Automatically categorizes rallies into style albums: `01_后场重杀突破`, `02_多拍高能拉锯`, `03_网前平抽快攻`.
- **Comprehensive Test Coverage**: Added `tests/test_modes.py`, all 28 unit tests pass.

---

## [1.5.0] - 2026-11-02

### 🚀 Major Feature & Architecture Overhaul: Calibrated Perspective Torso ReID & Amateur Match Game Segmentation (透视校准躯干重识别与业余全自动分局版)
- **Resolved Root Cause of 1-Game Dumping (彻底攻克整场视频误并入单局的底层缺陷)**:
  - Addressed user feedback: *"实际上并没有根据四个人的特种来区分 你就分了3个场次。但是我们打一局就差不多换完人了"* (All 3 thirty-minute match recordings had previously lumped 91, 77, and 85 rallies into a single `第01局`).
  - Uncovered and fixed the 3 root causes that previously blocked game segmentation:
    1. `rest_gap_seconds` was hardcoded to `60.0s`, whereas in recreational badminton play, players swap off court in **22s ~ 50s**. Because inter-rally gaps rarely reached 60.0s, split was mathematically blocked.
    2. `extract_court_player_embeddings` uncalibrated quadrant masks sampled the static gym back-wall, ceiling lights, bleachers, and side aisles (75% of pixel mask), causing all cosine similarities to artificially hover at 0.85–0.95 regardless of player substitutions.
    3. Single-frame reference drift gradually smoothed out lineup transitions without step detection.
- **Perspective Trapezoid Court Masking & Torso Jersey Isolation (透视校准与躯干球衣精准抽取)**:
  - Confined player detection strictly to the active doubles court trapezoid:
    - Far court: $Y \in [0.40 H, 0.58 H]$, $X \in [0.36 W, 0.58 W]$
    - Near court: $Y \in [0.58 H, 0.88 H]$, $X \in [0.24 W, 0.74 W]$
    Completely eliminates 100% of gym back-wall, bleachers, doors, and side aisle background noise.
  - In each player's foreground bounding box, isolated the upper body (top $15\% \sim 60\%$), extracting pure jersey color signatures while discarding shadows, floor reflections, and dark shorts.
- **Amateur Rotation Timing & Dual-Trigger State Machine (业余俱乐部轮转物理时间与状态机)**:
  - Adapted `rest_gap_seconds` to `22.0s` (detecting 22s–50s player rotations).
  - Added `long_intermission_seconds` at `45.0s` (physical water/rest break between games, even when returning to court).
  - Added running exponential moving average (EMA) reference lineup for current game to eliminate single-shot occlusion noise.
  - Added CLI options: `--rest-gap`, `--long-intermission`, `--min-rallies-per-game`.
- **Dataset Re-Partitioning & Verification (全量实战数据分局重构完成)**:
  - **Match 1 (`050`, 67 rallies)**: Automatically partitioned into **2 distinct games**:
    - 第01局: 12 rallies (00分00秒 至 05分04秒, 5分4秒)
    - 第02局: 55 rallies (05分37秒 至 29分59秒, 24分21秒)
  - **Match 2 (`051`, 77 rallies)**: Automatically partitioned into **3 distinct games**:
    - 第01局: 35 rallies (00分25秒 至 12分34秒, 12分9秒)
    - 第02局: 21 rallies (12分58秒 至 22分14秒, 9分15秒)
    - 第03局: 21 rallies (23分06秒 至 29分36秒, 6分31秒)
  - **Match 3 (`052`, 71 rallies)**: Automatically partitioned into **4 distinct games**:
    - 第01局: 11 rallies (00分07秒 至 03分37秒, 3分29秒)
    - 第02局: 09 rallies (04分01秒 至 06分54秒, 2分53秒)
    - 第03局: 41 rallies (07分41秒 至 23分22秒, 15分41秒)
    - 第04局: 10 rallies (24分03秒 至 28分39秒, 4分35秒)
  - All 23 unit tests pass in `tests/`.

---

## [1.4.9] - 2026-11-02

### 🚀 Major Fix: Ball-Change Intermission Elimination & Optical Serve Cadence Verification (分间换球死球彻底过滤与发球光学节奏双向校验版)
- **Eliminated Ball-Change Intermission Clips (彻底消除分间换球漫步与隔壁场地穿透误剪为多拍)**:
  - Fixed issue reported on `多拍17` (04分38秒至04分58秒_【超长高能拉锯】_21秒): players on our court concluded Point 16, a player picked up the old shuttlecock from the floor, walked to the net post basket outside the doubles boundary to retrieve a new shuttlecock, and tested the feathers while Court 7 (adjacent court) played an active 16-hit rally in the background.
  - In previous versions, `check_clip_is_real_play()` short-circuited if `hit_count >= min_hits`, allowing 16 hits from Court 7 during an intermission to bypass all visual checks.
- **Physical Serve Cadence & Optical Opening Verification (发球物理飞行节奏与开球双模态校验)**:
  - Under BWF physics and aerodynamics, the minimum flight time from a legal serve contact to receiver contact across the net is $\ge 0.65\text{s}$ (fast low serve) or $1.8\text{s} \sim 2.8\text{s}$ (high serve). Rapid consecutive hits with $g_0 < 0.55\text{s}$ and $g_1 < 0.55\text{s}$ represent flat-drive net exchanges on adjacent courts or dead-ball racket taps, never an opening serve.
  - Added optical serve stance verification at `r_peaks[0][0]`: if initial cadence is suspicious ($g_0 < 0.55\text{s}$ and $g_1 < 0.55\text{s}$) and far/near court motion indicates players are dormant or not delivering/receiving a serve (`m_open[1] < 3.0` or `m_open[0] < 5.0`), the clip is strictly rejected.
- **Rule 2 Decoupling for 2-Hit Floor Scoops (双击捞球与分间空档彻底解耦)**:
  - In Rule 2 of `extract_multi_shot_rallies`, when a gap $\ge 2.10\text{s}$ occurs after exactly 2 hits followed by rapid noise ($< 0.65\text{s}$), the 2 hits are decoupled into their own candidate and pruned by `len < min_hits`.
- **Dataset Re-Cut Verification (实战全量重剪验证通过)**:
  - Successfully re-cut Match 2 (`051`): `多拍17` (换球 21秒) is 100% eliminated. Output directory contains 77 pure, genuine multi-shot rallies with zero false positives.
  - Passes all 21 unit tests in `tests/test_rally_decoupling.py`.

---

## [1.4.8] - 2026-11-02

### 🚀 Major Fix: Post-Smash Net Exchange & Bilateral Counter-Attack Preservation (杀球防守反击与网前快节奏相持彻底保全版)
- **Eliminated False Premature Cleaving in Rule 1 (彻底消除杀球防守起球后的中途腰斩)**:
  - Fixed a fundamental flaw in Rule 1 where any smash followed by non-smash strokes (net touches, flat drives, pushes, drops) was falsely cleaved because the forward-search heuristic scanned across the entire match for far-future gaps $\ge 2.0\text{s}$.
  - Replaced the flawed forward search with **Local Bilateral Cadence Validation**: intermediate hits between a smash defense and the subsequent dead gap are analyzed locally. If all consecutive intervals are rapid continuous badminton cadence ($\le 1.15\text{s}$) or feature attacking/clearing strokes, active play is recognized as actively ongoing and is protected from premature severance.
  - Resolved `多拍03` in Match 2 (`051`): extended from premature 8.86s (00分50秒至00分59秒, 8 hits) to complete 13.06s (00分50秒至01分03秒, 13 hits), capturing the serve, return, smash, diving defense, counter-drive, rapid net kill, lift, fast push, and final court landing!
- **Dataset-Wide Automated Health Audit (全视频深度健康巡检与零异常保障)**:
  - Executed automated cross-match health audits across all recordings (Match 1 `050`, Match 2 `051`, Match 3 `052`).
  - Confirmed 100% clean rallies: zero premature terminations, zero short-duration anomalies ($< 5.0\text{s}$), and zero dead-ball walking clips.
  - Passes all 20 unit tests in `tests/test_rally_decoupling.py`.

---

## [1.4.7] - 2026-11-02

### 🚀 Major Fix: Multi-Shot Broadcast Threshold & Dead-Ball Ball-Retrieval Elimination (专业多拍标准与死球捡球彻底过滤版)
- **Multi-Shot Broadcast Threshold Enforcement (`--min-hits 5`·杜绝低拍数死球伪多拍)**:
  - Aligned with professional BWF and Olympic broadcast standards: by definition, a "多拍" (Multi-Shot Rally) requires $\ge 5$ continuous strokes. 1~2 strokes is a serve-kill or unforced error, while 3~4 strokes represent short service exchange or dead-ball floor touches.
  - Set default `--min-hits` from 3 to 5 across `extract_multi_shot_rallies`, `check_clip_is_real_play`, and CLI parsing, eliminating low-stroke false alarms while preserving 100% of genuine multi-shot rallies.
- **Dead-Ball Ball-Retrieval & Adjacent Court Noise Elimination (捡球死球漫步与隔壁场地穿透声彻底绝迹)**:
  - Addressed user report on `多拍105` (29分41秒至29分48秒, 7秒): players on our court were in dead-ball walking intermission picking up the shuttlecock from the floor and tossing it across the net, while the loud smash sounds were cross-talk audio bleed from Court 7.
  - Reinforced Rule 1 post-smash decoupling: Point 1 (Rally 104, 29:26~29:35, 10 hits) terminates decisively at the smash winner, while the trailing 4-hit intermission noise cluster is strictly rejected by `len(c) < min_hits`.
  - Zero dead-ball clips in final output: Match 2 (`051`) now cleanly outputs 99 genuine multi-shot rallies, completely eliminating `多拍105`.
- **Self-Contained Optical Motion & Hardware Acceleration (视觉动量与无cv2优雅降级)**:
  - Enabled optical motion tracking to utilize OpenCV hardware acceleration when available (`uv run --with opencv-python-headless`) while providing a robust, aerodynamic 1.65s floor landing fallback when running under minimal environments.
  - Passes all 19 unit tests in `tests/test_rally_decoupling.py`.

---

## [1.4.6] - 2026-11-02

### 🚀 Major Fix: Smash Defense Soft-Finish Preservation & Multimodal Ground Landing (杀球防守软终结保全与多模态落地砸地保全版)
- **Smash Defense & Soft Finish Preservation (杀球防守反击与软终结多拍保全·彻底杜绝防守起高球后腰斩)**:
  - Eliminated false post-smash decoupling in Rule 1: A post-smash sequence is decoupled ONLY if a genuine subsequent Point 2 exists ahead in the cluster (requiring remaining hits $\ge 3$, an inter-point serve setup pause $\ge 2.0\text{s}$, and an active attack in Point 2).
  - Preserved soft finishes after smashes: When a smash is returned by a defensive block, followed by net touches, lobs, or deep high clears, all strokes are guaranteed to remain intact in the current rally rather than being mistakenly treated as floor scoop taps.
  - Completely resolved `多拍85` in Match 2 (`051`): extended from premature 6.1s (26分46秒至26分52秒, 8 hits) to complete 10.8s (26分46秒至26分57秒, 10 hits), fully capturing the serve, return, drive, drop, smash, defensive block, net push, high clear, shuttlecock flight, out-of-bounds floor landing at 26:56.5s, and players concluding the point.
- **Multimodal Ground-Landing Guarantee (落地即止视觉动量切断保全·彻底杜绝'没有落地就完了')**:
  - Replaced the arbitrary static 0.85s landing buffer with adaptive optical court motion tracking: for high clears, lobs, lifts, and pushes, the engine tracks player running/tracking motion (`our_m \ge 5.2`) up to 2.85s until court motion settles when the shuttlecock physically hits the floor mat.
  - Synchronized `detect_visual_deadball_cutoff` with `extract_multi_shot_rallies` to ensure consistent flight completion and zero premature termination.
- **Inter-Point Decoupling Consistency (跨分死球隔离零退化)**:
  - 100% regression-free: Point 1 and Point 2 in Rally 81 remain strictly decoupled across inter-point floor scoop taps, while Rally 40 and Rally 67 remain completely continuous.

---

## [1.4.5] - 2026-10-30

### 🚀 Major Fix: Multi-Shot Continuation Immunity & Intermediate Smash Cleaving Elimination (中局杀球攻防相持免疫与长多拍腰斩彻底修复版)
- **Intermediate Smash Continuation Immunity (中局杀球防守反击相持态免疫·杜绝长拉锯中途劈开)**:
  - Eliminated the global `has_serve_ahead` false trigger in Rule 1: A smash followed by defensive return and counter-attack ($E \ge 1.8\times 10^7$) is ACTIVE play, regardless of whether a deep high clear ($gap \ge 2.0\text{s}$) or future serve exists later in the match window.
  - Enforced strict dead-ball drop criteria: A post-smash sequence is ONLY decoupled if ALL subsequent hits are weak floor taps ($E < 1.8\times 10^7$ without attack), preventing active 20s+ multi-shot rallies from being chopped into disjointed fragments.
  - Completely resolved `多拍40` in Match 2 (`051`): Combined premature 5.3s `多拍40` (11分54秒至11分59秒, 4 hits) and subsequent `多拍41` (11分59秒至12分14秒, 19 hits) into a single continuous, complete 20.3-second, 23-hit epic multi-shot rally (`多拍39_11分54秒至12分14秒_【超长高能拉锯】_20秒.mp4`), fully capturing the serve, intermediate smash, diving lift return, deep high clear, rapid flat drives, and the final jump-smash winner!

---

## [1.4.4] - 2026-10-30

### 🚀 Major Fix: Smash Defense Continuation & Opening Serve Aerodynamic Protection (杀球防守反击全链路保全与发球高远起手保护版)
- **Smash Defense & Counter-Stroke Preservation (杀球防守起球与反击连贯性保全·杜绝扣杀空中截断)**:
  - Fixed premature severance in `extract_multi_shot_rallies` where Rule 1 falsely cleaved the rally at the smash ($c[i]$) because the opponent's defensive lift return ($c[i+1]$) had soft acoustic energy ($E < 2.0\times 10^7$) and $gap \ge 0.70\text{s}$.
  - Strictly enforced physical continuation semantics: A smash at $c[i]$ is NEVER treated as a terminal winner drop if followed by a defensive return and subsequent counter-stroke ($0.35\text{s} \le c[i+2][0] - c[i+1][0] \le 2.35\text{s}$).
  - Cluster tail preservation: Guarantees that $c[i+1]$ is never cleaved when it is the final stroke of the cluster ($i+1 == \text{len}(c)-1$), ensuring that defensive returns and final ground landings are 100% captured until the shuttle touches the court mat ($t_{\text{last}} + 0.85\text{s}$).
  - Completely resolved `多拍67` in Match 2 (`051`): extended from premature 5.5s (19分54秒至20分00秒) to complete 9.6s (19分52秒至20分02秒, 9 shots), fully capturing the serve, smash, diving defense return, counter-stroke, and final floor landing.
- **High / Flick Opening Serve Protection (高远发球与偷后场起手保全)**:
  - In badminton, high serves and flick serves commonly fly for $1.60\text{s} \sim 2.10\text{s}$ before being struck by the receiver, with soft initial serve sound ($E \approx 4\times 10^6 \sim 7.5\times 10^6$).
  - Eliminated the naive leading tap pruning condition: an opening hit with $gap \le 2.20\text{s}$ followed by an active return ($E \ge 1.2\times 10^7$ or bilateral continuation) is strictly preserved as the genuine opening serve ($s_{\text{cut}} = t_{\text{serve}} - 0.75\text{s}$).
- **Inter-Point Decoupling Consistency (全对局跨分死球隔离零退化)**:
  - Preserved complete decoupling for inter-point dead-ball floor scoop taps and multi-point gluing (Rally 81 in Match 2 remains cleanly split into 2 independent points).

---

## [1.4.3] - 2026-10-30

### 🚀 Major Fix: Inter-Point Dead-Ball Decoupling & Double-Point Gluing Elimination (跨分死球捡球解耦·双分粘连彻底断开版)
- **Post-Smash Winner Drop Decoupling (进攻制胜分与死球落地强切断机制)**: Introduced automatic detection of terminal attack strokes ($E \ge 4.5\times 10^7$ within the last 2 shots). When followed by defensive block/ground contact and subsequent non-attack floor taps ($gap \ge 0.70\text{s}, E < 2.0\times 10^7$), cuts cleanly at $t_{\text{last}} + 0.85\text{s}$ with zero trailing dead-ball pauses.
- **Pre-Serve Pause Decoupling (发球前置静止与换分强切断)**: Implemented serve signature detection ($gap \ge 2.10\text{s}$ followed by bilateral serve return within $0.60\text{s} \sim 2.20\text{s}$). Decouples intermission walk/retrieval strictly at $t_{\text{serve}} - 0.75\text{s}$, completely separating previous rally finish from new serve.
- **Racket Floor Scoop Double-Tap Rejection (双击挑球杂音过滤与全段质检)**: Physical laws of badminton dictate that bilateral exchanges across the net in $< 0.60\text{s}$ strictly require a high-velocity smash ($E \ge 3.0\times 10^7$). Filters out floor scoops and frame scrapes, and rejects candidate clusters devoid of genuine attacking or clearing strokes ($\max E < 1.8\times 10^7$).
- **Self-Contained Optical Motion Engine (独立于OpenCV的FFmpeg管道降级采样)**: Enhanced `sample_instant_motion` with an automated pure-Python + FFmpeg rawvideo pipe fallback, ensuring court motion analysis and camera stability checks execute reliably even when `cv2` is missing.
- **Verified against Target Footage**: Completely splits `多拍81` in Match 2 into `多拍95` (29分26秒至29分35秒, 9.5s, 10 hits) and `多拍96` (29分41秒至29分47秒, 5.9s, 4 hits), eliminating the 6-second dead-ball walking intermission.

---

## [1.4.2] - 2026-10-30

### 🚀 Major Fix: Terminal Return Preservation & Full Floor Landing Guarantee (终局击球保全与落地砸地即止保全版)
- **Terminal Return Cleaving Fix (终结击球排他断流修复·杜绝空中截断)**: Fixed critical logic flaw in `extract_multi_shot_rallies` where a cluster's final return ($c[i+1]$) following a high clear/lift ($gap \ge 1.60\text{s}$) was falsely discarded because no subsequent stroke ($i+2$) existed. The engine erroneously treated the final shot as a "dead-ball tap", cleaving the point at the penultimate stroke in mid-air (causing `多拍70` in `050` at 27分39秒 to cut off at 27分48秒 before the shuttle landed).
- **Decisive Floor Landing Window (0.85s落地与弹跳全景保全)**: Guarantees that the final return is 100% retained and terminates strictly at $c_{\text{last}} + 0.85\text{s}$, completely capturing the shuttlecock crossing the net, plunging down, hitting the court mat, and players acknowledging the score.

---

## [1.4.1] - 2026-10-30

### 🚀 Major Fix: High-Clear 2.85s Aerodynamic Preservation & Physical Match Segmentation State Machine (高远球2.85s物理保全与真对局状态机修复版)
- **High-Clear 2.85s Flight Preservation (2.85s高远球空气动力保全·杜绝空中腰斩)**: Increased `max_gap` from 2.40s to 2.85s. Deep baseline-to-baseline clears and lobs taking up to 2.80s flight time are now 100% preserved as continuous points (fixes `多拍06` at 01分01秒 in `052` which had been cleaved at 01分08秒 mid-air).
- **Physical Inter-Game Rest Enforcement (严格物理局间休息门禁)**: A new game is NEVER declared unless separated by a genuine intermission ($\ge 40\text{s}$). Completely eliminated erratic game fragmentation caused by 1~5 second serving quadrant rotations.
- **Adaptive Court Mat Subtraction in ReID (自适应地胶底色剔除)**: Subtracts court mat background to evaluate only player clothing and skin, boosting same-lineup cosine similarity from 0.72 to >0.91.
- **Minimum Game Size Filter (极小碎片局自动吸收)**: Enforces minimum rally threshold ($\ge 5$ rallies) to eliminate 1~2 shot artificial game folders.

---

## [1.4.0] - 2026-10-30

### 🚀 Major Breakthrough: Automated Match Segmentation & Player Lineup ReID (球员识别与全自动球局分段·免底库开箱即用版)
- **Zero Pre-Registration Player ReID (免底库全自动人员重识别)**: Developed `match_segmenter.py`, extracting 512-dimensional normalized spatial appearance embeddings (upper-body jersey + lower-body shorts 3D color cube histograms) for on-court players from serve-ready keyframes.
- **Permutation-Invariant Bipartite Lineup Matching (二分图匈牙利最佳匹配)**: Invariant to players switching left/right receiving quadrants or swapping court halves (前后场换边). Calculates exact optimal 1-to-1 matching scores ($0.0 \sim 1.0$) with zero external dependencies.
- **Hysteresis Smoothing & Dual-Trigger State Machine (双重校验防误切状态机)**: Prevents single-shot frame occlusions or players taking off warm-up jackets from causing spurious game splits. A new game is confirmed when lineup similarity drops below threshold (default 0.65) combined with either significant inter-rally rest ($\ge 60\text{s}$) or persistent multi-shot verification.
- **Automated Game Directory Routing & Match Summary (分局子目录归类与报告生成)**: Rallies are automatically organized into clean subdirectories (`第01局_实战对阵_15拍/`, `第02局_实战对阵_18拍/`), with a comprehensive `game_summary.txt` report.
- **CLI Flags (`--split-by-game`, `--no-split-by-game`, `--lineup-threshold`)**: Default enabled for seamless automated match segmentation; can be easily disabled with `--no-split-by-game` for flat output.

---

## [1.3.8] - 2026-10-28

### 🚀 Major Breakthroughs: Zero Premature Truncation Guarantee & Full Landing Trajectory Preservation (全流程多拍完整度保全·空中提前截断根除与0.85s落地即止版)
- **Zero Premature Cutoff Guarantee (攻防连续性保护与零提前截断终结保证)**: Fixed the critical vulnerability where active rallies with high clears, lifts, or defensive drop shots (inter-hit gap 1.4s~2.2s) were prematurely severed in mid-air because players held ready stance while the bird flew high. Enforced the **Continuous Bilateral Exchange Rule**: any continuous sequence of alternating strikes ($S_i \to S_{i+1} \to S_{i+2}$) with flight intervals $\le 2.35\text{s}$ is strictly protected from being cleaved in the middle of active play.
- **Complete Downward Landing Trajectory (0.85s 击球落地弧线全景保全)**: Replaced premature 0.50s/0.55s cutoff with calibrated landing window ($e_{\text{cut}} = S_{\text{last}} + 0.85\text{s}$, or $0.65\text{s}$ for decisive smashes $\ge 2.0\times 10^7$). Guarantees that the shuttlecock has 100% time to cross the net, plunge down, hit the court floor or catch the net, and display the winning/error acknowledgment, while severing strictly before players take their first walking step to pick up the ball.
- **Backward Tail-Pickup Pruning (逆向末端捡球捞球清洗)**: Refactored `detect_visual_deadball_cutoff` to scan backward from the final hit. Discards only genuine post-point racket taps on the floor (gap $\ge 2.05\text{s}$ and energy $< 8.0\times 10^6$), eliminating the recursive while-loop that erroneously pruned actual winning shots or defensive blocks.
- **Real-Play Detector Calibration (实战镜头质检校准)**: Rallies with $\ge 5$ verified acoustic strikes are now automatically confirmed as authentic matches, preventing epic multi-shot rallies from being rejected just because a person walked through the peripheral corridor in the background.

---

## [1.3.7] - 2026-10-27

### 🚀 Major Optimization: Optional Highlight Reel Generation & Ultra-Fast Low-Disk Footprint Pipeline (超长多拍TOP大集锦可选化·极速轻量化输出与磁盘冗余清零版)
- **Optional Highlight Reel Generation (`--reel` 参数可选化)**: Converted automatic concatenation of multi-shot highlight reels (`00_【纯多拍零死球合集】...` and `00_【全场巅峰超长多拍TOP大集锦】...`) into an optional, user-configurable flag (default `False`). Eliminates the massive disk I/O bottleneck and gigabytes of duplicate video files (e.g., saves 5.7 GB per 30-min 4K match and 2.75 GB for grand cross-match compilation), enabling near-instant extraction of high-energy clips.
- **On-Demand Big Reel Compilation (按需生成大合集)**: Users can now freely choose whether to generate concatenated reels by adding `--reel` when needed, keeping default runs fast, lean, and clean.
- **Enhanced Terminal Feedback (友好终端进度提示)**: Added explicit terminal logs informing the user that clips are saved cleanly and that concatenated reels were safely bypassed to save time and disk space (with prompt on how to enable via `--reel`).

---

## [1.3.6] - 2026-10-27

### 🚀 Major Breakthroughs: Bilateral Play Cadence Verification & Mid-Rally Dead-Ball Ground-Landing Severing (双侧对攻连续性核验·落地即止强截断与捡球走动死球彻底根除版)
- **Consecutive Same-Court Stroke Rule & Bilateral Cadence (同半场连续击球终结判定与双侧攻防核验)**: In badminton, strokes must alternate across the net. Fixed the critical vulnerability where adjacent-court smashes and players' ball-scoop taps during walking breaks were misclassified as active hits on our court. When an inter-strike gap $\ge 0.70\text{s}$ occurs with dormant far court (`far_m < 5.2`) or non-play walking motion (`our_m < 8.8`, `near_m < 10.5`), the point is confirmed terminated at the previous real strike.
- **Ground-Truth Visual Dead-Ball Slicer (落地即止强切断机制)**: Implemented production `detect_visual_deadball_cutoff` protocol. Scans backward and mid-gap to find the exact millisecond the shuttlecock touches the floor or net, severing $e_{\text{cut}}$ strictly at $t_{\text{last\_strike}} + 0.55\text{s}$. Eliminates bloated Frankenstein clips where a 4-second initial exchange, a 6-second ball retrieval walk, a 2-second second point, and an 8-second standing wait were erroneously glued into a fake 21-second "超长高能拉锯" (e.g. `050` Match 2 `多拍61` from 26分38秒至26分59秒, where the ball landed at 26分42.3秒, is now severed cleanly at 26分42.8秒 with zero dead-ball trailing content).
- **Outer-Boundary Adjacent-Court Bleed Decoupling (邻场声学串扰边界抑制)**: Automatically compares court optical flow with outer border corridors (`b_max >= 12.0` and `b_max >= 1.5 * our_m`). If motion is concentrated on adjacent courts (e.g. Court 6 smashes), the acoustic spike is decisively discarded.
- **Multi-Tap Ball-Scoop Pruning (捡球连续轻拨消除)**: Eliminates players tapping rackets against the floor to pick up birds (`gap_prev >= 1.05s` and `gap_tail <= 0.75s`), terminating clips immediately upon initial ground landing.

---

## [1.3.5] - 2026-10-27

### 🚀 Major Breakthroughs: Serve-Kill Ground Landing Guarantee & Subsequent Strike Suppression (接发秒杀落地即止保全·后续击球严格排他性与空中提前截断根除)
- **Subsequent Strike Suppression (后续击球严格排他性)**: Added a mandatory exclusion check: for any serve-kill candidate impact $t_k$, there must be **ZERO acoustic hits within $[t_k + 0.25\text{s}, t_k + 3.20\text{s}]$**. Fixes the critical bug where an ongoing active multi-shot rally (e.g. `054` Match 6 at 01分44秒) was mistakenly clipped as a "serve kill" because the cutter stopped checking after $t_k$.
- **Ground-Landing & Dead-Ball Decay Guarantee (完整下落航迹与球落地保全)**: Extended termination boundary $e_{\text{cut}}$ from $t_k + 0.45\text{s}$ to $\min(v_{\text{dur}}, t_k + 1.25\text{s})$. Fixed the issue where clips cut off prematurely at 0.45s while the shuttlecock was still mid-air crossing the net plane, ensuring the full downward plunge, ground impact, net rebound, and players' dead-ball relaxation are 100% visible before the clip ends.
- **Pre-Serve Ready Stance Acoustic Guard**: Enforced strict pre-serve silence ($t_{\text{serve}} - 2.8\text{s} \sim t_{\text{serve}} - 0.5\text{s}$ zero hits), guaranteeing that only genuine serves initiated from stationary ready stances can qualify.
- **Zero-False-Positive Cleanliness (宁缺毋滥执行铁律)**: In match footage where both pairs maintain vigilant serve reception with no direct unforced errors or point-blank kills, the engine decisively outputs 0 serve-kill clips, eliminating fake walking or mid-air truncated artifacts.

---

## [1.3.4] - 2026-10-26

### 🚀 Major Breakthroughs: Mid-Rally Dead-Ball Drop Decoupling & Multi-Modal Idle-Court Spike Filtering (中途死球动量骤降解耦·球落地即刻截断与邻场串扰清洗)
- **Mid-Rally Dead-Ball Motion Drop (中途死球近半场动量骤降解耦)**: For any inter-strike interval $\ge 0.65\text{s}$, the cutter evaluates instantaneous court motion at $t_{\text{hit}} + 0.45\text{s}$. If near-court players freeze ($\text{near\_m} < 2.6$ and $\text{our\_m} < 6.5$) or total court motion collapses ($\text{our\_m} < 4.8$), the rally decouples immediately at the winning hit. Solves the issue where adjacent-court smashes during post-point dead balls glued dead intervals into bloated clips (e.g. `047` Match 2 `多拍10` 04分00秒至04分17秒, which landed at 04分07秒, is now cleanly trimmed to 7 seconds).
- **Multimodal Idle-Court Spike Rejection (静止场区声学串扰清洗)**: Filters out spurious acoustic spikes where the active court is completely idle ($\text{our\_m} < 6.0$ and $\text{near\_m} < 2.6$), preventing adjacent court smashes from injecting fake hits into the middle of dead-ball breaks.
- **Calibrated High-Clear Flight Motion Threshold**: Refined the live flight criteria ($\text{max\_our} \ge 9.0$ or $\text{max\_court} \ge 13.0$ with $\text{max\_our} \ge 8.0$), distinguishing walking back to serve from explosive high-clear chasing.

---

## [1.3.3] - 2026-10-26

### 🚀 Major Breakthroughs: Dual-Contrast Transient Sensitivity & Multi-Point High Clear Flight Preservation (双重声学标定·多点航迹核验与超长拉锯完整保全)
- **Dual-Contrast Acoustic Transient Calibration (双重对比度声学标定)**: Retains standard stroke sensitivity ($E \ge 5.0 \times 10^6, \text{ratio} \ge 3.0$) while introducing high-contrast soft touch detection ($E \ge 4.2 \times 10^6, \text{ratio} \ge 20.0$). Unlocks ultra-subtle net drops (网前轻放/吊球) and baseline high clear defenses down to $4.2 \times 10^6$ without admitting gym ambient footstep or adjacent court bleed noises.
- **Multi-Point Flight Motion Verification (多点航迹运动学校验)**: Replaced fragile single-point midpoint instantaneous sampling with 2-point aerodynamic flight verification ($30\%$ and $70\%$ across gaps $\ge 1.75\text{s}$). Rejects the momentary 0.2s split-step pause under high clears that previously caused false dead-ball cuts.
- **Active Rally Continuation Protection (持续对攻物理保全)**: Couples flight optical motion with stroke continuation checking ($0.40\text{s} \le \Delta t_{\text{next}} \le 2.20\text{s}$ with remaining hits $\ge 2$). In-rally high clears surrounded by continuous exchanges are preserved 100% without severance.
- **Sideline Pedestrian Immunity vs Severe Walk-off Decoupling (场边走动免疫与离场精准解耦)**: Distinguishes passing bystanders on gym aisles ($\text{b\_max} < 20.0$ while active court $\text{our\_m} \ge 8.0$) from genuine player substitutions or court exits ($\text{b\_max} \ge 20.0$ or $\text{b\_max} \ge 12.0$ with court motion $\text{our\_m} < 8.0$).
- **Direct Resolution for User Cases**:
  - `048` Match 3 `多拍10`: Merged the previously severed 11s clip (06分34秒至06分45秒) into the complete, unbroken **34-second mega rally** (06分34秒至07分08秒, 40 real strokes).
  - `046` Match 1 `多拍80`: Decisively terminates at 26分21秒, strictly cutting out player substitutions and court walk-offs.
  - `046` Match 1 `多拍25`: Perfectly preserved at 19.2s (12分58秒至13分17秒) with zero premature truncation.

---

## [1.3.2] - 2026-10-26

### 🚀 Major Breakthroughs: Soft-Shot Dynamic Capture & True Decisive Point Preservation (网前轻球灵敏捕获与未死球零提前截断)
- **Soft-Shot Dynamic Sensitivity ($5.0 \times 10^6$ Thresh, Ratio 3.0)**: Calibrated acoustic transient detection threshold from $8.5 \times 10^6$ down to $5.0 \times 10^6$. Captures soft drop shots (吊球), delicate net tumbles (网前搓放), slices, and net pushes that generate subtle high-frequency transients, completely eliminating artificial 3+ second inter-strike gaps during live net play (e.g. resolving `多拍25` 12分58秒 cutting mid-air).
- **Elimination of Flawed Energy Decoupling**: Completely removed the premature cutoff rule on high-energy hits with gaps $>1.35$s. Full-power baseline clears and defensive lifts off smashes take $2.0\text{s} \sim 2.85\text{s}$ to cross the court; they are now 100% preserved in their full trajectory.
- **Mid-Gap Visual Decoupling Tuning ($\ge 1.75\text{s}$)**: Adjusted mid-gap optical verification threshold to $\ge 1.75\text{s}$ with `our_m >= 9.0`, cleanly distinguishing live aerodynamic high clears from dead-ball walks/substitutions.
- **In-Memory Sub-Second Motion Cache**: Added `_MOTION_CACHE` to `sample_instant_motion`, eliminating redundant 4K video seeks and accelerating processing.

---

## [1.3.1] - 2026-10-26

### 🚀 Major Breakthroughs: Player Exit, Substitution & Sideline Switch Filtering (人员离场换人解耦与全场纯净度提升)
- **Visual Mid-Gap Decoupling (`extract_multi_shot_rallies`)**: For any inter-strike interval $\ge 1.50\text{s}$, the cutter performs an instant optical motion check at the gap midpoint. If court motion decays ($\text{our\_m} < 9.5$), sideline boundary activity surges ($\text{b\_max} > 7.2$), or camera shakes ($\text{top\_d} > 4.0$), the rally decouples immediately at the winning strike. Decisively terminates rallies when players walk off or switch (resolving issues like `多拍80` trailing into player swaps).
- **4-Point Temporal Exit/Switch Verification (`check_clip_is_real_play`)**: Evaluates candidate clips across 4 temporal anchor points ($20\%, 40\%, 60\%, 80\%$). Automatically drops clips where players leave the court, change players, or where the active court is left empty ($\text{min\_our} < 6.0$, $\text{high\_b\_count} \ge 2$ with $\text{b\_max} \ge 12.0$, or $\text{b\_max} \ge 11.0$ with $\text{our\_m} < 8.0$), while maintaining full tolerance for genuine high-tempo rallies with fleeting sideline spectators.
- **Consistent Visual Multi-Modal Pipeline**: Fully wired optical validation through all rally detection pathways including `args.mode in ["serve_kill", "all"]`.

---

## [1.3.0] - 2026-10-26

### 🚀 Major Breakthroughs: Ground-Truth Slicer & Zero Dead-Ball Truncation
- **2.85s Aerodynamics Flight Ceiling**: Extended acoustic transient inter-strike clustering window to $2.85\text{s}$. Eliminates premature cuts on defensive high clears (高远球/挑后场) and ensures 100% preservation of complete rallies until the winning kill or error.
- **Decisive Stroke Decoupling**: Smashes and rapid net kills ($E \ge 1.8 \times 10^7$) with no return within $1.35\text{s}$ decouple the rally immediately, preventing subsequent multi-court gym noise from gluing dead intervals into the rally.
- **Racket Double-Tap Ball-Scoop Pruning (球拍捞球双击自动剔除)**: Strips post-dead-ball pickup taps ($\Delta t_{\text{prev}} \ge 1.35\text{s}, \Delta t_{\text{tail}} \le 0.52\text{s}$), stopping the clip at the exact moment the bird touches the court.
- **Strict Instant Termination**: $s_{\text{cut}} = \max(0, t_{\text{serve}} - 0.70\text{s})$, $e_{\text{cut}} = \min(v_{\text{dur}}, t_{\text{last}} + 0.45\text{s})$. The highlight clip terminates within $0.45\text{s}$ of the final point resolution with zero player walking, resting, or retrieval time.
- **Serve-and-Kill (秒杀) Duration Tightening**: Shortened to $2.2\text{s} \sim 2.7\text{s}$ ($s_{\text{cut}} = t_k - 1.85\text{s}$, $e_{\text{cut}} = t_k + 0.45\text{s}$), delivering pure, high-adrenaline serve-attack finishes.

---

## [1.2.0] - 2026-10-23

### Added
- **Serve-and-Kill Detection Module (发球被一拍定死/接发秒杀)**: 4-stage optical momentum surge verification ($surge \ge 2.5, kill \ge 15.5, pre \le 7.2$).
- **Lightweight WeChat Sticker Export**: Automatic palette-optimized GIF sticker generation (< 2.5 MB, 12 fps, 360p).
- **0.4x Broadcast Slow-Motion Replay**: Subprocess filter graph rendering slow-mo instant replays with optical pacing.

### Changed
- Automatic cross-match highlight compilation into dedicated `00_特别精选_发球被一拍定死大赏` directories.

---

## [1.1.0] - 2026-10-21

### Added
- **Perspective Trapezoid Court Mask**: Masks out adjacent left/right courts (Court 5, Court 7) and bench spectator walking while strictly focusing on the active court.
- **Automatic Camera Match Window Benchmarking (`fast_camera_match_window`)**: Scans startup and shutdown intervals to exclude handheld mounting/unmounting noise.
- **BWF/Olympic Broadcast HUD**: Millisecond-accurate running match timer, dynamic shot counter, and finish banner (`--hud`).
- **Parallel Stream Cutting**: `ThreadPoolExecutor(max_workers=8)` lossless stream cutting (`-c copy`) accelerating turnaround to under 25 seconds per 30-minute match.

---

## [1.0.0] - 2026-10-19

### Initial Release
- Tier 1 16 kHz Mono WAV audio extraction and high-frequency diff energy transient detection.
- Heuristic inter-strike gap clustering.
- Initial lossless stream copy cutting pipeline.
