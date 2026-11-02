# dalta 情報站：交接文件

> 給接手的 Claude：這份是完整交接，開工前從頭讀一次。
> - 這個 repo 是**公開**的：不要寫進任何客戶名、私人資料、金鑰值。
> - 私人背景（決策紀錄、客戶雷達位置、排程）在 Vin 的記憶檔 `/areas/personal-intel-terminal.md`，不在這裡。
> - 最後更新：2026-11-02。

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
| 3 | **絕不連 Gmail**。任何自動化都不能讓別人有機會讀到 Vin 的信（他信箱有 McKinsey 等電子報，也不接）。**已知例外（11/3 Vin 知情接受）**：Claude 排程「情報站社群彙總」建立時系統會自動掛上帳號所有連線（含 Gmail），無法移除；它會讀 Threads／Dcard／IG 的陌生人文字。緩解：`ops/social_tw.md` 第 0 節要求網頁文字只當資料、不用其他連線；推送前與 `fetch.py` 讀取時都用 `ops/social_check.py` 只放行「短話題名＋數字」。若要再降風險，改成計數程式只回傳短詞與數字（11/3 提過的 B 方案）。 |
| 4 | **客戶雷達是私人的**。客戶名永遠不進這個公開 repo。 |
| 5 | **授權受限的數值**（ICE、FBX、DRAMeXchange 等）只顯示百分位或變化，不顯示原始值。 |
| 6 | 公開站不能出現 Vin 的身體、訓練等個人資料。 |
| 7 | **改程式前先逐項回報發現與方案，等 Vin 核准才動手**（「動手改程式前，先逐項回報…我核准後才開始改」）。核准後可以直接改、推、驗證。 |
| 8 | 被網站擋（Dcard 擋 GitHub IP、Threads 要登入等）就不接，**不要繞過**；不要建議 TDX。**唯一例外（11/3 Vin 同意）**：IG、Threads、Dcard 可以用 Claude 桌面 app 的內建瀏覽器（登入跟 Vin 的 Chrome 分開）加**副帳號**低量閱讀，一天一次；只存話題與次數，不存原文與帳號名。主帳號與 dalta 帳號不登入內建瀏覽器。 |
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
│    （先寫在 Actions 機器暫存 ops/vault_spool.py，每 3 小時＋迴圈結束時合併上傳；GCS 寫入免費每月 5,000 次）
├─ BigQuery 外部表 intel.snapshots：終端機「資料庫」分頁用 Vin 的 Google 登入（OAuth）直接查
└─ Cloud Run job tw-relay（asia-east1 彰化，台灣 IP，每 15 分鐘；深夜 00–06 只有整點那次做事）：抓 GitHub 抓不到的台灣來源
     （國道與省道即時路況、eTag、YouBike、主計總處等官方統計）→ 存 bucket → fetch.py 讀
     ops/tw_relay.py 每次執行從 GitHub 讀最新版，改了不用重新部署
     即時資料合成一個 relay/latest/live.json.gz（含各檔版本號 idx、這輪秒數與讀寫次數 last）；
     其他檔內容沒變不寫；慢工作依「這小時第幾個 15 分鐘」輪班、每段有時限（見 main()）
     fetch.py 的 relay_get() 讀 live.json.gz，靜態檔照 idx 版本號在 Actions 機器本機快取

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
| `ops/` | 預烤腳本（`bake_*.py`、Cloud Shell 用）、台灣抓取站 `tw_relay.py`、歷史資料庫暫存 `vault_spool.py`、社群每日彙總的做法與計數程式 `social_tw.md`（Claude 排程照這份跑）、設定檔：`themes.json` 主題鏈、`wiki_topics.json`、`voice_keywords.json`、`polls.json` |
| `tw_counties.json`、`tw_towns.json` | 縣市、鄉鎮邊界 |
| data 分支 `data/all.json` | 所有面板最新值（`panels.<id>`） |
| data 分支 `data/history.json` | 各指標日序列（走勢圖、預測帳本、論點用），每序列最多約 400 點 |
| data 分支 `data/panels/<id>.json` | 各面板單檔；`macro.json` 可手動維護 |
| data 分支 `data/archive/YYYY-MM-DD.json` | 每日存檔：頭條、熱詞、PTT、OSS 等 |
| data 分支 其他 `data/*.json` | 各面板的快取與中間序列，例如 `consume_series.json`、`polls_cache.json`、`geocode_cache.json`、`appstore_hist.json`、`ust_cache.json`、`news_kw_cache.json`、`wind_hist.json`（消費風向每日每話題的說／做分數，留 30 天）、`social_tw.json`（Threads／Dcard／IG 探索頁每日彙總，Claude 排程每天 21:52 寫，見 `ops/social_tw.md`）、`relay_usage.json`（抓取站每輪秒數、讀寫次數）、`geo_pending.sha` |

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
15. 美債 10 年單日 ±15 個基點（財政部收盤值）
16. 美債 10 減 2 年、10 減 3 個月轉正或倒掛（翻轉前要連 6 個交易日在另一邊，避免在 0 附近來回洗）

