import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badminton_cutter as cutter
import gui_engine as engine
from modes_handler import filter_solo_rallies, generate_condensed_reel, generate_vertical_clip


class TestTimelineCache(unittest.TestCase):
    def test_analysis_settings_source_and_manual_edits_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine.tempfile, "gettempdir", return_value=tmp):
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"source")
            config = engine.CutterConfig()
            identity = list(cutter.source_fingerprint(source))
            key = engine.analysis_cache_key(str(source), config)
            timeline = engine.VideoTimeline(str(source), "Match", "match", 10, analysis_key=key,
                                            source_identity=identity, segments=[engine.RallySegment(1, "rally", 1, 1, 7)])
            engine.save_timeline_json(timeline, engine._timeline_cache_path(key, edited=False))
            timeline.segments[0].lead_quadrant = 1
            engine.save_timeline_json(timeline)
            self.assertEqual(engine.try_load_cached_timeline(str(source), config).segments[0].lead_quadrant, 1)
            raw = engine.load_timeline_json(engine._timeline_cache_path(key, edited=False))
            self.assertIsNone(raw.segments[0].lead_quadrant)
            self.assertIsNone(engine.try_load_cached_timeline(str(source), engine.CutterConfig(min_hits=9)))
            self.assertIsNone(engine.try_load_cached_timeline(str(source), engine.CutterConfig(modes=["vertical"])))
            source.write_bytes(b"new contents")
            self.assertIsNone(engine.try_load_cached_timeline(str(source), config))

    def test_solo_uses_only_labeled_rallies(self):
        rallies = [{"index": 0}, {"index": 1}, {"index": 2, "lead_quadrant": 1}]
        self.assertEqual(filter_solo_rallies(rallies, "near_left"), [])
        self.assertEqual(filter_solo_rallies(rallies, "near_right"), [rallies[2]])
        self.assertEqual(filter_solo_rallies(rallies, "auto"), [rallies[2]])


