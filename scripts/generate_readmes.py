import os
import re
import sys
import argparse

def format_link(filepath, text=None):
    if text is None:
        text = os.path.basename(filepath)
    return f"[{text}](file://{filepath})"

def generate(output_dir):
    output_dir = os.path.abspath(output_dir)
    base_dir_name = os.path.basename(output_dir)
    date_match = re.search(r"(\d{4})", base_dir_name)
    date_tag = date_match.group(1) if date_match else "实战"

    # Auto-discover all match folders (01_场次..., 02_场次...)
    match_folders = sorted([
        f for f in os.listdir(output_dir)
        if os.path.isdir(os.path.join(output_dir, f)) and re.match(r"^\d{2}_场次", f)
    ])

    match_stats = []
    total_rallies = 0
    total_long_rallies = 0
    total_kills = 0
    all_match_sections = []
    all_kill_items = []

    for folder_name in match_folders:
        match_path = os.path.join(output_dir, folder_name)
        parts = folder_name.split("_")
        match_short = parts[1] if len(parts) > 1 else folder_name
        time_str = f"{match_short} ({parts[-1]})"

        # Find multi-shot reel
        reels = [f for f in os.listdir(match_path) if f.startswith("00_【") and f.endswith(".mp4")]
        reel_file = reels[0] if reels else ""

        # Find all multi-shot clips
        rallies = [f for f in sorted(os.listdir(match_path)) if f.startswith("多拍") and f.endswith(".mp4")]
        long_rallies = [f for f in rallies if "超长高能拉锯" in f]

        # Find serve kills
        kill_dir = os.path.join(match_path, "接发秒杀一拍定死")
        kills = []
        kill_reel_file = ""
        if os.path.exists(kill_dir):
            kills = [f for f in sorted(os.listdir(kill_dir)) if f.startswith("秒杀") and f.endswith(".mp4")]
            kreels = [f for f in os.listdir(kill_dir) if f.startswith("00_【") and f.endswith(".mp4")]
            kill_reel_file = kreels[0] if kreels else ""
            for kf in kills:
                all_kill_items.append((folder_name, match_short, kf, os.path.join(kill_dir, kf)))

        match_stats.append({
            "folder": folder_name,
            "time_str": time_str,
            "rallies_count": len(rallies),
            "long_count": len(long_rallies),
            "kills_count": len(kills),
            "reel_path": os.path.join(match_path, reel_file) if reel_file else "",
            "reel_name": reel_file
        })

        total_rallies += len(rallies)
        total_long_rallies += len(long_rallies)
        total_kills += len(kills)

        # Build Match Section
        sec_lines = []
        sec_lines.append(f"### 🏸 {folder_name}\n")
        sec_lines.append(f"- 📂 文件夹链接：{format_link(match_path, folder_name)}")
        if reel_file:
            sec_lines.append(f"- 🎞️ 单场多拍零死球合集：{format_link(os.path.join(match_path, reel_file), reel_file)}")
        if kill_reel_file:
            sec_lines.append(f"- ⚡ 接发秒杀合集：{format_link(os.path.join(kill_dir, kill_reel_file), kill_reel_file)}")
        sec_lines.append(f"- ⚡ 本场多拍回合清单（共 {len(rallies)} 段）：\n")

        sec_lines.append("| 序号 | 类别 | 原片时间区间 | 时长 | 视频文件链接 |")
        sec_lines.append("| :--- | :--- | :--- | :--- | :--- |")

        for r_file in rallies:
            m = re.match(r"多拍(\d+)_(.+?)至(.+?)_【(.+?)】_(\d+)秒\.mp4", r_file)
            if m:
                idx_str, s_zh, e_zh, label, dur_str = m.groups()
                cat_icon = "🔥 超长拉锯" if "超长" in label else "🏸 激烈对攻"
                clip_path = os.path.join(match_path, r_file)
                link = format_link(clip_path, r_file)
                sec_lines.append(f"| {idx_str} | {cat_icon} | {s_zh}至{e_zh} | {dur_str}秒 | {link} |")
            else:
                clip_path = os.path.join(match_path, r_file)
                sec_lines.append(f"| - | 🏸 实战多拍 | - | - | {format_link(clip_path, r_file)} |")

        if kills:
            sec_lines.append(f"\n- 💥 本场接发秒杀/发球被一拍定死清单（共 {len(kills)} 段）：\n")
            for kf in kills:
                sec_lines.append(f"  - {format_link(os.path.join(kill_dir, kf), kf)}")

        sec_lines.append("\n")
        all_match_sections.append("\n".join(sec_lines))

    # Grand Top Rallies file
    grand_reel_path = os.path.join(output_dir, "00_【全场巅峰超长多拍TOP大集锦】_纯净原画零死球无字幕版.mp4")
    grand_reel_size = f"{os.path.getsize(grand_reel_path) / (1024**3):.2f} GB" if os.path.exists(grand_reel_path) else "-"

    # Grand Serve-Kill file
    grand_kill_dir = os.path.join(output_dir, "00_特别精选_发球被一拍定死大赏")
    grand_kill_path = os.path.join(grand_kill_dir, "00_【发球被一拍定死_接发秒杀连贯大赏】_全场纯净原画版.mp4")
    grand_kill_size = f"{os.path.getsize(grand_kill_path) / (1024**2):.0f} MB" if os.path.exists(grand_kill_path) else "-"

    # Generate Serve-Kill README if grand_kill_dir exists
    if os.path.exists(grand_kill_dir):
        kill_readme_path = os.path.join(grand_kill_dir, "README_接发秒杀一拍定死精选.md")
        grand_kill_clips = sorted([
            f for f in os.listdir(grand_kill_dir)
            if f.startswith("全场秒杀") and f.endswith(".mp4")
        ])
        with open(kill_readme_path, "w", encoding="utf-8") as kf_out:
            kf_out.write(f"# ⚡ {date_tag}羽毛球实战 ·【接发秒杀/发球被一拍定死】真名场面精选大赏\n\n")
            kf_out.write("> **【视觉动量四阶段硬核验协议】**：严格核验 **发球前全场静止就位 ($\\le 7.5$) $\\rightarrow$ 发球瞬间 $\\rightarrow$ 接发球员雷霆扑杀/突击重杀 (动量跃升 $\\ge 14.0$, 跃升比 $\\ge 1.8$) $\\rightarrow$ 球落地死球**。\n")
            kf_out.write("> **彻底剔除所有走路、擦汗、低头捡球、路人横穿的假片段，100% 货真价实！**\n\n")
            if os.path.exists(grand_kill_path):
                kf_out.write(f"- 🎞️ **全场连贯合辑**：{format_link(grand_kill_path)} ({grand_kill_size})\n\n")
            kf_out.write(f"## 📋 真实秒杀名场面逐帧核准清单（共 {len(grand_kill_clips)} 段）\n\n")
            kf_out.write("| 序号 | 视频文件名称 | 时长 | 视频文件链接 |\n")
            kf_out.write("| :--- | :--- | :--- | :--- |\n")
            for idx_k, gk_file in enumerate(grand_kill_clips, 1):
                m_k = re.search(r"_(\d+)秒\.mp4$", gk_file)
                dur_k = f"{m_k.group(1)}秒" if m_k else "-"
                gk_full = os.path.join(grand_kill_dir, gk_file)
                kf_out.write(f"| {idx_k:02d} | {gk_file} | {dur_k} | {format_link(gk_full)} |\n")

    # Assemble Full README
    readme_lines = [
        f"# 🏸 {date_tag} 羽毛球实战 · 精彩多拍集锦全量精剪总览 (八大铁律标准版)\n",
        "> **剪辑执行标准**：本目录全部视频严格执行【羽毛球精彩集锦八大执行铁律】与【极速并发无损架构】全自动精剪。",
        "> **核心标准**：①绝对零死球截断（无走动/捡球/擦汗）；②绝对严禁未死球提前掐断；③绝对剔除无打球镜头与开机调试晃动画面；④人员进出场与换人严格过滤；⑤默认纯净原画无字幕·无遮挡直出（4K UHD `-c copy`）；⑥多场地声学解耦防串扰；⑦1:1真拍数实战对应；⑧接发秒杀四阶段视觉动量防伪核验。\n",
        "---\n",
        "## 🏆 全场巅峰汇总\n",
        f"- 📁 **总输出目录**：{format_link(output_dir, output_dir)}",
        f"- 📦 **Skill 算法版本**：`v1.3.2` [badminton-video-cutter-v1.3.2.zip](file://{os.path.join(output_dir, 'badminton-video-cutter-v1.3.2.zip')})",
        f"- 🏸 **实战总场次**：{len(match_folders)} 场完整双打对抗",
        f"- ⚡ **全量纯净多拍总数**：**{total_rallies} 个** (零死球·无无打球镜头·无字幕遮挡·4K UHD)",
        f"- 🔥 **15秒以上超长高能拉锯**：**{total_long_rallies} 个**",
        f"- 💥 **发球被一拍定死/接发秒杀名场面**：**{total_kills} 个** (含微信表情包GIF)",
    ]
    if os.path.exists(grand_reel_path):
        readme_lines.append(f"- 🎬 **【全场总冠军集锦】超长多拍大合集**：{format_link(grand_reel_path, os.path.basename(grand_reel_path))} ({grand_reel_size})")
    if os.path.exists(grand_kill_path):
        readme_lines.append(f"- ⚡ **【全场秒杀总合集】接发一拍定死大赏**：{format_link(grand_kill_path, os.path.basename(grand_kill_path))} ({grand_kill_size})")

    readme_lines.extend([
        "\n---\n",
        "## 📊 各场次剪辑明细统计\n",
        "| 场次编号 | 场次标识 | 纯净多拍数 | 15s+超长拉锯 | 接发秒杀数 | 单场多拍零死球大合集 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for stat in match_stats:
        reel_link = format_link(stat["reel_path"], stat["reel_name"]) if stat["reel_path"] else "-"
        readme_lines.append(f"| **{stat['folder'][:7]}** | {stat['time_str']} | **{stat['rallies_count']} 段** | {stat['long_count']} 段 | {stat['kills_count']} 个 | {reel_link} |")

    readme_lines.append("\n---\n")
    readme_lines.extend(all_match_sections)

    out_readme = os.path.join(output_dir, f"README_{date_tag}羽毛球多拍精选总览.md")
    with open(out_readme, "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines))
    print(f"✅ Generated up-to-date README: {out_readme}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", default="/Users/harry/视频/1019羽毛球精彩多拍集锦", help="Output directory")
    args = parser.parse_args()
    generate(args.output)
