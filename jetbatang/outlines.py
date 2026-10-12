"""외곽선을 옮기고 바꾸는 글리프 공통 도구."""
import pathops

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import (ARGS_ARE_XY_VALUES,
                                             OVERLAP_COMPOUND, Glyph,
                                             GlyphComponent)


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


def bounds(glyphs, name, tf=None):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(TransformPen(pen, tf) if tf else pen)
    return pen.bounds


def to_glyph(path):
    ttpen = TTGlyphPen(None)
    path.draw(ttpen)
    glyph = ttpen.glyph()
    return glyph if glyph.numberOfContours else None


def glyph_path(glyph):
    path = pathops.Path()
    glyph.draw(path.getPen(glyphSet=None), None)
    return path
