"""한글 획을 불리거나 깎는다. 경계 연산으로 외곽선을 하나로 만들고, 그 결과를 믿을 수 있는지 본다."""
import math
from collections import Counter

import pathops

from .outlines import glyph_path, to_glyph
from .scanline import SPECK, coverage, mismatch, overlap, painted, same_structure, shifted, structure


def embolden_ring(ex, ey):
    """굵기를 바꿀 때 외곽선을 옮겨 놓을 자리 (dx, dy) 목록. 원래 자리와 8 방향이다.

    같은 외곽선을 이 자리마다 겹쳐 놓으면 TrueType 의 nonzero winding 규칙이 합집합으로 칠해준다.
    경계 연산(boolean op) 없이 획이 두꺼워진다. 원래 자리가 없으면 옮기는 거리보다 가는 획은 양쪽으로
    옮긴 복사본 사이가 비어 속이 뚫린다. 반대로 모두 겹치는 곳만 남기면(thin_copies) 획이 가늘어진다.
    """
    rx, ry = ex / 2.0, ey / 2.0
    d = math.sqrt(0.5)
    ring = [(1, 0), (-1, 0), (0, 1), (0, -1),
            (d, d), (d, -d), (-d, d), (-d, -d)]
    return sorted({(0, 0)} | {(round(rx * a), round(ry * b)) for a, b in ring})


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

    원래 자리 (0, 0) 의 복사본은 나머지 복사본이 원래 외곽선을 다 덮지 못할 때만 함께 합친다. 옮기는
    거리보다 가는 획이 없으면 합집합은 같은데, 복사본이 하나 늘면 경계 연산이 더 자주 틀린다(ExtraBold
    Italic ％ 는 두 경계 연산이 모두 틀리고 복사본을 밀어도 틀려 겹친 채 남았다).
    """
    around = [offset for offset in offsets if offset != (0, 0)]
    if around and len(around) < len(offsets):
        path = _union_path(glyph, around)
        if path is not None and _covers(path, glyph):
            return path
    return _union_path(glyph, offsets)


def _covers(path, glyph):
    """path 가 glyph 가 칠하는 곳을 다 칠하는지. 경계 연산으로 잰다. 줄마다 칠해 견주면 합집합을 구하는
    만큼 느리다. 틀려서 덮었다고 보면 원래 자리 없이 합친 결과가 나갈 뿐이고, 합집합의 외곽선은 원래
    외곽선에서 옮긴 거리만큼 떨어져 있어 경계 연산이 자주 틀리는 겹친 직선도 없다."""
    try:
        missed = pathops.op(glyph_path(glyph), path, pathops.PathOp.DIFFERENCE)
    except pathops.PathOpsError:
        return False
    return ink(missed) < SPECK


def _union_path(glyph, offsets):
    """skia 의 경계 연산은 이런 입력 — 같은 외곽선을 평행 이동한 복사본들 — 에서
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


def merge_copies(glyph, offsets):
    """겹쳐 놓은 복사본들을 외곽선 하나로 합친다. 못 믿을 결과면 None 이고, 그러면 겹친 채로 둔다."""
    path = union_path(glyph, offsets)
    return None if path is None else to_glyph(path)


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


# 굵기를 바꾼 뒤 모양을 견줄 때 곡선 하나를 펴는 토막 수. 1 단위 격자에서 덩어리와 속공간을 가리기에 넉넉하다.
STRUCTURE_STEPS = 16


def structure_of(glyph):
    """glyph 의 덩어리와 속공간(1 단위 격자). 경계 연산이 내놓은 경로가 아니라 저장할 글리프로 본다.
    TTGlyphPen 이 좌표를 정수로 반올림하며 반 단위보다 좁은 틈을 메워서, 반올림 전 경로로 보면
    Bold ⓠ 의 꼬리가 원에 붙는 것을 놓친다."""
    return structure(coverage(glyph_path(glyph), STRUCTURE_STEPS))


def _outlines(path):
    """경로를 정리한 (바깥 외곽선들, 속공간 수). 넓이가 SPECK 보다 작은 부스러기 외곽선은 뺀다."""
    outer, holes = [], 0
    for contour in pathops.simplify(path, clockwise=True).contours:
        if abs(contour.area) < SPECK:
            continue
        if contour.clockwise:
            outer.append(contour)
        else:
            holes += 1
    return outer, holes