---

## 6. 面板清單（依終端機分頁）

終端機分頁：總覽、市場、總經、走向、訊號、輿情、台灣現場、資料庫。面板 id 與分頁對照在 `terminal/index.html` 的 `TAB_OF`。
3D 首頁的分類：市場、總經、走向、訊號、輿情、現場。每類有一排 chips。

| 分頁 | 面板（run key → 終端機 id） |
|---|---|
| 總覽 | `theses` 論點追蹤 · `insights`／`insights_cat` 洞見（Gemini） · 摘要 brief |
| 市場 | `pulse` 5 分鐘線 · `taiex` · `tw_market` · `taifex` · `fx` · `world` · `usbig` · `ust` 美債殖利率 · `fear` 恐慌結構 · `sectors` **美股板塊** · `commodities`（p-cmdty，含海運） · `logistics` 全球物流 · `luxury`（p-lux） · `tw_stocks` · `revenue` · `mops` |
| 總經 | `aicycle` AI 循環 · `champions` 台灣隱形冠軍 · `twsectors` 台灣內需產業 · `labor` 誰在擴張 · `dlead` dalta 領先指標 · `credit` 信用利差 · `exports` 出口結構 · `stress` 企業壓力 · `calendar`／`mktcal` · `liquidity`（p-liq） · `macro` · `gmacro` · `supply` · `consume` · `cards` · `lead` · `imports` · `housefc` · `house` · `demo` · `bizlife` · `cars` · `permits` · `renewal` 都更 · `prices` 物價細項 · `tourism` · `poly` · `veg`／`fruit`／`fish`／`meat` |
| 走向 | `weekly`（weekly.py） · `chain` 主題鏈 · `ledger` 預測帳本 · `voice` 趨勢雷達 · `wiki` · `tech2` · `gap` 台灣還沒報 · `migration` · `births` · 地圖工具（圈地報告、住哪裡） |
| 訊號 | `news`＋watch 關注領域 · `tenders`／`awards`／`tendermap` · `design` · `radar` 公司雷達 · `brands`／`taxreg` 新品牌 · `uspolicy` · `ossuse` · `clinics` · `aesthetic` 醫美 · `grants` · `crowd` · `aiwire` · `devpulse` · `tech` · `oss` · `lyst` · `media` · `think` · `corp` · `policy` · `ipr` · `secwords` |
| 輿情 | `wind` 消費風向（說 vs 做四格） · `pop` · `appstore` App 排行 · `gtop` 焦點新聞 · `worldnews` · `townnews` 鄉鎮新聞 · `youtube` · `attention` · `mood` 台灣情緒（Gemini 判讀 PTT、Cofacts、Mobile01、Bluesky） · `cofacts` · `polls` 民調 · `forums` Mobile01 · `ptt` · `social` Bluesky · `trends` |
| 台灣現場 | `geo`＋`mapfeed` 全台現場地圖 · `elect` 五都選戰 · `tw_pulse` · `roads` · `metro` · `weather`／`radar_wx`／`lightning`／`typhoon` · `alerts`（含停班停課） · `localnews` · `quake` · `power` · `airport`／`flights` · `plaact` 台海 · `cables` 海纜 · `pressure` 氣壓圖 · `cctv`（四都） · `oil` |
| 資料庫 | BigQuery：授權、全文搜尋、時光機、走勢（`vault_push` 寫入）· `relay_stats` 雲端用量（p-cloud） |

