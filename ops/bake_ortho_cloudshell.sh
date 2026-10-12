#!/bin/bash
# 在 Google Cloud Shell 貼一行執行：
#   bash <(curl -s https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/bake_ortho_cloudshell.sh)
# 抓五都航照（約 9,500 張圖磚，10–20 分鐘），拼好後推上 GitHub。中途斷線可重跑，已抓的會跳過。
set -e
mkdir -p ~/ortho-bake && cd ~/ortho-bake
echo "▸ 準備環境"
python3 -c "import PIL" 2>/dev/null || pip3 install --user -q pillow
curl -s -o bake_ortho.py https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/bake_ortho.py
echo "▸ 開始抓航照（請不要關掉這個分頁）"
python3 bake_ortho.py
echo
echo "▸ 推上 GitHub"
echo "  請貼上 GitHub 權杖（只給 intel-terminal 的 Contents 讀寫、1 天到期）。貼上時畫面不會顯示，貼完按 Enter："
read -rs TOKEN < /dev/tty
echo
rm -rf repo
git clone -q --depth 1 --filter=blob:none --sparse "https://x-access-token:${TOKEN}@github.com/v1endetta/intel-terminal.git" repo
cd repo
git sparse-checkout set 3d/ortho ops
mkdir -p 3d/ortho && cp -r ../out/3d/ortho/* 3d/ortho/
git -c user.name=v1endetta -c user.email=a0978952611@gmail.com add 3d/ortho
git -c user.name=v1endetta -c user.email=a0978952611@gmail.com commit -qm "3D: pre-baked NLSC orthophoto chunks for city views (taken from Cloud Shell)"
git push -q origin HEAD:main
cd .. && rm -rf repo
unset TOKEN
echo "✓ 完成。可以回到對話跟 Claude 說「推好了」。權杖用完可以直接到 GitHub 刪掉。"
