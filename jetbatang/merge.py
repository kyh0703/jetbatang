"""base 에 donor 글자를 더해 한 글꼴로 만드는 흐름. 각 단계는 영역별 모듈에 있다."""
import re
import sys

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
        self.glyf.glyphs[name] = glyph
        glyph.recalcBounds(self.glyf)
        self.hmtx.metrics[name] = (advance, glyph.xMin if glyph.numberOfContours else 0)
        self.order.append(name)

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


def donor_sources(donor, base, grid, weight):
    """donor 에서 가져올 글자를 고른다. (sources, grows, symbols, 건너뛴 글자 수) 를 준다.

    sources 는 {cp: (그릴 거리, 변환, 폭, 이름)}, grows 는 기본과 다른 굵기 증가량을 쓰는 글자의
    {cp: (gx, gy)}, symbols 는 1칸에 줄여 넣는 KS X 1001 기호다.
    """
    dcmap = donor.getBestCmap()
    dglyphs = donor.getGlyphSet()
    dhmtx = donor["hmtx"]
    cell, wide, ex, ey = grid.cell, grid.wide, weight.ex, weight.ey

    targets = {cp: dcmap[cp] for cp in dcmap if is_wide(cp)}
    targets.update({cp: dcmap[src] for cp, src in ALIASES.items() if src in dcmap})

    sources = {cp: (dglyphs[name], grid.centered(dhmtx[name][0]), wide, name)
               for cp, name in targets.items() if name in dhmtx.metrics}
    skipped = len(targets) - len(sources)
    combining = combining_kana(dglyphs, dcmap, dhmtx)
    made = voiced_kana(dglyphs, dcmap, dhmtx) | small_kana(dglyphs, dcmap, dhmtx) | spacing_marks(combining)
    for cp, (drawing, advance, name) in made.items():
        if cp not in dcmap:
            sources[cp] = (drawing, grid.centered(advance), wide, name)
    for cp, (drawing, advance, name) in combining.items():
        tf = grid.centered(advance)
        # 결합점의 advance 는 0. 현재 펜 위치에서 직전의 두 칸으로 돌아가 놓는다.
        sources[cp] = (drawing, Transform(tf.xx, tf.xy, tf.yx, tf.yy, tf.dx - wide, tf.dy), 0, name)
    bcmap = base.getBestCmap()
    bglyphs = base.getGlyphSet()
    one_cell = SymbolCell(donor, base, grid, ex)

    # 기본(ex, ey)과 다른 굵기 증가량으로 불리는 글자. 줄여 넣는 글자는 줄인 비율만큼 덜 불린다.
    # 원래 크기에서 굵게 한 다음 줄인 것과 같은 모양이라, 0.6 배로 좁아진 ⑧ ⓐ 의 속공간이 덜 막힌다.
    grows = {}
    symbols = set()
    for cp in ksx1001_symbols(bcmap):
        if cp in dcmap:
            tf, k = one_cell.place(dcmap[cp])
            sources[cp] = (dglyphs[dcmap[cp]], tf, cell, dcmap[cp])
            grows[cp] = (ex * k, ey * k)
            symbols.add(cp)
    for cp, (tf, grow) in fit_cell(dglyphs, dcmap, bglyphs, bcmap, grid.shear, ex).items():
        sources[cp] = (dglyphs[dcmap[cp]], tf, cell, dcmap[cp])
        grows[cp] = (grow, ey)
    return sources, grows, symbols, skipped


