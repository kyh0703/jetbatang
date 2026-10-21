"""굵기 목록, 저장소에 둔 RIDIBatang 경로, build.sh 가 fonts/ 에 남기는 빌드 기록. 표준 라이브러리만 쓴다."""
import hashlib
import importlib.metadata
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path


# 굵기 열여섯 종. (파일 접미사, 타이포그래픽 스타일, 한글 가로 굵기 증가량)
# build.sh 가 이 목록대로 만들고, 미리보기와 검사도 이 목록을 읽는다.
#
# RIDIBatang 은 세로획 81 짜리 한 굵기뿐이다. Regular 를 기준으로 삼고, 한글 세로획이
# 같은 굵기 라틴 세로획의 0.9 배(Regular 의 81 : 90)쯤 되게 한글 가로 굵기를 불리거나
# 깎는다(음수). 세로는 불릴 때 그 0.4 배, 깎을 때 0.8 배다.
#   라틴 세로획: Thin 50 / ExtraLight 66 / Light 79 / Regular 90
#                Medium 99 / SemiBold 108 / Bold 125 / ExtraBold 150
VARIANTS = [
    ("Thin", "Thin", -36),
    ("ThinItalic", "Thin Italic", -36),
    ("ExtraLight", "ExtraLight", -22),
    ("ExtraLightItalic", "ExtraLight Italic", -22),
    ("Light", "Light", -10),
    ("LightItalic", "Light Italic", -10),
    ("Regular", "Regular", 0),
    ("Italic", "Italic", 0),
    ("Medium", "Medium", 9),
    ("MediumItalic", "Medium Italic", 9),
    ("SemiBold", "SemiBold", 18),
    ("SemiBoldItalic", "SemiBold Italic", 18),
    ("Bold", "Bold", 36),
    ("BoldItalic", "Bold Italic", 36),
    ("ExtraBold", "ExtraBold", 56),
    ("ExtraBoldItalic", "ExtraBold Italic", 56),
]

# build.sh 가 열여섯 종을 모두 만든 뒤 fonts/ 에 남기는 기록. 어느 코드와 라이브러리로 만든 어느 파일인지
# 적어서, 검사와 package.sh 가 예전 코드로 만들었거나 일부만 다시 만든 fonts/ 를 알아보게 한다.
MANIFEST = "build-info.json"

# 보통 터미널에서 쓰는 네 스타일. 전체 묶음과 별도로 작은 기본 묶음을 만든다.
BASIC_FONTS = tuple(f"JetBatangNF-{suffix}.ttf" for suffix in ("Regular", "Bold", "Italic", "BoldItalic"))

# ZIP 의 DOS 시각은 UTC 1980~2107 년, 2초 단위로만 저장한다.
ZIP_MIN_EPOCH = 315532800
ZIP_MAX_EPOCH = 4354819198

# RIDIBatang 은 공식 배포 파일을 고치지 않고 저장소에 둔다. 내려받지 않아서 사이트 주소가 바뀌어도 빌드한다.
# 새 판이 나오면 이 파일만 바꿔 넣는다.
DONOR = "sources/RIDIBatang.otf"
# 이 파일들이 바뀌면 같은 베이스로도 글꼴이 달라진다. DONOR 가 들어 있어서 예전 RIDIBatang 으로 만든 fonts/ 는
# 기록과 맞지 않는다. 베이스 글꼴 zip 의 해시는 build.sh 에 있다.
SOURCES = ("build.py", "build.sh", "requirements.txt", "jetbatang/*.py", DONOR)
# 라이브러리 판을 고정한 파일. name==version 줄만 읽는다.
REQUIREMENTS = "requirements.txt"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_date_epoch(root):
    """SOURCE_DATE_EPOCH, 소스 커밋 시각, .git 없는 소스 묶음의 고정 시각 순서로 고른다."""
    value = os.environ.get("SOURCE_DATE_EPOCH")
    if value is None:
        root = Path(root)
        if not (root / ".git").exists():
            return ZIP_MIN_EPOCH
        try:
            value = subprocess.check_output(
                ["git", "-C", str(root), "log", "-1", "--format=%ct"], stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("커밋 시각을 읽을 수 없어요. Git 을 확인하거나 SOURCE_DATE_EPOCH 를 지정하세요") from exc
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"SOURCE_DATE_EPOCH 는 0 이상의 정수여야 해요: {value!r}")
    return int(value)


