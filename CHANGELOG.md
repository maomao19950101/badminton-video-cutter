# 🏸 Badminton Video Cutter - Changelog & Version History

All notable changes to the `badminton-video-cutter` skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-10-26 (Current Release)

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
