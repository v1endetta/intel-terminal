# dalta 情報站：交接文件

> 給接手的 Claude：這份是完整交接，開工前從頭讀一次。
> - 這個 repo 是**公開**的：不要寫進任何客戶名、私人資料、金鑰值。
> - 私人背景（決策紀錄、客戶雷達位置、排程）在 Vin 的記憶檔 `/areas/personal-intel-terminal.md`，不在這裡。
> - 最後更新：2026-10-30。

---

## 1. 這是什麼

Vin 的個人情報站。網址 https://intel.daltatw.com：首頁是 3D 台灣捲動劇本，終端機在 `/terminal/`。

- **用途**：個人、非商業。看懂市場往哪走、找資訊缺口、做預測。不是用來接案，也不要以 dalta 的客戶為出發點設計面板或判讀。
- **Owner**：Vin 拍板所有改動。網站是公開的，但定位仍是 Vin 自己用。
- **形式**：彭博終端式，全部資料源在同一處。每項資訊都要「看圖很快懂在講什麼」（長條、趨勢線、圓餅，取代大段文字）。

---

## 2. 鐵則（違反任何一條都要先停下來問）

| # | 規則 |
|---|---|
| 1 | **零花費**。Vin 不接受任何被扣款的可能。只用免費來源與免費額度；GCP 只在免費層內（有預算警示與超額自動斷電），不要加任何會計費的服務。 |
| 2 | **金鑰只放 GitHub Actions Secrets**，絕不印出金鑰值。探測輸出要遮罩。workflow 每輪會掃資料，資料裡出現任何 secret 值就整輪丟棄。 |
| 3 | **絕不連 Gmail**。任何自動化都不能讓別人有機會讀到 Vin 的信（他信箱有 McKinsey 等電子報，也不接）。 |
| 4 | **客戶雷達是私人的**。客戶名永遠不進這個公開 repo。 |
| 5 | **授權受限的數值**（ICE、FBX、DRAMeXchange 等）只顯示百分位或變化，不顯示原始值。 |
| 6 | 公開站不能出現 Vin 的身體、訓練等個人資料。 |
| 7 | **改程式前先逐項回報發現與方案，等 Vin 核准才動手**（「動手改程式前，先逐項回報…我核准後才開始改」）。核准後可以直接改、推、驗證。 |
| 8 | 被網站擋（Dcard 擋 GitHub IP、Threads 要登入等）就不接，**不要繞過**；不要建議 TDX。 |
| 9 | 省 Claude 額度：排程與自動化不要依賴 Vin 即時按確認；重活放 GitHub Actions，不放 Claude 排程。 |
| 10 | 用語：繁體中文、台灣用語。**漲是綠色、跌是紅色**（不用台灣紅漲綠跌）。品牌名 **dalta 一律小寫**。比較性資訊用 Markdown 表格加 emoji（✅🎯⚠️）。 |

---

## 3. 架構

```
GitHub repo v1endetta/intel-terminal（public）
├─ main 分支：程式碼。改動後 GitHub Pages 自動部署（CNAME → intel.daltatw.com）
└─ data 分支：資料。每輪抓取一個 commit；超過 2000 commit 自動壓平

GitHub Actions
├─ fetch.yml：長跑迴圈。cron 每小時 :07 補位；一條 run 跑約 5 小時，結束前自己 dispatch 下一條
│    每輪：同步 data 分支 → 同步 main 最新程式碼（改 fetch.py 下一輪就生效）→ python fetch.py（硬上限 900 秒）
│    間隔：平日台北 09–14、21–05 每 5 分鐘，其他時段每 15 分鐘
│    用 Workload Identity 換 GCP 暫時憑證（不存金鑰），寫入歷史資料庫
├─ weekly.yml：每天 08:40 UTC 跑 weekly.py（Gemini 寫「本週市場往哪走」，週一才真的重寫）
├─ city.yml：每週日跑 city.py（「住哪裡」各鄉鎮生活條件評分 → data/city_scores.json）
└─ pull-ortho.yml：手動，把 Cloud Shell 預烤的航照從 bucket 拉回 3d/

Google Cloud（專案 intel-vault-510704，免費層）
├─ Cloud Storage bucket intel-vault-510704-vault：每輪有變的面板整份存 raw/dt=YYYY-MM-DD/*.ndjson.gz
├─ BigQuery 外部表 intel.snapshots：終端機「資料庫」分頁用 Vin 的 Google 登入（OAuth）直接查
└─ Cloud Run job tw-relay（asia-east1 彰化，台灣 IP，每 15 分鐘）：抓 GitHub 抓不到的台灣來源
     （國道與省道即時路況、eTag、YouBike、主計總處等官方統計）→ 存 bucket → fetch.py 讀
     ops/tw_relay.py 每次執行從 GitHub 讀最新版，改了不用重新部署

Claude 端（不在 repo）：情報站晨間判讀排程、客戶雷達私人 artifact、提醒，見記憶檔
```

