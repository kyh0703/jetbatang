#!/usr/bin/env bash
# 재료를 내려받아 JetBatang NF 16 종을 fonts/ 에 만든다.
set -euo pipefail
cd "$(dirname "$0")"

NERD_VERSION="${NERD_VERSION:-v3.5.1}"
NERD_FAMILY="${NERD_FAMILY:-JetBrainsMono}"
BASE_PREFIX="${BASE_PREFIX:-JetBrainsMonoNerdFontMono}"
RIDI_URL="https://ridicorp.com/wp-content/themes/ridicorp/css/font/RIDIBatang.otf"
FAMILY="${FAMILY:-JetBatang NF}"
# 글꼴 정보에 찍히는 릴리스 버전. 릴리스 태그(vX.Y.Z)와 같은 값을 매번 넘긴다. 기본값을 두면
# 다음 릴리스에서 올리는 걸 잊어도 빌드가 돌아서, 다른 글꼴이 같은 버전으로 나간다.
VERSION="${VERSION:-}"
[ -n "$VERSION" ] || { echo "VERSION 을 지정하세요. 예: VERSION=1.5.0 ./build.sh"; exit 1; }
SCALE="${SCALE:-1.00}"
YSHIFT="${YSHIFT:-60}"
EMBOLDEN_SCALE="${EMBOLDEN_SCALE:-1.0}"
# 굵기마다 따로 도는 build.py 를 동시에 몇 개까지 돌릴지. 하나에 메모리를 350MB 안팎 쓴다.
JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

# 파일 접미사 : 타이포그래픽 스타일 : 한글 굵기 증가량
#
# RIDIBatang 은 세로획 82 짜리 한 굵기뿐이다. Regular 를 기준으로 삼고, 한글 세로획이
# 같은 굵기 라틴 세로획의 0.91 배(Regular 의 82 : 90)쯤 되게 한글 가로 굵기를 불리거나
# 깎는다(음수). 세로는 불릴 때 그 0.4 배, 깎을 때 0.8 배다.
#   라틴 세로획: Thin 50 / ExtraLight 66 / Light 79 / Regular 90
#                Medium 99 / SemiBold 108 / Bold 125 / ExtraBold 150
VARIANTS=(
  "Thin:Thin:-36"
  "ThinItalic:Thin Italic:-36"
  "ExtraLight:ExtraLight:-22"
  "ExtraLightItalic:ExtraLight Italic:-22"
  "Light:Light:-10"
  "LightItalic:Light Italic:-10"
  "Regular:Regular:0"
  "Italic:Italic:0"
  "Medium:Medium:9"
  "MediumItalic:Medium Italic:9"
  "SemiBold:SemiBold:18"
  "SemiBoldItalic:SemiBold Italic:18"
  "Bold:Bold:36"
  "BoldItalic:Bold Italic:36"
  "ExtraBold:ExtraBold:56"
  "ExtraBoldItalic:ExtraBold Italic:56"
)

command -v curl >/dev/null || { echo "curl 이 필요합니다"; exit 1; }
command -v unzip >/dev/null || { echo "unzip 이 필요합니다"; exit 1; }
python3 -c "import fontTools, pathops" 2>/dev/null || { echo "pip install fonttools skia-pathops 먼저 하세요"; exit 1; }
# 원본을 내려받기 전에 버전부터 확인한다. 규칙은 build.py 와 같은 함수 하나로 본다.
python3 -c 'import sys, build
try:
    build.font_revision(sys.argv[1])
except ValueError as exc:
    sys.exit(str(exc))' "$VERSION"

mkdir -p build fonts

if [ ! -f build/RIDIBatang.otf ]; then
  echo "==> RIDIBatang 내려받는 중"
  curl -sSL -o build/RIDIBatang.otf "$RIDI_URL"
fi

if [ ! -f "build/$BASE_PREFIX-Regular.ttf" ]; then
  echo "==> Nerd Font $NERD_FAMILY $NERD_VERSION 내려받는 중"
  curl -sSL -o "build/$NERD_FAMILY.zip" \
    "https://github.com/ryanoasis/nerd-fonts/releases/download/$NERD_VERSION/$NERD_FAMILY.zip"
  unzip -oq "build/$NERD_FAMILY.zip" -d build "$BASE_PREFIX-*.ttf"
fi

# 한 종을 만들고 로그를 한 번에 찍는다. 동시에 도는 다른 종의 로그와 줄이 섞이지 않게 한다.
build_one() {
  local suffix="${1%%:*}" rest="${1#*:}"
  local style="${rest%%:*}" embolden="${rest##*:}"
  embolden=$(python3 -c "print(round($embolden * $EMBOLDEN_SCALE, 2))")

  local args=(--embolden "$embolden")
  case "$suffix" in *Italic) args+=(--shear-from-base);; esac

  local log
  if log=$(python3 build.py \
      --base "build/$BASE_PREFIX-$suffix.ttf" \
      --donor build/RIDIBatang.otf \
      --out "fonts/JetBatangNF-$suffix.ttf" \
      --family "$FAMILY" --style "$style" --font-version "$VERSION" \
      --scale "$SCALE" --yshift "$YSHIFT" "${args[@]}" 2>&1); then
    printf '==> %s\n%s\n' "$suffix" "$log"
  else
    printf '==> %s 실패\n%s\n' "$suffix" "$log" >&2
    return 1
  fi
}
export -f build_one
export BASE_PREFIX FAMILY VERSION SCALE YSHIFT EMBOLDEN_SCALE

echo "==> 합치는 중 (version=$VERSION, scale=$SCALE, yshift=$YSHIFT, embolden×$EMBOLDEN_SCALE, jobs=$JOBS)"
printf '%s\n' "${VARIANTS[@]}" | xargs -P "$JOBS" -I{} bash -c 'build_one "$1"' _ {} ||
  { echo "빌드에 실패한 굵기가 있어요. 위 로그를 확인하세요"; exit 1; }

echo
echo "완료. fonts/ 를 확인하세요."
ls -la fonts/
