"""빌드 회귀 검사. build/ 의 원본 글꼴과 fonts/ 의 빌드 결과가 있어야 돈다(./build.sh).

    python3 -m unittest discover tests
"""
from io import BytesIO
import json
import re
import shutil
import tempfile
import unicodedata
import unittest
from pathlib import Path

import pathops
import uharfbuzz as hb
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from jetbatang import charset, kana, metadata, outlines, release, scanline, weight

ROOT = Path(__file__).resolve().parent.parent
DONOR = ROOT / "build" / "RIDIBatang.otf"
REGULAR = ROOT / "fonts" / "JetBatangNF-Regular.ttf"
ITALIC = ROOT / "fonts" / "JetBatangNF-Italic.ttf"
BUILT = sorted((ROOT / "fonts").glob("JetBatangNF-*.ttf"))
# 대문자 높이로 W 자리에 맞추는 1칸 글자. charset.NARROW 와 같은 글자다.
NARROW_SIGNS = "₩℃℉ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ"


def ksx1001():
    """KS X 1001 에서 한자를 뺀 1~12행. 한국어 문서가 쓰는 기호·자모·가나·외국 문자다."""
    for lead in range(0xA1, 0xAD):
        for trail in range(0xA1, 0xFF):
            try:
                yield bytes([lead, trail]).decode("euc_kr")
            except UnicodeDecodeError:
                pass


def ink(glyphs, name):
    """실제로 칠해지는 범위. glyf 의 xMin·xMax 는 곡선 조절점까지 넣은 상자라 기울인 ℃ 에서
    잉크보다 6 넓게 나온다."""
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    return pen.bounds


def section(glyphs, name, y, swap=False):
    """y 높이에서 가로로 자른 잉크 구간 [[x0, x1], ...]. 붙은 구간은 하나로 센다. swap 이면 x·y 를 바꿔
    그려서, x=y 자리에서 세로로 자른 [[y0, y1], ...] 이 된다."""
    path = pathops.Path()
    pen = path.getPen(glyphSet=glyphs)
    glyphs[name].draw(TransformPen(pen, (0, 1, 1, 0, 0, 0)) if swap else pen)
    band = pathops.Path()
    pen = band.getPen()
    pen.moveTo((-2000, y))
    pen.lineTo((2000, y))
    pen.lineTo((2000, y + 1))
    pen.lineTo((-2000, y + 1))
    pen.closePath()
    spans = []
    for x0, _, x1, _ in sorted(c.bounds for c in pathops.op(path, band, pathops.PathOp.INTERSECTION).contours):
        if spans and x0 <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], x1)
        else:
            spans.append([x0, x1])
    return spans


def topology(glyphs, name):
    """(바깥 외곽선 수, 속공간 수). 획이 서로 붙거나 속공간이 막히면 달라진다."""
    path = pathops.Path()
    glyphs[name].draw(path.getPen(glyphSet=glyphs))
    contours = list(pathops.simplify(path, clockwise=True).contours)
    outer = sum(c.clockwise for c in contours)
    return outer, len(contours) - outer


def one_cell_symbols(font, base):
    """RIDIBatang 에서 가져와 1칸에 줄여 넣은 KS X 1001 기호."""
    cmap = font.getBestCmap()
    base_names, base_cmap = set(base.getGlyphOrder()), base.getBestCmap()
    return [ch for ch in ksx1001() if ord(ch) in cmap and ord(ch) not in base_cmap
            and cmap[ord(ch)] not in base_names and ch not in NARROW_SIGNS
            and unicodedata.east_asian_width(ch) == "A"]


def stem(glyphs, name, at):
    """잉크 높이의 at 비율에서 자른 첫 획의 폭."""
    _, y0, _, y1 = ink(glyphs, name)
    x0, x1 = section(glyphs, name, y0 + (y1 - y0) * at)[0]
    return x1 - x0


@unittest.skipUnless(REGULAR.exists(), "fonts/JetBatangNF-Regular.ttf 가 없어요. ./build.sh 를 먼저 돌리세요")
class WeightTest(unittest.TestCase):
    def test_hangul_stems_follow_the_latin_weight(self):
        # RIDIBatang 은 한 굵기뿐이라 굵기마다 획을 불리거나 깎는다. 한글이 같은 굵기의 라틴보다
        # 눈에 띄게 굵거나 가늘면 섞어 쓴 줄이 얼룩져 보인다. Thin 라틴 옆에 Regular 굵기 한글을
        # 두면 한글만 진하다. 한글 ㅣ 와 라틴 H 의 세로획 비율이 Regular 와 거의 같아야 한다.
        def ratio(path):
            font = TTFont(path)
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            return stem(glyphs, cmap[ord("ㅣ")], 0.5) / stem(glyphs, cmap[ord("H")], 0.25)

        regular = ratio(REGULAR)
        for path in BUILT:
            with self.subTest(font=path.stem):
                self.assertAlmostEqual(ratio(path), regular, delta=0.05)

    def test_thin_faces_thin_almost_every_syllable(self):
        # 깎다가 획이 끊기는 글자는 덜 깎거나 Regular 굵기로 둔다. 경계 연산 라이브러리가 바뀌어 검증이
        # 자꾸 실패하면 음절 수백 자가 덜 깎이거나 Regular 굵기로 남아 Thin 문단이 얼룩지는데, ㅣ 하나만
        # 재는 위 검사로는 모른다. README 는 Regular 굵기로 남는 글자가 굵기마다 열세~열여덟 자라고 적었다.
        # 다 깎으면 잉크 상자가 좌우로 가로 증가량만큼 줄어든다. 그 7/8 도 줄지 않았으면 덜 깎은 글자로 센다.
        plain = {False: TTFont(REGULAR), True: TTFont(ITALIC)} if ITALIC.exists() else {False: TTFont(REGULAR)}
        for suffix, _, embolden in release.VARIANTS:
            path = ROOT / "fonts" / f"JetBatangNF-{suffix}.ttf"
            italic = suffix.endswith("Italic")
            if embolden >= 0 or not path.exists() or italic not in plain:
                continue
            font, reference = TTFont(path), plain[italic]
            cmap, rcmap = font.getBestCmap(), reference.getBestCmap()
            same, barely = [], []
            for cp in range(0xAC00, 0xD7A4):
                glyph, regular = font["glyf"][cmap[cp]], reference["glyf"][rcmap[cp]]
                if glyph.coordinates == regular.coordinates:
                    same.append(chr(cp))
                if (regular.xMax - regular.xMin) - (glyph.xMax - glyph.xMin) < 2 * round(-embolden / 2) * 7 / 8:
                    barely.append(chr(cp))
            with self.subTest(font=suffix):
                self.assertLessEqual(len(same), 20, "".join(same))
                self.assertLessEqual(len(barely), 11172 * 0.03, "".join(barely))

    def test_horizontal_strokes_follow_the_vertical_weight_rule(self):
        # 가로획은 불릴 때 가로 증가량의 0.4 배, 깎을 때 0.8 배만큼 바뀐다(README). 위아래로 반씩, 정수로
        # 반올림해 옮긴다. 이 비율이 빠지면 Thin 의 가로획이 세로획보다 굵어지고, Bold 의 가로획은 흐려진다.
        def bar(path):
            font = TTFont(path)
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            x0, _, x1, _ = ink(glyphs, cmap[0x3161])           # ㅡ
            (y0, y1), = section(glyphs, cmap[0x3161], (x0 + x1) / 2, swap=True)
            return y1 - y0

        regular = bar(REGULAR)
        for suffix, _, embolden in release.VARIANTS:
            path = ROOT / "fonts" / f"JetBatangNF-{suffix}.ttf"
            if not path.exists():
                continue
            ey = embolden * (0.4 if embolden > 0 else 0.8)
            with self.subTest(font=suffix):
                self.assertAlmostEqual(bar(path), regular + 2 * round(ey / 2), delta=1)

    def test_bold_faces_merge_the_overlapping_copies(self):
        # 불린 한글은 겹친 복사본을 외곽선 하나로 합친다. 합치지 못하고 겹친 채 둔 글자는 macOS 에서 획
        # 가장자리가 번지는데 FreeType 에서는 티가 안 난다. 경계 연산이 자꾸 틀려 그런 글자가 늘면 여기서 막는다.
        for suffix, _, embolden in release.VARIANTS:
            path = ROOT / "fonts" / f"JetBatangNF-{suffix}.ttf"
            if embolden <= 0 or not path.exists():
                continue
            font = TTFont(path)
            cmap, glyf = font.getBestCmap(), font["glyf"]
            left = [chr(cp) for cp in range(0xAC00, 0xD7A4) if glyf[cmap[cp]].isComposite()]
            with self.subTest(font=suffix):
                self.assertLessEqual(len(left), 20, "".join(left))


