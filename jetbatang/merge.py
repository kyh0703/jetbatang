"""base 에 donor 글자를 더해 한 글꼴로 만드는 흐름. 글자 고르기·칸 배치·획 굵기·NFD·이름 같은 영역별
계산은 각 모듈에 있고, 여기에는 그것을 이어 base 에 글리프를 넣는 단계와 그 순서가 있다."""
import re
import sys
from dataclasses import dataclass
from typing import NamedTuple

from fontTools.misc.transform import Transform
from fontTools.ttLib import TTFont

from .charset import ALIASES, BASE_ALIASES, WIDEN, is_wide, ksx1001_symbols
from .kana import combining_kana, small_kana, spacing_marks, voiced_kana
from .layout import Grid, SymbolCell, fit_cell
from .metadata import set_names, set_os2
from .nfd import add_nfd_jamo, add_nfd_substitutions, mark_combining
from .outlines import make_composite, outline
from .weight import Weight, embolden_ring, merge_copies, reweigh


def sanitize(name):
    n = re.sub(r"[^A-Za-z0-9._]", "_", name)
    return n if re.match(r"^[A-Za-z_]", n) else "g" + n


class Merge:
    """base 에 글리프를 더해 가는 상태. 새 이름이 겹치지 않게 하고, cmap 에 걸 글자를 모은다."""

    def __init__(self, base):
        self.base = base
        self.glyf, self.hmtx = base["glyf"], base["hmtx"]
        self.order = list(base.getGlyphOrder())
        self.taken = set(self.order)
        self.added = {}                         # cp → 글리프 이름

    def unique_name(self, dname):
        gname = sanitize("rb." + dname)
        i = 2
        while gname in self.taken:
            gname = sanitize(f"rb.{dname}.{i}")
            i += 1
        self.taken.add(gname)
        return gname

    def put(self, name, glyph, advance):
        """새 글리프를 넣는다. 같은 이름이 이미 있으면 덮어쓰지 않고 멈춘다."""
        if name in self.glyf.glyphs:
            raise ValueError(f"글리프 이름 {name} 이 이미 있어요")
        self.taken.add(name)
        self.glyf.glyphs[name] = glyph
        glyph.recalcBounds(self.glyf)
        self.hmtx.metrics[name] = (advance, glyph.xMin if glyph.numberOfContours else 0)
        self.order.append(name)

    def replace(self, name, glyph):
        """넣어 둔 글리프의 외곽선만 바꾼다. 폭은 그대로 둔다."""
        advance = self.hmtx[name][0]
        self.glyf.glyphs[name] = glyph
        glyph.recalcBounds(self.glyf)
        self.hmtx.metrics[name] = (advance, glyph.xMin if glyph.numberOfContours else 0)

    def remove(self, name):
        """넣어 둔 글리프를 뺀다."""
        del self.glyf.glyphs[name]
        del self.hmtx.metrics[name]
        self.order.remove(name)

    def finish(self):
        """글리프 순서와 개수를 맞추고, 모은 글자를 유니코드 cmap 에 건다."""
        self.base.setGlyphOrder(self.order)
        self.glyf.glyphOrder = self.order
        self.base["maxp"].numGlyphs = len(self.order)
        for sub in self.base["cmap"].tables:
            if not sub.isUnicode():
                continue
            for cp, gname in self.added.items():
                if cp <= 0xFFFF or sub.format in (12, 13):
                    sub.cmap[cp] = gname


@dataclass(frozen=True)
class Options:
    """build_font 에 넘기는 값. build.py 가 명령줄 인자로 만든다."""
    base: str
    donor: str
    out: str
    font_version: str
    family: str
    style: str
    scale: float            # 한글 배율(donor upem 기준)
    yshift: float           # 한글 세로 이동(base 단위)
    shear_from_base: bool   # base 의 italicAngle 만큼 한글도 기울인다
    shear_pivot: float      # 기울임 회전축 높이(em 비율)
    weight: Weight
    max_err: float          # 곡선 변환 허용오차(em 비율)


class Source(NamedTuple):
    """donor 에서 가져와 base 에 넣을 글자 하나."""
    drawing: object         # draw(pen) 하는 donor 글리프, 또는 kana 가 만든 글자
    transform: Transform    # base 칸으로 옮기는 변환
    advance: int
    name: str               # 새 글리프 이름의 바탕
    grow: tuple = None      # 기본과 다른 (가로, 세로) 굵기 증가량. None 이면 Weight 를 따른다
    one_cell: bool = False  # 1칸에 줄여 넣는 KS X 1001 기호