---

## 4. 檔案地圖

| 路徑 | 內容 |
|---|---|
| `fetch.py` | 抓取主程式，約 13,500 行、126 個 `run()`。每個來源獨立失敗，失敗沿用舊值 |
| `weekly.py` | 每週走向（只載入 fetch.py 第一個 `run(` 之前的函式） |
| `city.py` | 住哪裡評分 |
| `index.html` | **正式 3D 首頁**（由 `lab/g/index.html` 改標題而來，不要手改） |
| `lab/g/index.html` | 3D 首頁測試版（建置產物，不要手改） |
| `lab/g/src/` | **3D 首頁原始碼**（JS 模組、CSS、patch 腳本、`build.py`） |
| `lab/_src.html` | 3D 底層模板（地形、相機、標籤）；`build.py` 在上面套用模組與 patch |
| `lab/tools/` | 截圖測試工具：`setup.sh`、`flx.mjs`、`elshot.mjs` |
| `terminal/index.html` | 終端機（單檔，約 3,500 行） |
| `classic/` | 舊版首頁（保留） |
| `3d/` | 地形、材質、建築、航照等預烤素材 |
| `ops/` | 預烤腳本（`bake_*.py`、Cloud Shell 用）、台灣抓取站 `tw_relay.py`、設定檔：`themes.json` 主題鏈、`wiki_topics.json`、`voice_keywords.json`、`polls.json` |
| `tw_counties.json`、`tw_towns.json` | 縣市、鄉鎮邊界 |
| data 分支 `data/all.json` | 所有面板最新值（`panels.<id>`） |
| data 分支 `data/history.json` | 各指標日序列（走勢圖、預測帳本、論點用），每序列最多約 400 點 |
| data 分支 `data/panels/<id>.json` | 各面板單檔；`macro.json` 可手動維護 |
| data 分支 `data/archive/YYYY-MM-DD.json` | 每日存檔：頭條、熱詞、PTT、OSS 等 |
| data 分支 其他 `data/*.json` | 各面板的快取與中間序列，例如 `consume_series.json`、`polls_cache.json`、`geocode_cache.json` |

`README.md` 已經過時，以這份為準。

---

## 5. fetch.py 怎麼運作

**一輪的流程**
1. 載入上一輪結果與 `history.json`。
2. 依序跑 `run(pid, fn, keep_if_fresh_hours, cheap)`，清單在檔案最後約第 13,017 行起。
3. 寫 `all.json`、`history.json`、`timings.json`。
4. 每日存檔 `archive_day()`。
5. 推 GCP `vault_push()`。
6. Slack 通知 `notify()`。

**`run()` 的規則**
- `keep_if_fresh_hours`：上次成功距今未滿這個時數就跳過、沿用舊值。月或日資料靠它省請求。
- 失敗退避：上次失敗後，在「更新週期或 1 小時，取小者」內不重試。
- `SOFT_DEADLINE` = 開始後 660 秒。超過就只跑 `cheap=True` 的面板（只吃本輪結果、不打外部 API），其他沿用上一輪。
- 單一面板有時間上限 `PANEL_CAP`（預設 240 秒），超過當失敗。
- 結果寫 `RESULTS[pid]` 與 `data/panels/<pid>.json`，自動加 `updatedAt`；失敗會留 `error`。
- **順序有意義**：後面的面板會讀前面的結果，例如 `mapfeed`、`chain`、`twsectors`、`theses`、`ledger` 都吃本輪其他面板，所以放最後。新面板若重要，放前面避免被時限略過。
- 想強制重抓：在 run 行的 `keep_if_fresh_hours` 加條件，例如 `24 if "新欄位" in json.dumps(load_prev(pid) or {}) else 0`。

**常用工具函式**

