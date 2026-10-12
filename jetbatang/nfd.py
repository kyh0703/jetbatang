"""NFD 로 나뉜 한글 자모와 가나를 완성형 글리프로 조합한다."""
import unicodedata

from fontTools.otlLib.builder import buildLigatureSubstSubtable, buildLookup
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables

from .outlines import make_composite


def add_nfd_substitutions(font):
    """기존 라틴 GSUB 를 보존하면서 NFD 자모·가나를 같은 NFC 글리프로 조합한다."""
    cmap = font.getBestCmap()
    groups = [{} for _ in range(19)]
    for cp in range(0xAC00, 0xD7A4):
        if cp not in cmap:
            continue
        components = tuple(ord(ch) for ch in unicodedata.normalize("NFD", chr(cp)))
        if not all(component in cmap for component in components):
            continue
        group = groups[(cp - 0xAC00) // 588]
        group[tuple(cmap[component] for component in components)] = cmap[cp]
        if len(components) == 3:
            # NFC 의 LV 음절 뒤에 NFD 받침이 붙은 경우도 같은 LVT 음절로 조합한다.
            lv = cp - (cp - 0xAC00) % 28
            if lv in cmap:
                group[(cmap[lv], cmap[components[-1]])] = cmap[cp]
    kana = {}
    for cp in range(0x3041, 0x3100):
        components = tuple(ord(ch) for ch in unicodedata.normalize("NFD", chr(cp)))
        if (cp in cmap and len(components) == 2 and components[-1] in (0x3099, 0x309A)
                and all(component in cmap for component in components)):
            kana[tuple(cmap[component] for component in components)] = cmap[cp]
    subtables = [buildLigatureSubstSubtable(group) for group in (*groups, kana) if group]
    if not subtables:
        return

    if "GSUB" not in font:
        font["GSUB"] = newTable("GSUB")
        gsub = font["GSUB"].table = otTables.GSUB()
        gsub.Version = 0x00010000
        gsub.ScriptList = otTables.ScriptList()
        gsub.ScriptList.ScriptRecord = []
        gsub.FeatureList = otTables.FeatureList()
        gsub.FeatureList.FeatureRecord = []
        gsub.LookupList = otTables.LookupList()
        gsub.LookupList.Lookup = []
    gsub = font["GSUB"].table
    lookup_index = len(gsub.LookupList.Lookup)
    # 전체가 64 KiB 를 넘어도 각 하위 테이블에는 32비트 오프셋으로 접근한다.
    gsub.LookupList.Lookup.append(buildLookup(subtables, table="GSUB", extension=True))
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    features = gsub.FeatureList.FeatureRecord
    ccmp = [i for i, record in enumerate(features) if record.FeatureTag == "ccmp"]
    if not ccmp:
        index = next((i for i, record in enumerate(features) if record.FeatureTag > "ccmp"), len(features))
        record = otTables.FeatureRecord()
        record.FeatureTag = "ccmp"
        record.Feature = otTables.Feature()
        record.Feature.FeatureParams = None
        record.Feature.LookupListIndex = []
        features.insert(index, record)
        # FeatureRecord 는 태그 순서여야 하므로 삽입 뒤 기존 스크립트의 인덱스만 옮긴다.
        for script_record in gsub.ScriptList.ScriptRecord:
            script = script_record.Script
            languages = [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]
            for language in languages:
                if language is None:
                    continue
                language.FeatureIndex = [i + (i >= index) for i in language.FeatureIndex]
                if language.ReqFeatureIndex != 0xFFFF and language.ReqFeatureIndex >= index:
                    language.ReqFeatureIndex += 1
        variations = getattr(gsub, "FeatureVariations", None)
        if variations is not None:
            for variation in variations.FeatureVariationRecord:
                for substitution in variation.FeatureTableSubstitution.SubstitutionRecord:
                    if substitution.FeatureIndex >= index:
                        substitution.FeatureIndex += 1
        ccmp = [index]
    for index in ccmp:
        feature = features[index].Feature
        feature.LookupListIndex.append(lookup_index)
        feature.LookupCount = len(feature.LookupListIndex)
    gsub.FeatureList.FeatureCount = len(features)

    scripts = gsub.ScriptList.ScriptRecord
    for tag in ("DFLT", "hang", "kana"):
        record = next((record for record in scripts if record.ScriptTag == tag), None)
        # 없는 스크립트는 기존 DFLT 로 가게 둔다. ccmp 만 든 hang/kana 를 새로 만들면
        # 한글·가나로 시작하는 혼합 문자열에서 원래의 라틴 calt 리거처가 꺼진다.
        if record is None and tag != "DFLT":
            continue
        if record is None:
            record = otTables.ScriptRecord()
            record.ScriptTag = tag
            record.Script = otTables.Script()
            record.Script.LangSysRecord = []
            record.Script.LangSysCount = 0
            record.Script.DefaultLangSys = None
            scripts.append(record)
        script = record.Script
        if script.DefaultLangSys is None:
            script.DefaultLangSys = otTables.LangSys()
            script.DefaultLangSys.LookupOrder = None
            script.DefaultLangSys.ReqFeatureIndex = 0xFFFF
            script.DefaultLangSys.FeatureIndex = []
        for language in [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]:
            if not any(index in language.FeatureIndex for index in ccmp):
                language.FeatureIndex.append(ccmp[0])
            language.FeatureCount = len(language.FeatureIndex)
    scripts.sort(key=lambda record: record.ScriptTag)
    gsub.ScriptList.ScriptCount = len(scripts)


def add_nfd_jamo(merge, wide):
    """NFD 의 초성·중성·종성은 호환 자모의 외곽선을 재사용하되 서로 다른 glyph ID 를 준다.
    같은 ID 를 걸면 ccmp 가 호환 자모 "ㄱㅏ" 까지 "가" 로 조합해 버린다."""
    cmap = merge.base.getBestCmap() | merge.added
    modern_jamo = (*range(0x1100, 0x1113), *range(0x1161, 0x1176), *range(0x11A8, 0x11C3))
    for cp in modern_jamo:
        letter = unicodedata.name(chr(cp)).split(" ", 2)[2]
        compatible = ord(unicodedata.lookup("HANGUL LETTER " + letter))
        if compatible not in cmap:
            continue
        gname = merge.unique_name(f"nfd{cp:04X}")
        leading = cp < 0x1161
        merge.put(gname, make_composite(cmap[compatible], [(0 if leading else -wide, 0)]),
                  wide if leading else 0)
        merge.added[cp] = gname


def mark_combining(base, added):
    """결합 탁점·반탁점을 GDEF 에 결합 기호(3)로 적는다."""
    if "GDEF" in base and base["GDEF"].table.GlyphClassDef is not None:
        for cp in (0x3099, 0x309A):
            base["GDEF"].table.GlyphClassDef.classDefs[added[cp]] = 3
