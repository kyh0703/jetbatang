"""외곽선을 옮기고 바꾸는 글리프 공통 도구."""
import pathops

from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen, replayRecording
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import (ARGS_ARE_XY_VALUES,
                                             OVERLAP_COMPOUND, Glyph,
                                             GlyphComponent)

from .scanline import SPECK


def compose(parts):
    """[(글리프 이름, (dx, dy))] 를 차례로 부르는 composite 글리프."""
    g = Glyph()
    g.numberOfContours = -1
    g.components = []
    for src, (ox, oy) in parts:
        c = GlyphComponent()
        c.glyphName = src
        c.x, c.y = ox, oy
        c.flags = ARGS_ARE_XY_VALUES
        g.components.append(c)
    return g


def make_composite(src, offsets):
    """src 외곽선을 offsets 만큼씩 옮겨 겹쳐 부르는 composite 글리프."""
    g = compose([(src, offset) for offset in offsets])
    if len(offsets) > 1:
        g.components[0].flags |= OVERLAP_COMPOUND   # 겹칠 때만, 첫 component 에만 세운다
    return g


def outline(dglyph, tf, max_err):
    """donor 의 CFF 글리프를 tf 로 옮긴 TrueType 글리프로 만든다."""
    ttpen = TTGlyphPen(None)
    # CFF 와 glyf 는 외곽선 방향이 반대라 reverse_direction 이 필요하다.
    dglyph.draw(TransformPen(Cu2QuPen(ttpen, max_err, reverse_direction=True), tf))
    return ttpen.glyph()


def bounds(glyphs, name, tf=None):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(TransformPen(pen, tf) if tf else pen)
    return pen.bounds


def split_contours(recording):
    """RecordingPen 의 기록을 외곽선 하나씩으로 나눈다."""
    contours, cur = [], []
    for op, args in recording:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    return contours


def to_glyph(path):
    """경계 연산 결과를 TrueType 글리프로 만든다. 칠할 외곽선이 없으면 None.

    경계 연산은 넓이가 거의 0 인 부스러기 외곽선을 남기고, 좌표를 정수로 반올림하면 넓이가 0 이 되기도
    한다. 회색조에서는 보이지 않지만 흑백 렌더링의 dropout control 이 픽셀로 칠해서, 반올림한 뒤 넓이가
    SPECK 보다 작은 외곽선은 뺀다."""
    ttpen = TTGlyphPen(None)
    path.draw(ttpen)
    rounded = RecordingPen()
    ttpen.glyph().draw(rounded, None)
    kept = TTGlyphPen(None)
    for contour in split_contours(rounded.value):
        area = AreaPen()
        replayRecording(contour, area)
        if abs(area.value) >= SPECK:
            replayRecording(contour, kept)
    glyph = kept.glyph()
    return glyph if glyph.numberOfContours else None


def glyph_path(glyph):
    path = pathops.Path()
    glyph.draw(path.getPen(glyphSet=None), None)
    return path