| 函式 | 用途 |
|---|---|
| `get`、`gjson` | requests 包裝 |
| `_yahoo_get` | Yahoo Finance |
| `_gnews(q, limit)` | Google News RSS |
| `_gemini_json(prompt, lite_first, max_models)` | Gemini 免費層；JSON 輸出，多模型輪替 |
| `hist_put(group, key, date, value)`、`hist_get` | 寫入或讀取 `history.json` |
| `load_prev(pid)` | 讀上一輪結果 |
| `safe_err(e)` | 錯誤訊息去敏 |
| `write_json` | 拒寫 NaN |
| `_ym_shift` | 年月 YYYYMM 位移 |
| `_counties_in(text)` | 文字裡的縣市。注意「新北市」「竹北市」含「北市」，已用 `_cty_txt()` 處理 |
| `TW_COUNTIES`、`TW_AREAS`、`TOWNS`、`_TOWN_BY_NAME` | 22 縣市與鄉鎮對照 |

`html` 模組匯入成 `html_mod`。

**被擋的網站**：`curl_cffi` 加 `impersonate="chrome"`（例如 Mobile01）。

**金鑰（只列名稱，都在 Actions Secrets）**

| 用在哪 | Secrets |
|---|---|
| `fetch.yml` | `FRED_API_KEY`、`FINMIND_TOKEN`、`CWA_API_KEY`、`GUARDIAN_API_KEY`、`YOUTUBE_API_KEY`、`GEMINI_API_KEY`、`CONGRESS_API_KEY`、`SEC_CONTACT`、`SLACK_WEBHOOK_URL`、`GOOGLE_CSE_KEY`、`GOOGLE_CSE_CX`（CSE 已不收新客戶，形同無用）、`REDDIT_*`（建不了 app，未用） |
| `city.yml` | `MOENV_API_KEY` |

### 探測新來源的做法（不動正式資料）

1. 暫時加 `.github/workflows/probe.yml` 與 `ops/probe.py`。
2. `probe.py` 執行 fetch.py 到 `\nrun("pulse", p_pulse)\n` 之前，`INTEL_DATA_DIR` 設成暫存資料夾，只呼叫要測的函式。
3. 輸出 push 到 `probe-out` 分支來看。
4. 用完把這兩個檔刪掉。

本機容器的網路有白名單，大多數網站連不到，所以探測都走 Actions。

### Slack 通知（`notify()`，同一事件只推一次）

1. 地震規模 5.5 以上、3 小時內
2. 停班停課
3. 颱風警報
4. 台海：共機超過 30 天均值 2 倍且至少 20 架次，或國防部宣布演習
5. 海纜受損新聞
6. 台股收盤漲跌超過 3%
7. 景氣燈號換色
8. 供電橙燈以上
9. 信用利差快速擴大（只給百分位）
10. 風暴逼近主要貨櫃港
11. 美國政策點名台灣，或 BIS 涉及半導體與實體清單
12. 企業壓力：減班連兩期增加，或退票比率創 12 個月新高
13. dalta 領先指標確認轉折
14. 主論點的推翻條件觸發

---

## 6. 面板清單（依終端機分頁）

終端機分頁：總覽、市場、總經、走向、訊號、輿情、台灣現場、資料庫。面板 id 與分頁對照在 `terminal/index.html` 的 `TAB_OF`。
3D 首頁的分類：市場、總經、走向、訊號、輿情、現場。每類有一排 chips。

