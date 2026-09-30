"""build.py 회귀 검사. 원본 글꼴이 build/ 에 있어야 돈다(./build.sh 가 받아 둔다).

    python3 -m unittest discover tests
"""
import unicodedata
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont

import build

DONOR = Path(__file__).resolve().parent.parent / "build" / "RIDIBatang.otf"


@unittest.skipUnless(DONOR.exists(), "build/RIDIBatang.otf 가 없어요. ./build.sh 를 먼저 돌리세요")
class DonorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = TTFont(DONOR)
        cls.cmap = cls.donor.getBestCmap()

    def test_takes_every_wide_glyph_the_donor_has(self):
        # 터미널이 2칸으로 세는 글자를 빠뜨리면 다른 글꼴이 대신 그린다.
        missing = [f"U+{cp:04X}" for cp in sorted(self.cmap)
                   if unicodedata.east_asian_width(chr(cp)) in "WF" and not build.is_wide(cp)]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