class TestWebBoundary(unittest.TestCase):
    def test_media_range_requires_registration_and_writes_require_token(self):
        import codex_server as studio

        def send(method, url, headers=None, body=b""):
            lines = [f"{method} {url} HTTP/1.1", "Host: 127.0.0.1:18765", "Connection: close"]
            lines.extend(f"{key}: {value}" for key, value in (headers or {}).items())
            if body:
                lines.append(f"Content-Length: {len(body)}")
            request = io.BytesIO(("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body)
            response = io.BytesIO()
            connection = SimpleNamespace(makefile=lambda *args: request, sendall=response.write)
            studio.CodexRequestHandler(connection, ("127.0.0.1", 1), SimpleNamespace(server_port=18765))
            result = response.getvalue()
            return int(result.split(b" ", 2)[1]), result.partition(b"\r\n\r\n")[2]

        with tempfile.TemporaryDirectory() as tmp:
            path = (Path(tmp).resolve() / "source.mp4")
            path.write_bytes(b"0123456789")
            state = SimpleNamespace(video_files=[], timelines={}, current_vpath=None, to_summary_dict=lambda: {})
            with patch.object(studio, "STATE", state):
                route = f"/api/video?id={studio.video_id(str(path))}"
                self.assertEqual(send("GET", route)[0], 404)
                self.assertEqual(send("GET", f"/api/video?path={path}")[0], 404)
                state.video_files.append(str(path))
                self.assertEqual(send("GET", route, {"Range": "bytes=2-5"}), (206, b"2345"))
                self.assertEqual(send("GET", route, {"Range": "bytes=8-2"})[0], 416)
                self.assertEqual(send("GET", route, {"Host": "outside.example:18765"})[0], 403)
                self.assertEqual(send("POST", "/api/clear_videos", {"Content-Type": "text/plain"}, b"{}")[0], 403)
                headers = {"Content-Type": "application/json", "X-Studio-Token": studio.SESSION_TOKEN}
                self.assertEqual(send("POST", "/api/clear_videos", {**headers, "Origin": "https://outside.example"}, b"{}")[0], 403)
                self.assertEqual(send("POST", "/api/clear_videos", {**headers, "Origin": "http://127.0.0.1:18765"}, b"{}")[0], 200)
                self.assertFalse(state.video_files)


@unittest.skipUnless(shutil.which(cutter.DEFAULT_FFMPEG), "FFmpeg is required for real-media tests")
class TestMediaExport(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ffmpeg = cutter.DEFAULT_FFMPEG
        self.source = self.make_source("甲", 440)

    def ff(self, *args, check=True):
        return subprocess.run([self.ffmpeg, "-hide_banner", "-nostdin", *map(str, args)],
                              capture_output=True, check=check)

    def make_source(self, folder, frequency):
        path = self.root / folder / "同名 1's.mp4"
        path.parent.mkdir()
        self.ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=8",
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=8",
                "-c:v", "libx264", "-g", "180", "-sc_threshold", "0", "-c:a", "aac", path)
        return path

    def test_audio_cache_does_not_reuse_same_name(self):
        another = self.make_source("乙", 880)
        with patch.object(cutter.tempfile, "gettempdir", return_value=str(self.root)):
            first, second = [cutter.audio_cache_path(p, self.ffmpeg) for p in (self.source, another)]
            self.assertNotEqual(first, second)
            for src, dst in ((self.source, first), (another, second)):
                cutter.extract_audio_wav(str(src), dst, self.ffmpeg)
            self.assertNotEqual(Path(first).read_bytes(), Path(second).read_bytes())

    def test_concat_relative_path_with_quote_and_aspect_ratios(self):
        old = os.getcwd()
        try:
            os.chdir(self.root)
            self.assertTrue(generate_condensed_reel(self.ffmpeg, [str(self.source.relative_to(self.root))], "输出/拼接.mp4"))
        finally:
            os.chdir(old)
        for aspect, dimensions in (("9:16", "720x1280"), ("1:1", "720x720"), ("16:9", "1280x720")):
            with self.subTest(aspect=aspect):
                out = self.root / f"{dimensions}.mp4"
                self.assertTrue(generate_vertical_clip(self.ffmpeg, str(self.source), str(out), aspect))
                self.assertIn(dimensions.encode(), self.ff("-i", out, check=False).stderr)

    def test_frame_accurate_export_and_atomic_failure(self):
        out = self.root / "精剪.mp4"
        cutter.cut_exact(self.ffmpeg, str(self.source), 4.1, 1.2, str(out))
        frames = self.ff("-i", out, "-an", "-f", "framemd5", "-").stdout.splitlines()
        self.assertEqual(sum(not line.startswith(b"#") for line in frames), 36)
        self.assertAlmostEqual(cutter.get_video_duration(out, self.ffmpeg), 1.2, delta=1 / 30)
        original = out.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "FFmpeg"):
            cutter.cut_exact(self.ffmpeg, str(self.root / "missing.mp4"), 0, 1, str(out))
        self.assertEqual(original, out.read_bytes())
        self.assertFalse(list(self.root.glob(".badminton-*")))

    def test_cli_analyze_and_reuse_timeline(self):
        output = self.root / "输出"
        cli = Path(cutter.__file__).resolve()
        cmd = [sys.executable, "-B", str(cli), "-i", str(self.source), "-o", str(output),
               "--ffmpeg", self.ffmpeg, "--no-split-by-game"]
        subprocess.run([*cmd, "--analyze-only"], check=True, capture_output=True)
        timeline_path, = output.glob("*/match_timeline.json")
        payload = json.loads(timeline_path.read_text(encoding="utf-8"))
        payload["segments"] = [{"uid": 1, "kind": "rally", "s_cut": 4.1, "e_cut": 5.3,
                                "lead_quadrant": 0, "stroke_style": "drive"}]
        timeline_path.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run([*cmd, "--timeline", str(timeline_path), "--mode", "solo", "--exact"],
                       check=True, capture_output=True)
        clips = list(output.glob("*/个人高光Solo视角_near_left/*.mp4"))
        self.assertEqual(len(clips), 2)
        self.assertTrue(all(path.stat().st_size > 0 for path in clips))