def polygon_glyph(*contours):
    pen = TTGlyphPen(None)
    for points in contours:
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
    return pen.glyph()


class ThinningTest(unittest.TestCase):
    def test_thinning_moves_every_edge_inward_by_half_the_amount(self):
        # 가로·세로 40 을 깎으면 획은 양쪽에서 20 씩 줄어든다. 300 정사각형의 바깥은 [20, 280],
        # 가운데 100 정사각형 구멍은 [80, 220] 이 된다.
        square = polygon_glyph([(0, 0), (0, 300), (300, 300), (300, 0)],
                               [(100, 100), (200, 100), (200, 200), (100, 200)])
        thin = weight.thin_copies(square, weight.embolden_ring(40, 40))
        contours = sorted(thin.contours, key=lambda c: not c.clockwise)
        self.assertEqual([c.clockwise for c in contours], [True, False])
        for contour, box in zip(contours, [(20, 20, 280, 280), (80, 80, 220, 220)]):
            for got, want in zip(contour.bounds, box):
                self.assertAlmostEqual(got, want, delta=0.5)

    def test_thinning_never_paints_outside_the_original(self):
        # 여덟 방향 복사본만 겹치면 비스듬하고 좁은 틈은 여덟 복사본이 모두 잉크라서 틈 안이 칠해진다.
        # Thin 의 れ ね 에서 22 단위² 씩 생겼다. 깎은 결과는 원래 글자 안에만 있어야 한다.
        u = (0.4384, 0.8988)                  # 64°
        n = (-u[1], u[0])
        a, b = (200, 200), (200 + 400 * u[0], 200 + 400 * u[1])
        slit = pathops.Path()
        pen = slit.getPen()
        pen.moveTo((a[0] + 3 * n[0], a[1] + 3 * n[1]))
        pen.lineTo((b[0] + 3 * n[0], b[1] + 3 * n[1]))
        pen.lineTo((b[0] - 3 * n[0], b[1] - 3 * n[1]))
        pen.lineTo((a[0] - 3 * n[0], a[1] - 3 * n[1]))
        pen.closePath()
        square = polygon_glyph([(0, 0), (0, 400), (400, 400), (400, 0)])
        notched = outlines.to_glyph(pathops.op(outlines.glyph_path(square), slit, pathops.PathOp.DIFFERENCE,
                                               clockwise=True))
        thin = weight.thin_copies(notched, weight.embolden_ring(36, 28.8))
        outside = pathops.op(thin, outlines.glyph_path(notched), pathops.PathOp.DIFFERENCE)
        self.assertLess(weight.ink(outside), 1)

    def test_thinned_shape_pairs_each_stroke_with_its_original(self):
        # 깎다가 가운데가 좁은 획이 둘로 끊기면서 작은 점 하나가 사라지면 바깥 외곽선 수는 그대로라, 수만
        # 세면 모양이 그대로라고 보고 그 굵기로 내보낸다. 반대로 1 단위보다 가늘게 남은 목은 이어진 것이다.
        # 1 단위 격자로 이어짐을 재면 ThinItalic 의 て で ゑ 를 끊겼다고 보아 Regular 굵기로 남긴다.
        necked = polygon_glyph([(0, 0), (0, 100), (100, 100), (100, 55), (200, 55), (200, 100), (300, 100),
                                (300, 0), (200, 0), (200, 45), (100, 45), (100, 0)],
                               [(400, 0), (400, 20), (420, 20), (420, 0)])
        split = polygon_glyph([(10, 10), (10, 90), (90, 90), (90, 10)],
                              [(210, 10), (210, 90), (290, 90), (290, 10)])
        hairline = polygon_glyph([(10, 10), (10, 90), (90, 90), (90, 50), (210, 52), (210, 90), (290, 90),
                                  (290, 10), (210, 10), (210, 51), (90, 49), (90, 10)],
                                 [(405, 5), (405, 15), (415, 15), (415, 5)])
        self.assertFalse(weight.thinned_alike(necked, split))
        self.assertTrue(weight.thinned_alike(necked, hairline))


