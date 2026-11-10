import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from quality_review import audit_timeline, write_review_reports
from input_check import check_input_ready
from badminton_cutter import serve_kill_acoustic_candidates
from gui_engine import VideoTimeline, RallySegment, export_video_timeline
import badminton_cutter as cutter


class TestTimelineReview(unittest.TestCase):
    def test_nested_overlaps_disabled_segments_and_no_automatic_trimming(self):
        data = {"duration": 100, "segments": [
            dict(uid=1, s_cut=0, e_cut=90), dict(uid=2, s_cut=10, e_cut=20),
            dict(uid=3, s_cut=30, e_cut=40),
            dict(uid=4, s_cut=-1, e_cut=110, enabled=False)]}
        original = json.dumps(data)
        report = audit_timeline(data)
        self.assertEqual(report["summary"]["overlap_pairs"], 2)
        self.assertEqual(report["summary"]["long_segments"], 1)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(json.dumps(data), original)

    def test_invalid_boundaries_and_duplicate_ids_are_errors(self):
        data = {"duration": 10, "segments": [
            dict(uid=1, s_cut=float("nan"), e_cut=5),
            dict(uid=1, s_cut=8, e_cut=11)]}
        self.assertEqual(audit_timeline(data)["summary"]["errors"], 3)

    def test_invalid_export_stops_before_cutting_or_creating_output(self):
        timeline = VideoTimeline("/fake/source.mp4", "test", "match", 10,
                                 segments=[RallySegment(1, "rally", 1, 9, 12)])
        with tempfile.TemporaryDirectory() as tmp, patch("gui_engine.cut_lossless") as cut:
            with self.assertRaisesRegex(ValueError, "时间轴不能导出"):
                export_video_timeline(timeline, tmp)
            cut.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_old_timeline_reports_missing_diagnostics_without_inventing_counts(self):
        data = {"duration": 10, "serve_kills_scanned": True, "segments": []}
        with tempfile.TemporaryDirectory() as tmp:
            files = write_review_reports(data, tmp)
            report = json.loads(Path(files[0]).read_text())
            self.assertEqual(report["analysis_diagnostics"], {})
            self.assertEqual(report["issues"][0]["code"], "zero_short_candidates")
            self.assertTrue(Path(files[1]).is_file())

    def test_diagnostics_survive_timeline_roundtrip(self):
        tl = VideoTimeline("/source.mp4", "source", "source", 10,
                           analysis_diagnostics={"serve_kill": {"pre_silence_pass": 0}})
        self.assertEqual(VideoTimeline.from_dict(tl.to_dict()).analysis_diagnostics,
                         tl.analysis_diagnostics)


class TestInputReadiness(unittest.TestCase):
    def stat(self, size, stamp=1):
        return SimpleNamespace(st_size=size, st_mtime_ns=stamp, st_ctime_ns=stamp)

    def test_growing_file_is_pending_without_attempting_decode(self):
        with patch("input_check.os.stat", side_effect=[self.stat(10), self.stat(20)]), \
             patch("input_check.time.sleep"), patch("input_check.subprocess.run") as run:
            ok, message = check_input_ready("copy.mp4", "ffmpeg")
        self.assertFalse(ok)
        self.assertIn("仍在写入", message)
        run.assert_not_called()

    def test_stable_file_requires_metadata_and_audio_for_analysis(self):
        with tempfile.TemporaryDirectory() as tmp, patch("input_check.time.sleep"):
            source = Path(tmp) / "sample.mp4"
            source.write_bytes(b"stable")
            with patch("input_check.subprocess.run", return_value=SimpleNamespace(stderr="moov atom not found")):
                self.assertFalse(check_input_ready(source, "ffmpeg")[0])
            info = "Duration: 00:00:10.00 Video: h264"
            with patch("input_check.subprocess.run", return_value=SimpleNamespace(stderr=info)):
                self.assertFalse(check_input_ready(source, "ffmpeg")[0])
                self.assertTrue(check_input_ready(source, "ffmpeg", require_audio=False)[0])
            with patch("input_check.subprocess.run", return_value=SimpleNamespace(stderr=info+" Audio: aac")):
                self.assertTrue(check_input_ready(source, "ffmpeg")[0])


class TestShortCandidateDiagnostics(unittest.TestCase):
    def test_isolated_pair_passes_and_counts_balance(self):
        stats = {}
        pairs = serve_kill_acoustic_candidates([(10, 3e7), (11, 3e7)], stats)
        self.assertEqual(pairs, [(10, 11)])
        self.assertEqual(stats["pre_silence_pass"], 1)
        self.assertEqual(sum(stats["rejected"].values()) + len(pairs), stats["input_events"])

    def test_background_event_can_remove_acoustic_candidate(self):
        stats = {}
        # The quiet-window requirement is intentionally unchanged and now observable.
        pairs = serve_kill_acoustic_candidates([(8.8, 5e6), (10, 3e7), (11, 3e7)], stats)
        self.assertEqual(pairs, [])
        self.assertEqual(stats["rejected"]["pre_silence"], 1)
        self.assertEqual(stats["rejected"]["post_silence"], 1)


class TestBatchInputQueue(unittest.TestCase):
    def run_batch(self, wait, readiness):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input"
            source.mkdir()
            for name in ("a.mp4", "b.mp4"):
                (source / name).write_bytes(b"source")
            analyzed = []
            def analyze(path, idx, *args, **kwargs):
                analyzed.append(Path(path).name)
                return VideoTimeline(path, Path(path).stem, Path(path).stem, 10)
            args = ["cutter", "-i", str(source), "-o", str(Path(tmp) / "output"),
                    "--analyze-only", "--wait-for-input", str(wait)]
            with patch.object(sys, "argv", args), \
                 patch("input_check.check_input_ready", side_effect=readiness), \
                 patch("gui_engine.analyze_video_file", side_effect=analyze), \
                 patch.object(cutter.time, "sleep"), patch("builtins.print"):
                code = cutter.main()
            return code, analyzed

    def test_complete_file_processed_before_retrying_growing_file(self):
        code, analyzed = self.run_batch(1, [(False, "仍在写入"), (True, "ready"), (True, "ready")])
        self.assertEqual(code, 0)
        self.assertEqual(analyzed, ["b.mp4", "a.mp4"])

    def test_no_wait_finishes_ready_files_and_reports_pending_as_incomplete(self):
        code, analyzed = self.run_batch(0, [(False, "仍在写入"), (True, "ready")])
        self.assertEqual(code, 1)
        self.assertEqual(analyzed, ["b.mp4"])


if __name__ == "__main__":
    unittest.main()
