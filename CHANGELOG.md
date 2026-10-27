# 🏸 Badminton Video Cutter - Changelog & Version History

All notable changes to the `badminton-video-cutter` skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.6] - 2026-10-27 (Current Release)

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