| 分頁 | 面板（run key → 終端機 id） |
|---|---|
| 總覽 | `theses` 論點追蹤 · `insights`／`insights_cat` 洞見（Gemini） · 摘要 brief |
| 市場 | `pulse` 5 分鐘線 · `taiex` · `tw_market` · `taifex` · `fx` · `world` · `usbig` · `fear` 恐慌結構 · `sectors` **美股板塊** · `commodities`（p-cmdty，含海運） · `logistics` 全球物流 · `luxury`（p-lux） · `tw_stocks` · `revenue` · `mops` |
| 總經 | `aicycle` AI 循環 · `champions` 台灣隱形冠軍 · `twsectors` 台灣內需產業 · `dlead` dalta 領先指標 · `credit` 信用利差 · `exports` 出口結構 · `stress` 企業壓力 · `calendar`／`mktcal` · `liquidity`（p-liq） · `macro` · `gmacro` · `supply` · `consume` · `cards` · `lead` · `imports` · `housefc` · `house` · `demo` · `bizlife` · `cars` · `permits` · `renewal` 都更 · `prices` 物價細項 · `tourism` · `poly` · `veg`／`fruit`／`fish`／`meat` |
| 走向 | `weekly`（weekly.py） · `chain` 主題鏈 · `ledger` 預測帳本 · `voice` 趨勢雷達 · `wiki` · `tech2` · `gap` 台灣還沒報 · `migration` · `births` · 地圖工具（圈地報告、住哪裡） |
| 訊號 | `news`＋watch 關注領域 · `tenders`／`awards`／`tendermap` · `design` · `radar` 公司雷達 · `brands`／`taxreg` 新品牌 · `uspolicy` · `ossuse` · `clinics` · `aesthetic` 醫美 · `grants` · `crowd` · `aiwire` · `devpulse` · `tech` · `oss` · `lyst` · `media` · `think` · `jobs` · `corp` · `policy` · `ipr` · `secwords` |
| 輿情 | `pop` · `appstore` App 排行 · `gtop` 焦點新聞 · `worldnews` · `townnews` 鄉鎮新聞 · `youtube` · `attention` · `mood` 台灣情緒（Gemini 判讀 PTT、Cofacts、Mobile01、Bluesky） · `cofacts` · `polls` 民調 · `forums` Mobile01 · `ptt` · `social` Bluesky · `trends` |
| 台灣現場 | `geo`＋`mapfeed` 全台現場地圖 · `elect` 五都選戰 · `tw_pulse` · `roads` · `metro` · `weather`／`radar_wx`／`lightning`／`typhoon` · `alerts`（含停班停課） · `localnews` · `quake` · `power` · `airport`／`flights` · `plaact` 台海 · `cables` 海纜 · `pressure` 氣壓圖 · `cctv`（四都） · `oil` |
| 資料庫 | BigQuery：授權、全文搜尋、時光機、走勢（`vault_push` 寫入） |

其他系統用的 run key：`villages`、`geocode`、`relay_stats`、`etfholders`、`attention`、`culture`（3D 地圖藝文點位）、`wiki`、`jobtowns`、`chain`。

**命名陷阱**：`sectors` 是美股板塊。台灣內需產業是 `twsectors`／`p_tw_sectors`／`p-twsectors`／`P.twsectors`，以前撞名蓋掉過一次。

---

## 7. 終端機（`terminal/index.html`）

- 從 `raw.githubusercontent.com/v1endetta/intel-terminal/data/data/all.json` 讀資料，定時重抓。
- 版面：每個分頁是「先導讀結論、再分段」。`GUIDE` 物件是各分頁的導讀分段；面板屬哪個分頁看 `TAB_OF`。
- **新增面板要做的事**：
  1. 寫 `<section class="panel" id="p-xxx">` 與 renderer。
  2. 加進 `TAB_OF`、`GUIDE` 對應分段。
  3. 加進 `lab/tools/elshot.mjs` 的 `TAB` 對照，才能截圖。
- 有全站搜尋，以及網址記住畫面（deeplink）。
- 縣市卡 `countyCard()`、各地現況 `countyNow()` 吃 `alerts`、`localnews`、`culture`、`weather.countyRain`、`house`。
- **使用紀錄**（6 週修剪用）：只存在瀏覽器 localStorage。報告在 `/terminal/#usage`，可「複製全部」。3D 首頁也有，在 `lab/g/src/usage.js`。

---

## 8. 3D 首頁（`lab/g/src/`）

**建置與上線**
```bash
python3 lab/g/src/build.py lab/g/src        # → lab/g/src/index.html（已 gitignore）
# 語法檢查：抽出最大的 <script type="module"> 用 node --check
cp lab/g/src/index.html lab/g/index.html    # 測試版
python3 - <<'EOF'                            # 正式版：換標題寫到根目錄
s=open('lab/g/index.html').read().replace('<title>台灣此刻 · 劇本版（測試）</title>\n<meta name="robots" content="noindex">','<title>台灣此刻 · dalta 情報站</title>')
open('index.html','w').write(s)
EOF
```

