#!/usr/bin/env bash
# 릴리스 한 번을 처음부터 끝까지 한다. 열여섯 종을 빌드해 회귀 검사를 모두 통과하면 package.sh 로 자산을
# 만들고, vX.Y.Z 태그를 올린 뒤 그 자산을 붙여 초안 릴리스를 만든다. 노트를 쓰고 공개하는 일은 사람이 한다.
#   VERSION=1.8.0 ./release.sh
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${VERSION:-}"
[ -n "$VERSION" ] || { echo "VERSION 을 지정하세요. 예: VERSION=1.8.0 ./release.sh"; exit 1; }
export TAG="v$VERSION"
export OUT_DIR="${OUT_DIR:-fonts}"
command -v gh >/dev/null || { echo "gh 가 필요합니다"; exit 1; }

# 빌드에 십 분 넘게 걸리니, 릴리스로 내보내면 안 되는 상태는 그 전에 모두 본다.
# 라이브러리 판이 다르면 같은 코드로도 글꼴이 달라진다. build.sh 는 경고만 하지만 릴리스는 막는다.
python3 -c 'import sys
from jetbatang.release import library_warnings
lines = library_warnings(".")
sys.exit("\n".join(lines + ["그래서 릴리스를 멈춰요"]) if lines else None)'
[ -z "$(git status --porcelain)" ] ||
  { echo "커밋하지 않은 고침이나 새 파일이 있어요. 릴리스는 커밋한 코드로만 만들어요"; git status --short; exit 1; }
git fetch -q --tags origin
git merge-base --is-ancestor HEAD origin/main ||
  { echo "릴리스할 커밋이 origin/main 에 없어요. 먼저 main 에 올리세요"; exit 1; }
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  [ "$(git rev-parse "$TAG^{commit}")" = "$(git rev-parse HEAD)" ] ||
    { echo "$TAG 태그가 이미 다른 커밋($(git rev-parse --short "$TAG^{commit}"))에 있어요"; exit 1; }
fi
# 초안까지 본다. 다시 돌렸을 때 초안이 두 벌 생기거나 공개한 릴리스를 건드리지 않게 한다.
found=$(gh api 'repos/{owner}/{repo}/releases' --paginate --jq '.[] | select(.tag_name == env.TAG) | .html_url')
[ -z "$found" ] || { echo "$TAG 릴리스가 이미 있어요(초안 포함). 지운 뒤 다시 돌리세요: $found"; exit 1; }

VERSION="$VERSION" ./build.sh
# 기본값과 다른 빌드 값을 환경에 남겨 둔 채 빌드했으면 package.sh 는 경고만 하지만 릴리스는 막는다.
python3 -c 'import os, sys
from jetbatang.release import built_library_warnings, custom_build_warnings, verify_manifest
info = verify_manifest(".", fonts_dir=os.environ["OUT_DIR"])
lines = built_library_warnings(".", info["libraries"]) + custom_build_warnings(info)
sys.exit("\n".join(lines + ["그래서 릴리스를 멈춰요"]) if lines else None)'
JETBATANG_FONTS="$OUT_DIR" python3 -m unittest discover tests
./package.sh

# 태그는 검사를 다 통과한 뒤에만 올린다. 중간에 실패하면 고친 커밋에 같은 태그를 붙여 다시 돌리면 된다.
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || git tag -a "$TAG" -m "JetBatang NF $TAG"
git push -q origin "$TAG"
gh release create "$TAG" dist/* --draft --verify-tag --title "JetBatang NF $TAG" --generate-notes
echo "초안 릴리스를 만들었어요. 릴리스 노트를 쓰고 공개하세요"