def add_donor_glyphs(merge, weight, sources, grows, symbols, max_err, skipped):
    """sources 를 TrueType 글리프로 옮기고 굵기를 바꿔 base 에 넣는다."""
    reshaped, partly, kept = 0, [], []
    for cp in sorted(sources):
        drawing, tf, advance, dname = sources[cp]

        try:
            glyph = outline(drawing, tf, max_err)
        except Exception as exc:
            print(f"  skip U+{cp:04X} {dname}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        gname = merge.unique_name(dname)
        gx, gy = grows.get(cp, (weight.ex, weight.ey))

        # 깎을 때는 한글·가나 등, 불릴 때는 1칸 기호만 모양을 지키며 굵기를 바꾼다. 한글은 불리면
        # ㅃ ㄳ 처럼 가까운 획이 붙는 게 자연스럽지만, 줄여 넣은 ⑫ 의 숫자가 원에 붙으면 읽을 수 없다.
        # 1칸 기호는 0.6 배로 줄여 넣어 획이 이미 Light 라틴보다 가늘다(① 의 원 33). 한글만큼
        # 깎으면 Thin 에서 원이 7 로 거의 사라져서 깎지 않는다.
        if weight.thinner:
            reshape = cp not in symbols
        else:
            reshape = bool(weight.offsets) and cp in symbols
        if glyph.numberOfContours and reshape:
            changed, step = reweigh(glyph, gx, gy)
            if changed is None:
                kept.append(chr(cp))
            else:
                glyph = changed
                reshaped += 1
                if step < 1:
                    partly.append(chr(cp))
        elif weight.offsets and glyph.numberOfContours:
            # 원본 외곽선은 cmap 에 걸지 않는 글리프로 두고, 그것을 여러 번 겹쳐
            # 부르는 composite 를 실제 글자로 쓴다. 점을 복사하지 않아 용량이 거의 안 는다.
            src = gname + ".src"
            merge.taken.add(src)
            merge.put(src, glyph, advance)
            glyph = make_composite(src, embolden_ring(gx, gy))
        merge.put(gname, glyph, advance)
        merge.added[cp] = gname

    print(f"  한글 등 {len(merge.added)}자 추가, {skipped}자 건너뜀")
    if weight.thinner or weight.offsets:
        verb = "깎음" if weight.thinner else "불림(1칸 기호)"
        print(f"  모양을 지키며 {verb}: {reshaped}자"
              + (f", 덜 바꿈: {''.join(partly)}" if partly else "")
              + (f", 그대로 둠: {''.join(kept)}" if kept else ""))


def merge_overlaps(merge, weight, grows):
    """불린 글자의 겹친 composite 를 외곽선 하나로 합친다.

    겹쳐 놓은 composite 를 그대로 두면 macOS CoreText 가 겹친 가장자리마다
    안티앨리어싱을 따로 해서 획이 번져 보인다(FreeType 은 멀쩡하다).
    그래서 합집합을 구해 외곽선 하나로 만든다. 믿을 수 없는 글자만 겹친 채 둔다.
    """
    glyf, hmtx = merge.glyf, merge.hmtx
    merged, failed = 0, []
    for cp, name in merge.added.items():
        if not glyf[name].isComposite():
            continue
        src = name + ".src"
        one = merge_copies(glyf[src], embolden_ring(*grows.get(cp, (weight.ex, weight.ey))))
        if one is None:
            failed.append(chr(cp))
            continue
        glyf.glyphs[name] = one
        one.recalcBounds(glyf)
        hmtx.metrics[name] = (hmtx[name][0], one.xMin)
        merged += 1
    used = {c.glyphName for n in merge.added.values()
            if glyf[n].isComposite() for c in glyf[n].components}
    for name in merge.added.values():
        src = name + ".src"
        if src in glyf.glyphs and src not in used:
            del glyf.glyphs[src]
            del hmtx.metrics[src]
            merge.order.remove(src)
    print(f"  외곽선 합침: {merged}자" + (f", 겹친 채 둠: {' '.join(failed)}" if failed else ""))


def add_widened(merge, wide):
    """터미널이 2칸으로 세는 base 글자를 2칸 가운데로 옮겨 부른다. 원래 글리프는 그대로 둔다."""
    bcmap = merge.base.getBestCmap()
    for cp in WIDEN:
        if cp not in bcmap:
            continue
        src = bcmap[cp]
        gname = src + ".wide"
        merge.taken.add(gname)
        merge.put(gname, make_composite(src, [((wide - merge.hmtx[src][0]) // 2, 0)]), wide)
        merge.added[cp] = gname


def add_base_aliases(merge):
    """base 에 같은 글자가 있으면 RIDIBatang 에서 가져오지 않고 base 글리프를 그대로 건다."""
    bcmap = merge.base.getBestCmap()
    for cp, src in BASE_ALIASES.items():
        if cp not in bcmap and src in bcmap:
            merge.added[cp] = bcmap[src]


def build_font(args):
    """build.py 의 명령줄 인자대로 base 와 donor 를 합쳐 args.out 에 저장한다."""
    base = TTFont(args.base)
    donor = TTFont(args.donor)
    grid = Grid(base, donor, args)
    weight = Weight(args.embolden, args.embolden_y)
    print(f"base upem={grid.upem} cell={grid.cell} wide={grid.wide} | donor upem={grid.donor_upem} "
          f"| scale={grid.scale:.4f} shear={grid.shear:.4f} embolden={weight.ex:g}/{weight.ey:g}")

    merge = Merge(base)
    sources, grows, symbols, skipped = donor_sources(donor, base, grid, weight)
    add_donor_glyphs(merge, weight, sources, grows, symbols, grid.max_err, skipped)
    if weight.offsets:
        merge_overlaps(merge, weight, grows)
    add_widened(merge, grid.wide)
    add_base_aliases(merge)
    add_nfd_jamo(merge, grid.wide)
    merge.finish()

    add_nfd_substitutions(base)
    mark_combining(base, merge.added)
    set_os2(base)
    set_names(base, donor, args)

    base.save(args.out)
    print(f"  저장: {args.out}")
