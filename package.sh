#!/usr/bin/env bash
# fonts/ 의 빌드 결과로 Releases 에 올릴 자산을 dist/ 에 만든다.
# JetBatangNF-all.zip 에는 글꼴과 Windows 설치 스크립트를 한 폴더에 담는다. 풀자마자 스크립트를
# 돌릴 수 있게 하려는 것이다. 몇 종만 받는 사람을 위해 install-windows.ps1 도 따로 둔다.
set -euo pipefail
cd "$(dirname "$0")"

command -v zip >/dev/null || { echo "zip 이 필요합니다"; exit 1; }
fonts=(fonts/JetBatangNF-*.ttf)
[ -e "${fonts[0]}" ] || { echo "fonts/ 에 글꼴이 없어요. ./build.sh 를 먼저 돌리세요"; exit 1; }

rm -rf dist
mkdir -p dist
cp "${fonts[@]}" install-windows.ps1 dist/
zip -qj dist/JetBatangNF-all.zip "${fonts[@]}" install-windows.ps1 LICENSE

echo "dist/ 에 만들었어요. 모두 Releases 에 올리세요."
ls -la dist/
