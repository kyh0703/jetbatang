#!/usr/bin/env bash
# fonts/ 의 빌드 결과로 Releases 에 올릴 자산을 dist/ 에 만든다.
# JetBatangNF-all.zip 에는 글꼴과 Windows 설치 스크립트를 한 폴더에 담는다. 풀자마자 스크립트를
# 돌릴 수 있게 하려는 것이다. 몇 종만 받는 사람을 위해 install-windows.ps1 도 따로 둔다.
# fonts/ 가 지금 코드로 열여섯 종을 끝까지 빌드한 그대로일 때만 만든다. 예전 코드로 만들었거나
# 일부만 다시 만든 글꼴이 릴리스로 나가지 않게, build.sh 가 남긴 기록과 맞춰 본다.
set -euo pipefail
cd "$(dirname "$0")"

command -v zip >/dev/null || { echo "zip 이 필요합니다"; exit 1; }
command -v python3 >/dev/null || { echo "python3 이 필요합니다"; exit 1; }
# 첫 줄은 버전, 나머지는 기록에 있는 글꼴 파일 이름이다. jetbatang/release.py 는 표준 라이브러리만 쓴다.
# 빌드할 때 깔려 있던 라이브러리가 requirements.txt 와 달랐으면 알린다. 막지는 않는다.
checked=$(python3 -c 'import sys
from jetbatang.release import built_library_warnings, verify_manifest
try:
    info = verify_manifest(".")
except ValueError as exc:
    sys.exit(str(exc))
for line in built_library_warnings(".", info["libraries"]):
    print(line, file=sys.stderr)
print(info["version"], *info["fonts"], sep="\n")')
version=${checked%%$'\n'*}
fonts=()
while IFS= read -r name; do fonts+=("fonts/$name"); done <<< "${checked#*$'\n'}"

rm -rf dist
mkdir -p dist
cp "${fonts[@]}" install-windows.ps1 dist/
zip -qj dist/JetBatangNF-all.zip "${fonts[@]}" install-windows.ps1 LICENSE
# 받은 사람이 sha256sum -c SHA256SUMS 로 확인할 수 있게 dist/ 의 파일마다 해시를 적는다.
python3 -c 'import pathlib
from jetbatang.release import sha256_file
dist = pathlib.Path("dist")
lines = [f"{sha256_file(path)}  {path.name}\n" for path in sorted(dist.iterdir())]
(dist / "SHA256SUMS").write_text("".join(lines))'

echo "dist/ 에 $version 자산을 만들었어요. 모두 Releases 에 올리세요."
ls -la dist/
