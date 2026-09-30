"""build.py 회귀 검사. 원본 글꼴이 build/ 에 있어야 돈다(./build.sh 가 받아 둔다).

    python3 -m unittest discover tests
"""
import unicodedata
import unittest
from pathlib import Path

from fontTools.misc.transform import Transform
from fontTools.ttLib import TTFont

import build

DONOR = Path(__file__).resolve().parent.parent / "build" / "RIDIBatang.otf"


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


if __name__ == "__main__":
    unittest.main()
