import unittest
import subprocess
from pathlib import Path
import sys

class TestCliMatchSegmentation(unittest.TestCase):
    def test_cli_help_includes_split_by_game(self):
        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "badminton_cutter.py"),
            "--help"
        ]
        res = subprocess.run(
            cmd,
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