def donor_sources(donor, base, grid, weight):
    """donor 에서 가져올 글자를 고른다. {cp: Source} 를 준다."""
    dcmap = donor.getBestCmap()
    dglyphs = donor.getGlyphSet()
    dhmtx = donor["hmtx"]
    cell, wide, ex, ey = grid.cell, grid.wide, weight.ex, weight.ey

    targets = {cp: dcmap[cp] for cp in dcmap if is_wide(cp)}
    targets.update({cp: dcmap[src] for cp, src in ALIASES.items() if src in dcmap})

    sources = {cp: Source(dglyphs[name], grid.centered(dhmtx[name][0]), wide, name)
               for cp, name in targets.items()}
    combining = combining_kana(dglyphs, dcmap, dhmtx)
    made = voiced_kana(dglyphs, dcmap, dhmtx) | small_kana(dglyphs, dcmap, dhmtx) | spacing_marks(combining)
    for cp, (drawing, advance, name) in made.items():
        if cp not in dcmap:
            sources[cp] = Source(drawing, grid.centered(advance), wide, name)
    for cp, (drawing, advance, name) in combining.items():
        tf = grid.centered(advance)
        # 결합점의 advance 는 0. 현재 펜 위치에서 직전의 두 칸으로 돌아가 놓는다.
        sources[cp] = Source(drawing, Transform(tf.xx, tf.xy, tf.yx, tf.yy, tf.dx - wide, tf.dy), 0, name)
    bcmap = base.getBestCmap()
    bglyphs = base.getGlyphSet()
    one_cell = SymbolCell(donor, base, grid, ex)

    # 1칸에 줄여 넣는 글자는 줄인 비율만큼 덜 불린다. 원래 크기에서 굵게 한 다음 줄인 것과 같은
    # 모양이라, 0.6 배로 좁아진 ⑧ ⓐ 의 속공간이 덜 막힌다.
    for cp in ksx1001_symbols(bcmap):
        if cp in dcmap:
            tf, k = one_cell.place(dcmap[cp])
            sources[cp] = Source(dglyphs[dcmap[cp]], tf, cell, dcmap[cp], (ex * k, ey * k), True)
    for cp, (tf, grow) in fit_cell(dglyphs, dcmap, bglyphs, bcmap, grid.shear, ex).items():
        sources[cp] = Source(dglyphs[dcmap[cp]], tf, cell, dcmap[cp], (grow, ey))
    return sources


class DonorGlyphs(NamedTuple):
    """add_donor_glyphs 가 한 일."""
    skipped: int            # TrueType 외곽선으로 옮기지 못한 글자 수
    reshaped: int           # 모양을 지키며 굵기를 바꾼 글자 수
    partly: list            # 덜 바꾼 글자
    kept: list              # 모양이 바뀌어 그대로 둔 글자
    layered: dict           # 외곽선을 겹쳐 부르는 composite 로 둔 글자 {cp: 글리프 이름}


