
/* ---- 數字與圖表 ---- */
const meanAbs = a => a.reduce((s, v) => s + Math.abs(v), 0) / Math.max(1, a.length);
const diffs = a => a.slice(1).map((v, i) => v - a[i]);
const clean = a => (a || []).map(Number).filter(v => isFinite(v));
const hist = (k, s) => clean((((ST.H || {})[k] || {})[s] || []).map(x => x[1]));
const nf = v => { const a = Math.abs(v); return a >= 10000 ? Math.round(v).toLocaleString("en-US") : a >= 1000 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : a >= 100 ? v.toFixed(1) : a >= 10 ? v.toFixed(2) : v.toFixed(a >= 1 ? 2 : 3); };
const pct = (v, d = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;
const UPH = "#30d158", DNH = "#ff453a", NEU = "#f5f5f7", YLH = "#ffd60a";
const tone = v => v > 0 ? UPH : v < 0 ? DNH : NEU;
// 跟自己過去比：最新一次變化是過去平均變化的幾倍
function surprise(vals) {
  vals = clean(vals); if (vals.length < 8) return null;
  const d = diffs(vals), last = d[d.length - 1], m = meanAbs(d.slice(0, -1));
  if (!m || !isFinite(last)) return null;
  const prev = vals[vals.length - 2];
  return { x: Math.min(8, Math.abs(last) / m), last, n: d.length - 1, pct: prev ? last / Math.abs(prev) * 100 : null };
}
let SVGID = 0;
function lineSVG(vals, color, w = 320, h = 120) {
  vals = clean(vals); if (vals.length < 2) return "";
  const id = "g" + (++SVGID), mn = Math.min(...vals), mx = Math.max(...vals), pad = 8, sx = (w - pad * 2) / (vals.length - 1), sy = v => h - pad - (v - mn) / ((mx - mn) || 1) * (h - pad * 2);
  const pts = vals.map((v, i) => [pad + i * sx, sy(v)]), d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const last = pts[pts.length - 1], iMx = vals.indexOf(mx), iMn = vals.indexOf(mn);
  return `<svg class="chart" viewBox="0 0 ${w} ${h + 18}" preserveAspectRatio="none" aria-hidden="true">
  <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".32"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
  <line x1="${pad}" x2="${w - pad}" y1="${sy(mx).toFixed(1)}" y2="${sy(mx).toFixed(1)}" class="grid"/><line x1="${pad}" x2="${w - pad}" y1="${sy(mn).toFixed(1)}" y2="${sy(mn).toFixed(1)}" class="grid"/>
  <path d="${d} L${last[0].toFixed(1)} ${h} L${pad} ${h} Z" fill="url(#${id})" class="area"/>
  <path d="${d}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" class="ln"/>
  <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="7" fill="${color}" opacity=".22" class="dot"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.2" fill="${color}" class="dot"/>
  <text x="${w - pad}" y="${(sy(mx) - 4).toFixed(1)}" text-anchor="end" class="ax">${nf(mx)}</text><text x="${w - pad}" y="${(sy(mn) + 12).toFixed(1)}" text-anchor="end" class="ax">${nf(mn)}</text>
  <text x="${pad}" y="${h + 15}" class="ax">${vals.length} 筆前</text><text x="${w - pad}" y="${h + 15}" text-anchor="end" class="ax">最新</text></svg>`;
}
function barsHTML(rows, opt = {}) {
  rows = rows.filter(r => r && isFinite(r.v)); if (!rows.length) return "";
  const mx = Math.max(...rows.map(r => Math.abs(r.v))) || 1;
  return `<div class="bars">${rows.map(r => `<div class="bar"><span class="bn">${esc(r.name)}</span><span class="bt"><i style="width:${(Math.abs(r.v) / mx * 100).toFixed(1)}%;background:${r.color || (opt.signed === false ? "#64d2ff" : tone(r.v))}"></i></span><span class="bv" style="color:${r.color || (opt.signed === false ? NEU : tone(r.v))}">${esc(r.txt ?? nf(r.v))}</span></div>`).join("")}</div>`;
}
function listHTML(rows) { return `<ul class="lst">${rows.filter(Boolean).map(r => `<li>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.t)}</a>` : esc(r.t)}${r.s ? `<span>${esc(r.s)}</span>` : ""}</li>`).join("")}</ul>`; }
function sideHTML(o) {
  return `<div class="sh"><div class="se">${esc(o.eyebrow || "")}</div><div class="st">${esc(o.title || "")}</div>${o.big ? `<div class="sb" style="color:${o.color || NEU}">${esc(o.big)}${o.chg ? `<small>${esc(o.chg)}</small>` : ""}</div>` : ""}</div>${o.body || ""}${o.foot ? `<div class="sf">${o.foot}</div>` : ""}`;
}

/* ---- 候選：整個情報站，每一條有歷史的數字都參賽 ---- */
const CATW = { "市場": 1, "總經": 1, "走向": 0.9, "訊號": 0.9, "輿情": 0.8, "現場": 0.7 };
// 同一個分類裡也有輕重：台股、外資比棉花重要；每天跳很大的計數型資料打折
const GW = { taiex: 1.1, inst: 1.1, tpex: 0.9, world: 0.9, fx: 0.9, fear: 0.9, cmdty: 0.8, lux: 0.7, stock: 0.75, veg: 0.5, fish: 0.5, fruit: 0.5, meat: 0.5, liq: 0.7, jobs: 0.8, voice: 0.45, mood: 0.8, cofacts: 0.6, ptt: 0.4, elect: 0.8 };
const WCITY = { 紐約: [-74.0, 40.71], 倫敦: [-0.13, 51.5], 東京: [139.69, 35.69], 新加坡: [103.82, 1.35], 首爾: [126.98, 37.57], 香港: [114.17, 22.32], 上海: [121.47, 31.23], 法蘭克福: [8.68, 50.11], 巴黎: [2.35, 48.86], 孟買: [72.88, 19.07], 華盛頓: [-77.04, 38.9] };
const MKT = { "^GSPC": "紐約", "^IXIC": "紐約", "^DJI": "紐約", "^N225": "東京", "^HSI": "香港", "000001.SS": "上海", "^KS11": "首爾", "^NSEI": "孟買", "^GDAXI": "法蘭克福", "^STOXX50E": "法蘭克福", USD: "紐約", EUR: "法蘭克福", JPY: "東京", CNY: "上海" };
function candidates() {
  const out = [], add = (o, fn) => { try { const r = fn(); if (r) out.push(Object.assign(o, r)); } catch (e) { console.warn("story", o.grp, e); } };
  const series = (o, vals, name, unit, extra = {}) => add(Object.assign({}, o), () => {
    let v = clean(vals); if (o.partial) v = v.slice(0, -1);   // 今天還沒過完的計數，拿最後一個完整的日子比
    if (o.week) { const w = []; for (let i = 6; i < v.length; i++) w.push(v.slice(i - 6, i + 1).reduce((a, b) => a + b, 0)); v = w; }   // 每天的量有週末效應，改比「近 7 天合計」
    if (o.minMean && v.reduce((a, b) => a + b, 0) / Math.max(1, v.length) < o.minMean) return null;   // 量太小，跳一下就是好幾倍
    const s = surprise(v); if (!s) return null; const last = v[v.length - 1], up = s.last >= 0;
    if (s.pct != null && Math.abs(s.pct) > 50) return null;   // 一次差一半以上，多半是抓取出錯
    const chg = s.pct != null ? pct(s.pct) : (up ? "+" : "−") + nf(Math.abs(s.last));
    return Object.assign({ score: s.x * (o.w ?? GW[o.grp] ?? CATW[o.cat]), x: s.x, name, big: `${name} ${chg}`, value: last, chgTxt: chg, color: tone(s.last), vals: v.slice(-40), unit,
      say: o.week ? `${name}近 7 天合計 ${nf(last)}${unit ? " " + unit : ""}，比前一天算的 7 天合計${up ? "多" : "少"} ${chg.replace(/^[+−]/, "")}。` : `${name}最新是 ${nf(last)}${unit ? " " + unit : ""}，比前一筆${up ? "上升" : "下降"} ${chg.replace(/^[+−]/, "")}。`,
      why: `這次的變動是過去 ${s.n} 筆平均的 ${s.x.toFixed(1)} 倍。` }, extra);
  });
  // 市場
  series({ cat: "市場", grp: "taiex", link: "taiex", src: "證交所" }, hist("taiex", "TAIEX"), "台股加權", "點", { scene: "city101" });
  add({ cat: "市場", grp: "inst", link: "taiex", src: "證交所 · 三大法人" }, () => {
    const raw = (((ST.H || {}).institutions || {})["外資"]) || [], v = clean(raw.map(x => x[1])); if (v.length < 5) return null;
    const last = v[v.length - 1], past = v.slice(0, -1), x = Math.abs(last) / (meanAbs(past) || 1), buy = last > 0, d = String(raw[raw.length - 1][0]);
    const isMax = Math.abs(last) >= Math.max(...past.map(Math.abs));
    return { score: x * GW.inst, x, value: last, name: "外資", big: `外資${buy ? "買超" : "賣超"} ${nf(Math.abs(last))} 億`, chgTxt: `${buy ? "買超" : "賣超"} ${nf(Math.abs(last))} 億`, color: tone(last), vals: v, unit: "億",
      say: `${+d.slice(4, 6)}/${+d.slice(6, 8)} 外資在台股${buy ? "淨買進" : "淨賣出"} ${nf(Math.abs(last))} 億元${isMax ? `，是近 ${v.length} 個交易日最大的一筆` : ""}。`,
      why: `金額是過去 ${past.length} 個交易日平均的 ${x.toFixed(1)} 倍。`, scene: "globe", from: ["紐約", "倫敦", "東京", "新加坡"], bars: true };
  });
  series({ cat: "市場", grp: "tpex", link: "taiex", src: "櫃買中心" }, hist("tpex", "OTC"), "櫃買指數", "點");
  for (const it of ((P.world || {}).items || [])) series({ cat: "市場", grp: "world", link: "world", src: "Yahoo Finance · " + (it.asOf || "") }, it.spark, it.name, "", { scene: "globe", from: [MKT[it.sym] || "紐約"] });
  for (const it of ((P.fx || {}).items || [])) series({ cat: "市場", grp: "fx", link: "fx", src: "Yahoo 中價" }, it.spark, it.name + "兌台幣", "", { scene: "globe", from: [MKT[it.code] || "紐約"] });
  for (const it of ((P.fear || {}).items || [])) if (!/\//.test(it.sym)) series({ cat: "市場", grp: "fear", link: "fear", src: "CBOE" }, it.spark, it.name + " 恐慌指數", "", { scene: "globe", from: ["紐約"] });
  for (const it of ((P.commodities || {}).items || [])) series({ cat: "市場", grp: "cmdty", link: "cmdty", src: "期貨近月" }, it.spark, it.name, it.unit || "");
  for (const it of ((P.luxury || {}).items || [])) series({ cat: "市場", grp: "lux", link: "lux", src: "最近收盤" }, it.spark, it.name, it.ccy || "", { scene: "globe", from: ["巴黎"] });
  for (const it of ((P.tw_stocks || {}).items || [])) series({ cat: "市場", grp: "stock", link: "taiex", src: "證交所" }, it.spark, it.name, "元");
  // 總經
  for (const it of ((P.veg || {}).items || [])) series({ cat: "總經", grp: "veg", link: "veg", src: "農產品批發 · " + ((P.veg || {}).market || "") }, it.spark, it.name + "價格", "元/公斤");
  for (const g of ["fish", "fruit", "meat"]) { const H = (ST.H || {})[g] || {}; for (const k in H) series({ cat: "總經", grp: g, link: "veg", src: "農漁產批發" }, hist(g, k), k + "價格", "元/公斤"); }
  series({ cat: "總經", grp: "liq", link: "liq", src: "紐約聯準銀行" }, ((P.liquidity || {}).rrp || {}).spark, "逆回購餘額", "十億美元", { scene: "globe", from: ["紐約"] });
  // 訊號
  { const J = P.jobs || {}; series({ cat: "訊號", grp: "jobs", link: "jobs", src: "人力銀行職缺" }, J.spark, "全台職缺數", "個");
    for (const c of (J.cats || [])) series({ cat: "訊號", grp: "jobs", link: "jobs", src: "人力銀行職缺" }, c.spark, c.name + "職缺", "個"); }
  // 走向
  for (const k of (((P.voice || {}).kw) || [])) series({ cat: "走向", grp: "voice", link: "voice", src: "Google 新聞收錄", partial: true, week: true, minMean: 40 }, k.news_daily, `「${k.k}」新聞量`, "則");
  // 輿情
  series({ cat: "輿情", grp: "mood", link: "mood", src: "社群情緒" }, hist("mood", "taiwan"), "台灣情緒分數", "");
  series({ cat: "輿情", grp: "cofacts", link: "cofacts", src: "Cofacts", minMean: 5 }, hist("cofacts", "requests"), "可疑訊息回報量", "則");
  for (const b of (((P.ptt || {}).boards) || [])) series({ cat: "輿情", grp: "ptt", link: "ptt", src: "PTT", partial: true, week: true, minMean: 280 }, b.spark, `PTT ${b.zh || b.board}版熱度`, "");
  // 現場：選戰、電力、機場，加上會插隊的事件
  for (const c of (((P.elect || {}).cities) || [])) { const top = (c.cands || []).slice().sort((a, b) => b.p - a.p)[0]; if (top) series({ cat: "現場", grp: "elect", link: "elect", src: "預測市場" }, top.spark, `${c.city}・${top.name}當選機率`, "%", { scene: "elect", city: c.city, p: top.p / 100 }); }
  add({ cat: "現場", grp: "power", link: "power", src: "台電" }, () => { const pw = P.power || {}, r = pw.reserve_pct; if (r == null) return null;
    return { score: r < 6 ? 5 : r < 10 ? 2.5 : 0.2, x: 0, name: "備轉容量", big: `備轉容量 ${nf(r)}%`, chgTxt: "燈號" + (pw.level || ""), color: r < 6 ? DNH : r < 10 ? "#ff9f0a" : UPH, vals: pw.spark, unit: "%",
      say: `今天尖峰時段（${pw.peak_hours || ""}）預估備轉 ${nf(r)}%，燈號${pw.level || ""}。`, why: "備轉低於 10% 才會排進來，低於 6% 直接插隊。", scene: "power", pr: r }; });
  add({ cat: "現場", grp: "airport", link: "airport", src: "桃園機場" }, () => { const d = (P.airport || {}).dep || {}; if (!d.total) return null; const bad = (d.delayed || 0) + (d.cancelled || 0), r = bad / d.total;
    return { score: r > 0.25 ? 3 : r > 0.15 ? 1.2 : 0.1, x: 0, name: "桃機離境", big: `${bad} 班延誤或取消`, chgTxt: `共 ${d.total} 班`, color: r > 0.15 ? "#ff9f0a" : NEU, vals: null, unit: "",
      say: `今天桃園機場 ${d.total} 班離境，${d.delayed || 0} 班延誤、${d.cancelled || 0} 班取消。`, why: "延誤加取消超過 15% 才會排進來。", scene: "airport" }; });
  add({ cat: "現場", grp: "warn", link: "weather", src: "中央氣象署" }, () => { const w = ((P.radar_wx || {}).warnings) || []; if (!w.length) return null;
    const what = w[0].what, where = [...new Set(w.filter(x => x.what === what).map(x => x.where))];
    const sev = /颱風/.test(what) ? 6 : /豪雨/.test(what) ? 3.5 : /大雨/.test(what) ? 2.6 : /強風/.test(what) ? 2 : /低溫|高溫/.test(what) ? 1.6 : 1.2;
    return { score: sev + where.length / 14, x: 0, name: what + (w[0].level || ""), big: what + (w[0].level || ""), chgTxt: `${where.length} 縣市`, color: YLH, vals: null,
      say: `${where.length} 個縣市：${where.map(s => s.replace(/[縣市]$/, "")).join("、")}。`, why: "天氣示警直接插隊，嚴重度越高排越前面。", scene: "warn", where }; });
  add({ cat: "現場", grp: "quake", link: "quake", src: "中央氣象署" }, () => { const q = (((P.quake || {}).items) || []).find(x => x.mag >= 4.5 && Date.now() - new Date(x.at) < 48 * 3600e3); if (!q) return null;
    return { score: (q.mag - 3) * 1.6, x: 0, name: "地震", big: `規模 ${q.mag} 地震`, chgTxt: "震度 " + (q.intensity || ""), color: YLH, vals: null,
      say: `${q.loc.replace(/\s+/g, " ")}，深度 ${nf(q.depth)} 公里，最大震度 ${q.intensity || "—"}。`, why: "48 小時內規模 4.5 以上的地震直接插隊。", scene: "quake", q }; });
  return out.filter(o => isFinite(o.score));
}
// 五件事只從市場和總經挑：比自己平常動得最多的前五名，同一組資料只上一則
function pickTop(all, n = 5) {
  const top = [], usedG = new Set();
  for (const c of all.slice().sort((a, b) => b.score - a.score)) {
    if (!(c.cat === "市場" || c.cat === "總經") || usedG.has(c.grp)) continue;
    top.push(c); usedG.add(c.grp); if (top.length >= n) break;
  }
  return top;
}

/* ---- 固定的五件事：每一件回答一個不同的問題 ----
   1 台股：市場怎麼看台灣　2 外資：國際的錢進還是出　3 景氣：半年後往哪走
   4 製造業 PMI：工廠接單熱不熱　5 零售與餐飲：大家還願不願意花錢 */
function fixedFive() {
  const out = [], add = fn => { try { const r = fn(); if (r) out.push(r); } catch (e) { console.warn("five", e); } };
  add(() => { const v = hist("taiex", "TAIEX"); if (v.length < 2) return null; const last = v[v.length - 1], prev = v[v.length - 2], r = (last / prev - 1) * 100;
    return { cat: "市場", grp: "taiex", name: "台股加權", toc: `${nf(last)}　${pct(r)}`, value: last, iunit: "", chgTxt: pct(r), color: tone(r), big: `台股 ${nf(last)}`,
      say: `加權指數收在 ${nf(last)} 點，${r >= 0 ? "漲" : "跌"}了 ${nf(Math.abs(last - prev))} 點（${pct(r)}）。`,
      why: "台灣市場的體溫。大家對台灣經濟的看法，最後都會反映在這個數字上。", vals: v.slice(-40), link: "taiex", src: "證交所 · 加權指數", scene: "city101" }; });
  add(() => { const raw = (((ST.H || {}).institutions || {})["外資"]) || [], v = clean(raw.map(x => x[1])); if (!v.length) return null;
    const last = v[v.length - 1], buy = last > 0, d = String(raw[raw.length - 1][0]);
    return { cat: "市場", grp: "inst", name: "外資", value: Math.abs(last), iunit: " 億", chgTxt: `${buy ? "買超" : "賣超"} ${nf(Math.abs(last))} 億`, color: tone(last), big: `外資${buy ? "買超" : "賣超"} ${nf(Math.abs(last))} 億`,
      say: `${+d.slice(4, 6)}/${+d.slice(6, 8)} 外資在台股${buy ? "淨買進" : "淨賣出"} ${nf(Math.abs(last))} 億元。線從紐約、倫敦、東京、新加坡連回台北，亮的那一端是錢流去的方向。`,
      why: "外資是台股最大的買家，他們的錢往哪裡走，短線就往哪裡走。", vals: v, link: "taiex", src: "證交所 · 三大法人", scene: "globe", from: ["紐約", "倫敦", "東京", "新加坡"], bars: true }; });
  add(() => { const L = (P.lead || {}).lead || {}; if (L.value == null) return null; const up = (L.chg || 0) >= 0, m = String(L.month || "");
    return { cat: "總經", grp: "lead", name: "景氣燈號", toc: `${L.signal || ""}燈 ${Math.round(L.score || 0)} 分`, value: L.value, tocC: "#f5f5f7", tocDot: ({ "紅": "#ff453a", "黃紅": "#ff9f0a", "綠": "#30d158", "黃藍": "#ffd60a", "藍": "#0a84ff" })[L.signal] || null, iunit: "", chgTxt: `${up ? "+" : "−"}${Math.abs(L.chg || 0).toFixed(2)}`, color: tone(L.chg || 0), big: `景氣${L.signal || ""}燈 ${Math.round(L.score || 0)} 分`,
      say: `${m.slice(0, 4)} 年 ${+m.slice(4, 6)} 月景氣對策信號是${L.signal || ""}燈 ${Math.round(L.score || 0)} 分；領先指標 ${(+L.value).toFixed(2)}，${L.streak > 1 ? `已經連續 ${L.streak} 個月${up ? "上升" : "下降"}` : up ? "比上月上升" : "比上月下降"}。`,
      why: "領先指標通常比景氣早三到六個月轉向，看它就能先知道半年後的景氣。", vals: L.spark, link: "lead", src: "國發會", scene: "island" }; });
  add(() => { const S = (P.supply || {}).pmi || {}; if (S.value == null) return null; const up = (S.chg || 0) >= 0;
    return { cat: "總經", grp: "pmi", name: "製造業 PMI", toc: `${(+S.value).toFixed(1)}　${S.value >= 50 ? "擴張" : "收縮"}`, value: S.value, iunit: "", chgTxt: `${up ? "+" : "−"}${Math.abs(S.chg || 0).toFixed(1)}`, color: S.value >= 50 ? UPH : DNH, big: `製造業 PMI ${(+S.value).toFixed(1)}`,
      say: `${S.period || ""} 製造業採購經理人指數 ${(+S.value).toFixed(1)}，新增訂單 ${(+(S.orders || 0)).toFixed(1)}。高於 50 代表擴張，低於 50 代表收縮。`,
      why: "PMI 是問工廠採購經理的問卷，會比營收早一步反映接單冷熱。", link: "supply", src: "中華經濟研究院", scene: "industry",
      sideBody: barsHTML((S.inds || []).map(x => ({ name: x.name, v: x.value - 50, txt: (+x.value).toFixed(1), color: x.value >= 50 ? UPH : DNH }))) + '<p class="note">長條從 50 算起：往右是擴張、往左是收縮</p>' }; });
  add(() => { const C = P.consume || {}, F = C.focus || [], r = F.find(x => x.name === "零售業"), f = F.find(x => x.name === "餐飲業"); if (!r) return null;
    return { cat: "總經", grp: "consume", name: "零售與餐飲", toc: `零售 ${pct(r.yoy, 1)}${f ? "・餐飲 " + pct(f.yoy, 1) : ""}`, value: r.yoy, iunit: "%", chgTxt: `年增 ${pct(r.yoy, 1)}`, color: tone(r.yoy), big: `零售 ${pct(r.yoy, 1)}・餐飲 ${f ? pct(f.yoy, 1) : ""}`,
      say: `${C.month || ""} 零售業營業額比去年同月${r.yoy >= 0 ? "多" : "少"} ${Math.abs(r.yoy).toFixed(1)}%${f ? `，餐飲業${f.yoy >= 0 ? "多" : "少"} ${Math.abs(f.yoy).toFixed(1)}%` : ""}。`,
      why: "最貼近品牌的數字：大家還願不願意花錢，花在哪裡。", vals: r.spark, link: "consume", src: "經濟部統計處", scene: "island",
      sideBody: barsHTML([...F.slice(0, 4), ...(C.up || []).slice(0, 3)].filter((x, k, a) => a.findIndex(y => y.name === x.name) === k).slice(0, 7).map(x => ({ name: x.name.replace(/業$/, ""), v: x.yoy, txt: pct(x.yoy, 1) }))) + lineSVG(r.spark, tone(r.yoy)) }; });
  return out;
}

/* ---- 3D 場景：每種故事一個鏡頭 ---- */
const P101 = [121.5645, 25.034];
const ISLAND = MOBILE ? { tgt: V(0, 0, -60), pos: V(30, 600, 520) } : { tgt: V(0, 30, -10), pos: V(170, 400, 470) };
const spin = (cam, a) => { const d = cam.pos.clone().sub(cam.tgt).applyAxisAngle(V(0, 1, 0), a); return { tgt: cam.tgt.clone(), pos: cam.tgt.clone().add(d) }; };
function sceneFor(t, i) {
  const g = new THREE.Group(), col = new THREE.Color(t.color);
  if (t.scene === "city101") {
    const cam = camAt(...P101, MOBILE ? V(2.4, 3.2, 5.2) : V(7, 6.5, 10.5), 0.2);
    for (let k = 0; k < 5; k++) flatRing(g, ...P101, 0.3 + k * 0.5, 0.36 + k * 0.5, col, 0.95 - k * 0.16, 0.05);
    return { g, cam, geo: P101 };
  }
  if (t.scene === "globe" && GLOBE) {
    const TPE = [121.52, 25.04], up = (t.chgTxt || "").startsWith("+") || /買超/.test(t.chgTxt || "");
    for (const k of (t.from || ["紐約"])) { const p = WCITY[k]; if (!p) continue; const pts = GLOBE.arc(p, TPE, 0.28); sGrad(g, up ? pts : pts.reverse(), col, 1, true); GLOBE.node(...p); }
    return { g, cam: { tgt: V(0, -2600, -2200), pos: MOBILE ? V(0, 12500, 9000) : V(0, 9800, 7000) }, globe: true };
  }
  if (t.scene === "elect") {
    const POS = { "台北": [121.56, 25.06], "新北": [121.45, 24.99], "桃園": [121.3, 24.98], "台中": [120.68, 24.15], "台南": [120.22, 23.0], "高雄": [120.32, 22.64] }, ll = POS[t.city] || [121, 24];
    const c = gp(...ll, 0.05), cam = camAt(...ll, MOBILE ? V(2.4, 3.2, 5.2) : V(7, 6.5, 10.5), 0.2);
    for (const o of [0, 0.03, 0.06]) sLine(g, circlePts(c, 2.4 + o, -Math.PI / 2, -Math.PI / 2 + t.p * Math.PI * 2, 160), WH, 1);
    sLine(g, circlePts(c, 2.4, 0, Math.PI * 2, 160), WH, 0.3); flatRing(g, ...ll, 0, 0.12, WH, 1, 0.05);
    return { g, cam, geo: ll };
  }
  if (t.scene === "warn") {
    for (const C of COUNTIES) if (t.where.some(w => norm(C.name).startsWith(norm(w)) || norm(w).startsWith(norm(C.name)))) for (const r of C.rings) sLine(g, r.map(([lo, la]) => gp(lo, la, 0.6)), YL, 1);
    return { g, cam: ISLAND, layer: "wx" };
  }
  if (t.scene === "quake") { const q = t.q; for (let k = 0; k < 5; k++) flatRing(g, q.lon, q.lat, 4 + k * 7, 4.6 + k * 7, YL, 0.95 - k * 0.17, 0.3);
    return { g, cam: camAt(q.lon, q.lat, MOBILE ? V(30, 300, 260) : V(90, 170, 220)), geo: [q.lon, q.lat] }; }
  if (t.scene === "power") { const c = new THREE.Color(t.pr < 6 ? 0xff453a : t.pr < 10 ? 0xff9f0a : 0x30d158);
    for (const [lo, la] of [[120.48, 24.21], [120.2, 22.85], [121.37, 25.12], [121.13, 25.05], [120.75, 22.05]]) { flatRing(g, lo, la, 5, 6, c, 0.95); flatRing(g, lo, la, 9, 9.5, c, 0.45); }
    return { g, cam: spin(ISLAND, 0.2) }; }
  if (t.scene === "airport") { const o = gp(121.233, 25.077, 0.3); for (let k = 0; k < 16; k++) { const a = -2.75 + k * 0.13, b = o.clone().add(V(Math.cos(a) * 90, 0, Math.sin(a) * 90)); b.y = 0.1; sGrad(g, [b, o], WH, 0.7); }
    return { g, cam: camAt(121.233, 25.077, MOBILE ? V(20, 260, 220) : V(70, 150, 190)), geo: [121.233, 25.077] }; }
  if (t.scene === "industry") {
    for (const [lo, la] of [[120.995, 24.776], [120.615, 24.21], [120.272, 23.1]]) {
      const c = gp(lo, la, 0.35), hex = r => { const p = []; for (let k = 0; k <= 6; k++) { const a = k / 6 * Math.PI * 2 + Math.PI / 6; p.push(V(c.x + Math.cos(a) * r, c.y, c.z + Math.sin(a) * r)); } return p; };
      const fill = new THREE.Mesh(new THREE.CircleGeometry(11, 6, Math.PI / 6), addM(col, 0.22)); fill.rotation.x = -Math.PI / 2; fill.position.copy(c); g.add(fill);
      sLine(g, hex(11), col, 1); sLine(g, hex(16), col, 0.35);
    }
    return { g, cam: MOBILE ? { tgt: V(-25, 0, -60), pos: V(-5, 470, 360) } : { tgt: V(-35, 0, -60), pos: V(135, 270, 250) } };
  }
  return { g, cam: spin(ISLAND, [-0.42, 0.3, -0.18, 0.5, -0.6][i % 5]) };
}

/* ---- 右側圖表面板（電腦在台灣右邊，手機在上面）---- */
function storySide(t, i) {
  const body = t.sideBody ? t.sideBody : t.bars && t.grp === "inst" ? barsHTML(((((P.tw_market || {}).institutions) || {}).items || []).map(x => ({ name: x.name, v: x.net, txt: (x.net > 0 ? "+" : "−") + nf(Math.abs(x.net)) + " 億" }))) + lineSVG(t.vals, t.color)
    : t.scene === "warn" ? listHTML(t.where.map(w => ({ t: w, s: t.name })))
    : t.scene === "airport" ? listHTML((((P.airport || {}).dep || {}).upcoming || []).slice(0, 5).map(f => ({ t: `${f.flight} → ${f.to}`, s: `${f.sched} ${f.remark || ""}` })))
    : t.scene === "quake" ? listHTML([{ t: t.q.loc.replace(/\s+/g, " "), s: `深度 ${nf(t.q.depth)} 公里`, url: t.q.url }])
    : lineSVG(t.vals, t.color);
  return sideHTML({ eyebrow: `0${i + 1} · ${t.cat}`, title: t.name, big: t.chgTxt, color: t.color, body, foot: `<span>${esc(t.src || "")}</span><a href="/terminal/#p-${t.link}">終端機 ›</a>` });
}

/* ---- 自己逛：照情報站的分類，兩層選單 ---- */
const items = k => ((P[k] || {}).items || []);
function EXPLORE() {
  const lineOf = (title, vals, color, sub, link, big, chg) => () => ({ html: sideHTML({ eyebrow: sub, title, big, chg, color, body: lineSVG(vals, color), foot: `<a href="/terminal/#p-${link}">終端機 ›</a>` }) });
  const barsOf = (title, rows, sub, link, opt) => () => ({ html: sideHTML({ eyebrow: sub, title, body: barsHTML(rows(), opt), foot: `<a href="/terminal/#p-${link}">終端機 ›</a>` }) });
  const listOf = (title, rows, sub, link) => () => ({ html: sideHTML({ eyebrow: sub, title, body: listHTML(rows()), foot: `<a href="/terminal/#p-${link}">終端機 ›</a>` }) });
  const layer = (L, title, sub, extra) => () => ({ layer: L, html: sideHTML({ eyebrow: sub, title, body: extra ? extra() : "" }) });
  const tx = hist("taiex", "TAIEX");
  return [
    { cat: "市場", items: [
      { n: "洞見", f: () => insCatCard("市場") },
      { n: "台股", mapLens: "stock", f: () => { const v = tx, s = surprise(v); return lineOf("台股加權", v, s ? tone(s.last) : NEU, "市場 · 證交所", "taiex", v.length ? nf(v[v.length - 1]) : "", s && s.pct != null ? pct(s.pct) : "")(); } },
      { n: "法人", globe: 1, f: () => gxCard("inst") },
      { n: "個股", lens: "stock", f: barsOf("關注個股漲跌", () => items("tw_stocks").slice(0, 10).map(x => { const v = x.pct != null ? x.pct : (x.price && x.chg != null ? x.chg / (x.price - x.chg) * 100 : 0); return { name: x.name, v, txt: pct(v) }; }), "市場 · 最近收盤", "taiex") },
      { n: "資金流向", f: layer("flow", "資金流向", "市場 · 海外 → 台灣", () => { const W = Object.fromEntries(items("world").map(x => [x.sym || x.name, x])), tx = hist("taiex", "TAIEX"), s = surprise(tx), inst = ((((P.tw_market || {}).institutions) || {}).items || []).find(x => /外資/.test(x.name));
        return `<p class="why">線條是海外主要市場前一個交易日的漲跌，紅圈＝海外漲、台股卻跌（或反過來），傳導卡住。</p>` + barsHTML(items("world").slice(0, 8).map(x => ({ name: x.name, v: x.chg_pct, txt: pct(x.chg_pct) })))
          + `<p class="why">台股 ${s && s.pct != null ? pct(s.pct) : "—"}${inst ? `・外資${inst.net > 0 ? "買超" : "賣超"} ${nf(Math.abs(inst.net))} 億` : ""}</p>`; }) },
      { n: "全球股市", globe: 1, f: () => gxCard("world") },
      { n: "匯率", globe: 1, f: () => gxCard("fx") },
      { n: "恐慌", f: () => { const v = items("fear").find(x => x.sym === "^VIX") || {}; return lineOf("VIX 恐慌指數", v.spark, v.value > 25 ? DNH : v.value > 15 ? "#ff9f0a" : UPH, "市場 · 15 以下平靜、25 以上緊張", "fear", nf(v.value || 0), pct(v.chg_pct || 0))(); } },
      { n: "原物料", globe: 1, f: () => gxCard("cmdty") },
      { n: "全球物流", f: () => logisticsCard() },
      { n: "精品", globe: 1, f: () => gxCard("lux") },
      { n: "行事曆", globe: 1, f: () => gxCard("clock") },
    ] },
    { cat: "總經", items: [
      { n: "洞見", f: () => insCatCard("總經") },
      { n: "領先指標", f: () => dleadCard() },
      { n: "AI 循環", f: () => aicycleCard() },
      { n: "隱形冠軍", f: () => champCard() },
      { n: "內需產業", f: () => sectorsCard() },
      { n: "景氣指標", lens: "macro", f: listOf("台灣總經", () => items("macro").map(x => ({ t: `${x.label}  ${x.value}`, s: `${x.period} · 前期 ${x.prev}` })), "總經", "macro") },
      { n: "刷卡", lens: "cards" },
      { n: "出口結構", globe: 1, f: () => gxCard("exports") },
      { n: "企業壓力", f: () => stressCard() },
      { n: "新車", f: () => carsCard() },
      { n: "觀光", f: () => tourismCard() },
      { n: "房價", lens: "house" },
      { n: "建照", f: () => permitsCard() },
      { n: "物價細項", f: () => pricesCard() },
      { n: "菜價", f: barsOf("菜價兩週變化", () => items("veg").slice(0, 10).map(x => ({ name: x.name, v: x.chg14, txt: pct(x.chg14, 0) })), "總經 · " + ((P.veg || {}).market || ""), "veg") },
      { n: "油價", f: barsOf("中油牌價", () => items("oil").map(x => ({ name: x.name, v: x.price, txt: nf(x.price) + " 元" })), "總經 · " + ((P.oil || {}).effective || ""), "macro", { signed: false }) },
      { n: "美元流動性", globe: 1, f: () => gxCard("liq") },
      { n: "信用利差", f: () => creditCard() },
    ] },
    { cat: "走向", items: [
      { n: "本月洞見", f: () => insightsCard() },
      { n: "論點追蹤", f: () => thesesCard() },
      { n: "本週走向", f: () => weeklyCard() },
      { n: "台灣還沒報", f: () => gapCard() },
      { n: "區域報告", lens: "area" },
      { n: "住哪裡", lens: "city" },
      { n: "人口遷徙", lens: "move" },
      { n: "出生", lens: "birth" },
      { n: "趨勢雷達", f: barsOf("新聞量最多的主題", () => (((P.voice || {}).kw) || []).slice().sort((a, b) => b.news7 - a.news7).slice(0, 10).map(k => ({ name: k.k, v: k.news7, txt: k.news7 + " 則" })), "走向 · 近 7 天", "voice", { signed: false }) },
      { n: "主題熱度", f: listOf("升溫中的主題", () => (((P.wiki || {}).rows) || []).filter(r => r.spiked).slice(0, 8).map(r => ({ t: r.title, s: r.grp })), "走向 · 維基瀏覽", "wiki") },
      { n: "主題鏈", f: listOf("缺口與機會", () => (((P.chain || {}).rows) || []).slice(0, 8).map(r => ({ t: `${r.k}・${r.verdict || ""}`, s: r.why })), "走向", "chain") },
    ] },
    { cat: "訊號", items: [
      { n: "洞見", f: () => insCatCard("訊號") },
      { n: "新公司", lens: "biz" },
      { n: "公司生滅", f: () => bizlifeCard() },
      { n: "新興生意", f: () => nicheCard() },
      { n: "職缺", lens: "jobs", f: barsOf("各類職缺 7 天變化", () => (((P.jobs || {}).cats) || []).slice(0, 10).map(c => ({ name: c.name, v: c.chg7, txt: pct(c.chg7 || 0, 1) })), "訊號 · 全台 " + nf((P.jobs || {}).total || 0) + " 個職缺", "jobs") },
      { n: "補助徵件", f: () => grantsCard() },
      { n: "美國政策", f: () => uspolicyCard() },
      { n: "標案", lens: "tender", f: listOf("政府標案", () => items("tenders").slice(0, 7).map(x => ({ t: x.title, s: `${x.unit} · ${x.budget ? nf(x.budget / 1e4) + " 萬" : ""}`, url: x.url })), "訊號", "tenders") },
      { n: "公司雷達", f: listOf("盯梢中的公司", () => (((P.radar || {}).watch) || []).slice(0, 7).map(x => ({ t: x.name, s: x.desc })), "訊號", "radar") },
      { n: "診所", lens: "clinic" },
      { n: "醫美", lens: "aes" },
      { n: "AI 快線", globe: 1, f: () => gxCard("ai") },
      { n: "AI 與開源", f: () => ossCard() },
    ] },
    { cat: "輿情", items: [
      { n: "洞見", f: () => insCatCard("輿情") },
      { n: "焦點新聞", f: () => gtopCard() },
      { n: "地方新聞", lens: "news" },
      { n: "全球新聞", globe: 1, f: () => gxCard("wnews") },
      { n: "民調", f: () => pollsCard() },
      { n: "台灣情緒", lens: "mood", f: () => { const m = (P.mood || {}).taiwan || {}; return { html: sideHTML({ eyebrow: "輿情 · 社群情緒", title: "台灣人今天的心情", big: m.label || "", color: (m.score || 0) < 0 ? DNH : UPH, body: moodViz() + listHTML([{ t: m.line || "" }, ...(m.themes || []).map(t => ({ t: "· " + t }))]), foot: '<a href="/terminal/#p-mood">終端機 ›</a>' }) }; } },
      { n: "熱搜", f: listOf("Google 熱搜", () => items("trends").slice(0, 8).map(x => ({ t: x.title, s: x.traffic })), "輿情", "trends") },
      { n: "PTT", f: () => pttCard() },
      { n: "謠言", f: () => cofactsCard() },
    ] },
    { cat: "現場", items: [
      { n: "洞見", f: () => insCatCard("現場") },
      { n: "此刻", lens: "now" },
      { n: "天氣", f: layer("wx", "天氣與雷達", "現場 · 氣象署", () => { const W = P.weather || {}, warn = W.warnings || [];
        return (warn.length ? `<p class="why"><b style="color:#ff9f0a">${esc([...new Set(warn.map(w => w.what))].join("、"))}</b>：${esc(warn.map(w => norm(w.where)).join("、"))}</p>` : `<p class="why">目前沒有天氣特報。</p>`)
          + listHTML((W.items || []).map(w => ({ t: `${w.city}　${(+w.temp).toFixed(1)}°C　${w.weather || ""}`, s: `${w.forecast && w.forecast[0] ? `接下來 ${w.forecast[0].wx}・降雨 ${w.forecast[0].pop}%` : ""}${w.rain24h ? `・24 小時雨量 ${w.rain24h} mm` : ""}` }))); }) },
      { n: "地震", f: layer("quake", "顯著地震", "現場 · 氣象署", () => listHTML((((P.quake || {}).items) || []).slice(0, 8).map(q => ({ t: `M${q.mag}　${(q.loc || "").replace(/\s+/g, " ").replace(/\s*\(.*\)/, "")}`, s: `${q.intensity ? "最大震度 " + q.intensity + "・" : ""}深 ${q.depth} 公里・${new Date(q.at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}`, url: q.url })))) },
      { n: "停班停課", lens: "stop" },
      { n: "電力", lens: "power", f: () => { const pw = P.power || {}; return lineOf("備轉容量率", pw.spark, (pw.reserve_pct || 0) < 10 ? "#ff9f0a" : UPH, "現場 · 台電", "power", nf(pw.reserve_pct || 0) + "%", "燈號" + (pw.level || ""))(); } },
      { n: "車流", lens: "traffic" },
      { n: "航班", f: () => ({ layer: "flights", html: FL.built ? flightsSide() : sideHTML({ eyebrow: "現場 · 桃園機場 · ADS-B", title: "今天飛去哪裡", body: '<p class="empty">航線載入中…</p>' }) }) },
      { n: "台海", mapLens: "pla", f: () => plaCard() },
      { n: "海纜", lens: "cable" },
      { n: "選戰", lens: "elect", f: barsOf("五都領先者當選機率", () => (((P.elect || {}).cities) || []).map(c => { const t = (c.cands || []).slice().sort((a, b) => b.p - a.p)[0] || {}; return { name: `${c.city} ${t.name || ""}`, v: t.p, txt: nf(t.p || 0) + "%" }; }), "現場 · 預測市場", "elect", { signed: false }) },
      { n: "氣壓圖", globe: 1, f: () => gxCard("press") },
    ] },
  ];
}
/* ---- 資料身分標籤（學 God's Eye View）：每張卡片都說清楚「哪裡來、什麼時候、是觀測還是推算」 ----
   類型：即時＝幾分鐘內的觀測；收盤＝最近一個交易日；每日／每週／每月／每季＝官方定期公布的統計；彙整＝情報站整理的新聞或社群；推算＝模型或時刻表推估 */
const PROV = {
  "行事曆": ["mktcal", "Forex Factory 週行事曆・FRED・證交所・各交易所行事曆・公開資訊觀測站", "彙整", 180],
  "台股": ["taiex", "證交所", "收盤", 1440, p => p.date], "法人": ["tw_market", "證交所", "收盤", 1440], "個股": ["tw_stocks", "證交所", "收盤", 1440, p => p.date],
  "全球股市": ["world", "各國交易所（Yahoo Finance）", "收盤", 1440], "匯率": ["fx", "Yahoo 中價", "即時", 90], "恐慌": ["fear", "CBOE", "收盤", 1440],
  "原物料": ["commodities", "期貨近月", "收盤", 1440, p => p.asOf], "精品": ["luxury", "各交易所", "收盤", 1440, p => p.asOf], "資金流向": ["world", "海外交易所＋證交所", "收盤", 1440],
  "菜價": ["veg", "農業部批發市場行情", "每日", 1440, p => p.date], "油價": ["oil", "中油", "每週", 10080, p => p.effective], "景氣指標": ["macro", "主計總處・國發會・央行", "每月", 43200],
  "美元流動性": ["liquidity", "聯準會 FRED", "每日", 1440], "本週走向": ["weekly", "情報站彙整", "每週", 10080, p => p.week], "趨勢雷達": ["voice", "Google 趨勢・Google 新聞", "彙整", 360],
  "主題鏈": ["chain", "情報站彙整", "每週", 10080, p => p.week], "主題熱度": ["wiki", "維基百科瀏覽量", "每月", 43200, p => p.month], "AI 快線": ["aiwire", "各公司官網與新聞", "彙整", 120],
  "公司雷達": ["radar", "情報站彙整", "彙整", 1440], "台灣情緒": ["mood", "PTT・Dcard・新聞標題", "彙整", 180], "PTT": ["ptt", "PTT 熱門文章", "彙整", 60],
  "熱搜": ["trends", "Google 熱搜", "彙整", 120], "謠言": ["cofacts", "Cofacts 真的假的", "彙整", 180], "天氣": ["weather", "氣象署", "即時", 60],
  "地震": ["quake", "氣象署", "即時", 60], "選戰": ["elect", "Polymarket 報價＋新聞", "彙整", 120], "電力": ["power", "台電", "即時", 30, p => p.asof],
  "航班": ["flights", "adsb.lol 即時位置＋桃園機場時刻表（空中位置依時刻推算）", "即時", 30],
  "lens:now": ["weather", "氣象署・高公局・公路局・文化部藝文資訊", "即時", 60], "lens:house": ["house", "內政部實價登錄", "每季", 129600, p => p.season],
  "lens:biz": ["brands", "經濟部公司與商業登記，依地址歸到鄉鎮", "每月", 43200, p => p.month], "lens:jobs": ["jobs", "104 人力銀行刊登數", "每日", 1440],
  "lens:tender": ["tendermap", "政府電子採購網（依發包機關歸類，不是工程地點）", "每日", 1440], "lens:news": ["mapfeed", "Google 新聞，依標題地名歸到鄉鎮", "彙整", 180],
  "lens:stock": ["mops", "證交所・櫃買中心重大訊息；總部位置依登記地址", "每日", 1440], "lens:elect": ["elect", "Polymarket 報價（只看不押）＋新聞", "彙整", 120], "lens:macro": ["macro", "國發會・主計總處・央行", "每月", 43200], "lens:mood": ["mood", "PTT・LINE 查證・新聞標題（AI 判讀）", "彙整", 180], "lens:power": ["power", "台電", "即時", 30, p => p.asof],
  "全球新聞": ["worldnews", "BBC・半島電視台・NPR・衛報・日經亞洲・南華早報・韓聯社・CNA・日本時報（Gemini 翻譯與判讀）", "彙整", 60],
  "物價細項": ["prices", "行政院主計總處（全國）／臺北市政府主計處 消費者物價基本分類指數", "月資料", 1440],
  "觀光": ["tourism", "交通部觀光署 觀光統計資料庫・臺北市一般旅館營運報表", "年／月資料", 1440],
  "焦點新聞": ["gtop", "Google 新聞・焦點新聞（台灣，非個人化）", "即時", 30],
  "新興生意": ["taxreg", "財政部 全國營業（稅籍）登記", "月資料", 1440],
  "lens:clinic": ["clinics", "衛福部健保署 健保特約醫療院所名冊", "每日", 1440],
  "lens:aes": ["aesthetic", "衛福部醫事司 醫療機構與人員基本資料（全部機構，一年一版）對照健保特約名冊", "年資料", 10080, p => p.asof],
  "台海": ["plaact", "國防部 即時軍事動態（每天早上公布前 24 小時）", "每日", 1440, p => (p.latest || {}).date],
  "lens:cable": ["cables", "TeleGeography Submarine Cable Map（CC BY-NC-SA 3.0）＋Google 新聞", "每週", 10080],
  "lens:area": ["migration", "內政部遷入遷出・經濟部公司登記・健保署與衛福部醫事機構名冊・實價登錄・104・Google 新聞（各項期間不同，見每一列）", "彙整", 1440],
  "lens:city": ["migration", "Ookla Speedtest 開放資料・OpenStreetMap・內政部戶政司・環境部・實價登錄租賃・健保署（每週計算）", "彙整", 10080],
  "lens:move": ["migration", "內政部戶政司 遷入遷出統計", "月資料", 1440],
  "洞見": ["insights_cat", "情報站各分類資料（程式整理、Gemini 寫句子）", "彙整", 360],
  "本月洞見": ["insights", "政府開放資料交叉比對（程式算訊號、Gemini 寫句子）", "每日", 1440],
  "AI 循環": ["aicycle", "SEC 財報（雲端五家資本支出）・財報新聞（AI 擷取指引）・FinMind 月營收・DRAMeXchange（只放漲跌）", "彙整", 360],
  "民調": ["polls", "Google 新聞標題（AI 擷取民調數字，以調查單位公布為準）", "每 3 小時", 360],
  "內需產業": ["twsectors", "財政部電子發票各行業金額・營業登記新設", "每月", 1440, p => p.month],
  "隱形冠軍": ["champions", "FinMind 上市櫃月營收（含海外子公司）", "每月", 1440, p => p.month],
  "論點追蹤": ["theses", "情報站各面板的資料，依每個論點寫好的門檻由程式判斷；美元指數、日圓、費半、加權指數歷史來自 Yahoo Finance", "每輪", 720],
  "領先指標": ["dlead", "dalta 自建：台股、韓股、費半、M1B 減 M2、紐約與費城聯準會調查、美國公司債利差等權合成", "每月", 1440, p => p.month],
  "信用利差": ["credit", "ICE BofA 美國公司債利差（經 FRED），只顯示近 3 年百分位", "每日", 1440, p => (((p.rows || [])[0]) || {}).asof],
  "出口結構": ["exports", "財政部統計資料庫：出口按國家×主要貨品", "每月", 43200, p => p.month],
  "企業壓力": ["stress", "中央銀行退票統計；勞動部減班休息（從新聞標題擷取）", "每月", 43200, p => (p.bounce || {}).month],
  "全球物流": ["logistics", "Drewry WCI・Freightos FBX（只放變動）・GDACS 熱帶氣旋・物流媒體", "彙整", 180],
  "美國政策": ["uspolicy", "Federal Register（USTR、BIS、ITA）・USTR 新聞稿・Congress.gov", "每日", 480],
  "AI 與開源": ["ossuse", "GitHub Trending・Hugging Face 熱門模型與 Spaces・HF Daily Papers（重要性由 Gemini 依對市場的意義判讀）", "彙整", 360],
  "補助徵件": ["grants", "Google 新聞的補助、徵件公告（Gemini 判讀，以原公告為準）", "彙整", 360],
  "lens:stop": ["alerts", "行政院人事行政總處 天然災害停止上班及上課情形", "即時", 30, p => (p.stopwork || {}).updated],
  "氣壓圖": ["pressure", "Open-Meteo（各國氣象模式）海平面氣壓", "預報", 360],
  "lens:traffic": ["roads", "高公局・公路局即時車速；街上的小車是依時段模擬", "即時", 20, p => p.asOf && p.asOf.slice(11, 16)],
};
const PROV_K = { "預報": "est", "即時": "live", "收盤": "close", "每日": "stat", "每週": "stat", "每月": "stat", "每季": "stat", "彙整": "agg", "推算": "est" };
function provHTML(key) {
  const d = PROV[key]; if (!d) return "";
  const [pk, src, kind, ttl, st] = d, p = P[pk] || {}, up = p.updatedAt ? new Date(p.updatedAt) : null, age = up ? (Date.now() - up) / 6e4 : null;
  const stale = age != null && age > Math.max(ttl * 2.5, 90), sT = st ? st(p) : "";
  const agoT = age == null ? "" : age < 60 ? `${Math.max(1, Math.round(age))} 分鐘前` : age < 2880 ? `${Math.round(age / 60)} 小時前` : `${Math.round(age / 1440)} 天前`;
  return `<div class="prov${stale ? " stale" : ""}"><i class="pk-${PROV_K[kind] || "agg"}">${kind}</i><span>${esc(src)}${sT ? `・資料 ${esc(sT)}` : ""}${agoT ? `・${stale ? "最後更新" : "更新"} ${agoT}` : ""}${stale ? "・可能過期" : ""}</span></div>`;
}
let EXCAT = -1, EXITEM = -1;
function buildDock() {
  const E = EXPLORE(), d = $("dock2");
  ST.allChips = E.flatMap(c => c.items.map(it => c.cat + "/" + it.n)); ST.curCat = () => (E[EXCAT] || {}).cat;   // 給使用紀錄用
  d.innerHTML = `<div class="chips" id="chips" role="tablist" aria-label="項目"></div><div class="seg" role="tablist" aria-label="分類"><span class="hl" id="segHL"></span>${E.map((c, i) => `<button type="button" role="tab" data-c="${i}">${c.cat}</button>`).join("")}</div>`;
  const seg = d.querySelector(".seg");
  const moveHL = () => { const b = seg.querySelector(`[data-c="${EXCAT}"]`), hl = $("segHL"); if (b) { hl.style.width = b.offsetWidth + "px"; hl.style.transform = `translateX(${b.offsetLeft - 4}px)`; } seg.querySelectorAll("button").forEach(x => x.setAttribute("aria-selected", +x.dataset.c === EXCAT)); };
  const showCat = (ci, pick = 0) => { EXCAT = ci; moveHL(); const c = E[ci];
    $("chips").innerHTML = c.items.map((it, j) => `<button type="button" role="tab" data-j="${j}"${it.lens ? ` data-lens="${it.lens}" title="地圖會跟著換"` : it.globe ? ` data-globe="1" title="在地球上看"` : ""}>${esc(it.n)}</button>`).join("");
    $("chips").classList.remove("in"); void $("chips").offsetWidth; $("chips").classList.add("in"); pickItem(pick); };
  const wxBoost = on => LBL.forEach(L => { if (L.group === "wx") { if (L.prio0 == null) L.prio0 = L.prio; L.prio = L.prio0 + (on ? 20 : 0); } });   // 選「天氣」時，天氣標籤排在縣市示警前面
  const pickItem = j => { EXITEM = j; const it = E[EXCAT].items[j]; wxBoost(false); if (it.globe) ST.lastGlobe = [EXCAT, j]; else if (it.lens) ST.lastMap = [EXCAT, j]; $("chips").querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", +b.dataset.j === j));
    // 有地圖視角的分類：地圖換成那個視角，卡片交給分層地圖（依目前層級回答）
    if (it.lens) { if (it.lens === "now") setLayer("wx"); else if (cur && layers[cur]) { layers[cur].g.visible = false; layers[cur].off && layers[cur].off(); cur = null; } dimTo = 0; navSetLens(it.lens); return; }   // 現場疊天氣圖層；其他視角把圖層收掉，畫面只留那個視角
    let r = null; try { r = it.f(); } catch (e) { console.warn(e); r = { html: sideHTML({ title: it.n, body: '<p class="empty">資料暫時讀不到</p>' }) }; }
    if (r.gx) GX.key = r.gx;
    if (r.layer) { setLayer(r.layer); wxBoost(r.layer === "wx"); } else if (cur && layers[cur]) { layers[cur].g.visible = false; layers[cur].off && layers[cur].off(); cur = null; document.querySelectorAll("#labels .lbl").forEach(x => x.style.opacity = 0); }
    dimTo = r.layer && r.layer !== "wx" && r.layer !== "gx" ? 1 : 0; showSide(r.html + provHTML(it.n), null); navSetLens(it.mapLens || "now", true); NAV.bare = !r.layer && !it.mapLens; };   // bare：沒有地點也沒有自己的圖層（天氣、地震有圖層，不算）   // mapLens：卡片照舊，地圖換成相關的視角（台股→公司總部漲跌）
  // 地球 ↔ 台灣：回到上次看的那個地球場景／地圖視角（沒有就用市場時鐘／現場）
  const at = (cat, n) => { const ci = E.findIndex(c => c.cat === cat); return [ci, Math.max(0, E[ci].items.findIndex(it => it.n === n))]; };
  ST.goEarth = () => { const [c, j] = ST.lastGlobe || at("市場", "行事曆"); showCat(c, j); };
  ST.goMap = () => { const [c, j] = ST.lastMap || at("現場", "此刻"); showCat(c, j); };
  seg.onclick = e => { const b = e.target.closest("button"); if (b) showCat(+b.dataset.c); };
  $("chips").onclick = e => { const b = e.target.closest("button"); if (b) pickItem(+b.dataset.j); };
  addEventListener("resize", moveHL);
  ST.redrawCard = () => {   // 每 5 分鐘讀到新資料時：開著的卡片原地重畫（保留捲動位置，不動鏡頭）
    const s = $("side"); if (!s || !s.classList.contains("on") || !document.body.classList.contains("exploring") || EXCAT < 0) return;
    const it = ((E[EXCAT] || {}).items || [])[EXITEM]; if (!it) return;
    if (it.lens) { NAV.key = ""; return; }   // 地圖視角的卡片：讓地圖下一輪自己重畫
    let r = null; try { r = it.f(); } catch (e) { return; } if (!r || !r.html) return;
    const top = s.scrollTop; s.innerHTML = r.html + provHTML(it.n); s.scrollTop = top; };
  ST.openAt = (cat, n) => { const [c, j] = at(cat, n); EXCAT = c; EXITEM = j; if (ST.explore) showCat(c, j); else { const d = document.querySelectorAll("#dots button"); d.length && d[d.length - 1].click(); } };
  ST.openExplore = () => { if (EXCAT < 0) { EXCAT = E.findIndex(c => c.cat === "現場"); EXITEM = 0; } showCat(EXCAT, Math.max(0, EXITEM)); requestAnimationFrame(moveHL); };
}

/* ---- 側邊面板切換（淡入、線條畫出來）---- */
let SIDE_KEY = null;
function showSide(html, geo) {
  const s = $("side"); ST.sideGeo = geo || null;
  s.classList.remove("on", "open"); clearTimeout(showSide.t);
  showSide.t = setTimeout(() => { s.innerHTML = html; s.classList.add("on");
    s.querySelectorAll(".ln").forEach(p => { const L = p.getTotalLength(); p.style.strokeDasharray = L; p.style.strokeDashoffset = L; p.getBoundingClientRect(); p.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.3,.7,.2,1)"; p.style.strokeDashoffset = 0; });
  }, html ? 180 : 0);
  if (!html) s.classList.remove("on");
}
if (MOBILE) addEventListener("DOMContentLoaded", () => {}); document.addEventListener("click", e => { const sd = e.target.closest && e.target.closest("#side"); if (!sd || !MOBILE || e.target.closest("a")) return;
  if (window.__swipedAt && performance.now() - window.__swipedAt() < 400) return;   // 剛用滑的開關過
  if (sd.classList.contains("open") && e.target.closest("button,li,input,label,[data-mkt],[data-pf],[data-nc],[data-nt]")) return;   // 展開時點裡面的東西，不要收起來
  sd.classList.toggle("open"); });
function hideSide() { SIDE_KEY = null; $("side").classList.remove("on"); ST.sideGeo = null; }

/* ---- 章節與 DOM ---- */
function chapterDom(i, html, cls = "") { const s = document.createElement("section"); s.className = "ch " + cls; s.dataset.i = i; s.innerHTML = `<div class="card">${html}</div>`; $("story").appendChild(s); return s; }
async function buildStory() {
  renderer.domElement.style.touchAction = "pan-y";
  try { ST.H = await (await fetch(RAW + "history.json?t=" + Date.now(), { cache: "no-store" })).json(); } catch (e) { ST.H = {}; }
  await buildGlobe(); GLOBE.g.visible = false; SG.add(GLOBE.g);
  const all = candidates(), top = fixedFive(); ST.top = top; ST.all = all;
  const now = new Date(), d = `${now.getMonth() + 1} 月 ${now.getDate()} 日 ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const CH = [];
  CH.push({ name: "開場", g: new THREE.Group(), cam: MOBILE ? { tgt: V(5, 0, -175), pos: V(35, 700, 420) } : ISLAND, cls: "hero",   // 手機：島往下放，讓出上面給五件事
    dom: `<div class="eyebrow">dalta 情報站 · ${d}</div><h1>台灣，此刻。</h1><p class="lede">每天固定看的五件事。</p><ol class="toc">${top.map((t, i) => `<li><span class="n">0${i + 1}</span><span class="c">${esc(t.cat)}</span><span class="t">${esc(t.name)}</span><span class="v" style="color:${t.tocC || t.color}">${t.tocDot ? `<i class="sig" style="background:${t.tocDot};color:${t.tocDot}"></i>` : ""}${esc(t.toc || t.chgTxt || "")}</span></li>`).join("")}</ol>${(((P.insights || {}).items) || [])[0] ? `<button type="button" class="insl" data-ins="1"><i>本月洞見</i>${esc(P.insights.items[0].title)} ›</button>` : ""}${((P.theses || {}).rows || []).length ? `<button type="button" class="insl" data-thz="1"><i style="background:#64d2ff">論點追蹤</i>主論點 ${esc(thesesSum())} ›</button>` : ""}<div class="herofoot"><span class="scrollhint">往下捲</span><button type="button" class="replay" id="replay">重播開場</button></div>` });
  top.forEach((t, i) => { const sc = sceneFor(t, i);
    CH.push({ name: t.cat, g: sc.g, cam: sc.cam, globe: sc.globe, layer: sc.layer, geo: sc.geo, side: storySide(t, i),
      dom: `<div class="eyebrow">0${i + 1} / 五件事 · ${esc(t.name)}</div><h2 style="color:${t.color}">${esc(t.big)}</h2><p>${esc(t.say)}</p><p class="why"><b>為什麼看這個</b>${esc(t.why)}</p>` }); });
  { const W = (P.weather || {}).items || [], hot = W.reduce((a, b) => (b.temp > (a ? a.temp : -99) ? b : a), null), cold = W.reduce((a, b) => (b.temp < (a ? a.temp : 99) ? b : a), null);
    const rain = W.filter(x => (x.rain1h || 0) > 0).map(x => x.city), warn = ((P.radar_wx || {}).warnings || []);
    CH.push({ name: "此刻", g: new THREE.Group(), cam: ISLAND, layer: "wx",
      dom: `<div class="eyebrow">06 / 現場</div><h2>此刻的台灣</h2><p>${hot ? `最熱的是${esc(hot.city)} ${nf(hot.temp)}°，最涼的是${esc(cold.city)} ${nf(cold.temp)}°。` : ""}${rain.length ? `${esc(rain.join("、"))}正在下雨。` : "這一小時全台沒有測站下雨。"}${warn.length ? `${esc(warn[0].what)}${esc(warn[0].level || "")}影響 ${warn.length} 個縣市。` : ""}</p>` }); }
  CH.push({ name: "自己逛", g: new THREE.Group(), cam: ISLAND, explore: true, cls: "last",
    dom: `<div class="eyebrow">07 / 自己逛</div><h2>情報站的全部，都在這裡</h2><p>選分類，再選項目。圖表會出現在台灣旁邊，有地點的會直接畫在地圖上。</p><div class="btns"><a class="pill primary" href="/terminal/">完整終端機</a><button class="pill ghost" id="toTop" type="button">回到開頭</button></div>` });
  CH.forEach((c, i) => { c.g.visible = false; SG.add(c.g); c.el = chapterDom(i, c.dom, c.cls || ""); c.g.traverse(o => { if (o.material) o.material.opacity = 0; }); });
  const dots = document.createElement("div"); dots.id = "dots"; dots.setAttribute("role", "navigation"); dots.setAttribute("aria-label", "章節");
  dots.innerHTML = CH.map((c, i) => `<button type="button" data-i="${i}" aria-label="${esc(c.name)}"><span>${esc(c.name)}</span></button>`).join(""); document.body.appendChild(dots);
  dots.onclick = e => { const b = e.target.closest("button"); if (b) scrollTo({ top: +b.dataset.i * secH(), behavior: "smooth" }); };
  $("toTop").onclick = () => scrollTo({ top: 0, behavior: "smooth" });
  ST.chapters = CH; buildDock(); window.__story = ST;
  $("replay").onclick = () => ST.replay && ST.replay();
  buildIntro();
}
const secH = () => (ST.chapters[0] && ST.chapters[0].el.offsetHeight) || innerHeight * 1.35;
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
function setExplore(on) {
  if (ST.explore === on) return; ST.explore = on;
  controls.enabled = on; controls.maxDistance = on ? 1600 : Infinity;
  renderer.domElement.style.touchAction = on ? "none" : "pan-y";   // 劇本模式要讓手指的上下滑動交給頁面捲動（OrbitControls 預設把整張畫布設成不能捲）
  document.body.classList.toggle("exploring", on); document.body.classList.toggle("storying", !on);
  if (on) { camera.clearViewOffset(); camera.near = 1; camera.updateProjectionMatrix(); if (camera.position.distanceTo(ISLAND.pos) > 5) flyTo(ISLAND.pos, ISLAND.tgt, 1.4); ST.openExplore && ST.openExplore(); ST.chapters.forEach((ch, k) => ch.el.classList.toggle("act", k === ST.chapters.length - 1)); } else { $("card").classList.remove("show"); ST.active = -1; }
}
const _d0 = new THREE.Vector3(), _d1 = new THREE.Vector3(), _sp = new THREE.Vector3();
function storyTick(dt) {
  const CH = ST.chapters; if (!CH.length) return;
  const N = CH.length, y = scrollY / secH(), i = Math.min(N - 1, Math.floor(y)), f = y - i, c = Math.min(N - 1, i + smooth(0.4, 0.92, f));
  ST.c = c; setExplore(c >= N - 1.001);
  for (let k = 0; k < N; k++) {
    const w = Math.max(0, 1 - Math.abs(c - k) * 2.2), ch = CH[k];
    ch.g.visible = w > 0.01; ch.g.traverse(o => { if (o.material && o.material.userData.op != null) o.material.opacity = o.material.userData.op * w; });
  }
  const gw = ST.globeForce ? 1 : CH.reduce((m, ch, k) => ch.globe ? Math.max(m, 1 - Math.abs(c - k) * 1.2) : m, 0);
  GLOBE.g.visible = gw > 0.01; GLOBE.g.traverse(o => { if (o.material && o.material.userData.op != null) { o.material.opacity = o.material.userData.op * Math.min(1, gw * 1.6); if (o.material.uniforms && o.material.uniforms.k) o.material.uniforms.k.value = Math.min(1, gw * 1.6); } });
  scene.fog = (gw > 0.05 || ST.earthOn) ? null : FOG; SEA = SEA || scene.children.find(o => o.geometry && o.geometry.type === "CircleGeometry"); if (SEA) SEA.visible = gw < 0.05 && !ST.earthOn;
  uni.uLightK.value = 1 - 0.55 * CH.reduce((m, ch, k) => (ch.g.children.length && !ch.globe) ? Math.max(m, 1 - Math.abs(c - k) * 1.5) : m, 0);
  if (ST.explore) { leader(null); return; }
  const act = Math.round(c), ca = CH[act]; dimTo = (ca.g.children.length && !ca.globe) || ca.side ? 1 : 0;
  if (act !== ST.active) { ST.active = act;
    if (ca.layer) setLayer(ca.layer); else if (cur && layers[cur]) { layers[cur].g.visible = false; layers[cur].off && layers[cur].off(); cur = null; }
    if (ca.side) showSide(ca.side, ca.geo); else hideSide();
    document.querySelectorAll("#dots button").forEach((b, k) => b.classList.toggle("on", k === act));
    CH.forEach((ch, k) => ch.el.classList.toggle("act", k === act)); }
  // 鏡頭：目標線性移動，距離用對數內插，方向平滑轉，停留時慢慢晃
  const _ca = CH[Math.floor(c)], _cb = CH[Math.min(N - 1, Math.floor(c) + 1)], _ce = c - Math.floor(c);
  let cm = camBlend(_ca.cam, _cb.cam, _ce, (!!_ca.globe) !== (!!_cb.globe) ? (_cb.globe ? 1 : -1) : 0);   // 進出地球：先拉高再轉過去，不要穿過地底
  const ik = easeIO(introTick()); if (ik < 1) cm = camBlend(INTRO_CAM, cm, ik);
  if (INTRO.on && INTRO.ek != null && INTRO.ek < 1) cm = camBlend(earthCam(), INTRO_CAM, easeIO(INTRO.ek));   // 開場：從太空縮到台灣
  const tgt = cm.tgt, dir = cm.dir.applyAxisAngle(V(0, 1, 0), Math.sin(T * 0.12) * 0.035), dist = cm.dist;
  controls.target.copy(tgt); camera.position.copy(tgt).addScaledVector(dir, dist);
  { const lim = gw > 0.05 ? -1e9 : 2 + dist * 0.05; if (camera.position.y < lim) { const dy = lim - camera.position.y; camera.position.y += dy; controls.target.y += dy; } }   // 換章時鏡頭不能鑽到地底（會看到一片咖啡色）
  { const nr = Math.min(40, Math.max(0.5, dist * 0.0012)); if (Math.abs(nr - camera.near) > 0.01) { camera.near = nr; camera.updateProjectionMatrix(); } }
  // 文字在左、圖表在右、台灣在中間；手機：圖表在上、文字在下
  if (MOBILE) camera.setViewOffset(innerWidth, innerHeight, 0, innerHeight * (act === 0 ? 0.04 : 0.1), innerWidth, innerHeight);   // 手機：主體放在上方圖表條和下方文字之間
  else camera.setViewOffset(innerWidth, innerHeight, -innerWidth * 0.03, 0, innerWidth, innerHeight);
  fly = null;
  leader(Math.abs(c - act) < 0.15 ? ST.sideGeo : null);
}
// 兩個鏡頭之間：目標線性移動，距離用對數內插，方向平滑轉
function camBlend(a, b, e, g = 0) {
  const et = g > 0 ? e * e * e : g < 0 ? 1 - Math.pow(1 - e, 3) : e, ed = g > 0 ? Math.sqrt(e) : g < 0 ? 1 - Math.sqrt(1 - e) : e;
  const tgt = a.tgt.clone().lerp(b.tgt, et), d0 = a.dir ? a.dir.clone().multiplyScalar(a.dist) : a.pos.clone().sub(a.tgt), d1 = b.dir ? b.dir.clone().multiplyScalar(b.dist) : b.pos.clone().sub(b.tgt);
  const L0 = d0.length(), L1 = d1.length(), dist = Math.exp(Math.log(L0) + (Math.log(L1) - Math.log(L0)) * (typeof ed === 'number' ? ed : e));
  const dir = d0.normalize().lerp(d1.normalize(), e).normalize();
  return { tgt, dir, dist, pos: tgt.clone().addScaledVector(dir, dist) };
}
// 圖表連回地點的細線
function leader(geo) {
  const ln = $("leader"), lg = $("leaderG"); if (!geo || !$("side").classList.contains("on")) { lg.style.opacity = 0; return; }
  _sp.copy(gp(geo[0], geo[1], 0.3)).project(camera);
  const x = (_sp.x + 1) / 2 * innerWidth, y = (1 - _sp.y) / 2 * innerHeight, r = $("side").getBoundingClientRect();
  const sx = MOBILE ? r.left + r.width / 2 : r.left, sy = MOBILE ? r.bottom : r.top + 28;
  ln.setAttribute("x1", sx); ln.setAttribute("y1", sy); ln.setAttribute("x2", x); ln.setAttribute("y2", y);
  $("leaderDot").setAttribute("cx", x); $("leaderDot").setAttribute("cy", y); lg.style.opacity = 1;
}