def write_archive(path, files, epoch):
    """입력 파일의 순서·수정 시각·권한·시스템 시간대에 관계없이 같은 ZIP 을 쓴다."""
    stamp = time.gmtime(max(ZIP_MIN_EPOCH, min(epoch, ZIP_MAX_EPOCH)))[:6]
    with zipfile.ZipFile(path, "w") as archive:
        for source in sorted(map(Path, files), key=lambda item: item.name):
            entry = zipfile.ZipInfo(source.name, date_time=stamp)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def sources_digest(root):
    """SOURCES 에 걸리는 파일을 한데 묶은 해시."""
    root = Path(root)
    digest = hashlib.sha256()
    for pattern in SOURCES:
        paths = sorted(root.glob(pattern))
        if not paths:
            raise FileNotFoundError(root / pattern)
        for path in paths:
            digest.update(f"{path.relative_to(root).as_posix()} {sha256_file(path)}\n".encode())
    return digest.hexdigest()


def pinned_versions(root):
    """REQUIREMENTS 에 고정한 {이름: 판}."""
    pins = {}
    for line in (Path(root) / REQUIREMENTS).read_text(encoding="utf-8").splitlines():
        name, pinned, version = line.split("#", 1)[0].partition("==")
        if pinned:
            pins[name.strip()] = version.strip()
    return pins


def installed_versions(names):
    """지금 깔린 {이름: 판}. 깔리지 않았으면 None."""
    found = {}
    for name in names:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = None
    return found


def library_mismatches(root, versions):
    """versions({이름: 판, 없으면 None}) 가운데 고정한 판과 다른 것. [(이름, 고정한 판, 실제 판)]"""
    return [(name, pin, versions.get(name)) for name, pin in pinned_versions(root).items()
            if versions.get(name) != pin]


def library_warnings(root):
    """지금 깔린 판이 고정한 판과 다른 라이브러리마다 경고 한 줄. build.sh 가 빌드하기 전에 찍는다.
    판이 다르면 같은 코드로도 글꼴이 달라질 수 있지만, 쓰던 환경으로 빌드하는 것을 막지는 않는다."""
    lines = []
    for name, pin, found in library_mismatches(root, installed_versions(pinned_versions(root))):
        got = "깔려 있지 않아요" if found is None else f"{found} 이 깔려 있어요"
        lines.append(f"경고: {REQUIREMENTS} 는 {name}=={pin} 인데 {got}. 같은 글꼴이 나오지 않을 수 "
                     f"있어요. pip install -r {REQUIREMENTS}")
    return lines


def built_library_warnings(root, libraries):
    """빌드 기록의 라이브러리 판이 고정한 판과 다르면 경고 한 줄씩. package.sh 가 찍는다. 이미 만든 글꼴은
    지금 다시 설치해도 그대로라서, 고정한 판으로 설치한 뒤 다시 빌드해야 경고가 사라진다."""
    lines = []
    for name, pin, found in library_mismatches(root, libraries):
        got = "깔려 있지 않았어요" if found is None else f"{found} 이었어요"
        lines.append(f"경고: fonts/ 를 빌드할 때 {name} 는 {got}({REQUIREMENTS} 는 {pin}). "
                     f"pip install -r {REQUIREMENTS} 로 설치하고 ./build.sh 로 다시 빌드하세요")
    return lines


def snapshot(root):
    """빌드를 시작할 때의 코드·라이브러리·고정 시각. 개별 빌드와 매니페스트가 같은 시각을 쓴다."""
    return {"sources": sources_digest(root), "libraries": installed_versions(pinned_versions(root)),
            "source_date_epoch": source_date_epoch(root)}


