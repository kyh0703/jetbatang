#!/usr/bin/env python3
"""Nerd Font 패치본(라틴+아이콘)과 RIDIBatang(한글)을 한 파일로 합친다.

터미널은 한글을 2칸으로 세기 때문에, 한글 advance 를 라틴 1칸의 정확히 2배로
못 박는 것이 이 스크립트의 핵심이다. RIDIBatang 은 한글 advance 가 922~963 으로
제각각이라 그대로 두면 격자가 어긋난다.
"""
import argparse

from jetbatang.merge import Options, build_font
from jetbatang.metadata import font_revision
from jetbatang.weight import Weight


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True,
                    help="라틴·아이콘을 담당할 Nerd Font Mono ttf")
    ap.add_argument("--donor", required=True, help="RIDIBatang.otf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--font-version", required=True,
                    help="릴리스 버전 X.Y.Z. 글꼴 정보의 버전(nameID 5)과 head.fontRevision 에 들어간다")
    ap.add_argument("--family", default="JetBatang NF")
    ap.add_argument("--style", default="Regular",
                    help="타이포그래픽 스타일. 예: Regular, Italic, SemiBold, Bold Italic")
    ap.add_argument("--scale", type=float, default=1.00,
                    help="한글 배율(donor upem 기준). 1.00 = RIDIBatang 원본 크기")
    ap.add_argument("--yshift", type=float, default=60.0,
                    help="한글 세로 이동(base 단위). 바탕체는 받침이 깊어 라틴보다 낮게 앉는다")
    ap.add_argument("--shear-from-base", action="store_true",
                    help="base 의 italicAngle 만큼 한글도 기울인다(가짜 이탤릭)")
    ap.add_argument("--shear-pivot", type=float, default=0.325,
                    help="기울임 회전축 높이(em 비율). 한글 세로 중앙")
    ap.add_argument("--embolden", type=float, default=0.0,
                    help="한글 가로 굵기 증가량(base 단위). 음수면 그만큼 깎는다. RIDIBatang 은 "
                         "한 굵기뿐이라 다른 굵기는 이걸로 만든다")
    ap.add_argument("--embolden-y", type=float, default=None,
                    help="한글 세로 굵기 증가량. 생략하면 --embolden 이 양수일 때 0.4 배, 음수일 때 "
                         "0.8 배. 명조 Bold 는 세로획이 주로 굵어지지만 가로획을 그대로 두면 저해상도에서 "
                         "세로획만 진하고 가로획은 흐려 얼룩져 보인다. 가로획이 겹겹이 쌓이는 "
                         "글자(능·동·닙)의 속공간이 메워지지 않는 선에서 절반 조금 못 되게 준다. "
                         "깎을 때는 RIDIBatang 의 가로획 67 과 세로획 81 의 비율대로 깎는다. "
                         "0.4 배만 깎으면 Thin 에서 가로획이 세로획보다 굵어진다")
    ap.add_argument("--max-err", type=float, default=0.001,
                    help="곡선 변환 허용오차(em 비율)")
    args = ap.parse_args()
    try:
        font_revision(args.font_version)
        weight = Weight(args.embolden, args.embolden_y)
    except ValueError as exc:
        ap.error(str(exc))
    return Options(base=args.base, donor=args.donor, out=args.out, font_version=args.font_version,
                   family=args.family, style=args.style, scale=args.scale, yshift=args.yshift,
                   shear_from_base=args.shear_from_base, shear_pivot=args.shear_pivot,
                   weight=weight, max_err=args.max_err)


def main():
    build_font(parse_args())


if __name__ == "__main__":
    main()
