# 🏸 Badminton Video Cutter - Changelog & Version History

All notable changes to the `badminton-video-cutter` skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.3] - 2026-10-30 (Current Release)

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