def font_files():
    """VARIANTS 순서대로 build.sh 가 fonts/ 에 만드는 파일 이름."""
    return [f"JetBatangNF-{suffix}.ttf" for suffix, _, _ in VARIANTS]


def _font_directory(root, fonts_dir):
    if fonts_dir is None:
        return Path(root) / "fonts"
    directory = Path(fonts_dir)
    return directory if directory.is_absolute() else Path(root) / directory


def write_manifest(root, version, started, custom=(), *, fonts_dir=None):
    """열여섯 종을 다 만든 뒤 기록을 남긴다. started 는 빌드를 시작할 때 잡은 snapshot 이고, custom 은
    기본값과 다르게 준 빌드 값("SCALE=1.05" 꼴)이다. 그사이에 코드나 원본이 바뀌었으면 무엇으로 만든 글꼴인지
    알 수 없어서, 기록하지 않고 ValueError."""
    if sources_digest(root) != started["sources"]:
        raise ValueError("빌드하는 동안 코드나 RIDIBatang 원본이 바뀌었어요. ./build.sh 로 다시 빌드하세요")
    fonts = _font_directory(root, fonts_dir)
    info = {"version": version, "sources": started["sources"], "libraries": started["libraries"],
            "source_date_epoch": started["source_date_epoch"],
            "custom": list(custom), "fonts": {name: sha256_file(fonts / name) for name in font_files()}}
    # 쓰다 멈춰도 반쯤 쓴 기록이 남지 않게 다 쓴 뒤에 바꿔 넣는다.
    part = fonts / (MANIFEST + ".part")
    part.write_text(json.dumps(info, indent=2) + "\n")
    os.replace(part, fonts / MANIFEST)


def verify_manifest(root, *, fonts_dir=None):
    """선택한 출력 폴더가 지금 코드로 열여섯 종을 끝까지 빌드한 그대로인지 본다. 아니면 ValueError."""
    fonts = _font_directory(root, fonts_dir)
    rebuild = "./build.sh 로 다시 빌드하세요"
    try:
        info = json.loads((fonts / MANIFEST).read_text())
    except FileNotFoundError:
        raise ValueError(f"{fonts / MANIFEST} 가 없어요. 빌드가 끝나지 않았거나 예전 build.sh 로 만든 "
                         f"글꼴이에요. {rebuild}") from None
    except ValueError:
        info = None
    if not (isinstance(info, dict) and isinstance(info.get("version"), str)
            and isinstance(info.get("sources"), str) and isinstance(info.get("libraries"), dict)
            and isinstance(info.get("custom"), list) and isinstance(info.get("fonts"), dict)
            and type(info.get("source_date_epoch")) is int and info["source_date_epoch"] >= 0):
        raise ValueError(f"{fonts / MANIFEST} 를 읽을 수 없어요. {rebuild}")
    if info["sources"] != sources_digest(root):
        raise ValueError(f"{fonts} 는 지금과 다른 {'·'.join(SOURCES)} 로 만들었어요. {rebuild}")
    if list(info["fonts"]) != font_files():
        raise ValueError(f"{fonts / MANIFEST} 의 굵기 목록이 VARIANTS 와 달라요. {rebuild}")
    for name, digest in info["fonts"].items():
        if not (fonts / name).exists() or sha256_file(fonts / name) != digest:
            raise ValueError(f"{fonts / name} 가 빌드한 뒤에 바뀌었거나 없어요. {rebuild}")
    return info


def custom_build_warnings(info):
    """기본값과 다른 빌드 값으로 만든 기록이면 경고 한 줄. package.sh 가 찍는다. 릴리스는 기본값으로 만든다."""
    if not info["custom"]:
        return []
    return [f"경고: 기본값과 다른 빌드 값({', '.join(info['custom'])})으로 만든 fonts/ 예요. "
            "릴리스는 기본값으로 빌드하세요"]