**組裝方式**
- `build.py` 讀 `lab/_src.html` 模板，把 `story.css` 塞進 `<style>`。
- 依序串接這些 JS：`story_head` · `story_body` · `intro` · `flights` · `mkcal` · `press` · `wnews` · `gx` · `earth` · `nav` · `cam` · `glass` · `tb` · `click` · `mobile` · `grants` · `prices` · `tourism` · `gtop` · `lens2` · `insights` · `seas` · `area` · `city` · `money` · `viz` · `usage` · `deeplink`。
- 最後依序 exec 這些 `*_patch.py`：fx、ortho、perf、adapt、facade、light、life、mem、landmark、nav、info、mobile、glass、refresh。

**主要模組**

| 檔案 | 內容 |
|---|---|
| `story_body.js` | 分類與 chips 定義、`PROV` 資料出處表、`ST`（`ST.redrawCard`、`ST.allChips`、`ST.curCat`、`__story.openAt(cat, name)`） |
| `viz.js` | 卡片圖表：weeklyCard、moodViz、newsViz、gapViz、worldViz、pttCard、cofactsCard、grantsViz、uspViz、pollsCard、champCard、sectorsCard 等 |
| `money.js` | 論點追蹤卡 thesesCard、thSL()、thesesSum() |
| `gx.js` | 地球模式的原物料，價格與單位 GX_UNIT |
| `insights.js` | 首頁 hero 的洞見與論點按鈕 |
| `refresh_patch.py` | 資料更新時重畫開著的卡片（**這個行為還沒實測**） |
| `story.css` | 樣式，`#side .vz*` 是卡片圖表 |

改了 `lab/g/src` 一定要重建、截圖驗證，再同步到 `lab/g/index.html` 與根目錄 `index.html`。

---

## 9. 測試與截圖

```bash
bash lab/tools/setup.sh build      # 建 lab/.work：假網站、data 分支資料、three.js（約 70 MB，gitignore）
# 3D：STEPS 用分號串步驟；wait|ms、js|程式、shot|名稱（全畫面）、el|名稱（只截 #side 卡片）、chip|文字、seg|分類
RI=999999 STEPS="wait|15000;js|(__story.openAt('總經','內需產業'),1);wait|4000;el|twsectors" node lab/tools/flx.mjs t 1440 900
# 手機：寬度給 390；截圖存在 lab/.work/<prefix>_<名稱>.png
# 終端機：node lab/tools/elshot.mjs 1280 p-theses p-twsectors → lab/.work/el_<id>.png
```

**注意**
- 開場動畫約 10 秒，`wait` 少於 15 秒時開卡片會被開場蓋住。
- chips 要先切到分類才看得到。開卡片用 `__story.openAt`，不要模擬點 chip。
- `el` 截很長的卡片會變黑，`#side` 的 maxHeight 先限在 2200px。
- 想用假資料測：直接改 `lab/.work/raw/all.json`。
- Chromium 已預裝在 `/opt/pw-browsers/chromium`，**不要**執行 `playwright install`。

---

## 10. 論點追蹤與預測帳本

**論點追蹤（`p_theses`）**
- `THESES`：18 條，每條 (id, 層級, 區域, 標題, 主張, 推翻條件)。
  - 主論點：t1 AI 資本支出到 2027 上半年不收手、t3 信用風險從最弱一端累積、t2 非 AI 經濟偏弱、t6 民間消費降級、t13 台股跑在實體經濟前面。
  - 觀察：t5、t10、t12、g1、t9。
  - 保留：t4、t7、t8、t11、t14、t15、g2、g3。
- 每條有：
  - 證據列 `E(...)`，正反方向
  - 推翻條件 kill
  - 量尺 gauge `GG(now, kill, ...)`
  - 狀態：ok 成立中／mixed 分歧／weak 轉弱／kill 觸發／pending 資料不足
  - 升降層提示與季度檢討
- `THESES_PRED`：每條一個可驗證預測（指標、方向、門檻、到期日、機率），進 `p_ledger` 的 `thesis` 規則。
- `THESES_REV`：預測改版代號，目前 `r2`。改了指標、方向或固定門檻時要升版，帳本會重寫還沒到期的那筆。
- 外部歷史：`_th_yq` 讀 Yahoo 週線（快取 6 小時）；`_th_jgb` 讀日本財務省 10 年債 CSV。

**預測帳本（`p_ledger`）**
- `LEDGER_RULES` 共 19 條：wiki_up／down／abroad、cards_hot、lead_up／down、veg_revert、elect_fav、house_mom、house_vol、mort_rate、biz_net、chain_gap／hot、credit_wide、bounce_hi、furlough_up、dlead_turn、thesis。
- 每條有歷史回測命中率 `bt_rate`。回測低於 55% 的規則要打折看；`house_vol` 約 41%，不能拿來推論房價。

