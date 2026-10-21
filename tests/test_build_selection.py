"""선택 빌드의 셸 동작을 작은 재료·외부 명령 경계로 검사한다. 네트워크와 실제 글꼴 빌드는 하지 않는다."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from jetbatang import metadata, release


ROOT = Path(__file__).resolve().parent.parent


def small_font():
    """.notdef 하나와 이름표만 있는 TrueType 글꼴."""
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph()})
    builder.setupHorizontalMetrics({".notdef": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "fixture", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    return builder


class BuildSelectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="jetbatang selection ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for pattern in release.SOURCES:
            for source in ROOT.glob(pattern):
                dest = self.root / source.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
        (self.root / "tests").mkdir()
        shutil.copyfile(ROOT / "tests" / "test_build.py", self.root / "tests" / "test_build.py")

        fixtures = self.root / "fixtures"
        fixtures.mkdir()
        archive = fixtures / "JetBrainsMono.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for suffix, _, _ in release.VARIANTS:
                bundle.writestr(f"JetBrainsMonoNerdFontMono-{suffix}.ttf", suffix.encode())
        # 베이스 zip 의 실제 다운로드 대신 작은 고정 재료를 쓴다. 해시 확인과 unzip 은 실제 구현 그대로 돈다.
        # RIDIBatang 은 위에서 SOURCES 로 복사한 저장소 원본을 그대로 쓴다.
        script = (self.root / "build.sh").read_text()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        script = re.sub(r'(?m)^NERD_PINNED_SHA256="[0-9a-f]+"$', f'NERD_PINNED_SHA256="{digest}"', script)
        (self.root / "build.sh").write_text(script)

        commands = self.root / "bin"
        commands.mkdir()
        curl = commands / "curl"
        curl.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            from pathlib import Path
            import shutil
            import sys
            root = Path(__file__).resolve().parent.parent
            (root / "download-attempted").touch()
            dest = Path(sys.argv[sys.argv.index("-o") + 1])
            name = sys.argv[-1].rsplit("/", 1)[-1]
            shutil.copyfile(root / "fixtures" / name, dest)
            """))
        curl.chmod(0o755)
        # 고비용 글꼴 빌드만 대체하고, 출력 파일과 실제 셸의 성공·실패 동작을 검사한다.
        (self.root / "build.py").write_text(textwrap.dedent("""\
            import argparse
            import os
            from pathlib import Path
            import sys
            parser = argparse.ArgumentParser()
            parser.add_argument("--out", required=True)
            args, _ = parser.parse_known_args()
            out = Path(args.out)
            if os.environ.get("FAIL_SUFFIX") == out.stem.removeprefix("JetBatangNF-"):
                sys.exit("requested fixture failure")
            out.write_bytes(b"opaque font build fixture")
            """))
        self.env = dict(os.environ)
        for name in ("OUT_DIR", "JETBATANG_FONTS", "SOURCE_DATE_EPOCH", "FAIL_SUFFIX", "NERD_VERSION",
                     "NERD_FAMILY", "BASE_PREFIX", "FAMILY", "SCALE", "YSHIFT", "EMBOLDEN_SCALE"):
            self.env.pop(name, None)
        self.env.update(VERSION="1.7.0", JOBS="1", PATH=os.pathsep.join(
            (str(commands), str(Path(sys.executable).parent), self.env.get("PATH", ""))))

    def build(self, *suffixes, out_dir=None, **overrides):
        env = dict(self.env, **overrides)
        if out_dir is not None:
            env["OUT_DIR"] = str(out_dir)
        return subprocess.run(["bash", "build.sh", *suffixes], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=60)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def protect_release_output(self):
        fonts = self.root / "fonts"
        fonts.mkdir()
        (fonts / "JetBatangNF-Regular.ttf").write_bytes(b"existing release font")
        (fonts / release.MANIFEST).write_bytes(b"existing release manifest")
        return {path.name: path.read_bytes() for path in fonts.iterdir()}

    def assert_release_unchanged(self, before):
        self.assertEqual({path.name: path.read_bytes() for path in (self.root / "fonts").iterdir()}, before)

    def regression(self, *names, fonts_dir=None):
        env = dict(self.env, PYTHONPATH=os.pathsep.join((str(self.root / "tests"), str(self.root))))
        if fonts_dir is not None:
            env["JETBATANG_FONTS"] = str(fonts_dir)
        return subprocess.run([sys.executable, "-m", "unittest", *names], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=60)

    def test_unknown_suffix_is_refused_before_downloads_or_output_changes(self):
        before = self.protect_release_output()
        result = self.build("Thin", "NotAStyle")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NotAStyle", result.stdout + result.stderr)
        self.assertFalse((self.root / "download-attempted").exists())
        self.assertFalse((self.root / "build" / "preview-fonts").exists())
        self.assert_release_unchanged(before)

    def test_selected_default_output_is_limited_and_release_safe(self):
        before = self.protect_release_output()
        result = self.build("ThinItalic", "Thin", "ThinItalic")
        self.assert_success(result)
        target = self.root / "build" / "preview-fonts"
        self.assertEqual(sorted(path.name for path in target.iterdir()),
                         ["JetBatangNF-Thin.ttf", "JetBatangNF-ThinItalic.ttf"])
        self.assert_release_unchanged(before)

    def test_partial_output_with_spaces_invalidates_only_target_manifest(self):
        before = self.protect_release_output()
        target = self.root / "build" / "선택 [fonts]"
        target.mkdir(parents=True)
        (target / release.MANIFEST).write_text("stale complete manifest")
        (target / "keep.txt").write_text("unrelated file")
        neighbor = target.parent / release.MANIFEST
        neighbor.write_text("unrelated manifest")
        self.assert_success(self.build("BoldItalic", "Regular", out_dir="build/선택 [fonts]"))
        self.assertEqual(sorted(path.name for path in target.iterdir()),
                         ["JetBatangNF-BoldItalic.ttf", "JetBatangNF-Regular.ttf", "keep.txt"])
        self.assertFalse((target / release.MANIFEST).exists())
        self.assertEqual((target / "keep.txt").read_text(), "unrelated file")
        self.assertEqual(neighbor.read_text(), "unrelated manifest")
        self.assert_release_unchanged(before)

    def test_absolute_selected_output_keeps_release_directory_absent(self):
        target = self.root / "absolute output [fonts]"
        self.assert_success(self.build("Italic", out_dir=target))
        self.assertEqual([path.name for path in target.iterdir()], ["JetBatangNF-Italic.ttf"])
        self.assertFalse((self.root / "fonts").exists())

    def test_failed_partial_build_cannot_leave_a_complete_manifest(self):
        before = self.protect_release_output()
        target = self.root / "build" / "preview-fonts"
        target.mkdir(parents=True)
        (target / release.MANIFEST).write_text("stale complete manifest")
        result = self.build("Thin", "ThinItalic", FAIL_SUFFIX="ThinItalic")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((target / release.MANIFEST).exists())
        self.assertTrue((target / "JetBatangNF-Thin.ttf").is_file())
        self.assertFalse((target / "JetBatangNF-ThinItalic.ttf").exists())
        self.assert_release_unchanged(before)

    def test_full_default_build_preserves_all_variants_and_manifest(self):
        self.assert_success(self.build(SOURCE_DATE_EPOCH="1234567890"))
        target = self.root / "fonts"
        self.assertEqual(sorted(path.name for path in target.glob("*.ttf")), sorted(release.font_files()))
        info = release.verify_manifest(self.root)
        self.assertEqual(list(info["fonts"]), release.font_files())
        self.assertEqual(info["source_date_epoch"], 1234567890)
        self.assertEqual(info["custom"], [])

    def test_full_custom_output_records_and_validates_its_own_manifest(self):
        before = self.protect_release_output()
        target = self.root / "complete output [fonts]"
        self.assert_success(self.build(out_dir=target, SCALE="1.05", SOURCE_DATE_EPOCH="1234567890"))
        info = release.verify_manifest(self.root, fonts_dir=target)
        self.assertEqual(list(info["fonts"]), release.font_files())
        self.assertEqual(info["source_date_epoch"], 1234567890)
        self.assertEqual(info["custom"], ["SCALE=1.05"])
        (target / release.font_files()[0]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            release.verify_manifest(self.root, fonts_dir=target)
        self.assert_release_unchanged(before)

    def test_explicit_all_faces_stays_in_preview_but_has_a_complete_manifest(self):
        before = self.protect_release_output()
        suffixes = [suffix for suffix, _, _ in release.VARIANTS]
        self.assert_success(self.build(*reversed(suffixes), suffixes[0]))
        info = release.verify_manifest(self.root, fonts_dir="build/preview-fonts")
        self.assertEqual(list(info["fonts"]), release.font_files())
        self.assert_release_unchanged(before)

    def test_invalid_epoch_fails_before_downloads(self):
        result = self.build("Thin", SOURCE_DATE_EPOCH="not-an-epoch")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SOURCE_DATE_EPOCH", result.stdout + result.stderr)
        self.assertFalse((self.root / "download-attempted").exists())
        self.assertFalse((self.root / "build" / "preview-fonts").exists())

    def test_donor_other_than_a_cff_font_is_refused_before_downloads(self):
        # 새 판을 받아 바꿔 넣다 웹 페이지나 TrueType 판이 들어가면, 베이스를 받은 뒤 열여섯 종이 모두 같은
        # 오류로 실패하거나 외곽선 방향이 뒤집힌 채 나온다. outlines.outline 은 CFF 외곽선을 가정한다.
        for case in ("웹 페이지", "TrueType"):
            with self.subTest(case=case):
                donor = self.root / release.DONOR
                if case == "웹 페이지":
                    donor.write_bytes(b"<!DOCTYPE html><title>Just a moment...</title>")
                else:
                    small_font().save(donor)
                result = self.build("Regular")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(release.DONOR, result.stdout + result.stderr)
                self.assertFalse((self.root / "download-attempted").exists())
                self.assertFalse((self.root / "build" / "preview-fonts").exists())

    def test_partial_external_regressions_do_not_require_a_full_manifest(self):
        self.assert_success(self.build("Thin"))
        result = self.regression("test_build.ReleaseTest.test_fonts_were_built_from_current_sources",
                                 fonts_dir="build/preview-fonts")
        self.assert_success(result)
        (self.root / "build" / "preview-fonts" / release.MANIFEST).write_text("stale complete manifest")
        result = self.regression("test_build.ReleaseTest.test_fonts_were_built_from_current_sources",
                                 fonts_dir="build/preview-fonts")
        self.assertNotEqual(result.returncode, 0)

    def test_complete_external_regressions_validate_the_selected_manifest(self):
        self.assert_success(self.build())
        target = self.root / "external full fonts"
        self.assert_success(self.build(out_dir=target))
        name = "test_build.ReleaseTest.test_fonts_were_built_from_current_sources"
        self.assert_success(self.regression(name, fonts_dir=target))
        (target / release.font_files()[0]).write_bytes(b"changed external face")
        self.assertNotEqual(self.regression(name, fonts_dir=target).returncode, 0)
        (target / release.MANIFEST).unlink()
        self.assertNotEqual(self.regression(name, fonts_dir=target).returncode, 0)
        self.assert_success(self.regression(name))

    def test_default_regressions_still_reject_missing_and_stale_manifests(self):
        self.assert_success(self.build())
        name = "test_build.ReleaseTest.test_fonts_were_built_from_current_sources"
        self.assert_success(self.regression(name))
        manifest = self.root / "fonts" / release.MANIFEST
        original = manifest.read_bytes()
        manifest.unlink()
        self.assertNotEqual(self.regression(name).returncode, 0)
        # JETBATANG_FONTS=fonts 는 기본 폴더 검사를 피하는 별칭이 아니다.
        self.assertNotEqual(self.regression(name, fonts_dir="fonts").returncode, 0)
        manifest.write_bytes(original)
        with (self.root / "jetbatang" / "charset.py").open("a") as source:
            source.write("\n# changed fixture source\n")
        self.assertNotEqual(self.regression(name).returncode, 0)

    def test_selected_font_regressions_read_names_and_versions_from_external_faces(self):
        target = self.root / "selected font output"
        target.mkdir()
        for suffix, style in (("Thin", "Thin"), ("ThinItalic", "Thin Italic")):
            builder = small_font()
            metadata.set_names(builder.font, builder.font, "JetBatang NF", style, "1.7.0")
            builder.save(target / f"JetBatangNF-{suffix}.ttf")
        names = ("test_build.NameTest.test_names_follow_the_weight_table",
                 "test_build.NameTest.test_every_face_names_itself_not_jetbrains_and_its_release",
                 "test_build.VersionTest.test_every_face_reports_one_release_version")
        self.assert_success(self.regression(*names, fonts_dir=target))
        # 이름을 망가뜨린 선택 파일을 놓치면, glob 만 바꾸고 개별 경로는 fonts/ 를 보던 회귀다.
        path = target / "JetBatangNF-Thin.ttf"
        with TTFont(path) as font:
            metadata.set_name(font, 4, "wrong selected font name")
            font.save(path)
        self.assertNotEqual(self.regression(names[0], fonts_dir=target).returncode, 0)
        result = self.regression("test_build.RegularTest", fonts_dir=target)
        self.assert_success(result)


if __name__ == "__main__":
    unittest.main()
