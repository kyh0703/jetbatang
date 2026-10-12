"""이름 테이블, 판 번호, OS/2 처럼 글꼴을 소개하는 정보를 쓴다."""
import re


# Windows GDI 는 한 가족에 Regular/Italic/Bold/Bold Italic 네 칸만 준다.
RIBBI = {"Regular", "Italic", "Bold", "Bold Italic"}

OFL_URL = "https://openfontlicense.org"

OFL_DESC = "This Font Software is licensed under the SIL Open Font License, Version 1.1."


def font_revision(version):
    """릴리스 버전 X.Y.Z 를 head.fontRevision 값으로 바꾼다. 1.9.0 < 1.10.0 처럼 태그 순서를 지킨다.

    v1.0.0~v1.4.0 은 base JetBrains Mono 의 2.304 를 그대로 물려받았다. 옛 판과 새 판이 함께 깔리면
    fontconfig 는 fontRevision 이 큰 쪽을 고르므로, 새 판은 모두 그보다 커야 한다. 그래서 X·Y 를
    정수부에, Z 를 소수부에 넣는다. 1.5.0 은 105.00, 1.10.2 는 110.02 다.
    부호 있는 16.16 고정소수에 들어가야 하므로 상한은 327.67.99 다.
    """
    # \d 는 전각 숫자도 받아서 [0-9] 로 쓴다. １.６.０ 은 Mac 이름 기록으로 저장할 수 없다.
    found = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version)
    if not found or int(found[2]) > 99 or int(found[3]) > 99:
        raise ValueError(f"버전은 X.Y.Z 꼴이고 Y·Z 는 0~99 여야 해요: {version!r}")
    major, minor, patch = map(int, found.groups())
    integer = major * 100 + minor
    if integer >= 32768:
        raise ValueError(f"글꼴 내부 버전값으로 저장할 수 있는 상한은 327.67.99 예요: {version!r}")
    return integer + patch / 100


def legacy_names(family, style):
    """nameID 1/2 에 넣을 (가족, 스타일). 16 종을 네 칸짜리 규칙에 욱여넣는다.

    RIBBI 바깥 굵기는 가족 이름 쪽에 굵기를 붙여 따로 가족을 만든다.
    (JetBatang NF SemiBold / Italic) 실제 가족은 nameID 16/17 로만 알린다.
    """
    if style in RIBBI:
        return family, style
    italic = style.endswith("Italic")
    weight = style[:-len("Italic")].strip() if italic else style
    return f"{family} {weight}", ("Italic" if italic else "Regular")


def get_name(font, nid):
    rec = font["name"].getDebugName(nid)
    return rec.strip() if rec else ""


def set_name(font, nid, value):
    font["name"].setName(value, nid, 3, 1, 0x409)   # Windows
    font["name"].setName(value, nid, 1, 0, 0)       # Mac


def set_os2(base):
    """한글을 쓸 수 있는 폰트라고 Windows 에 알린다."""
    os2 = base["OS/2"]
    try:
        os2.recalcUnicodeRanges(base)
    except Exception as exc:
        print(f"  (unicode range 재계산 생략: {exc})")
    os2.ulCodePageRange1 |= (1 << 19) | (1 << 21)   # 949 Wansung / 1361 Johab


def set_names(base, donor, family, style, font_version):
    """이름 테이블과 판 번호를 새로 쓴다.

    원본의 이름·상표 기록은 통째로 버리고 새로 쓴다.
    base 의 Reserved Font Name 과 donor 의 등록상표를 물려받지 않기 위해서다.
    """
    copyright_ = " | ".join(filter(None, [
        f"Latin & icons: {get_name(base, 0)}",
        f"Hangul: {get_name(donor, 0)}",
        "Merged derivative, SIL Open Font License 1.1.",
    ]))
    fam1, sub2 = legacy_names(family, style)
    full = f"{family} {style}"
    ps = (re.sub(r"[^A-Za-z0-9]", "", family) + "-"
          + re.sub(r"[^A-Za-z0-9]", "", style))

    drop = set(range(0, 15)) | {16, 17, 18, 20, 21, 22}
    base["name"].names = [n for n in base["name"].names if n.nameID not in drop]
    for nid, value in [(0, copyright_), (1, fam1), (2, sub2),
                       (3, f"{ps};merged-with-RIDIBatang"), (4, full),
                       (5, f"Version {font_version}"), (6, ps),
                       (13, OFL_DESC), (14, OFL_URL), (16, family), (17, style)]:
        set_name(base, nid, value)
    # 비워 두면 base 의 2.304 가 남아 JetBrains Mono 와 같은 판으로 보인다.
    base["head"].fontRevision = font_revision(font_version)
