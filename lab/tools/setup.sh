#!/bin/bash
# 建立本機截圖測試環境 lab/.work（不進 git）：假網站 site/、data 分支資料 raw/、three.js
# 用法：bash lab/tools/setup.sh        之後改完 3D 原始碼：bash lab/tools/setup.sh build
set -e
R=$(cd "$(dirname "$0")/../.." && pwd); W=$R/lab/.work
mkdir -p "$W/site/lab/g" "$W/raw" "$W/npm"
for f in 3d terminal tw_counties.json tw_towns.json; do ln -sfn "$R/$f" "$W/site/$f"; done
cp "$R/index.html" "$W/site/index.html"
if [ "$1" = build ]; then python3 "$R/lab/g/src/build.py" "$R/lab/g/src" && cp "$R/lab/g/src/index.html" "$W/site/lab/g/index.html"
else cp "$R/lab/g/index.html" "$W/site/lab/g/index.html"; fi
# 資料：data 分支最上層的 data/*.json（約 30 MB），網頁從 raw.githubusercontent.com 讀，截圖工具改導到這裡
git -C "$R" fetch -q --depth 1 origin +data:refs/remotes/origin/data
for p in $(git -C "$R" ls-tree --name-only origin/data data/ | grep '\.json$'); do git -C "$R" show "origin/data:$p" > "$W/raw/$(basename "$p")"; done
[ -d "$W/npm/node_modules/three" ] || (cd "$W/npm" && npm init -y >/dev/null && npm i -s three@0.160.0 topojson-client@3 world-atlas@2 >/dev/null)
echo "ready: $W"
