"""base 에 없는 체크·투표 기호를 같은 판 base 의 ✓ ✗ □ 로 만든다.

✓ ✗ □ 는 base 에 있지만 ✔ ✘ ☑ ☒ 는 Nerd Fonts 어느 판에도 없다. 테스트 러너와 할 일 목록이 많이 쓰는
글자라 빠지면 터미널이 다른 글꼴로 그려서, 옆의 ✓ 와 모양도 굵기도 다르다. ☐ 는 □ 를 그대로 건다
(charset.BASE_ALIASES).
"""
import pathops
from fontTools.misc.transform import Transform
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.perimeterPen import PerimeterPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from .outlines import compose, glyph_path, to_glyph


# 굵게 그릴 글자 → base 의 가는 글자. ✔ ✘ ← ✓ ✗
HEAVY = {0x2714: 0x2713, 0x2718: 0x2717}

# 상자 안에 표시를 넣은 글자 → 넣을 표시. ☑ ☒ ← ✓ ✗
BOXED = {0x2611: 0x2713, 0x2612: 0x2717}

# 상자. base □ 는 굵기와 관계없이 벽 50 이다.
BOX = 0x25A1

# ✔ 는 ✓ 의 획을 그 굵기의 이만큼 더 불린 다음 ✓ 자리로 줄인다. 줄이고 나면 Regular 에서 1.6 배쯤이다.
# 두 갈래가 붙으면 덜 불린다. ExtraBold ✘ 는 다 불리면 위쪽 V 홈이 메워져 갈래 사이가 높이 3/4 아래로
# 내려가서 7/8 만 불린다. 1칸 안에 줄여 넣으므로 ExtraBold 는 1.4 배쯤에서 그친다.
HEAVY_STEPS = (1.0, 0.875, 0.75, 0.625, 0.5)


def stroke(glyph, glyf):
    """획 굵기의 어림값. 가늘고 긴 획은 넓이의 두 배를 둘레로 나누면 굵기가 된다."""
    area, perimeter = AreaPen(), PerimeterPen()
    glyph.draw(area, glyf)
    glyph.draw(perimeter, glyf)
    return 2 * abs(area.value) / perimeter.value


def ink(glyph, glyf):
    pen = BoundsPen(None)
    glyph.draw(pen, glyf)
    return pen.bounds


def transformed(glyph, glyf, tf):
    pen = TTGlyphPen(None)
    glyph.draw(TransformPen(pen, tf), glyf)
    return pen.glyph()


def pieces(path, y):
    """path 를 높이 y 에서 가로로 자른 잉크 토막 수. 붙은 토막은 하나로 센다."""
    x0, _, x1, _ = path.bounds
    band = pathops.Path()
    pen = band.getPen()
    pen.moveTo((x0 - 1, y))
    pen.lineTo((x0 - 1, y + 1))
    pen.lineTo((x1 + 1, y + 1))
    pen.lineTo((x1 + 1, y))
    pen.closePath()
    return sum(1 for _ in pathops.op(path, band, pathops.PathOp.INTERSECTION).contours)


def heavy(glyph, glyf):
    """획을 불린 다음 원래 잉크 자리로 줄인 글리프. 한 열에 ✓ ✔ 가 섞여도 나란하다. 높이 3/4 에서 자른
    갈래 수가 원래 글자와 달라지면 HEAVY_STEPS 대로 덜 불린다.

    ✓ ✗ 는 직선으로만 된 외곽선이다. 한글처럼 여덟 방향 복사본을 겹쳐 불리면 이만큼 크게 불릴 때 비스듬한 획의
    끝이 계단처럼 깨져서, 외곽선을 따라 그은 선(뾰족한 모서리는 그대로 뾰족한 miter)을 더해 바깥으로 민다."""
    path = glyph_path(glyph)
    x0, y0, x1, y1 = ink(glyph, glyf)
    cut = y0 + (y1 - y0) * 0.75
    arms = pieces(path, cut)
    for step in HEAVY_STEPS:
        edge = pathops.Path(path)
        edge.stroke(step * stroke(glyph, glyf), pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 4)
        grown = pathops.op(path, edge, pathops.PathOp.UNION, clockwise=True)
        a0, b0, a1, b1 = grown.bounds
        sx, sy = (x1 - x0) / (a1 - a0), (y1 - y0) / (b1 - b0)
        grown = grown.transform(sx, 0, 0, sy, x0 - sx * a0, y0 - sy * b0)
        if pieces(grown, cut) == arms:
            return to_glyph(grown)
    raise ValueError("굵게 하면 갈래가 붙어요")


def boxed(mark, box, glyf):
    """mark 를 box 의 속공간 가운데에 줄여 넣은 글리프. 속공간과 표시 사이를 상자 벽만큼 띄운다.
    붙으면 작은 크기에서 ■ 처럼 뭉친다."""
    wall = stroke(box, glyf)
    bx0, by0, bx1, by1 = ink(box, glyf)
    room = min(bx1 - bx0, by1 - by0) - 4 * wall      # 양쪽 벽과 양쪽 틈
    x0, y0, x1, y1 = ink(mark, glyf)
    k = room / max(x1 - x0, y1 - y0)
    dx = (bx0 + bx1) / 2 - k * (x0 + x1) / 2
    dy = (by0 + by1) / 2 - k * (y0 + y1) / 2
    return transformed(mark, glyf, Transform(k, 0, 0, k, dx, dy))


def add_check_marks(merge):
    """HEAVY 와 BOXED 글자를 base 글리프로 만들어 넣는다. base 에 이미 있으면 두고, 재료가 없으면 건너뛴다."""
    bcmap = merge.base.getBestCmap()
    glyf, hmtx = merge.glyf, merge.hmtx
    for cp, src in HEAVY.items():
        if cp in bcmap or src not in bcmap:
            continue
        name = bcmap[src]
        merge.put(name + ".heavy", heavy(glyf[name], glyf), hmtx[name][0])
        merge.added[cp] = name + ".heavy"
    if BOX not in bcmap:
        return
    box = bcmap[BOX]
    for cp, src in BOXED.items():
        if cp in bcmap or src not in bcmap:
            continue
        # 상자는 □ 를 그대로 불러 ☐ 와 같게 그려지고, 표시만 줄인 글리프로 따로 둔다.
        mark = bcmap[src] + ".boxed"
        merge.put(mark, boxed(glyf[bcmap[src]], glyf[box], glyf), hmtx[box][0])
        merge.put(f"uni{cp:04X}", compose([(box, (0, 0)), (mark, (0, 0))]), hmtx[box][0])
        merge.added[cp] = f"uni{cp:04X}"
