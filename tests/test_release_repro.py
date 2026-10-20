"""빌드 시각과 ZIP 파일 메타데이터가 릴리스 바이트를 흔들지 않는지 본다."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from jetbatang import release

ROOT = Path(__file__).resolve().parent.parent


class BuildEpochTest(unittest.TestCase):
    def test_epoch_uses_commit_time_unless_explicitly_overridden(self):
        # 로컬 시각이나 checkout 시각이 아니라 소스 커밋 시각을 써야 두 머신의 빌드가 같다.
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory)
            os.environ.pop("SOURCE_DATE_EPOCH", None)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            env = dict(os.environ, GIT_AUTHOR_DATE="1700000000 +0000", GIT_COMMITTER_DATE="1700000000 +0000")
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Epoch Test", "-c", "user.email=epoch@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                            "commit", "-q", "--allow-empty", "-m", "fixed commit time"],
                           check=True, env=env, capture_output=True)
            self.assertEqual(release.source_date_epoch(root), 1700000000)
            os.environ["SOURCE_DATE_EPOCH"] = "1700000123"
            self.assertEqual(release.source_date_epoch(root), 1700000123)

    def test_source_archive_has_a_fixed_epoch_and_rejects_invalid_overrides(self):
        # .git 없는 소스 묶음도 벽시계를 쓰지 않는다. 틀린 환경 변수는 빌드 전에 거부한다.
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop("SOURCE_DATE_EPOCH", None)
            self.assertEqual(release.source_date_epoch(directory), 315532800)
            for value in ("", "-1", "1.5", "nan", "１７００００００００"):
                os.environ["SOURCE_DATE_EPOCH"] = value
                with self.subTest(value=value), self.assertRaises(ValueError):
                    release.source_date_epoch(directory)


class ArchiveReproTest(unittest.TestCase):
    def test_archive_ignores_input_order_mtime_mode_and_timezone(self):
        # 같은 자산을 다른 시각·권한·순서로 모아도 받은 ZIP 의 해시와 내용이 같아야 한다.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font, license_ = root / "JetBatangNF-Regular.ttf", root / "LICENSE"
            font.write_bytes(b"font bytes\x00\xff")
            license_.write_text("license\n", encoding="utf-8")
            with patch.dict(os.environ, {"TZ": "Pacific/Kiritimati"}):
                release.write_archive(root / "first.zip", [font, license_], 1700000001)
            for path in (font, license_):
                os.utime(path, (1750000000, 1750000000))
                path.chmod(0o600)
            with patch.dict(os.environ, {"TZ": "Etc/GMT+12"}):
                release.write_archive(root / "second.zip", [license_, font], 1700000001)
            self.assertEqual((root / "first.zip").read_bytes(), (root / "second.zip").read_bytes())
            with zipfile.ZipFile(root / "first.zip") as archive:
                self.assertEqual(set(archive.namelist()), {font.name, license_.name})
                self.assertEqual(archive.read(font.name), font.read_bytes())
                self.assertEqual(archive.read(license_.name), license_.read_bytes())
                self.assertEqual({entry.date_time for entry in archive.infolist()}, {(2023, 11, 14, 22, 13, 20)})

    def test_archive_accepts_epochs_outside_the_dos_timestamp_range(self):
        # SOURCE_DATE_EPOCH=0 도 일반 ZIP 으로 읽힌다. ZIP 의 날짜는 1980~2107 년에 맞춘다.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "LICENSE"
            source.write_bytes(b"license")
            for epoch, expected in ((0, (1980, 1, 1, 0, 0, 0)), (5000000000, (2107, 12, 31, 23, 59, 58))):
                with self.subTest(epoch=epoch):
                    release.write_archive(root / "bundle.zip", [source], epoch)
                    with zipfile.ZipFile(root / "bundle.zip") as archive:
                        self.assertEqual(archive.getinfo(source.name).date_time, expected)
                        self.assertEqual(archive.read(source.name), b"license")


class ReleasePackageTest(unittest.TestCase):
    def project(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for pattern in release.SOURCES:
            for source in ROOT.glob(pattern):
                target = root / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        for name in ("package.sh", "install-windows.ps1", "LICENSE"):
            shutil.copy2(ROOT / name, root / name)
        (root / "fonts").mkdir()
        for name in release.font_files():
            (root / "fonts" / name).write_bytes(b"font data: " + name.encode())
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1700000001"}):
            release.write_manifest(root, "1.7.0", release.snapshot(root))
        return root

    def test_manifest_records_and_validates_the_build_epoch(self):
        root = self.project()
        manifest_path = root / "fonts" / release.MANIFEST
        info = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(info["source_date_epoch"], 1700000001)
        for value in (None, "1700000001", -1, True):
            invalid = dict(info)
            if value is None:
                invalid.pop("source_date_epoch")
            else:
                invalid["source_date_epoch"] = value
            manifest_path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.verify_manifest(root)

    def test_package_uses_a_complete_external_output_directory(self):
        root = self.project()
        external = root / "preview output [완성본]"
        (root / "fonts").rename(external)
        env = dict(os.environ, OUT_DIR=str(external))
        result = subprocess.run(["bash", str(root / "package.sh")], cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with zipfile.ZipFile(root / "dist" / "JetBatangNF-all.zip") as archive:
            for name in release.font_files():
                self.assertEqual(archive.read(name), (external / name).read_bytes())

    def test_package_ships_exact_basic_styles_and_repeats_all_checksums(self):
        # 실제 package.sh 를 돈다. 두 ZIP 내용, 낱개 파일, SHA256SUMS, 재묶기의 동일성을 같이 본다.
        root = self.project()
        result = subprocess.run(["bash", str(root / "package.sh")], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dist = root / "dist"
        basic = {f"JetBatangNF-{style}.ttf" for style in ("Regular", "Bold", "Italic", "BoldItalic")}
        extras = {"install-windows.ps1", "LICENSE"}
        with zipfile.ZipFile(dist / "JetBatangNF-basic.zip") as archive:
            self.assertEqual(set(archive.namelist()), basic | extras)
            for name in basic:
                self.assertEqual(archive.read(name), (root / "fonts" / name).read_bytes())
        with zipfile.ZipFile(dist / "JetBatangNF-all.zip") as archive:
            self.assertEqual(set(archive.namelist()), set(release.font_files()) | extras)
        first = {path.name: path.read_bytes() for path in dist.iterdir()}
        sums = dict(line.split("  ", 1)[::-1] for line in first["SHA256SUMS"].decode().splitlines())
        self.assertEqual(set(sums), set(first) - {"SHA256SUMS"})
        for name, digest in sums.items():
            self.assertEqual(digest, hashlib.sha256(first[name]).hexdigest(), name)
        for path in (root / "fonts").glob("*.ttf"):
            os.utime(path, (1750000000, 1750000000))
        for name in extras:
            os.utime(root / name, (1750000000, 1750000000))
        # 묶을 때의 환경 값이 아니라 빌드 기록의 시각을 써야 한다.
        env = dict(os.environ, SOURCE_DATE_EPOCH="1800000000", TZ="Etc/GMT+12")
        result = subprocess.run(["bash", str(root / "package.sh")], cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({path.name: path.read_bytes() for path in dist.iterdir()}, first)


if __name__ == "__main__":
    unittest.main()
