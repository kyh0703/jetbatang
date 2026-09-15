#!/usr/bin/env bash
# 재료를 내려받아 JetBatang NF 16 종을 fonts/ 에 만든다.
set -euo pipefail
cd "$(dirname "$0")"

NERD_VERSION="${NERD_VERSION:-v3.5.1}"
NERD_FAMILY="${NERD_FAMILY:-JetBrainsMono}"
BASE_PREFIX="${BASE_PREFIX:-JetBrainsMonoNerdFontMono}"
RIDI_URL="https://ridicorp.com/wp-content/themes/ridicorp/css/font/RIDIBatang.otf"
FAMILY="${FAMILY:-JetBatang NF}"
SCALE="${SCALE:-1.00}"
YSHIFT="${YSHIFT:-60}"
EMBOLDEN_SCALE="${EMBOLDEN_SCALE:-1.0}"

# 파일 접미사 : 타이포그래픽 스타일 : 한글 굵기 증가량
#
# RIDIBatang 은 세로획 80 짜리 한 굵기뿐이다. Regular 를 기준으로 삼고,
# 라틴 세로획 비율만큼 한글을 불린다. Regular 보다 가는 쪽은 불릴 수 없어 0 이다.
#   라틴 세로획: Thin 50 / ExtraLight 66 / Light 79 / Regular 90
#                Medium 99 / SemiBold 108 / Bold 125 / ExtraBold 150
VARIANTS=(
  "Thin:Thin:0"
  "ThinItalic:Thin Italic:0"
  "ExtraLight:ExtraLight:0"
  "ExtraLightItalic:ExtraLight Italic:0"
  "Light:Light:0"
  "LightItalic:Light Italic:0"
  "Regular:Regular:0"
  "Italic:Italic:0"
  "Medium:Medium:8"
  "MediumItalic:Medium Italic:8"
  "SemiBold:SemiBold:16"
  "SemiBoldItalic:SemiBold Italic:16"
  "Bold:Bold:32"
  "BoldItalic:Bold Italic:32"
  "ExtraBold:ExtraBold:52"
  "ExtraBoldItalic:ExtraBold Italic:52"
)

command -v curl >/dev/null || { echo "curl 이 필요합니다"; exit 1; }
command -v unzip >/dev/null || { echo "unzip 이 필요합니다"; exit 1; }
python3 -c "import fontTools" 2>/dev/null || { echo "pip install fonttools 먼저 하세요"; exit 1; }

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

echo "==> 합치는 중 (scale=$SCALE, yshift=$YSHIFT, embolden×$EMBOLDEN_SCALE)"
for v in "${VARIANTS[@]}"; do
  suffix="${v%%:*}"; rest="${v#*:}"
  style="${rest%%:*}"; embolden="${rest##*:}"
  embolden=$(python3 -c "print(round($embolden * $EMBOLDEN_SCALE, 2))")

  args=(--embolden "$embolden")
  case "$suffix" in *Italic) args+=(--shear-from-base);; esac

  python3 build.py \
    --base "build/$BASE_PREFIX-$suffix.ttf" \
    --donor build/RIDIBatang.otf \
    --out "fonts/JetBatangNF-$suffix.ttf" \
    --family "$FAMILY" --style "$style" \
    --scale "$SCALE" --yshift "$YSHIFT" "${args[@]}"
done

echo
echo "완료. fonts/ 를 확인하세요."
ls -la fonts/