class ScanlineTest(unittest.TestCase):
    # 경계 연산 결과는 scanline 으로 직접 칠한 정답과 견주어 고른다. 이 정답이 틀리면 속공간을 먹은
    # 합집합도 통과해서, Bold 의 ㅇ 이 까맣게 메워진 채 나간다.
    RING = [(0, 0), (0, 300), (300, 300), (300, 0)], [(100, 100), (200, 100), (200, 200), (100, 200)]

    def test_coverage_paints_by_the_nonzero_rule(self):
        ring = scanline.coverage(outlines.glyph_path(polygon_glyph(*self.RING)))
        full = scanline.coverage(outlines.glyph_path(polygon_glyph(self.RING[0])))
        self.assertEqual(scanline.painted(ring), 300 * 300 - 100 * 100)
        self.assertEqual(scanline.mismatch(ring, full), 100 * 100)
        self.assertEqual(scanline.mismatch(ring, ring), 0)

    def test_union_check_rejects_a_union_that_ate_the_counter(self):
        ring, offsets = polygon_glyph(*self.RING), [(-5, 0), (5, 0)]
        eaten = outlines.glyph_path(polygon_glyph([(-5, 0), (-5, 300), (305, 300), (305, 0)]))
        right = outlines.glyph_path(polygon_glyph([(-5, 0), (-5, 300), (305, 300), (305, 0)],
                                                  [(105, 100), (195, 100), (195, 200), (105, 200)]))
        self.assertIsNone(weight.painted_like_stack(ring, offsets, [eaten]))
        self.assertIs(weight.painted_like_stack(ring, offsets, [eaten, right]), right)

    def test_structure_tells_a_filled_counter_from_a_new_one(self):
        # 굵기를 바꾸다 왼쪽 ㅁ 의 속공간이 막히고, 오른쪽 ㄷ 의 터진 곳이 닫혀 새 속공간이 생긴 글자.
        # 바깥 외곽선 둘·속공간 하나로 개수는 그대로라, 개수만 세면 모양이 그대로라고 본다.
        def shape_of(*contours):
            return scanline.structure(scanline.coverage(outlines.glyph_path(polygon_glyph(*contours))))

        square = [(0, 0), (0, 200), (200, 200), (200, 0)]
        def opening(y0, y1):
            return [(300, 0), (300, 200), (500, 200), (500, y1), (480, y1), (480, 180), (320, 180),
                    (320, 20), (480, 20), (480, y0), (500, y0), (500, 0)]
        before = shape_of(square, [(95, 95), (105, 95), (105, 105), (95, 105)], opening(95, 105))
        thicker = shape_of(square, [(97, 97), (103, 97), (103, 103), (97, 103)], opening(97, 103))
        swapped = shape_of(square, [(300, 0), (300, 200), (500, 200), (500, 0)],
                           [(320, 20), (480, 20), (480, 180), (320, 180)])
        self.assertTrue(scanline.same_structure(before, thicker))
        self.assertFalse(scanline.same_structure(before, swapped))


@unittest.skipUnless(DONOR.exists(), "build/RIDIBatang.otf 가 없어요. ./build.sh 를 먼저 돌리세요")
class DonorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = TTFont(DONOR)
        cls.cmap = cls.donor.getBestCmap()
        cls.glyphs = cls.donor.getGlyphSet()

    def test_takes_every_wide_glyph_the_donor_has(self):
        # 터미널이 2칸으로 세는 글자를 빠뜨리면 다른 글꼴이 대신 그린다.
        missing = [f"U+{cp:04X}" for cp in sorted(self.cmap)
                   if unicodedata.east_asian_width(chr(cp)) in "WF" and not charset.is_wide(cp)]
        self.assertEqual(missing, [])

    def test_merged_bold_paints_like_the_overlapped_copies(self):
        # Bold(embolden 36) 에서 skia 두 경로 중 한쪽이 틀리거나 예외를 내던 글자들.
        # 휑 은 OpBuilder 가, 흉 은 simplify 가 속공간을 먹고, 훙 은 simplify 가 예외를 낸다.
        offsets = weight.embolden_ring(36, 36 * 0.4)
        for ch in "휑흉훙":
            with self.subTest(ch=ch):
                name = self.cmap[ord(ch)]
                dx = (1200 - self.donor["hmtx"][name][0]) / 2.0
                src = outlines.outline(self.glyphs[name], Transform(1, 0, 0, 1, dx, 60), 1.0)
                merged = weight.merge_copies(src, offsets)
                self.assertIsNotNone(merged)

                truth = scanline.coverage(weight.stacked(src, offsets))
                got = scanline.coverage(weight.stacked(merged, [(0, 0)]))
                # 저장하며 좌표를 정수로 반올림해 외곽선이 반 단위까지 움직인다(1.6e-3 안팎).
                # 속공간을 먹은 합집합은 2.6e-2 넘게 어긋난다.
                self.assertLess(scanline.mismatch(truth, got), scanline.painted(truth) * 5e-3)


@unittest.skipUnless(DONOR.exists() and BUILT, "build/RIDIBatang.otf 나 fonts/ 가 없어요. ./build.sh 를 먼저 돌리세요")
class CoverageTest(unittest.TestCase):
    def test_every_face_maps_every_donor_character_at_its_cell_width(self):
        # 빠진 글자는 터미널이 다른 글꼴로 그리고, 폭이 2칸이 아니면 격자가 어긋난다. 결합 탁점·반탁점은
        # 앞 글자에 얹혀 폭이 0 이다.
        donor = TTFont(DONOR).getBestCmap()
        wide = ({cp for cp in donor if charset.is_wide(cp)} | set(charset.ALIASES)
                | ({*kana.VOICED, *kana.SMALL, *kana.SPACING_MARKS} - set(donor)))
        marks = {0x3099, 0x309A}
        for path in BUILT:
            font = TTFont(path)
            cmap, hmtx = font.getBestCmap(), font["hmtx"]
            with self.subTest(font=path.stem):
                self.assertEqual(sorted(cp for cp in wide | marks if cp not in cmap), [])
                width = {cp: hmtx[cmap[cp]][0] for cp in wide | marks}
                self.assertEqual({cp: w for cp, w in width.items() if w != (0 if cp in marks else 1200)}, {})


@unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
class NameTest(unittest.TestCase):
    # README WEIGHTS 표의 'GDI 방식 앱의 가족 이름'. Bold 만 RIBBI 의 Bold 칸을 쓴다.
    GDI_FAMILY = {"Thin": "JetBatang NF Thin", "ExtraLight": "JetBatang NF ExtraLight",
                  "Light": "JetBatang NF Light", "Regular": "JetBatang NF", "Medium": "JetBatang NF Medium",
                  "SemiBold": "JetBatang NF SemiBold", "Bold": "JetBatang NF", "ExtraBold": "JetBatang NF ExtraBold"}

    def test_names_follow_the_weight_table(self):
        # 앱은 nameID 1/2(GDI) 나 16/17(굵기를 따로 고르는 앱)로 굵기를 찾고, install-windows.ps1 은 nameID 4
        # 를 레지스트리 이름으로 쓴다. 상표 기록(nameID 7)은 원본에서 물려받지 않는다.
        for suffix, style, _ in release.VARIANTS:
            path = ROOT / "fonts" / f"JetBatangNF-{suffix}.ttf"
            if not path.exists():
                continue
            names = TTFont(path)["name"]
            italic = style.endswith("Italic")
            weight_name = style.removesuffix("Italic").strip() or "Regular"
            bold = weight_name == "Bold"
            subfamily = {(False, False): "Regular", (False, True): "Italic",
                         (True, False): "Bold", (True, True): "Bold Italic"}[bold, italic]
            with self.subTest(font=suffix):
                self.assertEqual((names.getDebugName(1), names.getDebugName(2)),
                                 (self.GDI_FAMILY[weight_name], subfamily))
                self.assertEqual(names.getDebugName(4), f"JetBatang NF {style}")
                self.assertEqual((names.getDebugName(16), names.getDebugName(17)), ("JetBatang NF", style))
                self.assertIsNone(names.getDebugName(7))

    def test_every_face_tells_windows_it_covers_hangul(self):
        # OS/2 의 Hangul Syllables 범위(56 번)와 949·1361 코드 페이지가 없으면 Windows 가 한글 글꼴로 고르지 않는다.
        for path in BUILT:
            os2 = TTFont(path)["OS/2"]
            with self.subTest(font=path.stem):
                self.assertEqual(os2.ulUnicodeRange2 >> (56 - 32) & 1, 1)
                self.assertEqual(os2.ulCodePageRange1 >> 19 & 1, 1)
                self.assertEqual(os2.ulCodePageRange1 >> 21 & 1, 1)


@unittest.skipUnless(REGULAR.exists(), "fonts/JetBatangNF-Regular.ttf 가 없어요. ./build.sh 를 먼저 돌리세요")
class RegularTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        font = TTFont(REGULAR)
        cls.cmap = font.getBestCmap()
        cls.glyf = font["glyf"]
        cls.hmtx = font["hmtx"]

    def glyph(self, ch):
        name = self.cmap[ord(ch)]
        return self.glyf[name], self.hmtx[name][0]

    def test_wide_symbols_sit_in_the_middle_of_two_cells(self):
        # 터미널이 2칸을 주는데 1칸 폭이면 왼쪽 칸에만 그려진다.
        for ch in "⚡﹢":
            with self.subTest(ch=ch):
                glyph, advance = self.glyph(ch)
                self.assertEqual(advance, 1200)
                self.assertAlmostEqual((glyph.xMin + glyph.xMax) / 2, 600, delta=1)

    def test_trigram_stays_one_cell_for_terminals_before_unicode_16(self):
        # ☰ 은 Unicode 16 에서야 2칸이 됐다. 1칸으로 세는 터미널에서 2칸 폭이면 옆 글자를 덮는다.
        _, advance = self.glyph("☰")
        self.assertEqual(advance, 600)

    def test_voiced_kana_missing_from_the_donor_carry_a_dakuten(self):
        for voiced, plain in zip("ゔヷヸヹヺ", "うワヰヱヲ"):
            with self.subTest(ch=voiced):
                self.assertTrue(ord(voiced) in self.cmap, f"{voiced} 가 없다")
                glyph, advance = self.glyph(voiced)
                self.assertEqual(advance, 1200)
                # 탁점 두 획이 청음 글자에 더해진다.
                self.assertEqual(glyph.numberOfContours, self.glyph(plain)[0].numberOfContours + 2)

    def test_small_ka_ke_and_spacing_marks_reuse_ridibatang_strokes(self):
        # RIDIBatang 에 없는 ゕ ゖ ゛ ゜ 가 빠지면 다른 글꼴의 고딕 가나가 섞인다. ゕ ゖ 는 か け 를
        # 원본의 ヵ ヶ 가 カ ケ 보다 작은 만큼 줄이고, ゛ ゜ 는 결합 탁점·반탁점과 같은 모양을
        # 제 칸 왼쪽 위에 그린다. 앞 글자 오른쪽 위에 붙어 보이게 하는 일본어 글꼴의 관례다.
        def height(ch):
            glyph, _ = self.glyph(ch)
            return glyph.yMax - glyph.yMin

        for small, big, twin, twin_big in zip("ゕゖ", "かけ", "ヵヶ", "カケ"):
            with self.subTest(ch=small):
                self.assertTrue(ord(small) in self.cmap, f"{small} 가 없다")
                _, advance = self.glyph(small)
                self.assertEqual(advance, 1200)
                self.assertAlmostEqual(height(small) / height(big), height(twin) / height(twin_big),
                                       delta=0.02)
        for mark, combining in zip("゛゜", "\u3099\u309A"):
            with self.subTest(ch=mark):
                self.assertTrue(ord(mark) in self.cmap, f"{mark} 가 없다")
                glyph, advance = self.glyph(mark)
                twin, _ = self.glyph(combining)
                self.assertEqual(advance, 1200)
                self.assertEqual(glyph.numberOfContours, twin.numberOfContours)
                self.assertAlmostEqual(glyph.xMax - glyph.xMin, twin.xMax - twin.xMin, delta=1)
                self.assertAlmostEqual(glyph.yMin, twin.yMin, delta=1)
                self.assertLess(glyph.xMax, 600)

    def test_fullwidth_won_sign_is_not_a_backslash(self):
        # RIDIBatang 은 ￦ 에 전각 역슬래시 모양을 걸어 두었다. ₩ 은 옆으로 넓고 \ 는 세로로 길다.
        glyph, advance = self.glyph("￦")
        self.assertEqual(advance, 1200)
        self.assertGreater(glyph.xMax - glyph.xMin, glyph.yMax - glyph.yMin)

    def test_one_cell_symbols_sit_on_the_center_line_of_wide_glyphs(self):
        # 1칸으로 줄인 기호가 위아래로 치우치면 ① 과 ㉠, ⑴ 과 ㈀ 이 한 줄에서 들쭉날쭉하다.
        # 짝마다 RIDIBatang 에서 그리는 틀(원, 괄호)이 같다.
        for narrow, wide in zip("①⑴", "㉠㈀"):
            with self.subTest(ch=narrow):
                glyph, advance = self.glyph(narrow)
                twin, _ = self.glyph(wide)
                self.assertEqual(advance, 600)
                self.assertAlmostEqual((glyph.xMin + glyph.xMax) / 2, 300, delta=2)
                self.assertAlmostEqual(glyph.yMin + glyph.yMax, twin.yMin + twin.yMax, delta=4)

    def test_one_cell_circles_are_as_big_as_the_base_circle(self):
        # ① ⓐ 이 base ○ 보다 작으면 ○ ● 와 나란히 쓸 때 한 단계 작은 글꼴처럼 보인다.
        ring, _ = self.glyph("○")
        for ch in "①ⓐ":
            with self.subTest(ch=ch):
                glyph, _ = self.glyph(ch)
                self.assertAlmostEqual(glyph.xMax - glyph.xMin, ring.xMax - ring.xMin, delta=4)

    def test_roman_numerals_stand_as_tall_as_capitals(self):
        # "Ⅳ. 결론" 의 Ⅳ 가 라틴 대문자보다 한참 작으면 소문자처럼 읽힌다.
        capital, _ = self.glyph("I")
        for ch in "ⅠⅣⅧⅰ":
            with self.subTest(ch=ch):
                glyph, advance = self.glyph(ch)
                self.assertEqual(advance, 600)
                self.assertGreater(glyph.yMax - glyph.yMin, 0.95 * (capital.yMax - capital.yMin))
                self.assertAlmostEqual((glyph.xMin + glyph.xMax) / 2, 300, delta=3)

    def test_ohm_angstrom_and_bar_reuse_the_latin_glyphs(self):
        # 옴(U+2126)·옹스트롬(U+212B) 기호는 그리스 Ω·라틴 Å 와 정준 등가인 같은 글자고,
        # ―(U+2015) 는 1칸 줄표다. RIDIBatang 것을 쓰면 라틴 옆에서 명조가 튄다.
        for ch, twin in zip("\u2126\u212B\u2015", "\u03A9\u00C5\u2014"):
            with self.subTest(ch=ch):
                self.assertEqual(self.cmap.get(ord(ch)), self.cmap[ord(twin)])


@unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
class NarrowSignTest(unittest.TestCase):
    @unittest.skipUnless(REGULAR.exists() and ITALIC.exists(), "Regular·Italic 빌드 결과가 없어요")
    def test_one_cell_signs_take_the_box_of_w_on_the_baseline(self):
        # ₩ ℃ ℉ 과 로마 숫자는 터미널이 1칸으로 센다. 굵기·기울기마다 base W 가 차지하는 가로
        # 범위 가운데에 들고(넓은 글자는 그 범위를 채우고), 한글처럼 올려 앉히지 않아 숫자와
        # 기준선이 같다. Regular 보다 가는 굵기는 깎기 전에 W 범위에 맞춰서, 깎은 만큼만 좁다.
        def hangul_stem(font):
            return stem(font.getGlyphSet(), font.getBestCmap()[ord("ㅣ")], 0.5)

        plain = {False: hangul_stem(TTFont(REGULAR)), True: hangul_stem(TTFont(ITALIC))}
        for path in BUILT:
            font = TTFont(path)
            cmap, glyphs, hmtx = font.getBestCmap(), font.getGlyphSet(), font["hmtx"]
            wx0, _, wx1, _ = ink(glyphs, cmap[ord("W")])
            thinned = max(0.0, plain[path.stem.endswith("Italic")] - hangul_stem(font))
            for ch in NARROW_SIGNS:
                with self.subTest(font=path.stem, ch=ch):
                    self.assertTrue(ord(ch) in cmap, f"{ch} 가 없다")
                    x0, y0, x1, _ = ink(glyphs, cmap[ord(ch)])
                    self.assertEqual(hmtx[cmap[ord(ch)]][0], 600)
                    self.assertAlmostEqual((x0 + x1) / 2, (wx0 + wx1) / 2, delta=3)
                    self.assertLessEqual(x1 - x0, wx1 - wx0 + 3)
                    if ch in "₩℃℉Ⅷ":
                        self.assertGreaterEqual(x1 - x0, wx1 - wx0 - thinned - 3)
                    self.assertAlmostEqual(y0, 0, delta=20)

    @unittest.skipUnless(REGULAR.exists() and ITALIC.exists(), "Regular·Italic 빌드 결과가 없어요")
    def test_squeezed_numerals_keep_their_strokes_apart(self):
        # Ⅷ 은 1칸에 넣으려고 가로를 0.55 배쯤 줄인다. 줄인 뒤에 한글과 같은 만큼 굵기를 불리면
        # ExtraBold 에서 획 다섯이 둘로 붙고, Bold 에서도 검은 덩어리처럼 보인다. 가운데 높이에서
        # 자른 획 수가 Regular 와 같아야 한다. 또 획이 셋 이상 나란히 선 글자는 획 사이를 채운 비율이
        # 같은 굵기에서 그런 라틴 글자 가운데 가장 빽빽한 M·w 를 넘지 않아야 한다. 두 획짜리 Ⅴ·Ⅸ 는
        # 비스듬히 잘린 획이 넓게 재져서 견주지 않는다. 가는 굵기는 한글처럼 획을 깎아 Regular 보다
        # 성기다.
        def cut(font, ch):
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            top = ink(glyphs, cmap[ord("x" if ch.islower() else "H")])[3]
            spans = section(glyphs, cmap[ord(ch)], top / 2)
            return len(spans), sum(b - a for a, b in spans) / (spans[-1][1] - spans[0][0])

        numerals = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ"
        plain = {False: TTFont(REGULAR), True: TTFont(ITALIC)}
        for path in BUILT:
            font = TTFont(path)
            italic = path.stem.endswith("Italic")
            densest = {False: cut(font, "M")[1], True: cut(font, "w")[1]}
            for ch in numerals:
                with self.subTest(font=path.stem, ch=ch):
                    strokes, filled = cut(font, ch)
                    regular_strokes, regular_filled = cut(plain[italic], ch)
                    self.assertEqual(strokes, regular_strokes)
                    if strokes >= 3:
                        self.assertLessEqual(filled, max(densest[ch.islower()], regular_filled) + 0.01)


@unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
class KoreanSymbolTest(unittest.TestCase):
    def test_draws_every_ks_x_1001_character_itself(self):
        # ※ ① ★ 이 없으면 터미널이 다른 글꼴의 고딕 기호를 섞어 그린다. 폭이 애매한 글자는
        # 터미널 기본값대로 1칸, 전각은 2칸이다. 라틴 글자 Ĳ ĳ ⁿ ː 는 base 에 없어 뺀다.
        for path in BUILT:
            with self.subTest(font=path.stem):
                font = TTFont(path)
                cmap, hmtx = font.getBestCmap(), font["hmtx"]
                missing = [ch for ch in ksx1001() if ord(ch) not in cmap and ch not in "Ĳĳⁿː"]
                self.assertEqual("".join(missing), "")
                wrong = [ch for ch in ksx1001() if ord(ch) in cmap and hmtx[cmap[ord(ch)]][0]
                         != (1200 if unicodedata.east_asian_width(ch) in "WF" else 600)]
                self.assertEqual("".join(wrong), "")

    def test_one_cell_symbols_stay_within_the_base_circle(self):
        # base ○ 는 칸보다 10 씩 넓게 그려져 있다. 새로 넣은 1칸 기호가 그보다 넓거나 한쪽으로
        # 치우치면 옆 칸을 덮는다. RIDIBatang 은 ☜ ☞ ∝ ℡ 같은 기호가 전각 틀의 한쪽으로 쏠려 있다.
        # 이탤릭 base ○ 는 오른쪽으로 14 밀려 있어서 폭만 견준다.
        for path in BUILT:
            base_path = ROOT / "build" / path.name.replace("JetBatangNF", "JetBrainsMonoNerdFontMono")
            if not base_path.exists():
                self.skipTest(f"{base_path.name} 가 없어요. ./build.sh 를 먼저 돌리세요")
            base = TTFont(base_path)
            font = TTFont(path)
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            r0, _, r1, _ = ink(glyphs, cmap[ord("○")])
            drawn = one_cell_symbols(font, base)
            self.assertGreaterEqual(len(drawn), 120)        # 153 자에서 라틴·NARROW·base 글자를 뺀 124 자
            for ch in drawn:
                with self.subTest(font=path.stem, ch=ch):
                    x0, _, x1, _ = ink(glyphs, cmap[ord(ch)])
                    self.assertLessEqual(x1 - x0, r1 - r0 + 2)
                    self.assertAlmostEqual((x0 + x1) / 2, 300, delta=2)

    @unittest.skipUnless(REGULAR.exists() and ITALIC.exists(), "Regular·Italic 빌드 결과가 없어요")
    def test_one_cell_symbols_keep_their_counters_in_every_weight(self):
        # 1칸 기호는 base ○ 크기로 0.6 배쯤 줄여 넣는다. 줄인 뒤에 한글과 같은 만큼 굵기를 불리면
        # ExtraBold 에서 ⑧ ⓐ 의 속공간이 막히고 ⑫ 의 숫자가 원에 붙는다. 굵기마다 바깥 외곽선과
        # 속공간 수가 같은 기울기의 Regular 와 같아야 한다.
        plain = {False: TTFont(REGULAR), True: TTFont(ITALIC)}
        for path in BUILT:
            base_path = ROOT / "build" / path.name.replace("JetBatangNF", "JetBrainsMonoNerdFontMono")
            if not base_path.exists():
                self.skipTest(f"{base_path.name} 가 없어요. ./build.sh 를 먼저 돌리세요")
            font = TTFont(path)
            reference = plain[path.stem.endswith("Italic")]
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            r_cmap, r_glyphs = reference.getBestCmap(), reference.getGlyphSet()
            for ch in one_cell_symbols(font, TTFont(base_path)):
                with self.subTest(font=path.stem, ch=ch):
                    self.assertEqual(topology(glyphs, cmap[ord(ch)]),
                                     topology(r_glyphs, r_cmap[ord(ch)]))

    @unittest.skipUnless(REGULAR.exists() and ITALIC.exists(), "Regular·Italic 빌드 결과가 없어요")
    def test_italic_leans_letters_but_keeps_symbols_upright(self):
        # base 이탤릭은 ○ ● ◇ 는 세우고 라틴 글자는 눕힌다. ★ 만 누우면 "★ 중요 ○ 선택" 이
        # 들쭉날쭉하고, Ⅳ 가 서 있으면 "Ⅳ. Italic" 에서 혼자 튄다.
        upright, italic = TTFont(REGULAR), TTFont(ITALIC)
        a_cmap, a_glyphs = upright.getBestCmap(), upright.getGlyphSet()
        b_cmap, b_glyphs = italic.getBestCmap(), italic.getGlyphSet()
        for ch in "★※":
            with self.subTest(ch=ch):
                a, b = ink(a_glyphs, a_cmap[ord(ch)]), ink(b_glyphs, b_cmap[ord(ch)])
                for p, q in zip(a, b):
                    self.assertAlmostEqual(p, q, delta=2)
        for ch in "Ⅰⅰ":
            with self.subTest(ch=ch):
                ax0, ay0, ax1, ay1 = ink(a_glyphs, a_cmap[ord(ch)])
                bx0, _, bx1, _ = ink(b_glyphs, b_cmap[ord(ch)])
                # 기울이면 잉크 폭이 는다. ⅰ 는 점과 아래 세리프가 높이가 달라 0.158 배까지는 안 는다.
                self.assertGreater((bx1 - bx0) - (ax1 - ax0), 0.05 * (ay1 - ay0))


@unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
class NfdTest(unittest.TestCase):
    @staticmethod
    def shape(font, text, *, script=None, features=None):
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        if script is not None:
            buffer.script = script
        hb.shape(font, buffer, features)
        return [(info.codepoint, pos.x_advance, pos.y_advance, pos.x_offset, pos.y_offset)
                for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)]

    def test_modern_hangul_components_are_available_to_font_fallback(self):
        # 앱이 정규화 전에 글자별로 글꼴을 고르면 자모 하나라도 없을 때 다른 글꼴로 넘어간다.
        components = {ord(ch) for cp in range(0xAC00, 0xD7A4)
                      for ch in unicodedata.normalize("NFD", chr(cp))}
        for path in BUILT:
            with self.subTest(font=path.stem):
                font = hb.Font(hb.Face(path.read_bytes()))
                missing = [f"U+{cp:04X}" for cp in sorted(components)
                           if not font.get_nominal_glyph(cp)]
                self.assertEqual(missing, [])

    def test_kana_combining_marks_draw_without_advancing_the_cursor(self):
        for path in BUILT:
            font = TTFont(path)
            cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
            for cp in (0x3099, 0x309A):
                with self.subTest(font=path.stem, mark=f"U+{cp:04X}"):
                    self.assertTrue(cp in cmap, f"U+{cp:04X} 결합점이 없다")
                    name = cmap[cp]
                    self.assertEqual(font["hmtx"][name][0], 0)
                    x0, _, x1, _ = ink(glyphs, name)
                    # 결합점은 다음 칸이 아니라 직전 가나의 오른쪽 위에 그린다.
                    self.assertGreaterEqual(x0, -1200)
                    self.assertLessEqual(x1, 0)

    def test_nfd_filenames_shape_like_nfc_without_changing_compatibility_jamo(self):
        samples = ("한글 각 값 뷁 한글.txt", "ガギグゲゴ ぱぴぷぺぽ ヴゔヷヸヹヺ.txt")
        for path in BUILT:
            font = hb.Font(hb.Face(path.read_bytes()))
            for text in samples:
                with self.subTest(font=path.stem, filename=text):
                    self.assertEqual(self.shape(font, unicodedata.normalize("NFD", text)),
                                     self.shape(font, text))
            with self.subTest(font=path.stem, text="ㄱㅏㄴ"):
                compatibility = self.shape(font, "ㄱㅏㄴ")
                self.assertEqual([glyph for glyph, *_ in compatibility],
                                 [font.get_nominal_glyph(ord(ch)) for ch in "ㄱㅏㄴ"])
                self.assertEqual(sum(row[1] for row in compatibility), 3600)

    def test_ccmp_composes_nfd_without_unicode_recomposition(self):
        # 초성 그룹마다 LV·LVT 와 마지막 음절을 골라 긴 조합과 범위 경계를 확인한다.
        syllables = [chr(0xAC00 + i * 588 + j) for i in range(19) for j in (0, 1, 587)]
        samples = syllables + list("がぱヴゔヷヸヹヺ")
        for path in BUILT:
            original = hb.Font(hb.Face(path.read_bytes()))
            # 완성형 cmap 만 메모리에서 가리면 HarfBuzz 가 미리 조합하지 못한다.
            # 완성형 글리프와 GSUB 는 그대로 두어 ccmp 로만 그 글리프에 도달하게 한다.
            with TTFont(path) as font:
                for sub in font["cmap"].tables:
                    if sub.isUnicode():
                        for ch in samples:
                            sub.cmap.pop(ord(ch), None)
                stream = BytesIO()
                font.save(stream)
            direct = hb.Font(hb.Face(stream.getvalue()))
            for ch in samples:
                with self.subTest(font=path.stem, text=ch):
                    nfd = unicodedata.normalize("NFD", ch)
                    expected = self.shape(original, ch)
                    # Latn 으로 Hangul preprocess 도 우회해 LV+T 규칙까지 직접 거친다.
                    self.assertEqual(self.shape(direct, nfd, script="Latn"), expected)
                    if ch in syllables and (ord(ch) - 0xAC00) % 588 == 587:
                        lv = chr(ord(ch) - (ord(ch) - 0xAC00) % 28)
                        self.assertEqual(self.shape(direct, lv + nfd[-1], script="Latn"), expected)
            for ch in "각ぱ":
                with self.subTest(font=path.stem, ccmp=False, text=ch):
                    self.assertNotEqual(
                        self.shape(direct, unicodedata.normalize("NFD", ch),
                                   script="Latn", features={"ccmp": False}),
                        self.shape(original, ch))

    def test_mixed_script_text_keeps_latin_ligatures(self):
        for path in BUILT:
            base_path = ROOT / "build" / path.name.replace("JetBatangNF", "JetBrainsMonoNerdFontMono")
            if not base_path.exists():
                self.skipTest(f"{base_path.name} 가 없어요. ./build.sh 를 먼저 돌리세요")
            original = hb.Font(hb.Face(base_path.read_bytes()))
            font = hb.Font(hb.Face(path.read_bytes()))
            latin = self.shape(original, "!= ->")
            with self.subTest(font=path.stem, prefix=""):
                self.assertNotEqual(latin, self.shape(original, "!= ->", features={"calt": False}))
                self.assertEqual(self.shape(font, "!= ->"), latin)
            for prefix, glyph_count in (("한글 ", 3), ("が ", 2)):
                with self.subTest(font=path.stem, prefix=prefix):
                    self.assertEqual(self.shape(font, prefix + "!= ->")[glyph_count:], latin)


