"""굵기 목록과, build.sh 가 fonts/ 에 남기는 빌드 기록. 표준 라이브러리만 쓴다."""
import hashlib
import json
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

# build.sh 가 열여섯 종을 모두 만든 뒤 fonts/ 에 남기는 기록. 어느 코드로 만든 어느 파일인지 적어서,
# 검사와 package.sh 가 예전 코드로 만들었거나 일부만 다시 만든 fonts/ 를 알아보게 한다.
MANIFEST = "build-info.json"

# 같은 재료로도 이 파일들이 바뀌면 글꼴이 달라진다. 재료의 해시는 build.sh 에 있다.
SOURCES = ("build.py", "build.sh", "requirements.txt", "jetbatang/*.py")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def font_files():
    """VARIANTS 순서대로 build.sh 가 fonts/ 에 만드는 파일 이름."""
    return [f"JetBatangNF-{suffix}.ttf" for suffix, _, _ in VARIANTS]


def write_manifest(root, version):
    fonts = Path(root) / "fonts"
    info = {"version": version, "sources": sources_digest(root),
            "fonts": {name: sha256_file(fonts / name) for name in font_files()}}
    (fonts / MANIFEST).write_text(json.dumps(info, indent=2) + "\n")


def verify_manifest(root):
    """fonts/ 가 지금 코드로 열여섯 종을 끝까지 빌드한 그대로인지 본다. 맞으면 (버전, 파일 이름들),
    아니면 ValueError."""
    fonts = Path(root) / "fonts"
    try:
        info = json.loads((fonts / MANIFEST).read_text())
    except FileNotFoundError:
        raise ValueError(f"fonts/{MANIFEST} 가 없어요. 빌드가 끝나지 않았거나 예전 build.sh 로 만든 "
                         "fonts/ 예요. ./build.sh 로 다시 빌드하세요") from None
    if info["sources"] != sources_digest(root):
        raise ValueError(f"fonts/ 는 지금과 다른 {'·'.join(SOURCES)} 로 만들었어요. "
                         "./build.sh 로 다시 빌드하세요")
    for name, digest in info["fonts"].items():
        if not (fonts / name).exists() or sha256_file(fonts / name) != digest:
            raise ValueError(f"fonts/{name} 가 빌드한 뒤에 바뀌었거나 없어요. ./build.sh 로 다시 빌드하세요")
    return info["version"], list(info["fonts"])
