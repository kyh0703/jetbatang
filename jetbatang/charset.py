"""어떤 글자를 RIDIBatang 에서 가져오고, 어떤 글자를 base 의 글리프로 때울지 정한다."""
import unicodedata


# 터미널에서 2칸을 차지하는(East Asian Wide) 구간만 가져온다.
# 나머지(라틴·그리스·키릴·괄호·수학기호·박스드로잉)는 base 쪽이 이미 고정폭이다.
WIDE_RANGES = [
    (0xAC00, 0xD7A3),   # 한글 완성형
    (0x3130, 0x318F),   # 한글 호환 자모
    (0x3041, 0x309F),   # 히라가나
    (0x30A0, 0x30FF),   # 가타카나
    (0x3000, 0x303F),   # CJK 문장부호 。、「」〜
    (0x3200, 0x32FF),   # 괄호문자·원문자 ㈜ ㉠
    (0x3300, 0x33FF),   # CJK 호환 문자 ㎡ ㎏ ㎞
    (0xFF01, 0xFF60),   # 전각 영숫자·기호
    (0xFFE0, 0xFFE6),   # 전각 통화기호 ￦
]

# RIDIBatang 에 없거나 잘못 그려진 글자를 같은 모양의 다른 글자로 때운다.
# ー(장음부호)는 가로 전폭 막대인데 RIDIBatang 에 없다. ―(horizontal bar) 가
# 같은 높이·같은 굵기의 막대라 그대로 쓴다. 없으면 コーヒー 가 두부로 깨진다.
# ￦(전각 원 기호)에는 전각 역슬래시 모양이 걸려 있어서 ₩ 모양을 쓴다.
ALIASES = {0x30FC: 0x2015, 0xFFE6: 0x20A9}

# base 가 1칸 폭으로 그렸지만 터미널은 2칸으로 세는 글자. 2칸 가운데로 옮긴다. ⚡ ﹢
# ☰(U+2630) 도 Unicode 16 부터 2칸이지만, 아직 1칸으로 세는 터미널에서 옆 글자를
# 덮지 않게 그대로 둔다. 2칸으로 세는 터미널에서는 왼쪽 칸에 그려질 뿐이다.
WIDEN = [0x26A1, 0xFE62]

# 터미널이 1칸으로 세는데 base 에 없는 글자 모양 기호. RIDIBatang 에서 가져와 대문자 높이로 base W
# 자리에 맞춘다. 다른 기호처럼 base ○ 크기로 줄이면 Ⅳ 가 소문자만 해진다. ₩ ℃ ℉ Ⅰ~Ⅹ ⅰ~ⅹ
NARROW = [0x20A9, 0x2103, 0x2109, *range(0x2160, 0x216A), *range(0x2170, 0x217A)]

# base 에 없는 KS X 1001 글자 가운데 base 의 다른 글자와 같은 것. 그 글리프를 그대로 건다.
# 옴(U+2126)·옹스트롬(U+212B) 기호는 그리스 Ω·라틴 Å 와 정준 등가이고, ―(U+2015) 는 1칸 줄표다.
BASE_ALIASES = {0x2126: 0x03A9, 0x212B: 0x00C5, 0x2015: 0x2014}


def is_wide(cp):
    return any(a <= cp <= b for a, b in WIDE_RANGES)


def ksx1001_symbols(bcmap):
    """base 에 없는 KS X 1001 기호 가운데 폭이 애매한 것. 터미널은 기본값으로 1칸에 센다.

    한국어 문서의 ※ ① ★ 같은 기호다. 한자 앞의 1~12행에서 고른다. Ĳ ĳ ⁿ ː 같은 라틴 글자는
    명조로 그리면 base 라틴 옆에서 튀어서 뺀다. 칸을 채워 이어져야 하는 괘선·블록(U+2500–259F)은
    줄이면 TUI 테두리가 끊기니 base 에 없어도 가져오지 않는다. NARROW 와 BASE_ALIASES 는 따로 다룬다.
    """
    for lead in range(0xA1, 0xAD):
        for trail in range(0xA1, 0xFF):
            try:
                ch = bytes([lead, trail]).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            cp = ord(ch)
            if (unicodedata.east_asian_width(ch) == "A" and cp not in bcmap
                    and not unicodedata.category(ch).startswith("L")
                    and not 0x2500 <= cp <= 0x259F
                    and cp not in NARROW and cp not in BASE_ALIASES):
                yield cp
