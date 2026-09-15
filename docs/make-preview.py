#!/usr/bin/env python3
"""README 에 넣는 미리보기 이미지를 만든다.

    pip install pillow
    python3 docs/make-preview.py

fonts/ 에 빌드된 ttf 가 있어야 한다.
"""
from PIL import Image, ImageDraw, ImageFont

BG, FG, WHITE = "#17171d", "#eaeaf0", "#ffffff"
BLUE, GREEN, YELLOW, DIM = "#8ec5ff", "#8bc098", "#ddbd7b", "#6e7681"

FOLDER, BRANCH, NODE, SEP = "", "", "", ""
TS, PY, RS, DOCKER = "", "", "", ""
CHECK, CROSS, WARN, BOLT = "", "", "", ""

WEIGHTS = [("Thin", 0), ("ExtraLight", 0), ("Light", 0), ("Regular", 0),
           ("Medium", 8), ("SemiBold", 16), ("Bold", 32), ("ExtraBold", 52)]


def face(suffix, size):
    return ImageFont.truetype(f"fonts/JetBatangNF-{suffix}.ttf", size)


def canvas(w, h):
    im = Image.new("RGB", (w, h), BG)
    return im, ImageDraw.Draw(im)


def terminal():
    """터미널 한 화면. 라틴 1칸 / 한글 2칸 격자가 맞는지 보이는 것이 목적이다."""
    S, X0, W, H = 38, 52, 1472, 464
    rows = [
        (0, "Bold",    BLUE,   f"{FOLDER} ~/project/office/portal  {BRANCH} main  {NODE} v22  {SEP}"),
        (0, "Regular", FG,     "$ 리디바탕을 터미널에 — 한글 English 0123 il1 0O"),
        (0, "Regular", GREEN,  "# 다람쥐 헌 쳇바퀴에 타고파 → advance 1200 = 라틴 2칸"),
        (2, "Regular", FG,     f"{TS} docs-link.ts   {PY} 통화.py   {RS} 런타임.rs   {DOCKER} 배포"),
        (2, "Regular", YELLOW, f"{CHECK} 정렬 확인  {CROSS} 실패  {WARN} 경고  {BOLT} ┌─┬─┐ │"),
        (2, "Bold",    WHITE,  "한글 = 2칸  |  ASCII = 1칸  |  아이콘 = 1칸"),
    ]
    im, d = canvas(W, H)
    for i, (indent, suffix, color, text) in enumerate(rows):
        x = X0 + indent * S * 0.6
        d.text((x, 89 + i * 61.5), text, font=face(suffix, S), fill=color, anchor="ls")
    im.save("docs/preview.png")


def weights():
    """굵기 여덟 단계. Regular 아래로는 한글이 더 가늘어지지 않는 것도 같이 보인다."""
    S, ROW, W = 34, 54, 1180
    im, d = canvas(W, 44 + ROW * len(WEIGHTS))
    label, note = face("Regular", 19), face("Regular", 17)
    for i, (name, em) in enumerate(WEIGHTS):
        y = 56 + i * ROW
        d.text((32, y), name, font=label, fill=DIM, anchor="ls")
        d.text((250, y), "한글 굵기 Hangul 0123", font=face(name, S), fill=FG, anchor="ls")
        d.text((W - 32, y), f"embolden {em}", font=note,
               fill=GREEN if em else DIM, anchor="rs")
    im.save("docs/weights.png")


def sizes():
    """실제 터미널 크기. 명조가 몇 px 부터 뭉개지는지 보라고 넣는다."""
    text = "한글 = 2칸 | 아이콘 1칸  뷁빻읊쫒 abc 0123"
    rows = [(s, w) for s in (13, 14, 16, 18) for w in ("Regular", "Bold")]
    im, d = canvas(940, 30 + sum(s + 20 for s, _ in rows))
    y = 18
    for s, w in rows:
        d.text((24, y + s * 0.8), f"{s}px {w}", font=face("Regular", 15),
               fill=DIM, anchor="ls")
        d.text((170, y + s * 0.8), text, font=face(w, s), fill=FG, anchor="ls")
        y += s + 20
    im.save("docs/sizes.png")


if __name__ == "__main__":
    terminal()
    weights()
    sizes()
    print("docs/preview.png, docs/weights.png, docs/sizes.png")
