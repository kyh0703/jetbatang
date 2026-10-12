"""가져온 글자를 base 의 1칸·2칸에 놓는 배율과 위치."""
import math

from fontTools.misc.transform import Transform

from .charset import NARROW
from .outlines import bounds


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


class Grid:
    """base 의 칸, 그리고 donor 글자를 base 로 옮기는 배율과 기울기."""

    def __init__(self, base, donor, args):
        self.upem = base["head"].unitsPerEm
        self.cell = base["hmtx"]["A"][0]        # 라틴 1칸
        self.wide = self.cell * 2               # 한글 2칸
        self.donor_upem = donor["head"].unitsPerEm
        self.scale = args.scale * self.upem / self.donor_upem
        self.max_err = args.max_err * self.upem
        self.pivot = args.shear_pivot * self.upem
        self.yshift = args.yshift
        self.shear = 0.0
        if args.shear_from_base:
            angle = base["post"].italicAngle          # 오른쪽으로 누우면 음수
            self.shear = math.tan(math.radians(-angle))

    def centered(self, advance):
        """donor advance box 를 한글 2칸 가운데에 놓는다. 원본의 좌우 균형을 그대로 보존한다."""
        dx = (self.wide - advance * self.scale) / 2.0
        # yx 항이 기울임. pivot 높이를 축으로 돌려 글자가 칸 밖으로 밀리지 않게 한다.
        return Transform(self.scale, 0, self.shear * self.scale, self.scale,
                         dx - self.shear * self.pivot, self.yshift)


class SymbolCell:
    """donor 기호를 base 1칸 가운데에 줄여 놓는다.

    1칸 기호는 base ○ 크기로 맞춘다. RIDIBatang ○ 이 base ○ 가 되는 배율로 줄이고, 그래도
    base ○ 보다 넓은 글자(① ♣)는 그 폭에 들게 더 줄인다. 굵기를 불릴 몫(ex)도 미리 뺀다.
    이탤릭에서도 base ○ ● ◇ 처럼 세워 둔다.
    """

    def __init__(self, donor, base, grid, ex):
        dcmap, bcmap = donor.getBestCmap(), base.getBestCmap()
        self.dglyphs = donor.getGlyphSet()
        self.grid, self.ex = grid, ex
        self.limit = grid.cell
        if 0x25CB in bcmap:
            x0, _, x1, _ = bounds(base.getGlyphSet(), bcmap[0x25CB])
            self.limit = x1 - x0
        x0, _, x1, _ = bounds(self.dglyphs, dcmap[0x25CB])
        self.circle = self.limit / (x1 - x0)
        self.dmid = (donor["hhea"].ascent + donor["hhea"].descent) / 2.0     # donor 전각 틀의 세로 가운데

    def place(self, name):
        """(변환, 배율). 2칸에 놓을 때와 세로 가운데가 같아서 ① 과 ㉠ 이 한 줄에 나란하다.
        가로는 잉크 가운데를 맞춘다. ☜ ☞ ∝ ℡ 처럼 전각 틀의 한쪽으로 쏠린 기호를 틀째 가운데에
        두면 base ○ 보다 옆 칸을 더 덮는다."""
        x0, _, x1, _ = bounds(self.dglyphs, name)
        k = min(self.circle, self.limit / (x1 - x0 + max(self.ex, 0.0)))
        cell, scale, yshift = self.grid.cell, self.grid.scale, self.grid.yshift
        return Transform(k, 0, 0, k, (cell - (x0 + x1) * k) / 2.0, (scale - k) * self.dmid + yshift), k