def add_donor_glyphs(merge, weight, sources, max_err):
    """sources 를 TrueType 글리프로 옮기고 굵기를 바꿔 base 에 넣는다. max_err 는 base 단위다."""
    skipped, reshaped, partly, kept, layered = 0, 0, [], [], {}
    for cp in sorted(sources):
        source = sources[cp]

        try:
            glyph = outline(source.drawing, source.transform, max_err)
        except Exception as exc:
            print(f"  skip U+{cp:04X} {source.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        gname = merge.unique_name(source.name)
        gx, gy = source.grow or (weight.ex, weight.ey)

        # 깎을 때는 한글·가나 등, 불릴 때는 1칸 기호만 모양을 지키며 굵기를 바꾼다. 한글은 불리면
        # ㅃ ㄳ 처럼 가까운 획이 붙는 게 자연스럽지만, 줄여 넣은 ⑫ 의 숫자가 원에 붙으면 읽을 수 없다.
        # 1칸 기호는 0.6 배로 줄여 넣어 획이 이미 Light 라틴보다 가늘다(① 의 원 33). 한글만큼
        # 깎으면 Thin 에서 원이 7 로 거의 사라져서 깎지 않는다.
        if weight.thinner:
            reshape = not source.one_cell
        else:
            reshape = weight.emboldens and source.one_cell
        if glyph.numberOfContours and reshape:
            changed, step = reweigh(glyph, gx, gy)
            if changed is None:
                kept.append(chr(cp))
            else:
                glyph = changed
                reshaped += 1
                if step < 1:
                    partly.append(chr(cp))
        elif weight.emboldens and glyph.numberOfContours:
            # 원본 외곽선은 cmap 에 걸지 않는 글리프로 두고, 그것을 여러 번 겹쳐
            # 부르는 composite 를 실제 글자로 쓴다. 점을 복사하지 않아 용량이 거의 안 는다.
            src = gname + ".src"
            merge.put(src, glyph, source.advance)
            glyph = make_composite(src, embolden_ring(gx, gy))
            layered[cp] = gname
        merge.put(gname, glyph, source.advance)
        merge.added[cp] = gname
    return DonorGlyphs(skipped, reshaped, partly, kept, layered)


def merge_overlaps(merge, layered):
    """add_donor_glyphs 가 겹쳐 부르는 composite 로 둔 글자({cp: 글리프 이름})를 외곽선 하나로 합친다.

    겹쳐 놓은 composite 를 그대로 두면 macOS CoreText 가 겹친 가장자리마다
    안티앨리어싱을 따로 해서 획이 번져 보인다(FreeType 은 멀쩡하다).
    그래서 합집합을 구해 외곽선 하나로 만든다. 믿을 수 없는 글자만 겹친 채 둔다.
    """
    glyf = merge.glyf
    merged, failed = 0, []
    for cp, name in layered.items():
        src = name + ".src"
        # composite 가 실제로 겹쳐 그리는 자리 그대로 합친다.
        offsets = [(c.x, c.y) for c in glyf[name].components]
        one = merge_copies(glyf[src], offsets)
        if one is None:
            failed.append(chr(cp))
            continue
        merge.replace(name, one)
        merged += 1
    used = {c.glyphName for n in merge.added.values()
            if glyf[n].isComposite() for c in glyf[n].components}
    for name in layered.values():
        src = name + ".src"
        if src not in used:
            merge.remove(src)
    print(f"  외곽선 합침: {merged}자" + (f", 겹친 채 둠: {' '.join(failed)}" if failed else ""))


def add_widened(merge, wide):
    """터미널이 2칸으로 세는 base 글자를 2칸 가운데로 옮겨 부른다. 원래 글리프는 그대로 둔다."""
    bcmap = merge.base.getBestCmap()
    for cp in WIDEN:
        if cp not in bcmap:
            continue
        src = bcmap[cp]
        gname = src + ".wide"
        merge.put(gname, make_composite(src, [((wide - merge.hmtx[src][0]) // 2, 0)]), wide)
        merge.added[cp] = gname


def add_base_aliases(merge):
    """base 에 같은 글자가 있으면 RIDIBatang 에서 가져오지 않고 base 글리프를 그대로 건다."""
    bcmap = merge.base.getBestCmap()
    for cp, src in BASE_ALIASES.items():
        if cp not in bcmap and src in bcmap:
            merge.added[cp] = bcmap[src]


def build_font(options):
    """options 대로 base 와 donor 를 합쳐 options.out 에 저장한다."""
    base = TTFont(options.base)
    donor = TTFont(options.donor)
    grid = Grid(base, donor, options.scale, options.yshift, options.shear_from_base, options.shear_pivot)
    weight = options.weight
    print(f"base upem={grid.upem} cell={grid.cell} wide={grid.wide} | donor upem={grid.donor_upem} "
          f"| scale={grid.scale:.4f} shear={grid.shear:.4f} embolden={weight.ex:g}/{weight.ey:g}")

    merge = Merge(base)
    sources = donor_sources(donor, base, grid, weight)
    done = add_donor_glyphs(merge, weight, sources, options.max_err * grid.upem)
    print(f"  한글 등 {len(merge.added)}자 추가, {done.skipped}자 건너뜀")
    if done.skipped:
        # 빠진 채 저장하면 그 글자는 터미널이 다른 글꼴로 그린다. 실패로 끝내 빌드 기록이 남지 않게 한다.
        raise SystemExit(f"{done.skipped}자를 TrueType 외곽선으로 옮기지 못했어요. 위의 skip 줄을 확인하세요")
    if weight.thinner or weight.emboldens:
        verb = "깎음" if weight.thinner else "불림(1칸 기호)"
        print(f"  모양을 지키며 {verb}: {done.reshaped}자"
              + (f", 덜 바꿈: {''.join(done.partly)}" if done.partly else "")
              + (f", 그대로 둠: {''.join(done.kept)}" if done.kept else ""))
    if weight.emboldens:
        merge_overlaps(merge, done.layered)
    add_widened(merge, grid.wide)
    add_base_aliases(merge)
    add_nfd_jamo(merge, grid.wide)
    # 글리프를 다 넣은 뒤에 cmap 을 건다. 아래 GSUB·GDEF·OS/2 단계는 그 cmap 을 읽는다.
    merge.finish()

    add_nfd_substitutions(base)
    mark_combining(base, merge.added)
    set_os2(base)
    set_names(base, donor, options.family, options.style, options.font_version)

    base.save(options.out)
    print(f"  저장: {options.out}")