class VersionTest(unittest.TestCase):
    def test_font_revision_orders_like_release_tags(self):
        # 같은 글꼴이 두 벌 깔리면 fontconfig 는 fontRevision 이 큰 쪽을 고른다. v1.0.0~v1.4.0 은
        # base JetBrains Mono 의 2.304 를 물려받았으니, 새 판은 모두 그보다 커야 옛 판을 이긴다.
        tags = ["1.0.0", "1.4.0", "1.4.1", "1.9.0", "1.10.0", "2.0.0"]
        fixed = [round(2.304 * 65536)] + [round(metadata.font_revision(tag) * 65536) for tag in tags]
        self.assertEqual(fixed, sorted(set(fixed)))

    def test_font_revision_rejects_what_it_cannot_order(self):
        # 전각 숫자(IME 로 친 １.６.０)도 X.Y.Z 로 받으면 nameID 5 의 Mac 기록을 저장하다 실패한다.
        for bad in ["1.5", "v1.5.0", "1.100.0", "1.5.100", "１.６.０"]:
            with self.subTest(version=bad), self.assertRaises(ValueError):
                metadata.font_revision(bad)

    def test_font_revision_rejects_values_that_cannot_be_saved(self):
        # head.fontRevision 은 부호 있는 16.16 고정소수다. 정수부가 32768 이면 저장할 수 없다.
        self.assertAlmostEqual(metadata.font_revision("327.67.99"), 32767.99)
        for bad in ["327.68.0", "328.0.0"]:
            with self.subTest(version=bad), self.assertRaises(ValueError):
                metadata.font_revision(bad)

    @unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
    def test_every_face_reports_one_release_version(self):
        # 버전이 비어 있으면 새 판을 깔았는지 글꼴 정보로 확인할 수 없다.
        versions = set()
        for path in BUILT:
            with self.subTest(font=path.stem):
                font = TTFont(path)
                found = re.fullmatch(r"Version (\d+\.\d+\.\d+)", font["name"].getDebugName(5) or "")
                self.assertIsNotNone(found, "nameID 5 가 'Version X.Y.Z' 가 아니다")
                self.assertAlmostEqual(font["head"].fontRevision, metadata.font_revision(found[1]),
                                       delta=1 / 65536)
                versions.add(found[1])
        self.assertEqual(len(versions), 1, versions)


class ReleaseTest(unittest.TestCase):
    @unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
    def test_fonts_were_built_from_current_sources(self):
        # 이 파일의 검사는 fonts/ 를 잰다. fonts/ 를 예전 코드로 만들었거나 일부만 다시 만들었으면
        # 검사가 통과해도 지금 코드를 잰 게 아니다. 빌드가 중간에 멈춰 기록이 없을 때도 마찬가지다.
        try:
            release.verify_manifest(ROOT)
        except ValueError as exc:
            self.fail(str(exc))

    def test_manifest_accepts_only_a_finished_build_of_the_current_tree(self):
        # package.sh 는 이 기록만 믿고 글꼴을 묶는다. 하나라도 받아들이면 예전 글꼴이 릴리스로 나간다.
        def built():
            root = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, root)
            for pattern in release.SOURCES:
                for path in ROOT.glob(pattern):
                    (root / path.relative_to(ROOT)).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(path, root / path.relative_to(ROOT))
            (root / "fonts").mkdir()
            for name in release.font_files():
                (root / "fonts" / name).write_bytes(name.encode())
            release.write_manifest(root, "1.6.0", release.snapshot(root))
            return root

        self.assertEqual(release.verify_manifest(built())["version"], "1.6.0")

        def edit_code(root):
            with open(root / "jetbatang" / "charset.py", "a") as f:
                f.write("# 고침\n")

        def write_manifest(root, text):
            (root / "fonts" / release.MANIFEST).write_text(text)

        def drop_one_font(root):
            path = root / "fonts" / release.MANIFEST
            info = json.loads(path.read_text())
            info["fonts"].pop(release.font_files()[0])
            path.write_text(json.dumps(info))

        cases = {
            "빌드한 뒤 코드를 고침": edit_code,
            "빌드한 뒤 글꼴이 바뀜": lambda root: (root / "fonts" / release.font_files()[3]).write_bytes(b"x"),
            "글꼴 하나가 없음": lambda root: (root / "fonts" / release.font_files()[5]).unlink(),
            "기록이 없음": lambda root: (root / "fonts" / release.MANIFEST).unlink(),
            "기록이 비었음": lambda root: write_manifest(root, ""),
            "기록에 키가 빠짐": lambda root: write_manifest(root, '{"version": "1.6.0"}'),
            "기록이 객체가 아님": lambda root: write_manifest(root, "[]"),
            "기록의 값 형식이 틀림": lambda root: write_manifest(
                root, '{"version": "1.6.0", "sources": "x", "libraries": {}, "fonts": []}'),
            "기록의 굵기 목록이 모자람": drop_one_font,
        }
        for case, spoil in cases.items():
            with self.subTest(case=case):
                root = built()
                spoil(root)
                with self.assertRaises(ValueError):
                    release.verify_manifest(root)

        with self.subTest(case="빌드하는 동안 코드를 고침"):
            root = built()
            (root / "fonts" / release.MANIFEST).unlink()
            before = release.snapshot(root)
            edit_code(root)
            with self.assertRaises(ValueError):
                release.write_manifest(root, "1.6.0", before)
            self.assertFalse((root / "fonts" / release.MANIFEST).exists())

    def test_library_mismatches_name_each_library_off_its_pin(self):
        # build.sh 와 package.sh 의 판 경고는 이 비교 하나에 기댄다. 고정값을 못 읽으면 경고가 조용히 사라진다.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        (root / release.REQUIREMENTS).write_text(
            "# 빌드와 검사에 쓰는 판\nfonttools==4.66.1\n\n  skia-pathops == 0.9.2  # 경계 연산\nuharfbuzz==0.56.3\n",
            encoding="utf-8")
        pins = {"fonttools": "4.66.1", "skia-pathops": "0.9.2", "uharfbuzz": "0.56.3"}
        self.assertEqual(release.pinned_versions(root), pins)
        self.assertEqual(release.library_mismatches(root, pins), [])
        self.assertEqual(release.library_mismatches(root, dict(pins, fonttools="4.66.0", uharfbuzz=None)),
                         [("fonttools", "4.66.1", "4.66.0"), ("uharfbuzz", "0.56.3", None)])

    def test_windows_installer_knows_every_face(self):
        # install-windows.ps1 은 Releases 에 따로 올라가 jetbatang/release.py 의 VARIANTS 를 읽지 못해서
        # 굵기 목록을 따로 들고 있다. 목록에 없는 굵기는 설치도 제거도 되지 않는다.
        script = (ROOT / "install-windows.ps1").read_text(encoding="utf-8-sig")
        listed = dict(re.findall(r"'(JetBatangNF-\w+\.ttf)'\s*=\s*'([^']+)'", script))
        expected = {f"JetBatangNF-{suffix}.ttf": f"JetBatang NF {style} (TrueType)"
                    for suffix, style, _ in release.VARIANTS}
        self.assertEqual(listed, expected)


if __name__ == "__main__":
    unittest.main()
