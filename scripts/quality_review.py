"""Read-only structural review of candidate timelines; not a play classifier."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path


def audit_timeline(data, long_seconds=30.0):
    if not math.isfinite(long_seconds) or long_seconds <= 0:
        raise ValueError("长片段复核门槛必须为有限正数")
    duration = float(data.get("duration", 0))
    issues, valid = [], []
    counts = Counter()
    seen = set()

    def flag(code, uids, message, severity="review", **details):
        issues.append(dict(code=code, uids=uids, message=message,
                           severity=severity, **details))

    if not math.isfinite(duration) or duration <= 0:
        flag("invalid_duration", [], "源视频时长无效", "error")
    for seg in data.get("segments", []):
        if not seg.get("enabled", True):
            continue
        uid = seg.get("uid")
        counts[seg.get("kind", "rally")] += 1
        if uid in seen:
            flag("duplicate_uid", [uid], "片段编号重复", "error")
        seen.add(uid)
        start, end = float(seg["s_cut"]), float(seg["e_cut"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
            flag("invalid_boundary", [uid], "切点非有限数、倒序或超出源视频", "error")
            continue
        valid.append((start, end, uid))
        if end - start > long_seconds:
            flag("long_segment", [uid], "长片段：核查是否含多分或等待；不要仅按时长删除",
                 start=start, end=end, duration=round(end-start, 3))
        peaks = seg.get("peaks", [])
        if peaks and any(not math.isfinite(float(p[0])) or not start <= float(p[0]) <= end for p in peaks):
            flag("peaks_outside_boundary", [uid], "部分声学事件位于切点外，可能需要同步更新估算拍数")
    # Compare every active interval, including nested overlaps and different kinds.
    active = []
    for start, end, uid in sorted(valid):
        active = [a for a in active if a[1] > start]
        for a_start, a_end, a_uid in active:
            overlap = min(a_end, end) - start
            if overlap > 0.001:
                flag("overlap", [a_uid, uid], "片段重叠：确认首尾预留，拼接前避免重复画面",
                     start=start, end=min(a_end, end), seconds=round(overlap, 3))
        active.append((start, end, uid))
    if data.get("serve_kills_scanned") and not counts["serve_kill"]:
        flag("zero_short_candidates", [], "未检出接发短分不代表不存在；查看声学与视觉淘汰统计")
    durations = [end-start for start, end, _ in valid]
    return {
        "schema_version": 1,
        "status": "structural_review_only",
        "source": data.get("video_path", ""),
        "notice": "本报告不证明回合真实、完整或分局正确；通过结构检查也需要画面复核。",
        "summary": {"enabled_segments": sum(counts.values()), "kinds": dict(counts),
                    "long_segments": sum(i["code"] == "long_segment" for i in issues),
                    "overlap_pairs": sum(i["code"] == "overlap" for i in issues),
                    "errors": sum(i["severity"] == "error" for i in issues),
                    "max_duration": round(max(durations, default=0), 3),
                    "sum_duration": round(sum(durations), 3)},
        "analysis_diagnostics": data.get("analysis_diagnostics", {}),
        "issues": issues,
    }


def write_review_reports(data, output_dir, long_seconds=30.0):
    report = audit_timeline(data, long_seconds)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    js_path, md_path = output / "review_report.json", output / "review_report.md"
    js_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    s = report["summary"]
    lines = ["# 回合候选复核清单", "", report["notice"], "",
             f"源视频：{report['source']}", "",
             f"候选 {s['enabled_segments']} 段；长片段 {s['long_segments']} 段；重叠 {s['overlap_pairs']} 对；切点/编号错误 {s['errors']} 处。",
             "", "优先复核错误、重叠、长片段，再抽查普通片段与被过滤区间。分局为估算；旧时间轴没有诊断数据时不推算淘汰原因。", "",
             "| 类型 | 片段编号 | 源视频区间（秒） | 说明 |", "|---|---|---|---|"]
    for issue in report["issues"]:
        interval = f"{issue['start']:.2f}–{issue['end']:.2f}" if "start" in issue else "—"
        lines.append(f"| {issue['code']} | {', '.join(map(str, issue['uids'])) or '—'} | {interval} | {issue['message']} |")
    lines += ["", "## 分析诊断", "", "```json",
              json.dumps(report["analysis_diagnostics"], ensure_ascii=False, indent=2), "```", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [str(js_path), str(md_path)]


def main():
    parser = argparse.ArgumentParser(description="复核现有时间轴，无需解码视频或重新分析")
    parser.add_argument("--input", "-i", required=True, help="时间轴 JSON 或包含 match_timeline.json 的目录")
    parser.add_argument("--output", "-o", required=True, help="复核报告目录；批量时保留相对目录结构")
    parser.add_argument("--long-seconds", type=float, default=30.0)
    args = parser.parse_args()
    source, output = Path(args.input), Path(args.output)
    paths = sorted(source.rglob("match_timeline.json")) if source.is_dir() else [source]
    if not paths:
        parser.error("未找到时间轴")
    errors = 0
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            dest = output / path.parent.relative_to(source) if source.is_dir() else output
            files = write_review_reports(data, dest, args.long_seconds)
            summary = audit_timeline(data, args.long_seconds)["summary"]
            errors += bool(summary["errors"])
            print(f"{path.parent.name}: {summary}; {files[1]}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors += 1
            print(f"复核失败 [{path}]: {exc}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
