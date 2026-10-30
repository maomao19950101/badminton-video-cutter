import unittest
import subprocess
import os

class TestCliMatchSegmentation(unittest.TestCase):
    def test_cli_help_includes_split_by_game(self):
        cmd = [
            "python3",
            "/Users/harry/.gemini/config/skills/badminton-video-cutter/scripts/badminton_cutter.py",
            "--help"
        ]
        res = subprocess.run(
            cmd,
            env=dict(os.environ, DEVELOPER_DIR="/Library/Developer/CommandLineTools"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--split-by-game", res.stdout)
        self.assertIn("--no-split-by-game", res.stdout)
        self.assertIn("--lineup-threshold", res.stdout)

if __name__ == "__main__":
    unittest.main()
