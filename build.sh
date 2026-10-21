#!/usr/bin/env bash
# 베이스 글꼴을 내려받아 sources/ 의 RIDIBatang 과 합쳐 JetBatang NF 를 만든다. 접미사를 고르면
# build/preview-fonts/ 에만 만든다.
set -euo pipefail
cd "$(dirname "$0")"

# 빌드 값과 그 기본값. 환경 변수로 바꿀 수 있다. 릴리스는 기본값으로 만든다. 기본값과 다른 값은
# 빌드 기록에 남아 package.sh 가 알린다.
DEFAULTS=(
  "NERD_VERSION=v3.5.1"
  "NERD_FAMILY=JetBrainsMono"
  "BASE_PREFIX=JetBrainsMonoNerdFontMono"
  "FAMILY=JetBatang NF"
  "SCALE=1.00"
  "YSHIFT=60"
  "EMBOLDEN_SCALE=1.0"
)
custom=()
for setting in "${DEFAULTS[@]}"; do
  name=${setting%%=*} default=${setting#*=}
  if [ -z "${!name:-}" ]; then
    printf -v "$name" '%s' "$default"
  elif [ "${!name}" != "$default" ]; then
    custom+=("$name=${!name}")
  fi
done
# 기본 Nerd Font 판의 zip 해시. 받은 파일이 이 값과 다르면 멈춘다. 새 판으로 올릴 때는 NERD_VERSION 기본값,
# NERD_PINNED, 이 해시를 함께 고친다. 다른 판이나 가족을 고르면 그 릴리스의 SHA-256.txt 로 본다.
NERD_PINNED="v3.5.1/JetBrainsMono.zip"
NERD_PINNED_SHA256="fab782a66f7d3019da64f6572db9fc5d3a4bcb19f9fa13e2d8a62e3693d6396e"
# 글꼴 정보에 찍히는 릴리스 버전. 릴리스 태그(vX.Y.Z)와 같은 값을 매번 넘긴다. 기본값을 두면
# 다음 릴리스에서 올리는 걸 잊어도 빌드가 돌아서, 다른 글꼴이 같은 버전으로 나간다.
VERSION="${VERSION:-}"
[ -n "$VERSION" ] || { echo "VERSION 을 지정하세요. 예: VERSION=1.8.0 ./build.sh"; exit 1; }
# 굵기마다 따로 도는 build.py 를 동시에 몇 개까지 돌릴지. 하나에 메모리를 350MB 안팎 쓴다.
JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

command -v curl >/dev/null || { echo "curl 이 필요합니다"; exit 1; }
command -v unzip >/dev/null || { echo "unzip 이 필요합니다"; exit 1; }
python3 -c "import fontTools, pathops" 2>/dev/null || { echo "pip install -r requirements.txt 먼저 하세요"; exit 1; }
# requirements.txt 와 다른 판이 깔려 있으면 알린다. 같은 글꼴이 나오지 않을 수 있지만, 쓰던 환경으로
# 빌드하는 것을 막지는 않는다. 깔린 판은 빌드 기록에도 남아 package.sh 가 다시 알린다.
python3 -c 'from jetbatang.release import library_warnings
for line in library_warnings("."):
    print(line)' >&2
# 베이스 글꼴을 내려받기 전에 버전부터 확인한다. 규칙은 build.py 가 쓰는 jetbatang/metadata.py 의 함수 하나로 본다.
python3 -c 'import sys
from jetbatang.metadata import font_revision
try:
    font_revision(sys.argv[1])
except ValueError as exc:
    sys.exit(str(exc))' "$VERSION"
# 빌드 값도 베이스 글꼴을 내려받기 전에 본다. 틀린 값이면 열여섯 종이 모두 같은 오류로 실패한다.
python3 -c 'import math, sys
for name, value in zip(sys.argv[1::2], sys.argv[2::2]):
    try:
        ok = math.isfinite(float(value))
    except ValueError:
        ok = False
    if not ok:
        sys.exit(f"{name} 는 숫자여야 해요: {value!r}")' \
  SCALE "$SCALE" YSHIFT "$YSHIFT" EMBOLDEN_SCALE "$EMBOLDEN_SCALE"
case "$JOBS" in
  ''|*[!0-9]*) echo "JOBS 는 0 이상의 정수여야 해요: '$JOBS'"; exit 1;;
