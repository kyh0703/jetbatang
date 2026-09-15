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

from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

# 터미널에서 2칸을 차지하는(East Asian Wide) 구간만 가져온다.
# 나머지(라틴·그리스·키릴·괄호·수학기호·박스드로잉)는 base 쪽이 이미 고정폭이다.
WIDE_RANGES = [
    (0xAC00, 0xD7A3),   # 한글 완성형
    (0x3130, 0x318F),   # 한글 호환 자모
    (0x3000, 0x303F),   # CJK 문장부호 。、「」〜
    (0x3200, 0x32FF),   # 괄호문자·원문자 ㈜ ㉠ ㎡
    (0xFF01, 0xFF60),   # 전각 영숫자·기호
    (0xFFE0, 0xFFE6),   # 전각 통화기호 ￦
]
OFL_URL = "https://openfontlicense.org"
OFL_DESC = "This Font Software is licensed under the SIL Open Font License, Version 1.1."


def sanitize(name):
    n = re.sub(r"[^A-Za-z0-9._]", "_", name)
    return n if re.match(r"^[A-Za-z_]", n) else "g" + n


def is_wide(cp):
    return any(a <= cp <= b for a, b in WIDE_RANGES)


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
    ap.add_argument("--style", default="Regular")
    ap.add_argument("--scale", type=float, default=1.00,
                    help="한글 배율(donor upem 기준). 1.00 = RIDIBatang 원본 크기")
    ap.add_argument("--yshift", type=float, default=60.0,
                    help="한글 세로 이동(base 단위). 바탕체는 받침이 깊어 라틴보다 낮게 앉는다")
    ap.add_argument("--shear-from-base", action="store_true",
                    help="base 의 italicAngle 만큼 한글도 기울인다(가짜 이탤릭)")
    ap.add_argument("--shear-pivot", type=float, default=0.325,
                    help="기울임 회전축 높이(em 비율). 한글 세로 중앙")
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

    shear = 0.0
    if args.shear_from_base:
        angle = base["post"].italicAngle          # 오른쪽으로 누우면 음수
        shear = math.tan(math.radians(-angle))

    print(f"base upem={upem} cell={cell} wide={wide} | donor upem={donor_upem} "
          f"| scale={scale:.4f} shear={shear:.4f}")

    dcmap = donor.getBestCmap()
    dglyphs = donor.getGlyphSet()
    dhmtx = donor["hmtx"]

    glyf, hmtx = base["glyf"], base["hmtx"]
    order = list(base.getGlyphOrder())
    taken = set(order)
    added, skipped = {}, 0

    for cp in sorted(c for c in dcmap if is_wide(c)):
        dname = dcmap[cp]
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
        glyf.glyphs[gname] = glyph
        glyph.recalcBounds(glyf)
        hmtx.metrics[gname] = (wide, glyph.xMin if glyph.numberOfContours else 0)
        order.append(gname)
        added[cp] = gname

    print(f"  한글 등 {len(added)}자 추가, {skipped}자 건너뜀")

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
    full = f"{args.family} {args.style}"
    ps = (re.sub(r"[^A-Za-z0-9]", "", args.family) + "-"
          + re.sub(r"[^A-Za-z0-9]", "", args.style))

    # 원본의 이름·상표 기록은 통째로 버리고 새로 쓴다.
    # base 의 Reserved Font Name 과 donor 의 등록상표를 물려받지 않기 위해서다.
    drop = set(range(0, 15)) | {16, 17, 18, 20, 21, 22}
    base["name"].names = [n for n in base["name"].names if n.nameID not in drop]
    for nid, value in [(0, copyright_), (1, args.family), (2, args.style),
                       (3, f"{ps};merged-with-RIDIBatang"), (4, full), (6, ps),
                       (13, OFL_DESC), (14, OFL_URL), (16, args.family), (17, args.style)]:
        set_name(base, nid, value)

    base.save(args.out)
    print(f"  저장: {args.out}")


if __name__ == "__main__":
    main()
