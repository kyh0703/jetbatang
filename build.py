#!/usr/bin/env python3
"""Nerd Font 패치본(라틴+아이콘)과 RIDIBatang(한글)을 한 파일로 합친다.

터미널은 한글을 2칸으로 세기 때문에, 한글 advance 를 라틴 1칸의 정확히 2배로
못 박는 것이 이 스크립트의 핵심이다. RIDIBatang 은 한글 advance 가 922~963 으로
제각각이라 그대로 두면 격자가 어긋난다.
"""
import argparse
import math
import re
import sys
import unicodedata

import pathops

from fontTools.otlLib.builder import buildLigatureSubstSubtable, buildLookup
from fontTools.misc.transform import Transform
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen, replayRecording
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import (ARGS_ARE_XY_VALUES,
                                             OVERLAP_COMPOUND, Glyph,
                                             GlyphComponent)

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

# RIDIBatang 에 없는 탁음 가나 → 탁점을 얹을 청음 가나. ゔ ヷ ヸ ヹ ヺ
VOICED = {0x3094: 0x3046, 0x30F7: 0x30EF, 0x30F8: 0x30F0, 0x30F9: 0x30F1, 0x30FA: 0x30F2}

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

# Windows GDI 는 한 가족에 Regular/Italic/Bold/Bold Italic 네 칸만 준다.
RIBBI = {"Regular", "Italic", "Bold", "Bold Italic"}
OFL_URL = "https://openfontlicense.org"
OFL_DESC = "This Font Software is licensed under the SIL Open Font License, Version 1.1."


def sanitize(name):
    n = re.sub(r"[^A-Za-z0-9._]", "_", name)
    return n if re.match(r"^[A-Za-z_]", n) else "g" + n


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


def font_revision(version):
    """릴리스 버전 X.Y.Z 를 head.fontRevision 값으로 바꾼다. 1.9.0 < 1.10.0 처럼 태그 순서를 지킨다.

    v1.0.0~v1.4.0 은 base JetBrains Mono 의 2.304 를 그대로 물려받았다. 옛 판과 새 판이 함께 깔리면
    fontconfig 는 fontRevision 이 큰 쪽을 고르므로, 새 판은 모두 그보다 커야 한다. 그래서 X·Y 를
    정수부에, Z 를 소수부에 넣는다. 1.5.0 은 105.00, 1.10.2 는 110.02 다.
    부호 있는 16.16 고정소수에 들어가야 하므로 상한은 327.67.99 다.
    """
    found = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not found or int(found[2]) > 99 or int(found[3]) > 99:
        raise ValueError(f"버전은 X.Y.Z 꼴이고 Y·Z 는 0~99 여야 해요: {version!r}")
    major, minor, patch = map(int, found.groups())
    integer = major * 100 + minor
    if integer >= 32768:
        raise ValueError(f"글꼴 내부 버전값으로 저장할 수 있는 상한은 327.67.99 예요: {version!r}")
    return integer + patch / 100


def embolden_ring(ex, ey):
    """굵기를 바꿀 방향 8 개를 (dx, dy) 목록으로 준다.

    같은 외곽선을 이 방향으로 조금씩 옮겨 겹쳐 놓으면 TrueType 의 nonzero
    winding 규칙이 합집합으로 칠해준다. 경계 연산(boolean op) 없이 획이 두꺼워진다.
    반대로 모두 겹치는 곳만 남기면(thin_copies) 획이 가늘어진다.
    """
    rx, ry = ex / 2.0, ey / 2.0
    d = math.sqrt(0.5)
    ring = [(1, 0), (-1, 0), (0, 1), (0, -1),
            (d, d), (d, -d), (-d, d), (-d, -d)]
    return sorted({(round(rx * a), round(ry * b)) for a, b in ring})


def make_composite(src, offsets):
    """src 외곽선을 offsets 만큼씩 옮겨 겹쳐 부르는 composite 글리프."""
    g = Glyph()
    g.numberOfContours = -1
    g.components = []
    for ox, oy in offsets:
        c = GlyphComponent()
        c.glyphName = src
        c.x, c.y = ox, oy
        c.flags = ARGS_ARE_XY_VALUES
        g.components.append(c)
    if len(offsets) > 1:
        g.components[0].flags |= OVERLAP_COMPOUND   # 겹칠 때만, 첫 component 에만 세운다
    return g


def outline(dglyph, tf, max_err):
    """donor 의 CFF 글리프를 tf 로 옮긴 TrueType 글리프로 만든다."""
    ttpen = TTGlyphPen(None)
    # CFF 와 glyf 는 외곽선 방향이 반대라 reverse_direction 이 필요하다.
    dglyph.draw(TransformPen(Cu2QuPen(ttpen, max_err, reverse_direction=True), tf))
    return ttpen.glyph()


def kana_contours(dglyph):
    """가나 외곽선을 나눠 몸통과 탁점·반탁점 경로를 골라낼 수 있게 한다."""
    rec = RecordingPen()
    dglyph.draw(rec)
    contours, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    return contours


class KanaMark:
    """원본 가나에서 떼어낸 결합 탁점·반탁점. 획 방향과 반탁점의 속공간을 유지한다."""

    def __init__(self, contours):
        self.contours = contours

    def draw(self, pen):
        for contour in self.contours:
            replayRecording(contour, pen)


class Voiced:
    """청음 가나에 ヴ 의 탁점을 얹은 글자. donor 글리프처럼 draw 만 한다."""

    def __init__(self, plain, room, marks):
        self.plain, self.room, self.marks = plain, room, marks

    def draw(self, pen):
        self.plain.draw(TransformPen(pen, self.room))
        for mark in self.marks:
            replayRecording(mark, pen)


