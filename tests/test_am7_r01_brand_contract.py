"""AM7-R01 active identity and retained Legacy identifier contract."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Am7R01BrandContractTests(unittest.TestCase):
    def test_active_identity_surfaces_are_ocria_am7(self):
        surfaces = {
            "simple_brush.py": ("Ocria Am7", "Ocria"),
            "setup.bat": ("Ocria Am7",),
            "start.bat": ("Ocria Am7",),
            "build-windows.bat": ("Ocria.exe", "dist\\Ocria", "Ocria-Am7-Windows-x64.zip"),
            "BossOCR.spec": ("name='Ocria'",),
            ".github/workflows/windows-release.yml": ("Ocria-Am7-Windows-x64.zip", "dist\\Ocria"),
            "README.md": ("# Ocria Am7", "Ocria.exe", "Ocria-Am7-Windows-x64.zip"),
            "docs/README.md": ("Ocria Am7", "Ocria.exe", "Ocria-Am7-Windows-x64.zip"),
        }
        for relative, expected in surfaces.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(surface=relative):
                for value in expected:
                    self.assertIn(value, text)

    def test_retained_legacy_identifiers_and_release_notes_contract_are_unchanged(self):
        workflow = (ROOT / ".github/workflows/windows-release.yml").read_text(encoding="utf-8")
        brush = (ROOT / "simple_brush.py").read_text(encoding="utf-8")
        self.assertIn("BossOCR.spec", workflow)
        self.assertIn("--notes-file release-notes\\Issue-1-BossOCR-release-notes.md", workflow)
        self.assertNotIn("--generate-notes", workflow)
        self.assertIn("BOSS", brush)
        self.assertIn("--no-forward", brush)


if __name__ == "__main__":
    unittest.main()
