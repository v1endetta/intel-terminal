# 社群每日彙總（Threads・Dcard・IG 探索頁）

每天 21:52（台北）由 Claude 排程執行，用 Vin 電腦上 **Claude 桌面 app 的內建瀏覽器**（已登入副帳號）讀取，結果寫進 data 分支 `data/social_tw.json`，給 `fetch.py` 的 `p_wind`（消費風向）當「說」那個軸的社群來源。

規則（鐵則 8 的例外，Vin 11/3 同意）：
- 只用內建瀏覽器的副帳號；不按讚、不追蹤、不留言、不點開 Reels。
- 只存「話題＋次數」，**不存標題原文、貼文內容、帳號名**。
- 一天一次。被要求驗證、跳出登入頁、看到 Cloudflare 驗證就停，該站這天跳過，不要繞過。
- 省額度：每站用 `browser_batch` 一次送出「打開頁面＋執行下面的計數程式」，只回傳數字與標題。

## 1. 話題清單

讀 `https://raw.githubusercontent.com/v1endetta/intel-terminal/data/data/panels/wind.json`，取 `topics` 裡 quad 不是 `low` 的前 10 個（照原順序）。每個話題用 `name`（寫回 JSON 的鍵）和 `q`（搜尋詞）。

## 2. Threads：每天幾篇

每個話題：導到 `https://www.threads.com/search?q=<q 編碼>&serp_type=default&filter=recent`，再執行：

```js
const sl=ms=>new Promise(r=>setTimeout(r,ms)); await sl(3000);
const seen=new Set(), now=Date.now(), grab=()=>document.querySelectorAll('time[datetime]').forEach(x=>seen.add(x.getAttribute('datetime')));
for(let i=0;i<12;i++){grab(); const t=[...seen].map(Date.parse); if(t.length>=40||(t.length&&now-Math.min(...t)>6048e5))break; window.scrollBy(0,innerHeight*0.9); await sl(1500+Math.random()*800);}
grab(); const t=[...seen].map(Date.parse).filter(x=>now-x<6048e5), span=t.length?(now-Math.min(...t))/36e5:0;
({n:t.length, perDay:+(t.length/Math.max(span,24)*24).toFixed(1), login:/登入|Log in/.test(document.title)})
```

`perDay` 就是 Threads 的值。列表是虛擬捲動，所以要邊捲邊收集時間。5 個話題一批，分兩批。

## 3. Dcard：近 7 天幾篇

每個話題：導到 `https://www.dcard.tw/search?query=<q 編碼>&sort=created`，執行（把 Q 換成 q）：

```js
await new Promise(r=>setTimeout(r,2500)); const q=Q, now=Date.now();
({n7:[...document.querySelectorAll('article')].filter(a=>a.innerText.includes(q)&&now-Date.parse(a.querySelector('time[datetime]')?.getAttribute('datetime')||0)<6048e5).length})
```

Dcard 搜尋會拆字，所以要再確認文章裡真的有完整的詞。

## 4. Dcard 各板熱門

板：`makeup` 美妝、`dressup` 穿搭、`food` 美食、`buyonline` 網購、`girl` 女孩、`fitness` 健身。導到 `https://www.dcard.tw/f/<板>?tab=popular`，執行：

```js
await new Promise(r=>setTimeout(r,2500)); const now=Date.now();
[...document.querySelectorAll('article')].map(a=>({h:(a.querySelector('h2,h3')?.innerText||'').slice(0,50), d:(now-Date.parse(a.querySelector('time[datetime]')?.getAttribute('datetime')||0))/864e5})).filter(x=>x.h&&x.d<3).map(x=>x.h)
```

## 5. IG 探索頁

導到 `https://www.instagram.com/explore/`，執行：

```js
const sl=ms=>new Promise(r=>setTimeout(r,ms)); await sl(4000); const seen=new Map();
for(let i=0;i<3;i++){document.querySelectorAll('a[href*="/p/"],a[href*="/reel/"]').forEach(a=>{const alt=a.querySelector('img')?.alt||''; if(!seen.has(a.href))seen.set(a.href,alt.replace(/\s+/g,' ').slice(0,160));}); window.scrollBy(0,innerHeight); await sl(1800+Math.random()*600);}
[...seen.values()].filter(Boolean)
```

這是演算法推給這個帳號的內容（帳號追蹤的是各類台灣大眾帳號），代表「平台在推什麼」，不是全台灣在討論什麼。

## 6. 歸納與寫檔

從第 4、5 步的標題與說明裡，歸納出跟消費、生活風格有關的具體話題（品牌、商品、作品、吃法、活動、生活習慣），同一件事合併，數出現幾則。不要政治、社會案件、個人感情細節。名稱用台灣常見叫法，2–12 字。

`data/social_tw.json`：

```json
{"date": "YYYY-MM-DD（台北）",
 "topics": {"<wind 的話題 name>": {"Threads": 每天篇數, "Dcard": 7天篇數}},
 "hot": [{"name": "話題", "src": "Dcard 美妝｜Dcard 穿搭｜…｜IG 推薦", "n": 則數}],
 "runs": {"threads": 成功話題數, "dcard": 成功話題數, "boards": 成功板數, "ig": 讀到幾則}}
```

`hot` 最多 40 個。某站失敗就不要放那一站的數字（不要寫 0），`runs` 記實際成功幾個。

推送：data 分支只改這一個檔；`git pull --rebase` 後再推，被拒就重試一次（抓取機器人每幾分鐘會推一次 data 分支）。