def voiced_kana(dglyphs, dcmap, dhmtx):
    """VOICED 글자를 {cp: (그릴 거리, advance, 이름)} 으로 만든다.

    ヴ 는 ウ 에 탁점 두 획을 얹고, 그 자리를 비우려고 ウ 를 가로로 조금 줄여 왼쪽으로
    옮긴 글자다. 청음 글자를 ウ 와 같은 만큼 옮기고 ヴ 의 탁점을 그대로 얹는다.
    ワ 는 ウ 에서 윗점만 뺀 모양이라 ヷ 는 원본 디자인과 거의 같아진다.
    """
    contours = kana_contours(dglyphs[dcmap[0x30F4]])  # ヴ

    def area(contour):
        pen = AreaPen()
        replayRecording(contour, pen)
        return abs(pen.value)

    body = max(contours, key=area)                    # ウ. 나머지 둘이 탁점이다
    marks = [c for c in contours if c is not body]
    plain, moved = BoundsPen(None), BoundsPen(None)
    dglyphs[dcmap[0x30A6]].draw(plain)                # ウ
    replayRecording(body, moved)
    (x0, _, x1, _), (v0, _, v1, _) = plain.bounds, moved.bounds
    a = (v1 - v0) / (x1 - x0)
    room = Transform(a, 0, 0, 1, v0 - a * x0, 0)
    return {cp: (Voiced(dglyphs[dcmap[src]], room, marks), dhmtx[dcmap[src]][0], f"uni{cp:04X}")
            for cp, src in VOICED.items() if cp not in dcmap and src in dcmap}


def combining_kana(dglyphs, dcmap, dhmtx):
    """ヴ 의 탁점, パ 의 반탁점을 {cp: (경로, 원래 폭, 이름)} 으로 준다."""
    voiced = kana_contours(dglyphs[dcmap[0x30F4]])
    def area(contour):
        pen = AreaPen()
        replayRecording(contour, pen)
        return abs(pen.value)

    body = max(voiced, key=area)
    dakuten = [contour for contour in voiced if contour is not body]
    top = bounds(dglyphs, dcmap[0x30CF])[3]           # ハ 몸통보다 위에 있는 두 경로가 반탁점
    handakuten = []
    for contour in kana_contours(dglyphs[dcmap[0x30D1]]):
        pen = BoundsPen(None)
        replayRecording(contour, pen)
        if pen.bounds[3] > top:
            handakuten.append(contour)
    return {0x3099: (KanaMark(dakuten), dhmtx[dcmap[0x30F4]][0], "dakutencomb"),
            0x309A: (KanaMark(handakuten), dhmtx[dcmap[0x30D1]][0], "handakutencomb")}


