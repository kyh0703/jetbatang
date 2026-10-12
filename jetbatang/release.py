"""굵기 목록과 build.sh 가 재료를 확인할 때 쓰는 파일 해시. 표준 라이브러리만 쓴다."""
import hashlib


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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
