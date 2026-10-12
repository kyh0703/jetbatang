"""경계 연산을 거치지 않고 nonzero 규칙으로 직접 칠해 본 정답. weight 가 경계 연산 결과를 이것과 맞춰 본다."""
import math

from fontTools.pens.basePen import BasePen


class EdgePen(BasePen):
    """외곽선을 꺾은선으로 펴서 (x0, y0, x1, y1) 선분으로 모은다. 곡선 하나를 steps 토막으로 편다.
    32 토막이면 곡선이 많은 ち 를 깎은 결과에서 꺾은선 차이만 2e-4 를 넘는다."""
    STEPS = 128

    def __init__(self, steps=STEPS):
        super().__init__(None)
        self.steps = steps
        self.edges = []
        self.start = self.cur = None

    def _moveTo(self, pt):
        self.start = self.cur = pt

    def _lineTo(self, pt):
        self.edges.append((*self.cur, *pt))
        self.cur = pt

    def _curveToOne(self, p1, p2, p3):
        x0, y0 = self.cur
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            self._lineTo((a * x0 + b * p1[0] + c * p2[0] + d * p3[0],
                          a * y0 + b * p1[1] + c * p2[1] + d * p3[1]))

    def _closePath(self):
        if self.cur != self.start:
            self._lineTo(self.start)

    _endPath = _closePath


def coverage(path, steps=EdgePen.STEPS):
    """nonzero 규칙으로 칠해지는 가로 구간을 높이 1 마다 구한다. {줄: [(x0, x1), ...]}

    TrueType 이 겹친 composite 를 칠하는 규칙 그대로라, 경계 연산을 거치지 않은 정답이 된다.
    steps 는 곡선 하나를 펴는 토막 수다.
    """
    pen = EdgePen(steps)
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


# 넓이가 이보다 작은 덩어리·속공간·겹침은 곡선을 꺾은선으로 펴고 좌표를 반올림하며 생긴 부스러기로 본다.
SPECK = 1.0


def regions(rows):
    """칠해진 구간을 이어 붙은 덩어리로 나눈다. [{줄: [(x0, x1), ...]}, ...]

    이웃한 두 줄의 구간이 가로로 겹치면 이어 붙은 것이다. 넓이가 SPECK 보다 작은 덩어리는 버린다.
    """
    spans = [(r, x0, x1) for r in sorted(rows) for x0, x1 in rows[r]]
    first = {}
    for n, (r, _, _) in enumerate(spans):
        first.setdefault(r, n)
    parent = list(range(len(spans)))

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for r, j in first.items():
        if r - 1 not in first:
            continue
        i, i_end, j_end = first[r - 1], first[r - 1] + len(rows[r - 1]), j + len(rows[r])
        while i < i_end and j < j_end:
            if min(spans[i][2], spans[j][2]) > max(spans[i][1], spans[j][1]):
                parent[root(i)] = root(j)
            if spans[i][2] < spans[j][2]:
                i += 1
            else:
                j += 1
    groups = {}
    for n, (r, x0, x1) in enumerate(spans):
        groups.setdefault(root(n), {}).setdefault(r, []).append((x0, x1))
    return [group for group in groups.values() if painted(group) >= SPECK]


def holes(rows):
    """칠해진 곳에 둘러싸인 빈 곳(속공간)을 덩어리로 나눈다. 바깥과 이어진 빈 곳은 뺀다."""
    painted_rows = [r for r, spans in rows.items() if spans]
    if not painted_rows:
        return []
    x0 = min(spans[0][0] for spans in rows.values() if spans) - 1
    x1 = max(spans[-1][1] for spans in rows.values() if spans) + 1
    r0, r1 = min(painted_rows) - 1, max(painted_rows) + 1
    empty = {}
    for r in range(r0, r1 + 1):
        spans, x = [], x0
        for a, b in rows.get(r, []):
            if a > x:
                spans.append((x, a))
            x = max(x, b)
        if x < x1:
            spans.append((x, x1))
        empty[r] = spans
    # 맨 위 줄은 비어 있어 바깥이다. 양옆 여백으로 바깥과 이어진 빈 곳도 모두 그 덩어리에 든다.
    return [group for group in regions(empty) if r0 not in group]


def _box(group):
    return (min(group), max(group), min(spans[0][0] for spans in group.values()),
            max(spans[-1][1] for spans in group.values()))


def _paired(xs, ys):
    """xs 와 ys 가 하나씩 짝지어지는지. 짝은 작은 쪽 넓이의 절반 넘게 겹치는 둘이다. 굵기를 바꾸면
    덩어리가 원래 덩어리를 품거나 그 안에 들어서 작은 쪽이 거의 다 겹치고, 이웃 덩어리와는 가장자리만
    조금 겹친다."""
    if len(xs) != len(ys):
        return False
    boxes = [_box(y) for y in ys]
    areas = [painted(y) for y in ys]
    links = []
    for x in xs:
        (r0, r1, a0, a1), area = _box(x), painted(x)
        links.append([b0 <= r1 and r0 <= b1 and c0 < a1 and a0 < c1
                      and painted(overlap(x, y)) > min(area, y_area) / 2
                      for y, (b0, b1, c0, c1), y_area in zip(ys, boxes, areas)])
    return all(sum(row) == 1 for row in links) and all(sum(col) == 1 for col in zip(*links))


def structure(rows):
    """coverage 의 (덩어리, 속공간). same_structure 로 견준다."""
    return regions(rows), holes(rows)


def same_structure(a, b):
    """두 structure 의 덩어리끼리, 속공간끼리 서로 겹치는 짝으로 하나씩 이어지는지.

    굵기를 바꾼 글자는 원래 글자를 품거나(불릴 때) 원래 글자 안에 든다(깎을 때). 모양이 그대로면
    덩어리와 속공간이 겹치는 짝으로 이어진다. 획이 끊기거나 붙거나 사라지면 덩어리 짝이, 속공간이
    막히거나 터지거나 둘로 갈리거나 새로 생기면 속공간 짝이 어긋난다. 바깥 외곽선과 속공간 수만 세면
    속공간 하나가 막히고 다른 곳에서 하나가 새로 닫힐 때 같은 모양으로 보인다.
    """
    return _paired(a[0], b[0]) and _paired(a[1], b[1])
