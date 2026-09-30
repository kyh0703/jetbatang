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

import pathops

from fontTools.misc.transform import Transform
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen, replayRecording
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
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

# 터미널이 1칸으로 세는데 base 에 없는 글자. RIDIBatang 에서 가져와 1칸에 맞춘다. ₩
NARROW = [0x20A9]

# Windows GDI 는 한 가족에 Regular/Italic/Bold/Bold Italic 네 칸만 준다.
RIBBI = {"Regular", "Italic", "Bold", "Bold Italic"}
OFL_URL = "https://openfontlicense.org"
OFL_DESC = "This Font Software is licensed under the SIL Open Font License, Version 1.1."


def sanitize(name):
    n = re.sub(r"[^A-Za-z0-9._]", "_", name)
    return n if re.match(r"^[A-Za-z_]", n) else "g" + n


def is_wide(cp):
    return any(a <= cp <= b for a, b in WIDE_RANGES)


def embolden_ring(ex, ey):
    """굵기를 더할 방향 8 개를 (dx, dy) 목록으로 준다.

    같은 외곽선을 이 방향으로 조금씩 옮겨 겹쳐 놓으면 TrueType 의 nonzero
    winding 규칙이 합집합으로 칠해준다. 경계 연산(boolean op) 없이 획이 두꺼워진다.
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
    rec = RecordingPen()
    dglyphs[dcmap[0x30F4]].draw(rec)                  # ヴ
    contours, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []

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


def fit_cell(dglyphs, dcmap, bglyphs, bcmap, shear, ex):
    """NARROW 글자를 base 1칸에 놓는 변환을 {cp: 변환} 으로 준다.

    기울이고 굵기를 불린 뒤의 가로 범위가 같은 굵기·기울기의 base W 와 같게 하고,
    세로는 대문자 H 높이를 base 에 맞춘다. RIDIBatang ₩ 은 폭이 815 라 Regular 에서
    가로를 0.69 배로 줄인다. 한글처럼 올려 앉히지 않는다.
    """
    def bounds(glyphs, name, tf=None):
        pen = BoundsPen(glyphs)
        glyphs[name].draw(TransformPen(pen, tf) if tf else pen)
        return pen.bounds

    sy = bounds(bglyphs, bcmap[ord("H")])[3] / bounds(dglyphs, dcmap[ord("H")])[3]
    wx0, _, wx1, _ = bounds(bglyphs, bcmap[ord("W")])
    left, width = wx0 + ex / 2, wx1 - wx0 - ex        # 굵기를 불릴 몫을 뺀 자리

    def span(name, sx):
        x0, _, x1, _ = bounds(dglyphs, name, Transform(sx, 0, shear * sy, sy, 0, 0))
        return x0, x1 - x0

    fits = {}
    for cp in NARROW:
        if cp not in dcmap or cp in bcmap:
            continue
        name = dcmap[cp]
        # 기울인 뒤의 폭은 sx 에 대해 일차라 두 점으로 푼다.
        _, w1 = span(name, 1.0)
        _, w2 = span(name, 0.5)
        sx = 0.5 + (width - w2) * 0.5 / (w1 - w2)
        x0, _ = span(name, sx)
        fits[cp] = Transform(sx, 0, shear * sy, sy, left - x0, 0)
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
    return pathops.simplify(stack, clockwise=stack.clockwise)


def by_opbuilder(glyph, offsets):
    builder = pathops.OpBuilder(fix_winding=True, keep_starting_points=False)
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
    """두 합집합이 모두 있고 칠해지는 넓이가 같으면 그 하나, 아니면 None."""
    if len(paths) < 2:
        return None
    a, b = ink(paths[0]), ink(paths[1])
    if not a or abs(a - b) > a * 1e-4:
        return None
    return paths[0]


# 합친 외곽선과 겹친 복사본이 칠하는 영역이 칠해진 넓이 대비 이만큼 넘게 어긋나면 틀린 것이다.
# 곡선을 꺾은선으로 펴며 생기는 차이는 5e-5 안쪽이고, 속공간을 먹은 결과는 5e-4 넘게 어긋난다.
COVER_TOL = 2e-4


class EdgePen(BasePen):
    """외곽선을 꺾은선으로 펴서 (x0, y0, x1, y1) 선분으로 모은다."""
    STEPS = 32

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


def mismatch(a, b):
    """두 coverage 가운데 한쪽만 칠하는 넓이."""
    both = 0.0
    for r in a.keys() & b.keys():
        p, q, i, j = a[r], b[r], 0, 0
        while i < len(p) and j < len(q):
            both += max(0.0, min(p[i][1], q[j][1]) - max(p[i][0], q[j][0]))
            if p[i][1] < q[j][1]:
                i += 1
            else:
                j += 1
    return painted(a) + painted(b) - 2 * both


def painted_like_stack(glyph, offsets, paths):
    """겹친 복사본을 직접 칠해 보고, 그와 같게 칠해지는 합집합을 고른다. 없으면 None."""
    truth = coverage(stacked(glyph, offsets))
    limit = painted(truth) * COVER_TOL
    for path in paths:
        if mismatch(truth, coverage(path)) <= limit:
            return path
    return None


def merge_copies(glyph, offsets):
    """겹쳐 놓은 복사본들을 외곽선 하나로 합친다. 못 믿을 결과면 None.

    skia 의 경계 연산은 이런 입력 — 같은 외곽선을 평행 이동한 복사본들 — 에서
    가로·세로 직선이 collinear 로 만나면 드물게 예외도 없이 속공간을 먹어 버린다.
    이탤릭 아·야 의 ㅇ 이 까맣게 메워지던 원인이었고, 조용히 틀리기 때문에 결과만
    보고는 알 수 없다. 그래서 알고리즘이 다른 두 경로로 구해 칠해지는 넓이가
    같을 때만 믿는다. 둘이 어긋나면 복사본을 조금 밀어 한 번 더 해 본다.

    그래도 어긋나면 겹친 복사본을 nonzero 규칙으로 직접 칠해 보고, 처음 구한 두
    합집합 가운데 그와 같게 칠해지는 쪽을 쓴다. 느려서 마지막에만 한다. 복사본을
    한 쌍씩 합치는 세 번째 경계 연산은 OpBuilder 와 같이 틀려서(Bold 휑,
    ExtraBold Italic ｓ) 다수결에 쓸 수 없다. 맞는 쪽이 없으면 겹친 채로 둔다.
    """
    first = unions(glyph, offsets)
    picked = agreed(first)
    if picked is None:
        picked = agreed(unions(glyph, nudge(offsets)))
    if picked is None:
        picked = painted_like_stack(glyph, offsets, first)
    if picked is None:
        return None
    ttpen = TTGlyphPen(None)
    picked.draw(ttpen)
    merged = ttpen.glyph()
    return merged if merged.numberOfContours else None


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
                    help="한글 가로 굵기 증가량(base 단위). RIDIBatang 은 한 굵기뿐이라 Bold 는 이걸로 만든다")
    ap.add_argument("--embolden-y", type=float, default=None,
                    help="한글 세로 굵기 증가량. 생략하면 --embolden 의 0.4 배. "
                         "명조 Bold 는 세로획이 주로 굵어지지만 가로획을 그대로 두면 저해상도에서 "
                         "세로획만 진하고 가로획은 흐려 얼룩져 보인다. 가로획이 겹겹이 쌓이는 "
                         "글자(능·동·닙)의 속공간이 메워지지 않는 선에서 절반 조금 못 되게 준다")
    ap.add_argument("--max-err", type=float, default=0.001,
                    help="곡선 변환 허용오차(em 비율)")
    args = ap.parse_args()

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
    ey = args.embolden_y if args.embolden_y is not None else ex * 0.4
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
    bcmap = base.getBestCmap()
    for cp, tf in fit_cell(dglyphs, dcmap, base.getGlyphSet(), bcmap, shear, ex).items():
        sources[cp] = (dglyphs[dcmap[cp]], tf, cell, dcmap[cp])

    for cp in sorted(sources):
        drawing, tf, advance, dname = sources[cp]

        try:
            glyph = outline(drawing, tf, max_err)
        except Exception as exc:
            print(f"  skip U+{cp:04X} {dname}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        gname = sanitize("rb." + dname)
        i = 2
        while gname in taken:
            gname = sanitize(f"rb.{dname}.{i}")
            i += 1
        taken.add(gname)

        if offsets and glyph.numberOfContours:
            # 원본 외곽선은 cmap 에 걸지 않는 글리프로 두고, 그것을 여러 번 겹쳐
            # 부르는 composite 를 실제 글자로 쓴다. 점을 복사하지 않아 용량이 거의 안 는다.
            src = gname + ".src"
            taken.add(src)
            put(src, glyph, advance)
            glyph = make_composite(src, offsets)
        put(gname, glyph, advance)
        added[cp] = gname

    print(f"  한글 등 {len(added)}자 추가, {skipped}자 건너뜀")

    if offsets:
        # 겹쳐 놓은 composite 를 그대로 두면 macOS CoreText 가 겹친 가장자리마다
        # 안티앨리어싱을 따로 해서 획이 번져 보인다(FreeType 은 멀쩡하다).
        # 그래서 합집합을 구해 외곽선 하나로 만든다. 믿을 수 없는 글자만 겹친 채 둔다.
        merged, failed = 0, []
        for cp, name in added.items():
            if not glyf[name].isComposite():
                continue
            src = name + ".src"
            one = merge_copies(glyf[src], offsets)
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

    base.setGlyphOrder(order)
    glyf.glyphOrder = order
    base["maxp"].numGlyphs = len(order)

    for sub in base["cmap"].tables:
        if not sub.isUnicode():
            continue
        for cp, gname in added.items():
            if cp <= 0xFFFF or sub.format in (12, 13):
                sub.cmap[cp] = gname

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
                       (3, f"{ps};merged-with-RIDIBatang"), (4, full), (6, ps),
                       (13, OFL_DESC), (14, OFL_URL), (16, args.family), (17, args.style)]:
        set_name(base, nid, value)

    base.save(args.out)
    print(f"  저장: {args.out}")


if __name__ == "__main__":
    main()