**目前讀數（10/23）**
- 主論點 4 條成立中、1 條分歧。
- 非電子出口 +18.9%，已過 t2 的門檻；要連 2 個月，且新公司轉正才算。
- G2 轉弱：中國非機電出口 +20%。
- G1：日本 10 年債 2.95%，3 個月 +0.2。
- 隱形冠軍指數 +7.5%，8 類裡 6 類成長。
- 營建 +30%，但建照 −36%。

---

## 11. 待辦與已知問題（2026-10-30）

| 狀態 | 項目 |
|---|---|
| ⏳ 待驗證 | 鄉鎮新聞（10/30 再修）：擋簡體字標題與來源（`TOWN_SIMP`），排除詞加路竹會、台電區處、新豐洲、三大園區。下一輪確認這幾類不再出現。已知漏網：標題沒寫縣市的跨縣市同名地標（台東「大溪－多良」被算成桃園大溪），發生率低，先不處理 |
| ⏳ 待驗證 | App 排行 `appstore`（10/31 上線）：排名歷史存在 data 分支 `data/appstore_hist.json`（每天一筆、留 40 天，含各類別個數）。11/7 之後 7 天爬升才準，確認爬升與類別變化合理。下一步可能做「消費者有感」交叉面板（說 vs 買四格），等 Vin 看幾週資料再決定 |
| ⏳ 待驗證 | 3D 卡片隨資料更新重畫（`refresh_patch.py`）還沒實測 |
| ✅ 已驗證 | 停班停課 22 縣市全部抓到（每個地區第一列少一格的問題）；雨量沒下雨的縣市記 0 |
| ✅ 已驗證 | 藝文活動：新北市不再被算成臺北市（10/30 新北市 18、臺北市 61） |
| 🎯 等 Vin 決定 | Lyst 時尚熱度：10/13 起 GitHub 被 Cloudflare 擋（探測 403 challenge，curl_cffi 也擋），面板停在 Q2 2026。照鐵則不繞過；要停用面板，還是保留舊值 |
| 🎯 等 Vin 決定 | 新增論點「營建 2027–28 轉弱」到觀察層（營建營收 +30%、建照 −36%） |
| 🎯 等 Vin 決定 | 回測：品牌庫存 → 運動鞋優先，再來韓國 20 天出口、美國新屋開工 |
| 🎯 等 Vin 決定 | Threads 官方 API（要 Vin 自己申請；之前拍板不接） |
| 📅 11/9 | 看非電子出口是否連 2 個月 >10%（t2 主論點） |
| 📅 11/28 | 6 週使用紀錄滿：請 Vin 從電腦與手機的 `#usage` 複製報告，整理建議砍、併、留的面板與 3D chips，等他拍板，**不要直接砍** |
| ⚠️ 已知 | 美股板塊 `sectors` 曾因撞名出過一次錯，已自癒；再出現就看 error 退避 |
| ⚠️ 已知 | Dcard 擋、嘖嘖擋（10/30 探測：GitHub IP 全站 Cloudflare challenge，連 robots.txt 都 403）、Threads 無免費管道、Custom Search 不收新客戶、Gemini grounding 免費層無額度：都不要再試。集資雷達 `crowd` 維持看新聞＋Kickstarter |
| ⚠️ 已知 | 10/31 探測消費者商品層級來源：App Store 台灣（免費、付費、營收榜）✅ 可讀；PChome 搜尋 API ✅ 可讀但只能按關鍵字查、沒有銷量數字；博客來（Cloudflare 403）、momo 排行榜（403）❌ 擋，不接 |
| ⚠️ 已知 | 鄉鎮新聞：嘉義市、新竹市的新聞本來就少寫區名，數量少是正常的；只寫縣市名的新聞放在各縣市新聞 `localnews` |

---

## 12. Git 慣例

- 在 main 直接 commit，再 `git pull -q --rebase --autostash && git push -q`。
- data 分支由機器人寫；手動改 `macro.json` 要在 data 分支上改。
- commit 訊息用中文寫清楚改了什麼、為什麼。
- 這是公開 repo：commit 前確認沒有客戶名、金鑰、私人資料。
