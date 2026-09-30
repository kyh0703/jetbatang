"""build.py 회귀 검사. build/ 의 원본 글꼴과 fonts/ 의 빌드 결과가 있어야 돈다(./build.sh).

    python3 -m unittest discover tests
"""
import unicodedata
import unittest
from pathlib import Path

from fontTools.misc.transform import Transform
from fontTools.ttLib import TTFont

import build

ROOT = Path(__file__).resolve().parent.parent
DONOR = ROOT / "build" / "RIDIBatang.otf"
REGULAR = ROOT / "fonts" / "JetBatangNF-Regular.ttf"
BUILT = sorted((ROOT / "fonts").glob("JetBatangNF-*.ttf"))


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
                   if unicodedata.east_asian_width(chr(cp)) in "WF" and not build.is_wide(cp)]
        self.assertEqual(missing, [])

    def test_merged_bold_paints_like_the_overlapped_copies(self):
        # Bold(embolden 36) 에서 skia 두 경로 중 한쪽이 틀리거나 예외를 내던 글자들.
        # 휑 은 OpBuilder 가, 흉 은 simplify 가 속공간을 먹고, 훙 은 simplify 가 예외를 낸다.
        offsets = build.embolden_ring(36, 36 * 0.4)
        for ch in "휑흉훙":
            with self.subTest(ch=ch):
                name = self.cmap[ord(ch)]
                dx = (1200 - self.donor["hmtx"][name][0]) / 2.0
                src = build.outline(self.glyphs[name], Transform(1, 0, 0, 1, dx, 60), 1.0)
                merged = build.merge_copies(src, offsets)
                self.assertIsNotNone(merged)

                truth = build.coverage(build.stacked(src, offsets))
                got = build.coverage(build.stacked(merged, [(0, 0)]))
                # 저장하며 좌표를 정수로 반올림해 외곽선이 반 단위까지 움직인다(1.6e-3 안팎).
                # 속공간을 먹은 합집합은 2.6e-2 넘게 어긋난다.
                self.assertLess(build.mismatch(truth, got), build.painted(truth) * 5e-3)


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

    def test_fullwidth_won_sign_is_not_a_backslash(self):
        # RIDIBatang 은 ￦ 에 전각 역슬래시 모양을 걸어 두었다. ₩ 은 옆으로 넓고 \ 는 세로로 길다.
        glyph, advance = self.glyph("￦")
        self.assertEqual(advance, 1200)
        self.assertGreater(glyph.xMax - glyph.xMin, glyph.yMax - glyph.yMin)


@unittest.skipUnless(BUILT, "fonts/ 에 빌드 결과가 없어요. ./build.sh 를 먼저 돌리세요")
class WonSignTest(unittest.TestCase):
    def test_won_sign_takes_the_box_of_w_on_the_baseline(self):
        # ₩ 은 터미널이 1칸으로 센다. 굵기·기울기마다 base W 가 차지하는 가로 범위에 들고,
        # 한글처럼 올려 앉히지 않아 숫자와 기준선이 같다.
        for path in BUILT:
            with self.subTest(font=path.stem):
                font = TTFont(path)
                cmap, glyf, hmtx = font.getBestCmap(), font["glyf"], font["hmtx"]
                self.assertTrue(0x20A9 in cmap, "₩ 가 없다")
                won, w = glyf[cmap[0x20A9]], glyf[cmap[ord("W")]]
                self.assertEqual(hmtx[cmap[0x20A9]][0], 600)
                self.assertAlmostEqual(won.xMin, w.xMin, delta=3)
                self.assertAlmostEqual(won.xMax, w.xMax, delta=3)
                self.assertAlmostEqual(won.yMin, 0, delta=20)



if __name__ == "__main__":
    unittest.main()