def add_nfd_substitutions(font):
    """기존 라틴 GSUB 를 보존하면서 NFD 자모·가나를 같은 NFC 글리프로 조합한다."""
    cmap = font.getBestCmap()
    groups = [{} for _ in range(19)]
    for cp in range(0xAC00, 0xD7A4):
        if cp not in cmap:
            continue
        components = tuple(ord(ch) for ch in unicodedata.normalize("NFD", chr(cp)))
        if not all(component in cmap for component in components):
            continue
        group = groups[(cp - 0xAC00) // 588]
        group[tuple(cmap[component] for component in components)] = cmap[cp]
        if len(components) == 3:
            # NFC 의 LV 음절 뒤에 NFD 받침이 붙은 경우도 같은 LVT 음절로 조합한다.
            lv = cp - (cp - 0xAC00) % 28
            if lv in cmap:
                group[(cmap[lv], cmap[components[-1]])] = cmap[cp]
    kana = {}
    for cp in range(0x3041, 0x3100):
        components = tuple(ord(ch) for ch in unicodedata.normalize("NFD", chr(cp)))
        if (cp in cmap and len(components) == 2 and components[-1] in (0x3099, 0x309A)
                and all(component in cmap for component in components)):
            kana[tuple(cmap[component] for component in components)] = cmap[cp]
    subtables = [buildLigatureSubstSubtable(group) for group in (*groups, kana) if group]
    if not subtables:
        return

    if "GSUB" not in font:
        font["GSUB"] = newTable("GSUB")
        gsub = font["GSUB"].table = otTables.GSUB()
        gsub.Version = 0x00010000
        gsub.ScriptList = otTables.ScriptList()
        gsub.ScriptList.ScriptRecord = []
        gsub.FeatureList = otTables.FeatureList()
        gsub.FeatureList.FeatureRecord = []
        gsub.LookupList = otTables.LookupList()
        gsub.LookupList.Lookup = []
    gsub = font["GSUB"].table
    lookup_index = len(gsub.LookupList.Lookup)
    # 전체가 64 KiB 를 넘어도 각 하위 테이블에는 32비트 오프셋으로 접근한다.
    gsub.LookupList.Lookup.append(buildLookup(subtables, table="GSUB", extension=True))
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    features = gsub.FeatureList.FeatureRecord
    ccmp = [i for i, record in enumerate(features) if record.FeatureTag == "ccmp"]
    if not ccmp:
        index = next((i for i, record in enumerate(features) if record.FeatureTag > "ccmp"), len(features))
        record = otTables.FeatureRecord()
        record.FeatureTag = "ccmp"
        record.Feature = otTables.Feature()
        record.Feature.FeatureParams = None
        record.Feature.LookupListIndex = []
        features.insert(index, record)
        # FeatureRecord 는 태그 순서여야 하므로 삽입 뒤 기존 스크립트의 인덱스만 옮긴다.
        for script_record in gsub.ScriptList.ScriptRecord:
            script = script_record.Script
            languages = [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]
            for language in languages:
                if language is None:
                    continue
                language.FeatureIndex = [i + (i >= index) for i in language.FeatureIndex]
                if language.ReqFeatureIndex != 0xFFFF and language.ReqFeatureIndex >= index:
                    language.ReqFeatureIndex += 1
        variations = getattr(gsub, "FeatureVariations", None)
        if variations is not None:
            for variation in variations.FeatureVariationRecord:
                for substitution in variation.FeatureTableSubstitution.SubstitutionRecord:
                    if substitution.FeatureIndex >= index:
                        substitution.FeatureIndex += 1
        ccmp = [index]
    for index in ccmp:
        feature = features[index].Feature
        feature.LookupListIndex.append(lookup_index)
        feature.LookupCount = len(feature.LookupListIndex)
    gsub.FeatureList.FeatureCount = len(features)

    scripts = gsub.ScriptList.ScriptRecord
    for tag in ("DFLT", "hang", "kana"):
        record = next((record for record in scripts if record.ScriptTag == tag), None)
        # 없는 스크립트는 기존 DFLT 로 가게 둔다. ccmp 만 든 hang/kana 를 새로 만들면
        # 한글·가나로 시작하는 혼합 문자열에서 원래의 라틴 calt 리거처가 꺼진다.
        if record is None and tag != "DFLT":
            continue
        if record is None:
            record = otTables.ScriptRecord()
            record.ScriptTag = tag
            record.Script = otTables.Script()
            record.Script.LangSysRecord = []
            record.Script.LangSysCount = 0
            record.Script.DefaultLangSys = None
            scripts.append(record)
        script = record.Script
        if script.DefaultLangSys is None:
            script.DefaultLangSys = otTables.LangSys()
            script.DefaultLangSys.LookupOrder = None
            script.DefaultLangSys.ReqFeatureIndex = 0xFFFF
            script.DefaultLangSys.FeatureIndex = []
        for language in [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]:
            if not any(index in language.FeatureIndex for index in ccmp):
                language.FeatureIndex.append(ccmp[0])
            language.FeatureCount = len(language.FeatureIndex)
    scripts.sort(key=lambda record: record.ScriptTag)
    gsub.ScriptList.ScriptCount = len(scripts)


def bounds(glyphs, name, tf=None):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(TransformPen(pen, tf) if tf else pen)
    return pen.bounds


def fit_cell(dglyphs, dcmap, bglyphs, bcmap, shear, ex):
    """NARROW 글자를 base 1칸에 놓는 {cp: (변환, 가로 굵기 증가량)} 을 준다.

    세로는 대문자 H 높이를 base 에 맞추고, 가로도 같은 배율로 키운다. 기울이고 굵기를 불린
    뒤에 같은 굵기·기울기의 base W 보다 넓으면 W 의 가로 범위에 맞게 가로만 줄인다.
    RIDIBatang ₩ 은 폭이 815 라 Regular 에서 가로를 0.69 배로 줄인다. W 보다 좁은 Ⅰ 같은
    글자는 W 자리 가운데에 둔다. 한글처럼 올려 앉히지 않고 잉크 바닥을 기준선에 맞춘다.
    RIDIBatang 로마 숫자는 전각 틀에 맞춰 기준선보다 43~59 내려 앉아 있다.

    가로로 줄이는 글자는 가로 굵기 증가량도 같은 비율로 줄인다. 원래 폭에서 굵게 한 다음 가로로
    줄인 것과 같은 모양이라, 획과 획 사이의 비율이 줄이지 않은 글자와 같다. 줄인 뒤에 ex 를 다
    불리면 ExtraBold Ⅷ 은 0.55 배로 좁아진 획 사이가 메워져 획 다섯이 둘로 붙는다.
    """
    sy = bounds(bglyphs, bcmap[ord("H")])[3] / bounds(dglyphs, dcmap[ord("H")])[3]
    wx0, _, wx1, _ = bounds(bglyphs, bcmap[ord("W")])

    def span(name, sx):
        x0, _, x1, _ = bounds(dglyphs, name, Transform(sx, 0, shear * sy, sy, 0, 0))
        return x0, x1 - x0

    def grow(sx):
        return ex * min(1.0, sx / sy)

    def inked(name, sx):
        """굵기를 불린 뒤의 잉크 폭. 깎을 때는 깎기 전 잉크로 맞춘다. 가는 획이 끊겨 덜 깎여도
        W 를 넘지 않는다."""
        return span(name, sx)[1] + max(grow(sx), 0.0)

    fits = {}
    for cp in NARROW:
        if cp not in dcmap or cp in bcmap:
            continue
        name = dcmap[cp]
        # 기울인 뒤의 폭은 sx 에 대해 거의 일차지만, Ⅷ 처럼 양 끝을 차지하는 점이 sx 에 따라
        # 바뀌는 글자는 두 점으로 풀면 10 가까이 어긋난다. 할선법으로 반 단위 안쪽까지 다듬는다.
        lo, wlo = 0.5, inked(name, 0.5)
        sx, w = 1.0, inked(name, 1.0)
        for _ in range(8):
            if abs(w - (wx1 - wx0)) < 0.5 or w == wlo:
                break
            lo, wlo, sx = sx, w, sx + (wx1 - wx0 - w) * (sx - lo) / (w - wlo)
            w = inked(name, sx)
        sx = min(sy, sx)
        x0, w = span(name, sx)
        # 기준선까지는 정수 단위로 옮긴다. 소수로 옮기면 ExtraBold ⅷ 의 겹친 복사본을 skia 가
        # 두 경로 모두 틀리게 합쳐서 겹친 채 남았다.
        bottom = round(sy * bounds(dglyphs, name)[1])
        # 굵기는 양쪽으로 반씩 자라므로 불리기 전의 잉크를 W 가운데에 둔다.
        fits[cp] = (Transform(sx, 0, shear * sy, sy, (wx0 + wx1 - w) / 2 - x0, -bottom), grow(sx))
    return fits


def shifted_copies(glyph, offsets):
    """외곽선을 offsets 만큼씩 옮긴 복사본을 pathops.Path 로 하나씩 준다."""
    for ox, oy in offsets:
        copy = pathops.Path()
        glyph.draw(copy.getPen(glyphSet=None), None)
        yield copy.transform(1, 0, 0, 1, ox, oy)


def stacked(glyph, offsets):
    """복사본을 합치지 않고 한 경로에 겹쳐 담는다. composite 가 칠하는 모양 그대로다."""
    stack = pathops.Path()
    pen = stack.getPen(glyphSet=None)
    for copy in shifted_copies(glyph, offsets):
        copy.draw(pen)
    return stack


def by_simplify(glyph, offsets):
    stack = stacked(glyph, offsets)
    return pathops.simplify(stack, clockwise=True)


def by_opbuilder(glyph, offsets):
    builder = pathops.OpBuilder(fix_winding=True, keep_starting_points=False, clockwise=True)
    for copy in shifted_copies(glyph, offsets):
        builder.add(copy, pathops.PathOp.UNION)
    return builder.resolve()


def ink(path):
    """칠해지는 넓이. 속공간은 방향이 반대라 저절로 빠진다."""
    return abs(sum(c.area if c.clockwise else -c.area for c in path.contours))


def nudge(offsets):
    """복사본의 x·y 가 서로 겹치지 않게 아주 조금씩 어긋나게 민다.

    (-13, 5) 와 (13, 5) 처럼 y 가 같으면 두 복사본의 가로획이 같은 높이에서
    collinear 로 만난다. 경계 연산이 가장 자주 틀리는 자리다. 미는 양은 최대
    0.06 단위, 좌표를 정수로 반올림해 저장하고 나면 남지 않는다.
    """
    mid = (len(offsets) - 1) / 2.0
    return [(ox + (i - mid) * 0.017, oy + (i - mid) * 0.011)
            for i, (ox, oy) in enumerate(offsets)]


def unions(glyph, offsets):
    """알고리즘이 다른 두 경계 연산으로 구한 합집합. 예외를 낸 쪽은 뺀다."""
    paths = []
    for union in (by_simplify, by_opbuilder):
        try:
            paths.append(union(glyph, offsets))
        except pathops.PathOpsError:
            pass
    return paths


def agreed(paths):
    """두 경계 연산 결과가 모두 있고 칠해지는 넓이가 같으면 그 하나, 아니면 None."""
    if len(paths) < 2:
        return None
    a, b = ink(paths[0]), ink(paths[1])
    if not a or abs(a - b) > a * 1e-4:
        return None
    return paths[0]


# 경계 연산 결과와 정답이 칠하는 영역이 칠해진 넓이 대비 이만큼 넘게 어긋나면 틀린 것이다.
# 곡선을 꺾은선으로 펴며 생기는 차이는 5e-5 안쪽이고, 속공간을 먹은 합집합은 5e-4 넘게 어긋난다.
COVER_TOL = 2e-4


class EdgePen(BasePen):
    """외곽선을 꺾은선으로 펴서 (x0, y0, x1, y1) 선분으로 모은다. 곡선 하나를 STEPS 토막으로 편다.
    32 토막이면 곡선이 많은 ち 를 깎은 결과에서 꺾은선 차이만 2e-4 를 넘는다."""
    STEPS = 128

    def __init__(self):
        super().__init__(None)
        self.edges = []
        self.start = self.cur = None

    def _moveTo(self, pt):
        self.start = self.cur = pt

    def _lineTo(self, pt):
        self.edges.append((*self.cur, *pt))
        self.cur = pt

    def _curveToOne(self, p1, p2, p3):
        x0, y0 = self.cur
        for i in range(1, self.STEPS + 1):
            t = i / self.STEPS
            u = 1 - t
            a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            self._lineTo((a * x0 + b * p1[0] + c * p2[0] + d * p3[0],
                          a * y0 + b * p1[1] + c * p2[1] + d * p3[1]))

    def _closePath(self):
        if self.cur != self.start:
            self._lineTo(self.start)

    _endPath = _closePath


def coverage(path):
    """nonzero 규칙으로 칠해지는 가로 구간을 높이 1 마다 구한다. {줄: [(x0, x1), ...]}

    TrueType 이 겹친 composite 를 칠하는 규칙 그대로라, 경계 연산을 거치지 않은 정답이 된다.
    """
    pen = EdgePen()
    path.draw(pen)
    hits = {}
    for x0, y0, x1, y1 in pen.edges:
        if y0 == y1:
            continue
        wind = 1 if y1 > y0 else -1
        slope = (x1 - x0) / (y1 - y0)
        # 줄 r 은 높이 r + 0.5 에서 잰다. 선분의 아래 끝은 넣고 위 끝은 뺀다.
        for r in range(math.ceil(min(y0, y1) - 0.5), math.ceil(max(y0, y1) - 0.5)):
            hits.setdefault(r, []).append((x0 + (r + 0.5 - y0) * slope, wind))
    rows = {}
    for r, xs in hits.items():
        xs.sort()
        spans, winding, start = [], 0, 0.0
        for x, wind in xs:
            if winding == 0:
                start = x
            winding += wind
            if winding == 0:
                spans.append((start, x))
        rows[r] = spans
    return rows


def painted(rows):
    return sum(x1 - x0 for spans in rows.values() for x0, x1 in spans)


def overlap(a, b):
    """두 coverage 가 함께 칠하는 구간."""
    rows = {}
    for r in a.keys() & b.keys():
        p, q, i, j, spans = a[r], b[r], 0, 0, []
        while i < len(p) and j < len(q):
            lo, hi = max(p[i][0], q[j][0]), min(p[i][1], q[j][1])
            if lo < hi:
                spans.append((lo, hi))
            if p[i][1] < q[j][1]:
                i += 1
            else:
                j += 1
        if spans:
            rows[r] = spans
    return rows


def mismatch(a, b):
    """두 coverage 가운데 한쪽만 칠하는 넓이."""
    return painted(a) + painted(b) - 2 * painted(overlap(a, b))


def painted_like_stack(glyph, offsets, paths):
    """겹친 복사본을 직접 칠해 보고, 그와 같게 칠해지는 합집합을 고른다. 없으면 None."""
    truth = coverage(stacked(glyph, offsets))
    limit = painted(truth) * COVER_TOL
    for path in paths:
        if mismatch(truth, coverage(path)) <= limit:
            return path
    return None


def union_path(glyph, offsets):
    """겹쳐 놓은 복사본들의 합집합 경로. 못 믿을 결과면 None.

    skia 의 경계 연산은 이런 입력 — 같은 외곽선을 평행 이동한 복사본들 — 에서
    가로·세로 직선이 collinear 로 만나면 드물게 예외도 없이 속공간을 먹어 버린다.
    이탤릭 아·야 의 ㅇ 이 까맣게 메워지던 원인이었고, 조용히 틀리기 때문에 결과만
    보고는 알 수 없다. 그래서 알고리즘이 다른 두 경로로 구해 칠해지는 넓이가
    같을 때만 믿는다. 둘이 어긋나면 복사본을 조금 밀어 한 번 더 해 본다.

    그래도 어긋나면 겹친 복사본을 nonzero 규칙으로 직접 칠해 보고, 처음 구한 두
    합집합 가운데 그와 같게 칠해지는 쪽을 쓴다. 느려서 마지막에만 한다. 복사본을
    한 쌍씩 합치는 세 번째 경계 연산은 OpBuilder 와 같이 틀려서(Bold 휑,
    ExtraBold Italic ｓ) 다수결에 쓸 수 없다.
    """
    first = unions(glyph, offsets)
    picked = agreed(first)
    if picked is None:
        picked = agreed(unions(glyph, nudge(offsets)))
    if picked is None:
        picked = painted_like_stack(glyph, offsets, first)
    return picked


def to_glyph(path):
    ttpen = TTGlyphPen(None)
    path.draw(ttpen)
    glyph = ttpen.glyph()
    return glyph if glyph.numberOfContours else None


def merge_copies(glyph, offsets):
    """겹쳐 놓은 복사본들을 외곽선 하나로 합친다. 못 믿을 결과면 None 이고, 그러면 겹친 채로 둔다."""
    path = union_path(glyph, offsets)
    return None if path is None else to_glyph(path)


def topology(path):
    """(바깥 외곽선 수, 속공간 수). 가는 획이 끊기거나 획 사이가 터지면 달라진다."""
    contours = list(pathops.simplify(path, clockwise=True).contours)
    outer = sum(c.clockwise for c in contours)
    return outer, len(contours) - outer


def by_intersection(path, offsets):
    thin = None
    for ox, oy in offsets:
        copy = pathops.Path(path).transform(1, 0, 0, 1, ox, oy)
        thin = copy if thin is None else pathops.op(thin, copy, pathops.PathOp.INTERSECTION,
                                                     clockwise=True)
    return thin


def rectangle(x0, y0, x1, y1):
    rect = pathops.Path()
    rect.moveTo(x0, y0)
    rect.lineTo(x0, y1)
    rect.lineTo(x1, y1)
    rect.lineTo(x1, y0)
    rect.close()
    return rect


def by_complement(path, offsets):
    """바깥(넉넉한 상자에서 글자를 뺀 곳)을 불린 만큼 상자에서 뺀다. 교집합과 같은 답을
    경계 연산 한 번과 nonzero 합집합 한 번으로 구한다. 상자 가장자리는 옮긴 거리보다 바깥이라
    결과에 닿지 않는다."""
    clean = pathops.simplify(path, clockwise=True)
    m = max(max(abs(ox), abs(oy)) for ox, oy in offsets) + 2
    x0, y0, x1, y1 = clean.bounds
    box = rectangle(x0 - 2 * m, y0 - 2 * m, x1 + 2 * m, y1 + 2 * m)
    if not box.clockwise:
        box.reverse()
    clean.reverse()     # 상자와 방향이 반대인 외곽선을 겹치면 글자 자리가 비어 바깥만 칠해진다
    stack = pathops.Path()
    for ox, oy in offsets:
        stack.addPath(box.transform(1, 0, 0, 1, ox, oy))
        stack.addPath(clean.transform(1, 0, 0, 1, ox, oy))
    outside = pathops.simplify(stack, clockwise=True)
    return pathops.op(rectangle(x0 - m, y0 - m, x1 + m, y1 + m), outside,
                      pathops.PathOp.DIFFERENCE, clockwise=True)


def shifted(rows, ox, oy):
    """coverage 를 정수 (ox, oy) 만큼 옮긴다. 줄은 정수 높이마다 재므로 그대로 옮겨진다."""
    return {r + oy: [(x0 + ox, x1 + ox) for x0, x1 in spans] for r, spans in rows.items()}


def thin_copies(glyph, offsets):
    """복사본이 모두 겹치는 곳만 남겨 획을 깎은 경로. 못 믿을 결과면 None. offsets 는 정수여야
    한다. 정답을 칠할 때 원래 외곽선의 줄을 그대로 옮겨 쓴다.

    union_path 의 반대다. 같은 외곽선을 사방으로 옮긴 복사본의 교집합은 옮긴 거리만큼
    획을 양쪽에서 깎는다. 원래 자리의 외곽선도 함께 겹친다. 여덟 방향 복사본만 겹치면
    비스듬하고 좁은 틈은 여덟 복사본이 모두 잉크라서 틈 안이 칠해진다(Thin 의 れ ね).
    skia 의 경계 연산은 교집합에서도 조용히 틀려서(LightItalic 의 책), 알고리즘이 다른 두
    경로로 구해 칠해지는 넓이가 같을 때만 믿는다. 어긋나면 원래 외곽선을 직접 칠한 구간을
    옮겨 가며 겹친 정답과 같게 칠해지는 쪽을 쓴다.
    """
    offsets = sorted({(0, 0), *offsets})
    path = glyph_path(glyph)
    results = []
    for thin in (by_intersection, by_complement):
        try:
            results.append(thin(path, offsets))
        except pathops.PathOpsError:
            pass
    picked = agreed(results)
    if picked is not None:
        return picked
    source = coverage(path)
    truth = None
    for ox, oy in offsets:
        moved = shifted(source, ox, oy)
        truth = moved if truth is None else overlap(truth, moved)
    limit = painted(truth) * COVER_TOL
    for result in results:
        if mismatch(truth, coverage(result)) <= limit:
            return result
    return None


def glyph_path(glyph):
    path = pathops.Path()
    glyph.draw(path.getPen(glyphSet=None), None)
    return path


def shape_of(glyph):
    """glyph 의 topology. 못 구하면 None. 경계 연산이 내놓은 경로가 아니라 저장할 글리프로 본다.
    TTGlyphPen 이 좌표를 정수로 반올림하며 반 단위보다 좁은 틈을 메워서, 반올림 전 경로로 보면
    Bold ⓠ 의 꼬리가 원에 붙는 것을 놓친다."""
    try:
        return topology(glyph_path(glyph))
    except pathops.PathOpsError:
        return None


# 굵기를 바꾸다 모양이 바뀌는 글자는 이 비율로 덜 바꿔 본다. Thin 에서는 ㎡ 『 의 가는 획이
# 사라지고, Bold 에서는 1칸으로 줄인 ⑫ 의 숫자가 원에 붙는다. 끝까지 안 되면 그대로 둔다.
REWEIGH_STEPS = (1.0, 0.75, 0.5, 0.25)


def reweigh(glyph, gx, gy):
    """획을 가로 gx, 세로 gy 만큼 불리거나(양수) 깎아(음수) 외곽선 하나로 만든 글리프와 실제로
    바꾼 비율. 가는 획이 끊기거나 사라지고, 획이 서로 붙거나 속공간이 막혀 바깥 외곽선이나
    속공간 수가 바뀌면 덜 바꿔 본다. 끝까지 안 되면 (None, 0)."""
    shape = shape_of(glyph)
    if shape is None:
        return None, 0.0
    for step in REWEIGH_STEPS:
        ring = embolden_ring(abs(gx) * step, abs(gy) * step)
        result = union_path(glyph, ring) if gx > 0 or gy > 0 else thin_copies(glyph, ring)
        reweighed = None if result is None else to_glyph(result)
        if reweighed is not None and shape_of(reweighed) == shape:
            return reweighed, step
    return None, 0.0


def legacy_names(family, style):
    """nameID 1/2 에 넣을 (가족, 스타일). 16 종을 네 칸짜리 규칙에 욱여넣는다.

    RIBBI 바깥 굵기는 가족 이름 쪽에 굵기를 붙여 따로 가족을 만든다.
    (JetBatang NF SemiBold / Italic) 실제 가족은 nameID 16/17 로만 알린다.
    """
    if style in RIBBI:
        return family, style
    italic = style.endswith("Italic")
    weight = style[:-len("Italic")].strip() if italic else style
    return f"{family} {weight}", ("Italic" if italic else "Regular")


def get_name(font, nid):
    rec = font["name"].getDebugName(nid)
    return rec.strip() if rec else ""


def set_name(font, nid, value):
    font["name"].setName(value, nid, 3, 1, 0x409)   # Windows
    font["name"].setName(value, nid, 1, 0, 0)       # Mac


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True,
                    help="라틴·아이콘을 담당할 Nerd Font Mono ttf")
    ap.add_argument("--donor", required=True, help="RIDIBatang.otf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--font-version", required=True,
                    help="릴리스 버전 X.Y.Z. 글꼴 정보의 버전(nameID 5)과 head.fontRevision 에 들어간다")
    ap.add_argument("--family", default="JetBatang NF")
    ap.add_argument("--style", default="Regular",
                    help="타이포그래픽 스타일. 예: Regular, Italic, SemiBold, Bold Italic")
    ap.add_argument("--scale", type=float, default=1.00,
                    help="한글 배율(donor upem 기준). 1.00 = RIDIBatang 원본 크기")
    ap.add_argument("--yshift", type=float, default=60.0,
                    help="한글 세로 이동(base 단위). 바탕체는 받침이 깊어 라틴보다 낮게 앉는다")
    ap.add_argument("--shear-from-base", action="store_true",
                    help="base 의 italicAngle 만큼 한글도 기울인다(가짜 이탤릭)")
    ap.add_argument("--shear-pivot", type=float, default=0.325,
                    help="기울임 회전축 높이(em 비율). 한글 세로 중앙")
    ap.add_argument("--embolden", type=float, default=0.0,
                    help="한글 가로 굵기 증가량(base 단위). 음수면 그만큼 깎는다. RIDIBatang 은 "
                         "한 굵기뿐이라 다른 굵기는 이걸로 만든다")
    ap.add_argument("--embolden-y", type=float, default=None,
                    help="한글 세로 굵기 증가량. 생략하면 --embolden 이 양수일 때 0.4 배, 음수일 때 "
                         "0.8 배. 명조 Bold 는 세로획이 주로 굵어지지만 가로획을 그대로 두면 저해상도에서 "
                         "세로획만 진하고 가로획은 흐려 얼룩져 보인다. 가로획이 겹겹이 쌓이는 "
                         "글자(능·동·닙)의 속공간이 메워지지 않는 선에서 절반 조금 못 되게 준다. "
                         "깎을 때는 RIDIBatang 의 가로획 67 과 세로획 82 의 비율대로 깎는다. "
                         "0.4 배만 깎으면 Thin 에서 가로획이 세로획보다 굵어진다")
    ap.add_argument("--max-err", type=float, default=0.001,
                    help="곡선 변환 허용오차(em 비율)")
    args = ap.parse_args()
    try:
        revision = font_revision(args.font_version)
    except ValueError as exc:
        ap.error(str(exc))

    base = TTFont(args.base)
    donor = TTFont(args.donor)

    upem = base["head"].unitsPerEm
    cell = base["hmtx"]["A"][0]        # 라틴 1칸
    wide = cell * 2                    # 한글 2칸
    donor_upem = donor["head"].unitsPerEm
    scale = args.scale * upem / donor_upem
    max_err = args.max_err * upem
    pivot = args.shear_pivot * upem

    ex = args.embolden
    ey = args.embolden_y if args.embolden_y is not None else ex * (0.4 if ex > 0 else 0.8)
    if ex * ey < 0:
        ap.error("--embolden 과 --embolden-y 는 부호가 같아야 해요")
    thinner = ex < 0 or ey < 0
    offsets = embolden_ring(ex, ey) if (ex > 0 or ey > 0) else []

    shear = 0.0
    if args.shear_from_base:
        angle = base["post"].italicAngle          # 오른쪽으로 누우면 음수
        shear = math.tan(math.radians(-angle))

    print(f"base upem={upem} cell={cell} wide={wide} | donor upem={donor_upem} "
          f"| scale={scale:.4f} shear={shear:.4f} embolden={ex:g}/{ey:g}")

    dcmap = donor.getBestCmap()
    dglyphs = donor.getGlyphSet()
    dhmtx = donor["hmtx"]

    glyf, hmtx = base["glyf"], base["hmtx"]
    order = list(base.getGlyphOrder())
    taken = set(order)
    added = {}

    def unique_name(dname):
        gname = sanitize("rb." + dname)
        i = 2
        while gname in taken:
            gname = sanitize(f"rb.{dname}.{i}")
            i += 1
        taken.add(gname)
        return gname

    def put(name, glyph, advance=wide):
        glyf.glyphs[name] = glyph
        glyph.recalcBounds(glyf)
        hmtx.metrics[name] = (advance, glyph.xMin if glyph.numberOfContours else 0)
        order.append(name)

    def centered(advance):
        """donor advance box 를 한글 2칸 가운데에 놓는다. 원본의 좌우 균형을 그대로 보존한다."""
        dx = (wide - advance * scale) / 2.0
        # yx 항이 기울임. pivot 높이를 축으로 돌려 글자가 칸 밖으로 밀리지 않게 한다.
        return Transform(scale, 0, shear * scale, scale, dx - shear * pivot, args.yshift)

    targets = {cp: dcmap[cp] for cp in dcmap if is_wide(cp)}
    targets.update({cp: dcmap[src] for cp, src in ALIASES.items() if src in dcmap})

    # cp → (그릴 거리, 변환, 폭, 이름)
    sources = {cp: (dglyphs[name], centered(dhmtx[name][0]), wide, name)
               for cp, name in targets.items() if name in dhmtx.metrics}
    skipped = len(targets) - len(sources)
    for cp, (drawing, advance, name) in voiced_kana(dglyphs, dcmap, dhmtx).items():
        sources[cp] = (drawing, centered(advance), wide, name)
    for cp, (drawing, advance, name) in combining_kana(dglyphs, dcmap, dhmtx).items():
        tf = centered(advance)
        # 결합점의 advance 는 0. 현재 펜 위치에서 직전의 두 칸으로 돌아가 놓는다.
        sources[cp] = (drawing, Transform(tf.xx, tf.xy, tf.yx, tf.yy, tf.dx - wide, tf.dy), 0, name)
    bcmap = base.getBestCmap()
    bglyphs = base.getGlyphSet()

    # 1칸 기호는 base ○ 크기로 맞춘다. RIDIBatang ○ 이 base ○ 가 되는 배율로 줄이고, 그래도
    # base ○ 보다 넓은 글자(① ♣)는 그 폭에 들게 더 줄인다. 굵기를 불릴 몫도 미리 뺀다.
    # 이탤릭에서도 base ○ ● ◇ 처럼 세워 둔다.
    limit = cell
    if 0x25CB in bcmap:
        x0, _, x1, _ = bounds(bglyphs, bcmap[0x25CB])
        limit = x1 - x0
    x0, _, x1, _ = bounds(dglyphs, dcmap[0x25CB])
    circle = limit / (x1 - x0)
    dmid = (donor["hhea"].ascent + donor["hhea"].descent) / 2.0     # donor 전각 틀의 세로 가운데

    def in_cell(name):
        """donor 기호를 base 1칸 가운데에 줄여 놓는 (변환, 배율). 2칸에 놓을 때와 세로 가운데가 같아서
        ① 과 ㉠ 이 한 줄에 나란하다. 가로는 잉크 가운데를 맞춘다. ☜ ☞ ∝ ℡ 처럼 전각 틀의 한쪽으로
        쏠린 기호를 틀째 가운데에 두면 base ○ 보다 옆 칸을 더 덮는다."""
        x0, _, x1, _ = bounds(dglyphs, name)
        k = min(circle, limit / (x1 - x0 + max(ex, 0.0)))
        return Transform(k, 0, 0, k, (cell - (x0 + x1) * k) / 2.0, (scale - k) * dmid + args.yshift), k

    # 기본(ex, ey)과 다른 굵기 증가량으로 불리는 글자. 줄여 넣는 글자는 줄인 비율만큼 덜 불린다.
    # 원래 크기에서 굵게 한 다음 줄인 것과 같은 모양이라, 0.6 배로 좁아진 ⑧ ⓐ 의 속공간이 덜 막힌다.
    grows = {}
    symbols = set()
    for cp in ksx1001_symbols(bcmap):
        if cp in dcmap:
            tf, k = in_cell(dcmap[cp])
            sources[cp] = (dglyphs[dcmap[cp]], tf, cell, dcmap[cp])
            grows[cp] = (ex * k, ey * k)
            symbols.add(cp)
    for cp, (tf, grow) in fit_cell(dglyphs, dcmap, bglyphs, bcmap, shear, ex).items():
        sources[cp] = (dglyphs[dcmap[cp]], tf, cell, dcmap[cp])
        grows[cp] = (grow, ey)

    reshaped, partly, kept = 0, [], []
    for cp in sorted(sources):
        drawing, tf, advance, dname = sources[cp]

        try:
            glyph = outline(drawing, tf, max_err)
        except Exception as exc:
            print(f"  skip U+{cp:04X} {dname}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        gname = unique_name(dname)
        gx, gy = grows.get(cp, (ex, ey))

        # 깎을 때는 한글·가나 등, 불릴 때는 1칸 기호만 모양을 지키며 굵기를 바꾼다. 한글은 불리면
        # ㅃ ㄳ 처럼 가까운 획이 붙는 게 자연스럽지만, 줄여 넣은 ⑫ 의 숫자가 원에 붙으면 읽을 수 없다.
        # 1칸 기호는 0.6 배로 줄여 넣어 획이 이미 Light 라틴보다 가늘다(① 의 원 33). 한글만큼
        # 깎으면 Thin 에서 원이 7 로 거의 사라져서 깎지 않는다.
        if thinner:
            reshape = cp not in symbols
        else:
            reshape = bool(offsets) and cp in symbols
        if glyph.numberOfContours and reshape:
            changed, step = reweigh(glyph, gx, gy)
            if changed is None:
                kept.append(chr(cp))
            else:
                glyph = changed
                reshaped += 1
                if step < 1:
                    partly.append(chr(cp))
        elif offsets and glyph.numberOfContours:
            # 원본 외곽선은 cmap 에 걸지 않는 글리프로 두고, 그것을 여러 번 겹쳐
            # 부르는 composite 를 실제 글자로 쓴다. 점을 복사하지 않아 용량이 거의 안 는다.
            src = gname + ".src"
            taken.add(src)
            put(src, glyph, advance)
            glyph = make_composite(src, embolden_ring(gx, gy))
        put(gname, glyph, advance)
        added[cp] = gname

    print(f"  한글 등 {len(added)}자 추가, {skipped}자 건너뜀")
    if thinner or offsets:
        verb = "깎음" if thinner else "불림(1칸 기호)"
        print(f"  모양을 지키며 {verb}: {reshaped}자"
              + (f", 덜 바꿈: {''.join(partly)}" if partly else "")
              + (f", 그대로 둠: {''.join(kept)}" if kept else ""))

    if offsets:
        # 겹쳐 놓은 composite 를 그대로 두면 macOS CoreText 가 겹친 가장자리마다
        # 안티앨리어싱을 따로 해서 획이 번져 보인다(FreeType 은 멀쩡하다).
        # 그래서 합집합을 구해 외곽선 하나로 만든다. 믿을 수 없는 글자만 겹친 채 둔다.
        merged, failed = 0, []
        for cp, name in added.items():
            if not glyf[name].isComposite():
                continue
            src = name + ".src"
            one = merge_copies(glyf[src], embolden_ring(*grows.get(cp, (ex, ey))))
            if one is None:
                failed.append(chr(cp))
                continue
            glyf.glyphs[name] = one
            one.recalcBounds(glyf)
            hmtx.metrics[name] = (hmtx[name][0], one.xMin)
            merged += 1
        used = {c.glyphName for n in added.values()
                if glyf[n].isComposite() for c in glyf[n].components}
        for name in added.values():
            src = name + ".src"
            if src in glyf.glyphs and src not in used:
                del glyf.glyphs[src]
                del hmtx.metrics[src]
                order.remove(src)
        print(f"  외곽선 합침: {merged}자" + (f", 겹친 채 둠: {' '.join(failed)}" if failed else ""))

    # 터미널이 2칸으로 세는 base 글자를 2칸 가운데로 옮겨 부른다. 원래 글리프는 그대로 둔다.
    for cp in WIDEN:
        if cp not in bcmap:
            continue
        src = bcmap[cp]
        gname = src + ".wide"
        taken.add(gname)
        put(gname, make_composite(src, [((wide - hmtx[src][0]) // 2, 0)]))
        added[cp] = gname

    # base 에 같은 글자가 있으면 RIDIBatang 에서 가져오지 않고 base 글리프를 그대로 건다.
    for cp, src in BASE_ALIASES.items():
        if cp not in bcmap and src in bcmap:
            added[cp] = bcmap[src]


    # NFD 의 초성·중성·종성은 호환 자모의 외곽선을 재사용하되 서로 다른 glyph ID 를 준다.
    # 같은 ID 를 걸면 ccmp 가 호환 자모 "ㄱㅏ" 까지 "가" 로 조합해 버린다.
    cmap = bcmap | added
    modern_jamo = (*range(0x1100, 0x1113), *range(0x1161, 0x1176), *range(0x11A8, 0x11C3))
    for cp in modern_jamo:
        letter = unicodedata.name(chr(cp)).split(" ", 2)[2]
        compatible = ord(unicodedata.lookup("HANGUL LETTER " + letter))
        if compatible not in cmap:
            continue
        gname = unique_name(f"nfd{cp:04X}")
        leading = cp < 0x1161
        put(gname, make_composite(cmap[compatible], [(0 if leading else -wide, 0)]),
            wide if leading else 0)
        added[cp] = gname
    base.setGlyphOrder(order)
    glyf.glyphOrder = order
    base["maxp"].numGlyphs = len(order)

    for sub in base["cmap"].tables:
        if not sub.isUnicode():
            continue
        for cp, gname in added.items():
            if cp <= 0xFFFF or sub.format in (12, 13):
                sub.cmap[cp] = gname

    add_nfd_substitutions(base)
    if "GDEF" in base and base["GDEF"].table.GlyphClassDef is not None:
        for cp in (0x3099, 0x309A):
            base["GDEF"].table.GlyphClassDef.classDefs[added[cp]] = 3

    # 한글을 쓸 수 있는 폰트라고 Windows 에 알린다
    os2 = base["OS/2"]
    try:
        os2.recalcUnicodeRanges(base)
    except Exception as exc:
        print(f"  (unicode range 재계산 생략: {exc})")
    os2.ulCodePageRange1 |= (1 << 19) | (1 << 21)   # 949 Wansung / 1361 Johab

    copyright_ = " | ".join(filter(None, [
        f"Latin & icons: {get_name(base, 0)}",
        f"Hangul: {get_name(donor, 0)}",
        "Merged derivative, SIL Open Font License 1.1.",
    ]))
    fam1, sub2 = legacy_names(args.family, args.style)
    full = f"{args.family} {args.style}"
    ps = (re.sub(r"[^A-Za-z0-9]", "", args.family) + "-"
          + re.sub(r"[^A-Za-z0-9]", "", args.style))

    # 원본의 이름·상표 기록은 통째로 버리고 새로 쓴다.
    # base 의 Reserved Font Name 과 donor 의 등록상표를 물려받지 않기 위해서다.
    drop = set(range(0, 15)) | {16, 17, 18, 20, 21, 22}
    base["name"].names = [n for n in base["name"].names if n.nameID not in drop]
    for nid, value in [(0, copyright_), (1, fam1), (2, sub2),
                       (3, f"{ps};merged-with-RIDIBatang"), (4, full),
                       (5, f"Version {args.font_version}"), (6, ps),
                       (13, OFL_DESC), (14, OFL_URL), (16, args.family), (17, args.style)]:
        set_name(base, nid, value)
    # 비워 두면 base 의 2.304 가 남아 JetBrains Mono 와 같은 판으로 보인다.
    base["head"].fontRevision = revision

    base.save(args.out)
    print(f"  저장: {args.out}")


if __name__ == "__main__":
    main()
