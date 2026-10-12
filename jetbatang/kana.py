"""RIDIBatang 에 없는 가나를 있는 가나의 외곽선으로 만든다."""
from fontTools.misc.transform import Transform
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen, replayRecording
from fontTools.pens.transformPen import TransformPen

from .outlines import bounds


# RIDIBatang 에 없는 탁음 가나 → 탁점을 얹을 청음 가나. ゔ ヷ ヸ ヹ ヺ
VOICED = {0x3094: 0x3046, 0x30F7: 0x30EF, 0x30F8: 0x30F0, 0x30F9: 0x30F1, 0x30FA: 0x30F2}

# RIDIBatang 에 없는 작은 히라가나 → (줄일 히라가나, 그만큼 줄어든 원본 가타카나 짝). ゕ ゖ
SMALL = {0x3095: (0x304B, 0x30AB, 0x30F5), 0x3096: (0x3051, 0x30B1, 0x30F6)}

# RIDIBatang 에 없는 띄어 쓰는 탁점·반탁점 → 같은 모양의 결합 문자. ゛ ゜
SPACING_MARKS = {0x309B: 0x3099, 0x309C: 0x309A}


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


class Moved:
    """다른 글자를 옮기거나 줄여 그리는 글자. donor 글리프처럼 draw 만 한다."""

    def __init__(self, glyph, tf):
        self.glyph, self.tf = glyph, tf

    def draw(self, pen):
        self.glyph.draw(TransformPen(pen, self.tf))


def contour_area(contour):
    pen = AreaPen()
    replayRecording(contour, pen)
    return abs(pen.value)


def split_voiced(dglyphs, dcmap):
    """ヴ 를 몸통 ウ 와 탁점 두 획으로 나눈다. 가장 넓은 경로가 몸통이다."""
    contours = kana_contours(dglyphs[dcmap[0x30F4]])
    body = max(contours, key=contour_area)
    return body, [contour for contour in contours if contour is not body]


def voiced_kana(dglyphs, dcmap, dhmtx):
    """VOICED 글자를 {cp: (그릴 거리, advance, 이름)} 으로 만든다.

    ヴ 는 ウ 에 탁점 두 획을 얹고, 그 자리를 비우려고 ウ 를 가로로 조금 줄여 왼쪽으로
    옮긴 글자다. 청음 글자를 ウ 와 같은 만큼 옮기고 ヴ 의 탁점을 그대로 얹는다.
    ワ 는 ウ 에서 윗점만 뺀 모양이라 ヷ 는 원본 디자인과 거의 같아진다.
    """
    body, marks = split_voiced(dglyphs, dcmap)
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
    _, dakuten = split_voiced(dglyphs, dcmap)
    top = bounds(dglyphs, dcmap[0x30CF])[3]           # ハ 몸통보다 위에 있는 두 경로가 반탁점
    handakuten = []
    for contour in kana_contours(dglyphs[dcmap[0x30D1]]):
        pen = BoundsPen(None)
        replayRecording(contour, pen)
        if pen.bounds[3] > top:
            handakuten.append(contour)
    return {0x3099: (KanaMark(dakuten), dhmtx[dcmap[0x30F4]][0], "dakutencomb"),
            0x309A: (KanaMark(handakuten), dhmtx[dcmap[0x30D1]][0], "handakutencomb")}


def small_kana(dglyphs, dcmap, dhmtx):
    """SMALL 글자를 {cp: (그릴 거리, advance, 이름)} 으로 만든다.

    원본의 ヵ ヶ 는 カ ケ 를 0.81 배쯤 줄여 아래로 내린 모양이다. か け 를 같은 배율로 줄이고,
    잉크 가운데와 바닥을 カ→ヵ 만큼 옮긴다.
    """
    made = {}
    for cp, (big, twin_big, twin) in SMALL.items():
        if cp in dcmap or not all(c in dcmap for c in (big, twin_big, twin)):
            continue
        bx0, by0, bx1, by1 = bounds(dglyphs, dcmap[twin_big])
        sx0, sy0, sx1, sy1 = bounds(dglyphs, dcmap[twin])
        s = ((sx1 - sx0) / (bx1 - bx0) + (sy1 - sy0) / (by1 - by0)) / 2
        x0, y0, x1, _ = bounds(dglyphs, dcmap[big])
        cx = (x0 + x1) / 2 + ((sx0 + sx1) - (bx0 + bx1)) / 2
        bottom = y0 + sy0 - by0
        tf = Transform(s, 0, 0, s, cx - s * (x0 + x1) / 2, bottom - s * y0)
        made[cp] = (Moved(dglyphs[dcmap[big]], tf), dhmtx[dcmap[big]][0], f"uni{cp:04X}")
    return made


def spacing_marks(combining):
    """SPACING_MARKS 글자를 {cp: (그릴 거리, advance, 이름)} 으로 만든다. combining 은
    combining_kana 의 결과다.

    결합 문자는 원본 ヴ パ 의 오른쪽 위 자리에 있다. 같은 모양을 좌우로만 옮겨, 원래 칸의
    오른쪽 끝에서 떨어져 있던 만큼 왼쪽 끝에서 떨어지게 한다. 일본어 글꼴은 띄어 쓰는 ゛ ゜ 를
    칸 왼쪽 위에 그려서, 앞 글자 오른쪽 위에 붙어 보이게 한다.
    """
    made = {}
    for cp, src in SPACING_MARKS.items():
        mark, advance, _ = combining[src]
        pen = BoundsPen(None)
        mark.draw(pen)
        x0, _, x1, _ = pen.bounds
        made[cp] = (Moved(mark, Transform(1, 0, 0, 1, (advance - x1) - x0, 0)), advance, f"uni{cp:04X}")
    return made
