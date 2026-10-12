#!/bin/bash
# 在 Google Cloud Shell 貼一行執行：
#   bash <(curl -s https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/bake_ortho_cloudshell.sh)
# 抓航照（市區 z16＋全島 z14），拼好後放到 Google Cloud 儲存空間，再由 GitHub Actions 搬進網站。
# 中途斷線可重跑，已抓的圖磚會跳過。不需要任何權杖。
set -e
mkdir -p ~/ortho-bake && cd ~/ortho-bake
echo "▸ 準備環境"
python3 -c "import PIL" 2>/dev/null || pip3 install --user -q pillow
curl -s -o bake_ortho.py https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/bake_ortho.py
echo "▸ 開始抓航照（請不要關掉這個分頁，約 40 分鐘）"
python3 bake_ortho.py
echo
echo "▸ 上傳到 Google Cloud 儲存空間"
gcloud storage rm -r -q gs://intel-vault-510704-vault/bake/ortho 2>/dev/null || true
gcloud storage cp -r out/3d/ortho gs://intel-vault-510704-vault/bake/
echo "✓ 完成。回到對話跟 Claude 說「好了」。"
