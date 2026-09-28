# dalta 情報站

個人用的彭博式情報終端機。一個靜態頁面（GitHub Pages）＋一支 Python 抓取腳本（GitHub Actions 每 15 分鐘跑一次，把結果 commit 回 repo）。

## 結構

```
main 分支（程式碼，改動才觸發 Pages 部署）
  fetch.py               抓取腳本；每個來源獨立失敗、失敗保留舊值
  index.html             終端機頁面，從 data 分支的 raw 網址讀 all.json
  .github/workflows/fetch.yml   長跑迴圈：每 5／15 分鐘抓一次並 commit 到 data 分支

data 分支（資料，每次抓取一個 commit；超過 2000 個 commit 自動壓平重來）
  data/all.json          所有面板最新值
  data/history.json      各指標日序列（走勢圖），最多 400 點
  data/panels/<id>.json  各面板單檔；macro.json 為手動維護（在 data 分支上改）
```

## 面板與來源

| 面板 | 來源 | 金鑰 |
|---|---|---|
| taiex、tw_stocks | 證交所 OpenAPI | 無 |
| fx | 臺灣銀行牌告 CSV | 無 |
| poly | Polymarket Gamma API | 無 |
| tech | GitHub Search、Hugging Face Hub、Hacker News | 無 |
| trends | Google Trends RSS（TW） | 無 |
| luxury、commodities | Yahoo Finance chart API；原物料備援 FRED | FRED_API_KEY（選填） |
| revenue | FinMind 月營收；備援證交所／櫃買 OpenAPI | FINMIND_TOKEN（選填，免費額度較高） |
| media | WWD RSS、Bing News RSS（BoF、台灣時尚媒體） | 無 |
| reddit | Reddit API | REDDIT_CLIENT_ID／SECRET（雲端 IP 沒金鑰幾乎會被擋） |
| lyst | Lyst Index 季報頁 | 無 |
| macro | 手動維護 `data/panels/macro.json`；腳本會嘗試主計總處 SDMX | 無 |

金鑰放在 repo 的 Settings → Secrets and variables → Actions。

## 手動觸發

Actions → fetch → Run workflow。
