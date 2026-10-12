"""경계 연산을 거치지 않고 nonzero 규칙으로 직접 칠해 본 정답. weight 가 경계 연산 결과를 이것과 맞춰 본다."""
import math

from fontTools.pens.basePen import BasePen


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


def shifted(rows, ox, oy):
    """coverage 를 정수 (ox, oy) 만큼 옮긴다. 줄은 정수 높이마다 재므로 그대로 옮겨진다."""
    return {r + oy: [(x0 + ox, x1 + ox) for x0, x1 in spans] for r, spans in rows.items()}
