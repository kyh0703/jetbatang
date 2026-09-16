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
from fontTools.pens.cu2quPen import Cu2QuPen
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
    (0x3200, 0x32FF),   # 괄호문자·원문자 ㈜ ㉠ ㎡
    (0xFF01, 0xFF60),   # 전각 영숫자·기호
    (0xFFE0, 0xFFE6),   # 전각 통화기호 ￦
]
# RIDIBatang 에 없는 글자를 같은 모양의 다른 글자로 때운다.
# ー(장음부호)는 가로 전폭 막대인데 RIDIBatang 에 없다. ―(horizontal bar) 가
# 같은 높이·같은 굵기의 막대라 그대로 쓴다. 없으면 コーヒー 가 두부로 깨진다.
ALIASES = {0x30FC: 0x2015}

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
    g.components[0].flags |= OVERLAP_COMPOUND   # 첫 component 에만 세운다
    return g


def shifted_copies(glyph, offsets):
    """외곽선을 offsets 만큼씩 옮긴 복사본을 pathops.Path 로 하나씩 준다."""
    for ox, oy in offsets:
        copy = pathops.Path()
        glyph.draw(copy.getPen(glyphSet=None), None)
        yield copy.transform(1, 0, 0, 1, ox, oy)


def by_simplify(glyph, offsets):
    stack = pathops.Path()
    pen = stack.getPen(glyphSet=None)
    for copy in shifted_copies(glyph, offsets):
        copy.draw(pen)
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


def merge_copies(glyph, offsets):
    """겹쳐 놓은 복사본들을 외곽선 하나로 합친다. 못 믿을 결과면 None.

    skia 의 경계 연산은 이런 입력 — 같은 외곽선을 평행 이동한 복사본들 — 에서
    가로·세로 직선이 collinear 로 만나면 드물게 예외도 없이 속공간을 먹어 버린다.
    이탤릭 아·야 의 ㅇ 이 까맣게 메워지던 원인이었고, 조용히 틀리기 때문에 결과만
    보고는 알 수 없다. 그래서 알고리즘이 다른 두 경로로 구해 칠해지는 넓이가
    같을 때만 믿는다. 둘이 어긋나면 복사본을 조금 밀어 한 번 더 해 보고,
    그래도 어긋나면 합치지 않고 겹친 채로 둔다.
    """
    for offs in (offsets, nudge(offsets)):
        try:
            first, second = by_simplify(glyph, offs), by_opbuilder(glyph, offs)
        except pathops.PathOpsError:
            continue
        a, b = ink(first), ink(second)
        if not a or abs(a - b) > a * 1e-4:
            continue
        ttpen = TTGlyphPen(None)
        first.draw(ttpen)
        merged = ttpen.glyph()
        if merged.numberOfContours:
            return merged
    return None


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
    added, skipped = {}, 0

    def put(name, glyph):
        glyf.glyphs[name] = glyph
        glyph.recalcBounds(glyf)
        hmtx.metrics[name] = (wide, glyph.xMin if glyph.numberOfContours else 0)
        order.append(name)

    targets = {cp: dcmap[cp] for cp in dcmap if is_wide(cp)}
    for cp, src in ALIASES.items():
        if cp not in targets and src in dcmap:
            targets[cp] = dcmap[src]

    for cp in sorted(targets):
        dname = targets[cp]
        if dname not in dhmtx.metrics:
            skipped += 1
            continue

        # advance box 기준 중앙 정렬 — 원본의 좌우 균형을 그대로 보존한다.
        dx = (wide - dhmtx[dname][0] * scale) / 2.0
        # yx 항이 기울임. pivot 높이를 축으로 돌려 글자가 칸 밖으로 밀리지 않게 한다.
        tf = Transform(scale, 0, shear * scale, scale, dx - shear * pivot, args.yshift)

        ttpen = TTGlyphPen(None)
        # CFF 와 glyf 는 외곽선 방향이 반대라 reverse_direction 이 필요하다.
        pen = TransformPen(Cu2QuPen(ttpen, max_err, reverse_direction=True), tf)
        try:
            dglyphs[dname].draw(pen)
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

        glyph = ttpen.glyph()
        if offsets and glyph.numberOfContours:
            # 원본 외곽선은 cmap 에 걸지 않는 글리프로 두고, 그것을 여러 번 겹쳐
            # 부르는 composite 를 실제 글자로 쓴다. 점을 복사하지 않아 용량이 거의 안 는다.
            src = gname + ".src"
            taken.add(src)
            put(src, glyph)
            glyph = make_composite(src, offsets)
        put(gname, glyph)
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
            hmtx.metrics[name] = (wide, one.xMin)
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