def thinned_alike(glyph, thinned):
    """깎은 글자가 원래 글자와 모양이 같은지. thinned 는 glyph 안에 든다.

    깎으면 속공간이 바깥과 이어지거나 둘이 합쳐질 수는 있어도 새로 생기지는 않아서, 속공간 수가 같으면
    속공간은 그대로다. 획은 하나가 끊기면서 다른 하나가 사라지면 수가 같으므로, 깎은 바깥 외곽선이 원래
    바깥 외곽선에 하나씩 드는지도 본다. 깎은 외곽선은 원래 외곽선보다 안쪽으로 들어가 있어서, 그 위의 점이
    원래 글자의 어느 덩어리에 드는지로 짝을 찾는다. 반올림한 꼭짓점 몇은 원래 외곽선에 걸치거나 살짝 밖에
    있어서(LightItalic ㎿) 점마다 물어 많은 쪽을 따른다. 1 단위 격자로 이어짐을 재면 가는 굵기에서 1 단위보다
    가늘게 이어진 곳을 끊긴 것으로 보아 ThinItalic 의 て で ゑ 를 Regular 굵기로 남기므로, 외곽선으로 잰다.
    """
    try:
        before, holes = _outlines(glyph_path(glyph))
        after, thinned_holes = _outlines(glyph_path(thinned))
    except pathops.PathOpsError:
        return False
    if holes != thinned_holes or len(before) != len(after):
        return False
    owners = set()
    for contour in after:
        votes = Counter()
        for _, points in contour.segments:
            # 섬은 속공간 안의 바깥 외곽선이다. 점을 품는 외곽선 가운데 가장 작은 것이 그 점의 덩어리다.
            containing = [i for i, outer in enumerate(before) if points and outer.contains(points[-1])]
            if containing:
                votes[min(containing, key=lambda i: abs(before[i].area))] += 1
        if not votes:
            return False
        owners.add(votes.most_common(1)[0][0])
    return len(owners) == len(before)


# 굵기를 바꾸다 모양이 바뀌는 글자는 이 비율로 덜 바꿔 본다. Thin 에서는 ㎡ 『 의 가는 획이
# 사라지고, Bold 에서는 1칸으로 줄인 ⑫ 의 숫자가 원에 붙는다. 끝까지 안 되면 그대로 둔다.
REWEIGH_STEPS = (1.0, 0.75, 0.5, 0.25)


def reweigh(glyph, gx, gy):
    """획을 가로 gx, 세로 gy 만큼 불리거나(양수) 깎아(음수) 외곽선 하나로 만든 글리프와 실제로
    바꾼 비율. 모양이 바뀌면 덜 바꿔 본다. 끝까지 안 되면 (None, 0).

    불릴 때는 1 단위 격자로 덩어리와 속공간을 짝지어 본다. 1 단위보다 좁아진 틈은 붙은 것으로 보아,
    ExtraBold ⓟ 의 p 가 원에 거의 닿는 것도 막는다. 깎을 때는 thinned_alike 로 본다."""
    emboldening = gx > 0 or gy > 0
    shape = structure_of(glyph) if emboldening else None
    for step in REWEIGH_STEPS:
        ring = embolden_ring(abs(gx) * step, abs(gy) * step)
        result = union_path(glyph, ring) if emboldening else thin_copies(glyph, ring)
        reweighed = None if result is None else to_glyph(result)
        if reweighed is None:
            continue
        if same_structure(shape, structure_of(reweighed)) if emboldening else thinned_alike(glyph, reweighed):
            return reweighed, step
    return None, 0.0


class Weight:
    """한글 굵기를 바꿀 양. ex·ey 는 가로·세로 증가량이고, 음수면 그만큼 깎는다.

    ey 를 주지 않으면 불릴 때 ex 의 0.4 배, 깎을 때 0.8 배다. 명조 Bold 는 세로획이 주로 굵어지지만
    가로획을 그대로 두면 저해상도에서 얼룩져 보여서, 가로획이 겹겹이 쌓이는 글자(능·동·닙)의 속공간이
    메워지지 않는 선에서 절반 조금 못 되게 준다. 깎을 때는 RIDIBatang 의 가로획 67 과 세로획 81 의
    비율대로 깎는다. 0.4 배만 깎으면 Thin 에서 가로획이 세로획보다 굵어진다.
    """

    def __init__(self, ex, ey=None):
        if ey is None:
            ey = ex * (0.4 if ex > 0 else 0.8)
        if not (math.isfinite(ex) and math.isfinite(ey)):
            raise ValueError("굵기 증가량은 유한한 수여야 해요")
        # 부호가 다르면 깎을지 불릴지 정할 수 없다.
        if ex * ey < 0:
            raise ValueError("--embolden 과 --embolden-y 는 부호가 같아야 해요")
        self.ex, self.ey = ex, ey
        self.thinner = ex < 0 or ey < 0
        self.emboldens = ex > 0 or ey > 0