esac

# 모든 작업과 빌드 기록이 같은 고정 시각을 쓴다. 잘못된 값이면 다운로드 전에 멈춘다.
SOURCE_DATE_EPOCH=$(python3 -c 'import sys
from jetbatang.release import source_date_epoch
try:
    print(source_date_epoch("."))
except ValueError as exc:
    sys.exit(str(exc))')
export SOURCE_DATE_EPOCH

# 코드·원본 해시와 라이브러리 판은 코드에서 무엇이든 읽기 전에 잡아 둔다. 아래 VARIANTS 처럼 여기서 읽어 둔 값도
# 글꼴을 바꾸므로, 그 뒤에 코드나 원본이 바뀌면 끝날 때 견주어 기록하지 않는다.
started=$(python3 -c 'import json, sys
from jetbatang.release import snapshot
try:
    print(json.dumps(snapshot(".")))
except OSError as exc:
    sys.exit(f"빌드에 쓰는 파일을 읽을 수 없어요: {exc}")')

# 파일 접미사 : 타이포그래픽 스타일 : 한글 굵기 증가량. 목록과 값은 jetbatang/release.py 의 VARIANTS 에 있다.
variants=$(python3 -c 'from jetbatang.release import VARIANTS
for variant in VARIANTS:
    print(*variant, sep=":")')
VARIANTS=()
while IFS= read -r variant; do VARIANTS+=("$variant"); done <<< "$variants"
# RIDIBatang 은 내려받지 않고 저장소에 둔 원본을 쓴다. 이 파일도 위에서 잡은 해시에 들어 있다.
DONOR=$(python3 -c 'from jetbatang.release import DONOR; print(DONOR)')
# 새 판으로 바꿔 넣다 웹 페이지나 TrueType 판이 들어가면, 베이스 글꼴을 받은 뒤 열여섯 종이 모두 같은 오류로
# 실패하거나 외곽선 방향이 뒤집힌 채 나온다. jetbatang/outlines.py 가 CFF 외곽선을 가정하므로 받기 전에 본다.
python3 -c 'import sys
from fontTools.ttLib import TTFont, TTLibError
try:
    cff = "CFF " in TTFont(sys.argv[1], lazy=True)
except (OSError, TTLibError) as exc:
    sys.exit(f"{sys.argv[1]} 를 글꼴로 읽을 수 없어요: {exc}")
if not cff:
    sys.exit(f"{sys.argv[1]} 가 CFF 외곽선 OpenType 이 아니에요. RIDIBatang 공식 OTF 를 넣으세요")' "$DONOR"

# 모르는 접미사는 재료나 출력 파일을 건드리기 전에 거절한다.
for suffix in "$@"; do
  known=false
  for variant in "${VARIANTS[@]}"; do
    if [ "$suffix" = "${variant%%:*}" ]; then known=true; break; fi
  done
  if ! "$known"; then
    printf '알 수 없는 글꼴 접미사: %s\n' "$suffix" >&2
    printf '사용 가능한 접미사:' >&2
    printf ' %s' "${VARIANTS[@]%%:*}" >&2
    printf '\n' >&2
    exit 1
  fi
done
# 요청 순서·중복과 관계없이 VARIANTS 순서를 지킨다.
SELECTED=()
for variant in "${VARIANTS[@]}"; do
  if [ "$#" -eq 0 ]; then
    SELECTED+=("$variant")
  else
    for suffix in "$@"; do
      if [ "$suffix" = "${variant%%:*}" ]; then SELECTED+=("$variant"); break; fi
    done
  fi
done
if [ "$#" -eq 0 ]; then
  OUT_DIR="${OUT_DIR:-fonts}"
else
  OUT_DIR="${OUT_DIR:-build/preview-fonts}"
fi
mkdir -p -- build "$OUT_DIR"

sha256() {
  python3 -c 'import sys; from jetbatang.release import sha256_file; print(sha256_file(sys.argv[1]))' "$1"
}

# url 을 dest 에 받는다. dest 가 이미 있고 SHA-256 이 맞으면 그대로 쓴다. 받는 동안에는
# dest.part 에 쓰고 해시가 맞을 때만 dest 로 옮긴다. 그래서 dest 는 언제나 끝까지 받아 확인한
# 파일이다. HTTP 오류 페이지나 받다 끊긴 파일이 재료 자리에 남아 다음 빌드까지 깨뜨리지 않는다.
fetch() {
  local label=$1 url=$2 dest=$3 want=$4 got
  if [ -f "$dest" ]; then
    [ "$(sha256 "$dest")" = "$want" ] && return 0
    echo "==> $dest 가 고정한 해시와 달라서 다시 받아요"
  fi
  echo "==> $label 내려받는 중"
  if ! curl -fsSL --retry 3 -o "$dest.part" "$url"; then
    rm -f "$dest.part"
    echo "내려받지 못했어요: $url" >&2
    exit 1
  fi
  got=$(sha256 "$dest.part")
  if [ "$got" != "$want" ]; then
    rm -f "$dest.part"
    printf '받은 파일의 SHA-256 이 고정한 값과 달라요: %s\n  고정: %s\n  받음: %s\n' "$url" "$want" "$got" >&2
    exit 1
  fi
  mv "$dest.part" "$dest"
}

# 풀어 둔 베이스 글꼴이 어느 판의 어느 zip(SHA-256) 에서 나왔는지 build/$BASE_PREFIX.source 에 적는다.
# 파일 이름에는 판이 없어서, 이 기록 없이는 NERD_VERSION 을 바꿔도 예전 베이스로 빌드된다. 기본 판은
# 해시까지 보아서 NERD_PINNED_SHA256 을 고치면 다시 푼다. 다른 판은 해시를 알려면 내려받아야 해서 판만 본다.
nerd_source="$NERD_VERSION/$NERD_FAMILY.zip"
nerd_stamp="build/$BASE_PREFIX.source"

base_ready() {
  local variant stamp
  [ -f "$nerd_stamp" ] || return 1
  stamp=$(cat "$nerd_stamp")
  if [ "$nerd_source" = "$NERD_PINNED" ]; then
    [ "$stamp" = "$NERD_PINNED $NERD_PINNED_SHA256" ] || return 1
  else
    [ "${stamp%% *}" = "$nerd_source" ] || return 1
  fi
  for variant in "${VARIANTS[@]}"; do
    [ -f "build/$BASE_PREFIX-${variant%%:*}.ttf" ] || return 1
  done
}

if ! base_ready; then
  nerd_url="https://github.com/ryanoasis/nerd-fonts/releases/download/$NERD_VERSION"
  if [ "$nerd_source" = "$NERD_PINNED" ]; then
    nerd_sha256=$NERD_PINNED_SHA256
  else
    nerd_sha256=$(curl -fsSL --retry 3 "$nerd_url/SHA-256.txt" |
      awk -v name="$NERD_FAMILY.zip" '$2 == name { print $1 }') || nerd_sha256=
    [ -n "$nerd_sha256" ] ||
      { echo "$nerd_url/SHA-256.txt 에서 $NERD_FAMILY.zip 의 해시를 찾지 못했어요" >&2; exit 1; }
  fi
  nerd_zip="build/$NERD_FAMILY-$NERD_VERSION.zip"
  fetch "Nerd Font $NERD_FAMILY $NERD_VERSION" "$nerd_url/$NERD_FAMILY.zip" "$nerd_zip" "$nerd_sha256"

  # 따로 풀어서 16 종이 모두 있을 때만 build/ 로 옮기고, 마지막에 기록을 남긴다.
  rm -f "$nerd_stamp"
  rm -rf build/nerd.part
  unzip -oq "$nerd_zip" -d build/nerd.part "$BASE_PREFIX-*.ttf" ||
    { rm -rf build/nerd.part; echo "$nerd_zip 에서 $BASE_PREFIX-*.ttf 를 풀지 못했어요" >&2; exit 1; }
  for variant in "${VARIANTS[@]}"; do
    [ -f "build/nerd.part/$BASE_PREFIX-${variant%%:*}.ttf" ] ||
      { rm -rf build/nerd.part; echo "$nerd_zip 에 $BASE_PREFIX-${variant%%:*}.ttf 가 없어요" >&2; exit 1; }
  done
  mv build/nerd.part/*.ttf build/
  rm -rf build/nerd.part
  echo "$nerd_source $nerd_sha256" > "$nerd_stamp"
fi

# 한 종을 만들고 로그를 한 번에 찍는다. 동시에 도는 다른 종의 로그와 줄이 섞이지 않게 한다.
build_one() {
  local suffix="${1%%:*}" rest="${1#*:}"
  local style="${rest%%:*}" embolden="${rest##*:}"
  embolden=$(python3 -c 'import sys; print(round(float(sys.argv[1]) * float(sys.argv[2]), 2))' \
    "$embolden" "$EMBOLDEN_SCALE")

  local args=(--embolden="$embolden")
  case "$suffix" in *Italic) args+=(--shear-from-base);; esac

  local log
  # 값은 --옵션=값 꼴로 넘긴다. 띄어 넘기면 argparse 가 -1e1 같은 음수를 옵션으로 읽는다.
  if log=$(python3 build.py \
      --base="build/$BASE_PREFIX-$suffix.ttf" \
      --donor="$DONOR" \
      --out="$OUT_DIR/JetBatangNF-$suffix.ttf" \
      --family="$FAMILY" --style="$style" --font-version="$VERSION" \
      --scale="$SCALE" --yshift="$YSHIFT" "${args[@]}" 2>&1); then
    printf '==> %s\n%s\n' "$suffix" "$log"
  else
    printf '==> %s 실패\n%s\n' "$suffix" "$log" >&2
    return 1
  fi
}
export -f build_one
export BASE_PREFIX DONOR FAMILY VERSION SCALE YSHIFT EMBOLDEN_SCALE OUT_DIR

# 빌드가 도중에 멈추면 예전 기록이 새 파일과 섞여 남지 않게 먼저 지운다.
python3 -c 'import pathlib, sys; from jetbatang.release import MANIFEST
pathlib.Path(sys.argv[1], MANIFEST).unlink(missing_ok=True)' "$OUT_DIR"
echo "==> 합치는 중 (version=$VERSION, scale=$SCALE, yshift=$YSHIFT, embolden×$EMBOLDEN_SCALE, jobs=$JOBS, out=$OUT_DIR)"
printf '%s\n' "${SELECTED[@]}" | xargs -P "$JOBS" -I{} bash -c 'build_one "$1"' _ {} ||
  { echo "빌드에 실패한 굵기가 있어요. 위 로그를 확인하세요"; exit 1; }
# 열여섯 종을 이번에 모두 만든 경우에만 완전한 빌드 기록을 남긴다.
if [ "${#SELECTED[@]}" -eq "${#VARIANTS[@]}" ]; then
  python3 -c 'import json, sys
from jetbatang.release import write_manifest
try:
    write_manifest(".", sys.argv[1], json.loads(sys.argv[2]), sys.argv[4:], fonts_dir=sys.argv[3])
except ValueError as exc:
    sys.exit(str(exc))' "$VERSION" "$started" "$OUT_DIR" ${custom[@]+"${custom[@]}"}
fi

echo
echo "완료. $OUT_DIR/ 를 확인하세요."
ls -la -- "$OUT_DIR/"
