"""Native Windows installer behavior, with temporary files and no live font registration.

Run with Windows PowerShell 5.1 or Windows PowerShell 7, for example:
    JETBATANG_POWERSHELL=powershell.exe python3 -m unittest discover -s tests -p test_windows_installer.py
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from jetbatang import release


ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = os.environ.get("JETBATANG_POWERSHELL") or shutil.which("powershell.exe")
if not POWERSHELL and os.name == "nt":
    POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def windows_path(path):
    if os.name == "nt":
        return str(path)
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


def make_font(path, version, suffix="Regular", style="Regular"):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    italic = suffix.endswith("Italic")
    weight_name = suffix.removesuffix("Italic") or "Regular"
    weights = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Regular": 400,
               "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800}
    bold = weight_name == "Bold"
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder([".notdef", "space", "A"])
    font.setupCharacterMap({32: "space", 65: "A"})
    empty = TTGlyphPen(None).glyph()
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((500, 800))
    pen.lineTo((900, 0))
    pen.closePath()
    font.setupGlyf({".notdef": empty, "space": empty, "A": pen.glyph()})
    font.setupHorizontalMetrics({name: (1000, 0) for name in (".notdef", "space", "A")})
    font.setupHorizontalHeader(ascent=900, descent=-200)
    font.setupNameTable({
        "familyName": "JetBatang NF", "styleName": style,
        "uniqueFontIdentifier": f"{version};NONE;JetBatangNF-{suffix}",
        "fullName": f"JetBatang NF {style}", "psName": f"JetBatangNF-{suffix}",
        "version": f"Version {version}",
    })
    font.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200,
                  usWeightClass=weights[weight_name],
                  fsSelection=(1 if italic else 0) | (32 if bold else 0) | (64 if not italic and not bold else 0))
    font.setupPost(italicAngle=-9 if italic else 0)
    font.font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    font.font["head"].fontRevision = float(version)
    font.save(path)


@unittest.skipUnless(POWERSHELL, "Native Windows PowerShell is required (no live installation is performed)")
class WindowsInstallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="jetbatang-installer-fixtures-")
        cls.addClassCleanup(cls.fixtures.cleanup)
        root = Path(cls.fixtures.name)
        for suffix, style, _ in release.VARIANTS:
            make_font(root / f"old-{suffix}.ttf", "1.0", suffix, style)
            make_font(root / f"new-{suffix}.ttf", "1.1", suffix, style)
        shutil.copyfile(root / "old-Regular.ttf", root / "old.ttf")
        shutil.copyfile(root / "new-Regular.ttf", root / "new.ttf")
        cls.arguments = [
            POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", windows_path(ROOT / "tests" / "windows_installer_scenarios.ps1"),
            "-Installer", windows_path(ROOT / "install-windows.ps1"),
            "-Fixtures", windows_path(root),
        ]

    def scenario(self, name):
        completed = subprocess.run(
            [*self.arguments, "-Scenario", name], capture_output=True, timeout=180,
        )
        output = completed.stdout.decode("utf-8", errors="replace")
        output += completed.stderr.decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0, output)

    def test_locked_all_users_update_preserves_registry_identities_and_scope(self):
        self.scenario("locked-update")

    def test_rollback_restores_registry_kind_path_and_checksum_backed_bytes(self):
        self.scenario("rollback")

    def test_uninstall_uses_registered_hash_paths_and_tolerates_locks(self):
        self.scenario("uninstall-locked")

    def test_mixed_scope_is_rejected_without_mutation(self):
        self.scenario("mixed-scope")

    def test_all_users_install_requires_elevation_without_per_user_fallback(self):
        self.scenario("not-elevated")

    def test_explicit_all_users_install_and_scope_conflict(self):
        self.scenario("explicit-all-users")

    def test_single_face_essentials_and_all_faces_with_literal_paths(self):
        self.scenario("subsets")

    def test_mid_update_failure_automatically_restores_previous_state(self):
        self.scenario("partial-failure")

    def test_corrupt_font_is_rejected_before_any_change(self):
        self.scenario("invalid-font")

    def test_tampered_backup_is_rejected_before_rollback_mutation(self):
        self.scenario("tampered-backup")

    def test_ambiguous_face_registration_is_rejected(self):
        self.scenario("ambiguous")

    def test_unchanged_hash_is_an_idempotent_install(self):
        self.scenario("unchanged")

    def test_relative_machine_paths_and_existing_aliases_are_preserved(self):
        self.scenario("relative-aliases")

    def test_rollback_refuses_to_overwrite_a_later_registration_change(self):
        self.scenario("rollback-drift")


if __name__ == "__main__":
    unittest.main()
