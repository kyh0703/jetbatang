#!/usr/bin/env bash
# 재료를 내려받아 JetBatang NF 네 굵기를 fonts/ 에 만든다.
set -euo pipefail
cd "$(dirname "$0")"

NERD_VERSION="${NERD_VERSION:-v3.5.1}"
NERD_FAMILY="${NERD_FAMILY:-JetBrainsMono}"
BASE_PREFIX="${BASE_PREFIX:-JetBrainsMonoNerdFontMono}"
RIDI_URL="https://ridicorp.com/wp-content/themes/ridicorp/css/font/RIDIBatang.otf"
FAMILY="${FAMILY:-JetBatang NF}"
SCALE="${SCALE:-1.00}"
YSHIFT="${YSHIFT:-60}"

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

build_one() {   # $1=파일 접미사  $2=스타일 이름  $3...=추가 인자
  local suffix="$1" style="$2"; shift 2
  python3 build.py \
    --base "build/$BASE_PREFIX-$suffix.ttf" \
    --donor build/RIDIBatang.otf \
    --out "fonts/JetBatangNF-$suffix.ttf" \
    --family "$FAMILY" --style "$style" --scale "$SCALE" --yshift "$YSHIFT" "$@"
}

echo "==> 합치는 중 (scale=$SCALE, yshift=$YSHIFT)"
build_one Regular    "Regular"
build_one Bold       "Bold"
build_one Italic     "Italic"      --shear-from-base
build_one BoldItalic "Bold Italic" --shear-from-base

echo
echo "완료. fonts/ 를 확인하세요."
ls -la fonts/
