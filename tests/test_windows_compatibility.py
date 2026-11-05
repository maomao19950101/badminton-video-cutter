# -*- coding: utf-8 -*-
"""
Automated unit tests for Windows compatibility and packaging in Badminton Studio Pro.
Validates:
1. Windows launcher batch script (`启动可视化剪辑软件_Windows.bat`)
2. Windows PyInstaller packager (`打包Windows独立EXE程序.bat`)
3. Windows spec definition (`BadmintonAICutter_Win64.spec`)
4. Windows instruction documentation (`Windows使用说明_双击即用.txt`)
5. Cross-platform path handling for Windows backslashes in Web UI and Server
"""

import os
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestWindowsCompatibility(unittest.TestCase):
    def test_windows_launcher_bat(self):
        bat_path = os.path.join(ROOT_DIR, "启动可视化剪辑软件_Windows.bat")
        self.assertTrue(os.path.exists(bat_path), "Windows launcher batch script must exist")
        with open(bat_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("羽毛球比赛剪辑工作室", content)
        self.assertIn("Badminton Studio Pro", content)
        self.assertIn("codex_server.py", content)
        self.assertNotIn("AI 视频剪辑大师", content)

    def test_windows_packager_bat(self):
        bat_path = os.path.join(ROOT_DIR, "打包Windows独立EXE程序.bat")
        self.assertTrue(os.path.exists(bat_path), "Windows packager batch script must exist")
        with open(bat_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('--name "羽毛球比赛剪辑工作室"', content)
        self.assertIn("Badminton Studio Pro", content)
        self.assertIn("index.html;ui", content)
        self.assertNotIn("羽毛球AI剪辑大师", content)

    def test_windows_pyinstaller_spec(self):
        spec_path = os.path.join(ROOT_DIR, "BadmintonAICutter_Win64.spec")
        self.assertTrue(os.path.exists(spec_path), "Windows PyInstaller spec must exist")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('name="羽毛球比赛剪辑工作室"', content)
        self.assertIn("index.html", content)
        self.assertIn("app_icon.ico", content)

    def test_windows_instruction_txt(self):
        doc_path = os.path.join(ROOT_DIR, "Windows使用说明_双击即用.txt")
        self.assertTrue(os.path.exists(doc_path), "Windows instructions must exist")
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("羽毛球比赛剪辑工作室 · Badminton Studio Pro", content)
        self.assertIn("Apple Pro Blue", content)
        self.assertNotIn("翡翠绿", content)
        self.assertNotIn("AI 视频剪辑大师", content)

    def test_windows_path_handling_in_ui(self):
        ui_path = os.path.join(ROOT_DIR, "scripts", "ui", "index.html")
        with open(ui_path, "r", encoding="utf-8") as f:
            html = f.read()

        # UI must handle Windows backslash separators
        self.assertIn('split("\\\\")', html)

    def test_windows_support_in_server(self):
        server_path = os.path.join(ROOT_DIR, "scripts", "codex_server.py")
        with open(server_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn('platform.system() == "Windows"', code)
        self.assertIn("msedge.exe", code)
        self.assertIn("chrome.exe", code)
        self.assertIn("OpenFileDialog", code)
        self.assertIn("FolderBrowserDialog", code)


if __name__ == "__main__":
    unittest.main()
