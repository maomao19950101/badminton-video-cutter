---
name: badminton-video-cutter
description: 剪辑固定机位、有现场音轨的羽毛球比赛录像。提取多拍与接发短分候选，先分析时间轴、复核切点，再导出片段或合集；也支持估算分局、比例裁剪和本地剪辑工作台。支持 MP4、MOV、MKV 和 TS。
metadata:
  version: "1.9.0"
---

# 羽毛球比赛视频剪辑

## 工作流程

1. **检查素材与环境。** 使用用户指定的视频和输出目录；未指定输出目录时使用本次任务目录。确认 Python 3.10+、FFmpeg、NumPy、OpenCV 可用，优先复用已验证的环境。0 字节、大小变化或缺少 MP4 元数据可能表示仍在复制，不直接认定损坏。CLI 会先处理可读素材；仍在复制时可用 `--wait-for-input 300` 有限等待。没有现场音轨时不能进行本工具的自动分析。
2. **批量任务先分析。** 使用 `--analyze-only` 生成 `match_timeline.json`、`review_report.md` 和 `review_report.json`。默认模式 `all` 提取多拍与接发短分候选；不将候选数量表述为真实得分数。断点重试复用缓存，只有源素材或分析设置变化、或确需重扫时使用 `--rescan`。
3. **复核后导出。** 阅读复核报告，优先检查非法切点、重叠和长片段，再抽查普通候选及被过滤区间。看发球前、最后一拍及落地后的画面；长片段还要看中间是否停顿。遇到错误在工作台调整或编辑时间轴，然后用 `--timeline` 导出。长片段和重叠是复核提示，不据此自动删回合或压缩首尾。具体方法见 [质量复核](references/quality-review.md)。
4. **选择导出精度。** 默认保留源编码、分辨率和无字幕画面。流复制切点受关键帧影响；已人工调整且需要贴合切点时用 `--exact`。按需启用 `--reel`、`--hud`、`--slowmo`、`--gif`。拼接前处理或确认重叠，避免重复画面。
5. **验收并报告。** 检查文件可读、有所需音视频流，并抽查成品首尾。分别报告处理成功、无候选、尚未复制完成和执行失败；给出文件位置、候选数量与复核范围。文件可播放不等于内容正确。未逐段复核的结果仍标为候选，不承诺“零死球”或准确拍数；分局标为估算。

```bash
# 第一步：分析与复核报告；完整素材先处理，未完成复制的素材随后重试
python scripts/badminton_cutter.py -i "/path/to/videos" -o "/path/to/output" \
  --mode all --analyze-only --wait-for-input 300

# 第二步：复核并调整时间轴后，按单个源视频导出
python scripts/badminton_cutter.py -i "/path/to/match.mp4" -o "/path/to/output" \
  --timeline "/path/to/output/match-folder/match_timeline.json" --mode all

# 只检查旧时间轴，不重新解码或覆盖时间轴
python scripts/quality_review.py -i "/path/to/output" -o "/path/to/review"
```

## 模式选择

| 用户需求 | 参数与边界 |
|---|---|
| 多拍或接发短分候选 | `--mode duopai` 或 `--mode serve_kill` |
| 多拍纯享 | `--mode condensed`；默认至少 5 拍、5 秒，不是所有得分 |
| 比例转换 | `--mode vertical --aspect-ratio 9:16`；也支持 `1:1`、`16:9` |
| 个人高光 | 先标注主角站位，再用 `--mode solo --player near_left` 等 |
| 分类高光 | `--mode showcase`；依赖长回合或人工打法标注，证据不足归入未判定 |

接发短分检出为 0 时，先看 `analysis_diagnostics.serve_kill` 的逐层淘汰数。全场静音条件可能被邻场击球破坏；不要直接断言没有短分，也不要在没有视频对照时随意放宽阈值。旧时间轴缺少诊断字段时报告缺失，不填入推测数值。

依赖安装、工作台、缓存和导出并发见 [使用说明](README.md)。校准场地、连续动作识别和代理视频提速尚未实现；需要改算法时先按质量复核文档建立真实素材对照。
