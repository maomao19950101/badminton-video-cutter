# 羽毛球比赛视频剪辑工作室

将固定底线机位录制的羽毛球比赛转成回合时间轴和视频片段。使用现场音轨定位候选击球，再结合球场画面的运动变化估算回合边界。优先使用场地完整、机位稳定、主场地居中且击球声清楚的素材。邻场响声、遮挡和大幅晃动可能影响结果。

## 安装与启动

需要 Python 3.10+、FFmpeg、NumPy 和 OpenCV。安装 FFmpeg 后将它加入 PATH，或者设置 `BADMINTON_FFMPEG` 指向可执行文件。CLI 也支持 `--ffmpeg`。帧级精剪与比例裁剪需要 FFmpeg 支持 `libx264`，HUD 需要 ASS 字幕滤镜和可用字体。

在解包目录执行以下命令。推荐在虚拟环境安装依赖，也可用 uv 运行。

```bash
python -m pip install -r requirements.txt
python scripts/badminton_cutter.py --help
python scripts/codex_server.py
```

```bash
uv run --python 3.12 --with-requirements requirements.txt python scripts/badminton_cutter.py --help
```

macOS 可双击 `启动可视化剪辑软件_Mac.command`。Windows 可运行同包的 Windows 启动器。Web 工作台监听本机回环地址，首次启动会打开工作台窗口或浏览器。Tkinter 工作台也可用 `python scripts/badminton_gui.py` 启动，需要当前 Python 安装了 Tk。

## 使用方式

```bash
# 建议先分析并查看复核报告，再按时间轴导出
python scripts/badminton_cutter.py -i "比赛目录" -o "剪辑输出" --analyze-only --wait-for-input 300

# 先生成时间轴，批量确认前不写视频
python scripts/badminton_cutter.py -i "比赛.mp4" -o "剪辑输出" --analyze-only

# 复用已审核的时间轴，帧级精剪并输出比例转换视频
python scripts/badminton_cutter.py -i "比赛.mp4" -o "精剪输出" \
  --timeline "剪辑输出/场次目录/match_timeline.json" --mode vertical --aspect-ratio 9:16 --exact
```

- `all`（兼容别名 `highlight`）是默认模式。只要多拍或接发秒杀候选时用 `duopai` 或 `serve_kill`。
- `condensed` 将达到门槛的多拍片段拼成纯享视频，默认门槛为 5 拍、5 秒。低于门槛的短分仍会跳过。
- `vertical` 对前 5 个入选回合做居中裁剪，支持 9:16、1:1 和 16:9。
- `solo` 根据人工标注的回合主角站位筛选。先在工作台标注，再选“按时间轴导出”。CLI 可通过 `--timeline` 读取人工标注，`--player auto` 选中全部已有站位标注的回合。
- `showcase` 按长回合和手工标注的打法分组。未提供打法、也未达到长回合门槛的片段归入“打法未判定”。
- `--reel` 额外拼接合集。HUD、GIF 与慢动作单独开启。默认输出保留源视频分辨率与原编码。

时间轴中的 `lead_quadrant` 使用 0 近左、1 近右、2 远左、3 远右。未标注使用 `null`。`stroke_style` 使用 `smash`、`drive` 或空字符串。站位相对画面，换边后按当前画面重新标注。请人工复核算法估算的切点、拍数和局界。

## 剪辑速度

- 初次分析提取 16 kHz 音频、识别候选回合并缓存时间轴。同一源文件与分析设置的重复任务复用缓存。换文件、改分析设置或升级算法会重新分析。人工编辑与自动缓存分开存储。需要长期保存时保留导出目录中的 `match_timeline.json`。
- 只改输出模式、格式或精度时，工作台可直接“按时间轴导出”。CLI 可显式传入 `--timeline`，跳过分析步骤。强制重扫用 `--rescan`。
- 流复制默认 8 路并发，精剪默认 2 路。机械盘、网络盘或外接盘连续卡顿时，可用 `--jobs 2` 或 `--jobs 4` 对比。使用 `--no-split-by-game` 可跳过分局分析。
- 流复制速度快，切点受 GOP 影响。`--exact` 重新编码，让成品边界贴合时间轴帧。全程耗时随视频长度、编码、硬盘、候选数量与导出模式变化。

测试可用 `python -m unittest discover -s tests` 运行。需要 FFmpeg 的集成用例会在 FFmpeg 缺失时跳过。

历史变更见 [CHANGELOG.md](CHANGELOG.md)。

## 1.9.0 质量复核与输入检查

分析和导出会在场次目录生成 `review_report.md` / `review_report.json`，提示大于 30 秒的长片段、所有重叠对、非法切点与编号等问题。报告是复核清单，不是准确率认证，也不会自动修改切点。导出入口拒绝非法切点、无效时长和重复片段编号。分局与拍数均为估算；报告中的“回合数”不再误写成“拍数”。

旧时间轴可直接复核，无需视频依赖：

```bash
python scripts/quality_review.py -i "剪辑输出" -o "复核报告"
```

CLI 每个输入先检查文件稳定性、视频元数据与音轨。未就绪文件暂缓，完整素材先分析，再按 `--wait-for-input` 等待重试；默认值 0 表示不额外等待。等待预算从处理完首轮完整素材后开始，元数据探测与正在执行的分析不计入精确超时保证。单次元数据探测最多 15 秒。超时的素材明确列为未处理，进程返回非零；成功生成的时间轴可复用缓存。

CLI 现在输出候选拆分、首尾定位、视觉核验和导出的进度。`analysis_diagnostics.serve_kill` 保存声学各门槛与视觉筛选计数，帮助解释“为什么检出 0 个”；历史时间轴没有这些计数时保留缺失状态。

详细复核与真实素材验收方法见 [质量复核](references/quality-review.md)。本版没有新增球场校准、连续动作分类或代理解码，也没有未经验证地放宽检测阈值。

1.9.0 调整了候选标签与分局目录命名。再次导出建议选新目录，避免旧版本留下的片段与新结果混在一起；工具不会清理既有导出文件。