其他系統用的 run key：`villages`、`geocode`、`relay_stats`、`etfholders`、`attention`、`culture`（3D 地圖藝文點位）、`wiki`、`chain`。

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

## 11. 待辦與已知問題（2026-11-02）

| 狀態 | 項目 |
|---|---|
| ⏳ 待驗證 | 鄉鎮新聞（10/30 再修）：擋簡體字標題與來源（`TOWN_SIMP`），排除詞加路竹會、台電區處、新豐洲、三大園區。下一輪確認這幾類不再出現。已知漏網：標題沒寫縣市的跨縣市同名地標（台東「大溪－多良」被算成桃園大溪），發生率低，先不處理 |
| ⏳ 待驗證 | App 排行 `appstore`（10/31 上線）：排名歷史存在 data 分支 `data/appstore_hist.json`（每天一筆、留 40 天，含各類別個數）。11/7 之後 7 天爬升才準，確認爬升與類別變化合理。下一步可能做「消費者有感」交叉面板（說 vs 買四格），等 Vin 看幾週資料再決定 |
| ✅ 已驗證 | 美債殖利率 `ust`（10/31 上線）：財政部名目＋實質曲線 CSV（去年整年快取 `data/ust_cache.json`）、FRED 期限溢酬 THREEFYTP10、Yahoo ^MOVE（ICE 授權，只輸出 5 年百分位）。標售：最近 90 天用 TreasuryDirect（開標當天就有；欄位是 `competitiveAuctionCloseDate`、`indirectBiddersCompetitiveParAwarded`、`subtotalCompetitiveParAwardedInsideOfOfferingAmount`、`inflationProtected`），Fiscal Data 要晚幾天才補，只拿來算前 6 次平均。Slack 第 15、16 條；論點 t3 期限溢酬、t13 實質利率。歷史在 `history.json` 的 `ust` 群組 |
| ✅ 已修（11/2 全站檢查） | 趨勢雷達每輪刪掉設定裡已拿掉的關鍵字序列（舊設定曾含不該公開的詞）；data 分支 11/2 手動壓平清掉舊版本，並加 `.gitignore` 擋 `__pycache__` |
| ✅ 已修（11/2） | 台北房價指數：data.taipei 改成 Big5 編碼，兩種都試；解析失敗沿用舊序列（10/30 曾被蓋成空的） |
| ✅ 已修（11/2） | 台股：MIS 備援改用成交時間 `tlong` 當日期；`p_taiex` 每輪清掉週末與跟前一天完全相同的點（休市日重記） |
| ✅ 已修（11/2） | 關注領域新聞查詢有 1 小時快取 `data/news_kw_cache.json`（每輪最多重抓 14 個）；`ipr` 上限 290 秒；Forex Factory 只留本週檔；金鑰掃描補 `SEC_CONTACT`；手機頁首不再橫向捲動 |
| ✅ 已驗證（11/2） | 經濟部統計處（外銷訂單 `lead`、零售指數 `supply`）對國外機房 Cloudflare 403：`ops/tw_relay.py` 的 `moea_daily` 每天代抓存 `relay/static/moea_orders`、`moea_retail`，`fetch.py` 的 `_moea_text()` 直接抓失敗就讀這份。零售、外銷訂單 11/2 都已恢復（`lead.errs` 空的） |
| ✅ 已拿掉（11/2，Vin 拍板） | 104 職缺：API 自 10/22 起總數一律回 1001，`jobs`／`jobtowns` 抓取、終端機面板、3D 晶片與地圖圖層、縣市卡、圈地報告的職缺列都拿掉；`fetch.py` 開頭會刪掉留下的面板檔與 `history.json` 的 `jobs` 群組。替代評估：1111 只有總數和關鍵字篩選、沒有地區、連續查約 30 次就 403；台灣就業通開放資料只給 1,000 筆不能分頁；518、yes123 沒有總數；Cake 被 Cloudflare 擋。都不接。終端機裡 `renderJobs` 等程式碼沒有資料就不會跑，留著無害 |
| ⚠️ 已知 | AI 廠商動態 `devpulse.diag` 寫「md got html」「0 entries」是正常的：markdown 版失敗後改讀網頁版，Gemini、DeepSeek、xAI 都有抓到 |
| ✅ 已驗證 | 誰在擴張 `labor`（11/2 上線，取代 104）：勞動部統計月報 xlsx（`statdb.mol.gov.tw/html/mon/{表號}.xlsx`，GitHub 讀得到）：26010 勞保投保人數按行業（最近 13 個月）、22120 廠商職位空缺按行業（每季）、24040 積欠工資墊償（月，官方的年增與今年累計年增直接讀表上那兩列）。自寫 `_xlsx_rows()` 讀 xlsx（沒裝 openpyxl）。判讀：投保年增 >1% 且職缺年增 >5% 擴張；職缺年增 >10% 但投保 ≤0.5% 缺工；歷史存 `labor_ins`、`labor_vac`、`labor_arrears`。月報其他可用的表：27010 就業保險按行業、22010～22110 勞動力與失業。下一步「勞動溫度計」合成指標還缺：主計總處加班工時與進入率（要從台灣抓取站試主計總處資料庫表號）、能源署產業用電（擋 GitHub，走台灣抓取站）。勞保開放資料（data.gov.tw 33369）與台電行業別售電（31966）一年才釋出一次，不用 |
| ⏳ 待驗證 | **雲端費用修正（11/2，Vin 核准）**：10 月帳單 NT$23，主因抓取站每輪平均約 184 秒（慢工作全綁在每輪、大多在等政府網站）× 96 輪，加上每輪重寫 11 個檔（GCS 寫入 10.6 萬次，免費 5,000）。改法：抓取站即時資料並行抓、慢工作輪班限時、深夜每小時一輪、即時資料合成 `live.json.gz`、沒變不寫、`state.json` 沒變不寫、原始存檔每 3 小時；`fetch.py` 歷史資料庫改暫存每 3 小時上傳、門牌待辦沒變不傳、靜態檔本機快取。拿掉沒人用的 `fw_1968`。終端機「資料庫」分頁新增 `p-cloud` 雲端用量（`relay_stats` 面板）。目標：CPU 約 3–4 成、GCS 寫入 8 成以下。11/2 實測：首輪 11.4 秒（一次性重寫 6 檔），之後每輪 1.4–2.2 秒、寫 1 次讀 1 次。`p-cloud` 的寫入估算前幾天會被首輪拉高，穩定後應約 2,250（抓取站）＋約 800（歷史資料庫）＋零星。抓取站 `relay_usage` 只記 fetch.py 有讀到的輪次，會漏幾輪，屬正常。亞洲出站流量（Cloud Run 彰化 → 美國 bucket）沒有免費額度，可降不可歸零，等 Vin 決定。下一步：11/4 看 `p-cloud` 穩定讀數；預算警示門檻請 Vin 在 Cloud Shell 確認 |
| ⏳ 待驗證 | **消費風向 `wind`（11/3 上線，Vin 核准 C）**：做＝`_wind_do()` 從 appstore（新進、爬升 ≥10 名、前 3 名）、pop（Spotify 上榜 ≤10 天或升 ≥5、KKBOX 新進或升 ≥3、Netflix 上榜 ≤2 週）、attention 票房前 6、trends、YouTube 7 天內上架的熱門挑候選，w＝行為強度；說＝`_wind_talk()` 的 PTT、Mobile01、LINE TODAY、焦點新聞、時尚媒體標題。Gemini（1 次）把同一件事歸成話題並排除政治、社會案件、比賽結果、常駐大 App；每個話題再查 Google 新聞 `when:14d` 算近 7 天 vs 前 7 天。x＝log10(新聞+1)/2＋標題提及每則 0.1（上限 0.4）；y＝最強排行 w＋多一個來源 0.12。四格：hit 真流行（x≥.5、y≥.5）、quiet 安靜成長（y≥.5、x<.5 且近 7 天有 3 天以上）、new 剛冒出來（同上但未滿 3 天）、hype 只有聲量（x≥.5、不在任何榜上，只限有排行可對照的影視／音樂／App／遊戲）、talk 有在講但沒有榜可對照（實體商品、飲食、生活習慣沒有銷售榜，不能說是炒作）；只在榜上沒在爬的（`_wind_onchart`）標 `static`，有人講算 hit、沒人講算 low。每 6 小時。終端機 `p-wind`（輿情第一段）、3D 輿情「消費風向」chip。待驗證：Gemini 歸類的品質、門檻 0.5 合不合理（新聞 10 篇≈0.52）、連 3 天的安靜成長在 11/6 後才會出現。社群（11/3 試跑後定案）：Threads 最新搜尋算每天篇數（用收集到的貼文跨幾小時換算、只算含全部關鍵字的貼文）、Dcard 搜尋（sort=created、要含全部關鍵字）算 7 天篇數、Dcard 3 板熱門與 IG 探索頁歸納成 `hot` 話題；`browser_batch` 整批 50 秒上限；Dcard 連續約 12 頁會跳 Cloudflare 驗證，所以最多 5 個話題＋3 個板、每頁等 8 秒、遇到驗證當天停。11/3 04:10 第一次排程手動觸發顯示成功但沒推檔（原因不明，可能卡在 50 秒上限），同晚由對話內手動跑完推了第一份（Threads 9、Dcard 9、熱門 0）；IG 搜尋與 hashtag 沒有日期與數量，不用；Reels 不讀。`p_wind` 社群分數＝0.15×log10(Threads+1)＋0.15×log10(Dcard+1)，跟標題提及合計最多 0.4；`hot` 進 Gemini 的討論素材。兩天沒更新就不用。Claude 排程每天 21:52（需要 Vin 電腦開著、桌面 app 開著）。IG 副帳號由 Vin 在手機追蹤 Claude 列的台灣大眾帳號名單養探索頁。中央大學消費者信心指數要探測，拿來回測 `mood` |
| ⚠️ 已知 | Netflix 台灣週榜 `pop.netflix.week` 11/2 還停在 10/18 那週，比預期晚一週，待查是 Netflix 晚發還是抓取問題 |
| ⏳ 待驗證 | 3D 卡片隨資料更新重畫（`refresh_patch.py`）還沒實測 |
| ✅ 已驗證 | 停班停課 22 縣市全部抓到（每個地區第一列少一格的問題）；雨量沒下雨的縣市記 0 |
| ✅ 已驗證 | 藝文活動：新北市不再被算成臺北市（10/30 新北市 18、臺北市 61） |
| 🎯 等 Vin 決定 | Lyst 時尚熱度：10/13 起 GitHub 被 Cloudflare 擋（探測 403 challenge，curl_cffi 也擋），面板停在 Q2 2026。照鐵則不繞過；要停用面板，還是保留舊值 |
| 🎯 等 Vin 決定 | 新增論點「營建 2027–28 轉弱」到觀察層（營建營收 +30%、建照 −36%） |
| 🎯 等 Vin 決定 | 回測：品牌庫存 → 運動鞋優先，再來韓國 20 天出口、美國新屋開工 |
| 🎯 等 Vin 決定 | Threads 官方 API（要 Vin 自己申請；之前拍板不接） |
| 🎯 等 Vin 決定 | 社群彙總安全升級（11/3 Vin：先照現狀跑一段時間再說）。選項：B＝計數程式只回傳 12 字內短詞與數字（品質掉、最省事）；D＝Vin 電腦上獨立程式（Windows 工作排程器＋專用 Chrome 設定檔）讀三站，標題用公鑰加密推 GitHub，Actions 用 Secrets 私鑰解開交 Gemini 歸納、過 `social_check.py`（最安全、零 Claude 額度，代價是一次設定、網站改版會靜靜壞掉、比內建瀏覽器容易被認成機器人）；E＝另開沒連線的 Claude 帳號（可能要付費，違反零花費） |
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
