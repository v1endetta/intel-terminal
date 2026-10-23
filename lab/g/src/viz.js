
/* ---- 卡片主圖：每張卡先用一張圖講「這張在說什麼」，文字只補原因 ----
   走勢＝線、比較＝正負長條、占比＝甜甜圈、位置＝台灣小地圖、分量＝泡泡、離門檻多遠＝子彈圖 */
const VZ_G = "rgba(255,255,255,.09)", VZ_M = "#8e8e93";
const vzFig = (svg, cap) => svg ? `<figure class="vz">${svg}${cap ? `<figcaption>${cap}</figcaption>` : ""}</figure>` : "";
const vzF = (v, d = 1) => v == null || !isFinite(v) ? "—" : (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : (+v).toFixed(d));

// 正負走勢：0 以上綠、以下紅
function vzDiverge(vals, o = {}) {
  vals = clean(vals); if (vals.length < 3) return "";
  const W = 320, H = o.h || 96, p = 6, mx = Math.max(o.min || 0.1, ...vals.map(Math.abs)), sx = (W - p * 2) / (vals.length - 1), y = v => H / 2 - v / mx * (H / 2 - p), id = "vz" + (++SVGID);
  const pts = vals.map((v, i) => [p + i * sx, y(v)]), d = pts.map((q, i) => (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1)).join(" "), L = pts[pts.length - 1], area = `${d} L${L[0].toFixed(1)} ${H / 2} L${p} ${H / 2} Z`;
  return `<svg viewBox="0 0 ${W} ${H + 16}" role="img" aria-label="${esc(o.label || "走勢")}"><defs><clipPath id="${id}a"><rect width="${W}" height="${H / 2}"/></clipPath><clipPath id="${id}b"><rect y="${H / 2}" width="${W}" height="${H / 2}"/></clipPath></defs>
    <line x1="${p}" x2="${W - p}" y1="${H / 2}" y2="${H / 2}" stroke="${VZ_G}"/>
    <path d="${area}" fill="${UPH}" opacity=".2" clip-path="url(#${id}a)"/><path d="${area}" fill="${DNH}" opacity=".2" clip-path="url(#${id}b)"/>
    <path d="${d}" fill="none" stroke="${UPH}" stroke-width="1.8" stroke-linejoin="round" clip-path="url(#${id}a)"/><path d="${d}" fill="none" stroke="${DNH}" stroke-width="1.8" stroke-linejoin="round" clip-path="url(#${id}b)"/>
    <circle cx="${L[0].toFixed(1)}" cy="${L[1].toFixed(1)}" r="7" fill="${tone(vals[vals.length - 1])}" opacity=".25"/><circle cx="${L[0].toFixed(1)}" cy="${L[1].toFixed(1)}" r="3.4" fill="${tone(vals[vals.length - 1])}"/>
    <text x="${p}" y="11" class="vzt">${esc(o.hi || "")}</text><text x="${p}" y="${H - 3}" class="vzt">${esc(o.lo || "")}</text>
    <text x="${p}" y="${H + 13}" class="vzt">${esc(o.from || "")}</text><text x="${W - p}" y="${H + 13}" text-anchor="end" class="vzt">${esc(o.to || "最新")}</text></svg>`;
}
// 小走勢（放在一段文字旁邊）
function vzSpark(vals, color, w = 96, h = 28) {
  vals = clean(vals); if (vals.length < 3) return "";
  const mn = Math.min(...vals), mx = Math.max(...vals), sx = (w - 4) / (vals.length - 1), y = v => h - 3 - (v - mn) / ((mx - mn) || 1) * (h - 6);
  const d = vals.map((v, i) => (i ? "L" : "M") + (2 + i * sx).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
  return `<svg class="vzs" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/><circle cx="${(2 + (vals.length - 1) * sx).toFixed(1)}" cy="${y(vals[vals.length - 1]).toFixed(1)}" r="2.6" fill="${color}"/></svg>`;
}
// 正負長條（中線對齊）：漲綠跌紅
function vzDivBars(rows, unit = "%") {
  rows = rows.filter(r => r && r.v != null && isFinite(r.v)); if (!rows.length) return "";
  const mx = Math.max(...rows.map(r => Math.abs(r.v))) || 1;
  return `<div class="vzd">${rows.map(r => { const w = Math.abs(r.v) / mx * 50, c = r.color || tone(r.v);
    return `<div class="vzd-r"><span class="vzd-n">${esc(r.name)}</span><span class="vzd-t"><i style="${r.v >= 0 ? `left:50%` : `right:50%`};width:${w.toFixed(1)}%;background:${c}"></i></span><span class="vzd-v" style="color:${c}">${esc(r.txt ?? ((r.v >= 0 ? "+" : "−") + vzF(Math.abs(r.v), 2) + unit))}</span></div>`; }).join("")}</div>`;
}
// 甜甜圈＋圖例
function vzDonut(parts, center, sub) {
  parts = parts.filter(x => x.v > 0); const tot = parts.reduce((a, x) => a + x.v, 0); if (!tot) return "";
  const R = 46, r = 30, cx = 56, cy = 56; let a0 = -Math.PI / 2;
  const arcs = parts.map(x => { const a1 = a0 + x.v / tot * Math.PI * 2, lg = a1 - a0 > Math.PI ? 1 : 0, P1 = [cx + R * Math.cos(a0), cy + R * Math.sin(a0)], P2 = [cx + R * Math.cos(a1), cy + R * Math.sin(a1)], Q1 = [cx + r * Math.cos(a1), cy + r * Math.sin(a1)], Q2 = [cx + r * Math.cos(a0), cy + r * Math.sin(a0)];
    const path = parts.length === 1 ? `M${cx - R} ${cy}A${R} ${R} 0 1 1 ${cx + R} ${cy}A${R} ${R} 0 1 1 ${cx - R} ${cy}M${cx - r} ${cy}A${r} ${r} 0 1 0 ${cx + r} ${cy}A${r} ${r} 0 1 0 ${cx - r} ${cy}Z`
      : `M${P1[0].toFixed(2)} ${P1[1].toFixed(2)}A${R} ${R} 0 ${lg} 1 ${P2[0].toFixed(2)} ${P2[1].toFixed(2)}L${Q1[0].toFixed(2)} ${Q1[1].toFixed(2)}A${r} ${r} 0 ${lg} 0 ${Q2[0].toFixed(2)} ${Q2[1].toFixed(2)}Z`;
    a0 = a1; return `<path d="${path}" fill="${x.color}" stroke="#121317" stroke-width="1.5" fill-rule="evenodd"/>`; }).join("");
  return `<div class="vzn"><svg viewBox="0 0 112 112" width="112" height="112" role="img" aria-label="占比">${arcs}<text x="56" y="56" text-anchor="middle" class="vzc">${esc(center)}</text><text x="56" y="71" text-anchor="middle" class="vzt">${esc(sub || "")}</text></svg>`
    + `<ul class="vzl">${parts.map(x => `<li><i style="background:${x.color}"></i>${esc(x.name)}<b>${x.v}</b></li>`).join("")}</ul></div>`;
}
// 台灣小地圖：縣市輪廓＋點
function vzTaiwan(pts) {
  if (typeof COUNTIES === "undefined" || !COUNTIES.length) return "";
  const L0 = 119.3, L1 = 122.1, A0 = 21.85, A1 = 25.35, H = 210, W = Math.round(H * (L1 - L0) * Math.cos(23.6 * Math.PI / 180) / (A1 - A0));
  const X = lo => ((lo - L0) / (L1 - L0) * W).toFixed(1), Y = la => ((A1 - la) / (A1 - A0) * H).toFixed(1), inb = ([lo, la]) => lo >= L0 && lo <= L1 && la >= A0 && la <= A1;
  const paths = COUNTIES.map(c => (c.rings || []).filter(r => r.length > 2 && inb(r[0])).map(r => { const k = Math.max(1, Math.floor(r.length / 120)); return "M" + r.filter((_, i) => i % k === 0).map(q => X(q[0]) + " " + Y(q[1])).join("L") + "Z"; }).join("")).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="vzm" role="img" aria-label="台灣各縣市"><path d="${paths}" fill="rgba(255,255,255,.06)" stroke="rgba(255,255,255,.22)" stroke-width=".6"/>`
    + pts.filter(q => q.ll && inb(q.ll)).map(q => `<circle cx="${X(q.ll[0])}" cy="${Y(q.ll[1])}" r="${q.r || 4}" fill="${q.color}" opacity="${q.op ?? 0.95}" stroke="#121317" stroke-width="1"/>`).join("") + `</svg>`;
}
// 泡泡圖：x＝影響台灣、y＝多新、大小＝幾家報
function vzBubbles(xs, colOf) {
  xs = xs.filter(x => x.at); if (!xs.length) return "";
  const W = 320, H = 170, l = 8, r = 8, t = 12, b = 26, now = Date.now(), h0 = x => Math.max(0, (now - new Date(x.at)) / 36e5), hm = Math.max(6, ...xs.map(h0)), hrs = x => Math.min(hm, h0(x));
  const X = (x, i) => l + 14 + Math.min(4.2, Math.max(-0.2, (x.tw || 0) + ((i * 37) % 9 - 4) * 0.09)) / 4 * (W - l - r - 28), Y = (x, i) => t + hrs(x) / hm * (H - t - b - 8) + ((i * 53) % 7) * 1.3;
  const dots = xs.map((x, i) => ({ x, i, cx: X(x, i), cy: Y(x, i), rr: 5 + 3.5 * Math.min(5, (x.n_src || 1) - 1) + (i < 3 ? 2 : 0) })).reverse();
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="新聞分量與對台灣的影響">`
    + [0, 1, 2, 3, 4].map(k => `<line x1="${(l + 14 + k / 4 * (W - l - r - 28)).toFixed(1)}" x2="${(l + 14 + k / 4 * (W - l - r - 28)).toFixed(1)}" y1="${t}" y2="${H - b}" stroke="${VZ_G}"/>`).join("")
    + dots.map(d => `<circle cx="${d.cx.toFixed(1)}" cy="${d.cy.toFixed(1)}" r="${d.rr.toFixed(1)}" fill="${colOf(d.x)}" opacity="${d.i < 8 ? 0.9 : 0.35}" stroke="#121317" stroke-width="1"/>${d.i < 8 ? `<text x="${d.cx.toFixed(1)}" y="${(d.cy + 3.5).toFixed(1)}" text-anchor="middle" class="vzb">${d.i + 1}</text>` : ""}`).join("")
    + `<text x="${l}" y="${H - 8}" class="vzt">無關</text><text x="${W / 2}" y="${H - 8}" text-anchor="middle" class="vzt">→ 越右越影響台灣</text><text x="${W - r}" y="${H - 8}" text-anchor="end" class="vzt">重大</text>`
    + `<text x="${W - r}" y="${t - 2}" text-anchor="end" class="vzt">↑ 越上越新（最舊 ${Math.round(hm)} 小時前）</text></svg>`;
}
// 子彈圖：現在的位置 vs 推翻線
function vzBullet(g, col) {
  if (!g || g.now == null || g.kill == null) return "";
  if (g.off) col = "#8e8e93";   // 淡季：還不到判斷的時候，整條變灰
  const span = Math.max(Math.abs(g.now - g.kill) * 1.6, Math.abs(g.kill) * 0.25, g.min_span || 1), lo = Math.min(g.now, g.kill) - span * 0.25, hi = Math.max(g.now, g.kill) + span * 0.25;
  const P = v => ((v - lo) / (hi - lo) * 100).toFixed(1), k = P(g.kill), n = P(g.now), safeL = g.side > 0 ? k : 0, safeW = g.side > 0 ? 100 - k : k;
  return `<div class="vzg${g.off ? " off" : ""}"><span class="vzg-t"><i class="vzg-s" style="left:${safeL}%;width:${safeW}%"></i><i class="vzg-k" style="left:${k}%"></i><i class="vzg-n" style="left:${n}%;background:${col}"></i></span>`
    + `<span class="vzg-l"><b style="color:${col}">${esc(g.label)} ${vzF(g.now, g.d ?? 1)}${esc(g.unit || "")}</b>　推翻線 ${vzF(g.kill, g.d ?? 1)}${esc(g.unit || "")}${g.off ? `<br>${esc(g.off_txt || "淡季，還不到判斷的時候")}` : ""}</span></div>`;
}

/* ---- 洞見：每一則旁邊放它引用那項資料的小走勢 ---- */
function vzSeries(k) {
  const it = (key, f) => (items(key).find(f) || {}), D = P[k] || {};
  const M = {
    fear: () => ["VIX", it("fear", x => x.sym === "^VIX").spark], world: () => ["S&P 500", it("world", x => x.sym === "^GSPC").spark],
    taiex: () => ["加權指數", hist("taiex", "TAIEX")], fx: () => ["美元兌台幣", it("fx", x => x.code === "USD").spark],
    commodities: () => ["WTI 原油", it("commodities", x => x.sym === "CL=F").spark], luxury: () => ["LVMH", it("luxury", x => x.sym === "MC.PA").spark],
    cards: () => ["刷卡年增", ((D.rows || [])[0] || {}).spark], cars: () => ["新車掛牌", (D.car || {}).spark], lead: () => ["領先指標", (D.lead || {}).spark],
    dlead: () => ["dalta 領先", (D.series || {}).B], credit: () => ["CCC 利差百分位", ((D.rows || []).find(r => r.id === "BAMLH0A3HYC") || {}).trend],
    consume: () => ["零售業營業額", ((D.focus || [])[0] || {}).spark], power: () => ["備轉容量率", D.spark], mood: () => ["台灣情緒", D.spark_tw],
    housefc: () => ["台北房價指數", D.tpe_spark], aicycle: () => ["雲端資本支出", ((D.capex || {}).rows || []).map(r => r.total)],
    exports: () => ["電子零組件出口", ((D.goods || [])[0] || {}).spark], stress: () => ["退票比率", (D.bounce || {}).spark],
    logistics: () => ["Drewry WCI", ((D.drewry || {}).wci || {}).spark], gmacro: () => ["美國 CPI", it("gmacro", x => x.label === "CPI 年增").spark],
    bizlife: () => ["公司新設", D.new_spark], taxreg: () => ["營業登記新設", (D.monthly || []).map(x => x[1])], ptt: () => ["PTT 熱度", null],
  };
  try { if (M[k]) { const [n, v] = M[k](); if (clean(v).length >= 4) return { n, v: clean(v) }; } } catch (e) { /* 沒有就不畫 */ }
  let found = null; (function walk(o, dep) { if (found || !o || dep > 3) return; if (Array.isArray(o)) { if (o.length >= 6 && o.every(x => typeof x === "number")) found = o; else o.slice(0, 3).forEach(x => walk(x, dep + 1)); return; }
    if (typeof o === "object") for (const [kk, vv] of Object.entries(o)) { if (/spark|trend|series/i.test(kk) || dep < 2) walk(vv, dep + 1); if (found) return; } })(D, 0);
  return found ? { n: INS_SRC_ZH[k] || k, v: clean(found) } : null;
}
function vzInsRow(x) {
  const s = (x.src || []).map(vzSeries).find(Boolean); if (!s) return "";
  const c = s.v[s.v.length - 1] >= s.v[0] ? UPH : DNH;
  return `<div class="vzi">${vzSpark(s.v.slice(-40), c, 110, 30)}<span>${esc(s.n)}・近 ${Math.min(40, s.v.length)} 筆</span></div>`;
}

/* ---- 本週走向：每個方向一個箭頭＋第一個數字 ---- */
function vzWeekly(W) {
  const D = (W && W.dirs) || []; if (!D.length) return "";
  const ar = t => t === "up" ? ["↗", UPH] : t === "down" ? ["↘", DNH] : ["→", YLH];
  return `<div class="vzw">${D.map(d => { const [a, c] = ar(d.tone), w = String(d.why || ""), k = w.split(/[，,；;。]/)[0], rest = w.slice(k.length).replace(/^[，,；;。]/, "");
    return `<div class="vzw-r"><b class="vzw-a" style="color:${c}">${a}</b><div><b>${esc(d.t)}</b><span>${esc(k)}</span>${rest ? `<em>${esc(rest)}</em>` : ""}</div></div>`; }).join("")}</div>`;
}
function weeklyCard() {
  const W = P.weekly || {}, D = W.dirs || [];
  if (!D.length) return { html: sideHTML({ eyebrow: "走向 · 本週", title: "本週走向", body: '<p class="empty">每週一更新。</p>' }) };
  return { html: sideHTML({ eyebrow: `走向 · ${W.week || ""}`, title: W.headline || "本週走向", body: vzWeekly(W), foot: '<a href="/terminal/#p-weekly">終端機 ›</a>' }) };
}

/* ---- 台灣情緒：近幾次的分數走勢＋各來源 ---- */
function moodViz() {
  const M = P.mood || {}, s = M.spark_tw || hist("mood", "taiwan"), S = M.sources || {}, os = (M.overseas || {}).score, tw = (M.taiwan || {}).score;
  const rows = [{ name: "台灣整體", v: tw }, ...Object.entries(S).map(([k, v]) => ({ name: k, v: v.score })), { name: "海外", v: os }].filter(r => r.v != null).map(r => ({ ...r, txt: (r.v >= 0 ? "+" : "−") + Math.abs(r.v).toFixed(1) }));
  return vzFig(vzDiverge(s, { hi: "正面", lo: "負面", from: `${clean(s).length} 次前`, to: "現在", label: "台灣情緒走勢" })) + vzDivBars(rows, "");
}

/* ---- 地方新聞：每縣市一點（顏色＝類別）＋類別占比 ---- */
const NEWS_C = { 建設: "#64d2ff", 交通: "#ff9f0a", 災害: "#ff453a", 商業: "#30d158", 活動: "#bf5af2", 政策: "#ffd60a", 社會: "#aeaeb2", 政治: "#8e8e93" };
const newsCat = x => String(x.kc || (String(x.s || "").split("｜")[0]) || "其他");
function newsViz(list) {
  const cnt = {}; list.forEach(([, x]) => { const k = newsCat(x); cnt[k] = (cnt[k] || 0) + 1; });
  const parts = Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ name: k, v, color: NEWS_C[k] || "#636366" }));
  const pts = list.map(([k, x]) => { const c = COUNTIES.find(q => q.name === k), h = (Date.now() - new Date(x.at)) / 36e5; return c ? { ll: c.c, color: NEWS_C[newsCat(x)] || "#636366", r: h < 6 ? 5.5 : 4, op: h < 6 ? 1 : 0.6 } : null; }).filter(Boolean);
  return `<div class="vzrow">${vzTaiwan(pts)}${vzDonut(parts, `${list.length}`, "個縣市")}</div>`;
}

/* ---- 台灣還沒報：缺口分在哪幾類 ---- */
const GAP_C = ["#64d2ff", "#bf5af2", "#ffd60a", "#30d158", "#ff9f0a", "#ff375f", "#5e5ce6", "#aeaeb2"];
function gapViz(xs) {
  const cnt = {}; xs.forEach(x => { cnt[x.cat] = (cnt[x.cat] || 0) + 1; });
  const z = xs.filter(x => x.tw_n === 0).length;
  return vzDonut(Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k, v], i) => ({ name: k, v, color: GAP_C[i % GAP_C.length] })), `${xs.length}`, "則") + `<p class="vzcap">${z} 則在台灣近 30 天中文新聞裡 0 報導</p>`;
}

/* ---- 全球股市：依漲跌排的正負長條 ---- */
function worldViz() {
  return vzDivBars(items("world").filter(x => x.chg_pct != null).sort((a, b) => b.chg_pct - a.chg_pct).map(x => ({ name: x.name, v: x.chg_pct })));
}

/* ---- 第二批：PTT、謠言、焦點新聞、補助徵件、美國政策 ---- */
// 小走勢列：名稱｜近期走勢｜比平常幾倍
function vzRatioRows(rows) {
  rows = rows.filter(r => clean(r.spark).length >= 6); if (!rows.length) return "";
  return `<div class="vzr">${rows.map(r => { const s = clean(r.spark), m = s.slice(0, -1).reduce((a, b) => a + b, 0) / (s.length - 1), x = m ? s[s.length - 1] / m : 1, c = x >= 1.5 ? "#ff9f0a" : x <= 0.67 ? "#64d2ff" : "#8e8e93";
    return `<div class="vzr-r"><span class="vzr-n">${esc(r.name)}</span>${vzSpark(s, c, 90, 24)}<b style="color:${c}">${x.toFixed(1)} 倍</b></div>`; }).join("")}</div>`;
}
function pttCard() {
  const B = ((P.ptt || {}).boards) || [];
  if (!B.length) return { html: sideHTML({ eyebrow: "輿情 · PTT", title: "PTT 哪個版比平常熱？", body: '<p class="empty">資料載入中。</p>' }) };
  const ratio = b => { const s = clean(b.spark), m = s.slice(0, -1).reduce((a, x) => a + x, 0) / Math.max(1, s.length - 1); return m ? s[s.length - 1] / m : 1; };
  const R = B.slice().sort((a, b) => ratio(b) - ratio(a)), top = R[0];
  return { html: sideHTML({ eyebrow: "輿情 · PTT 各版熱度", title: "哪個版比平常熱？", big: `${top.zh || top.board} ${ratio(top).toFixed(1)} 倍`, color: ratio(top) >= 1.5 ? "#ff9f0a" : NEU,
    body: vzRatioRows(R.slice(0, 10).map(b => ({ name: b.zh || b.board, spark: b.spark })))
      + `<p class="why">熱度是近期文章的推文量。倍數＝現在比這個版自己平常（近 ${clean(top.spark).length} 次）的平均，1.5 倍以上標橘色。</p>`
      + listHTML(R.slice(0, 3).flatMap(b => (b.top || []).slice(0, 1).map(t => ({ t: t.title, s: `${b.zh || b.board}・推 ${t.push}`, url: t.url })))),
    foot: '<a href="/terminal/#p-ptt">終端機 ›</a>' }) };
}
const COF_C = { "尚未查核": "#8e8e93", "含錯誤訊息": "#ff453a", "含正確訊息": "#30d158", "個人意見": "#ffd60a", "查證中": "#8e8e93" };
function cofactsCard() {
  const C = P.cofacts || {}, H = C.hot || [], all = H.concat(C.fresh || []), cnt = {};
  if (!H.length) return { html: sideHTML({ eyebrow: "輿情 · Cofacts", title: "大家在查證什麼？", body: '<p class="empty">資料載入中。</p>' }) };
  all.forEach(x => { const k = x.verdict || "查證中"; cnt[k] = (cnt[k] || 0) + 1; });
  const short = x => /^https?:\/\/\S+$/.test(String(x.text).trim()) ? `只有一個連結（${String(x.text).trim().replace(/^https?:\/\/(www\.)?/, "").split("/")[0]}）` : String(x.text).length > 42 ? String(x.text).slice(0, 42) + "…" : String(x.text);
  return { html: sideHTML({ eyebrow: "輿情 · Cofacts 真的假的", title: "大家在查證什麼？", big: `${(C.stats || {}).rumor || cnt["含錯誤訊息"] || 0} 則已確認含錯誤`, color: "#ff453a",
    body: vzDonut(Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ name: k, v, color: COF_C[k] || "#636366" })), `${all.length}`, "則")
      + `<p class="vzcap">大部分還沒人查核：被回報不等於是假的，但多人回報代表正在流傳。</p>`
      + listHTML(H.slice(0, 6).map(x => ({ t: short(x), s: `${x.verdict || "查證中"} · ${x.requests} 人回報`, url: x.url }))),
    foot: '<a href="/terminal/#p-cofacts">終端機 ›</a>' }) };
}
// 焦點新聞：上榜多久（越久＝話題越持久）
function gtopViz(xs) {
  const h = x => x.first ? Math.max(0, (Date.now() - new Date(x.first)) / 36e5) : 0;
  return `<div class="nvh">上榜多久（越長越持久）</div>` + barsHTML(xs.slice(0, 8).map(x => ({ name: `${x.rank}. ${String(x.t).slice(0, 9)}`, v: Math.max(0.1, h(x)), txt: h(x) < 1 ? "剛上榜" : h(x) < 24 ? `${Math.round(h(x))} 小時` : `${Math.round(h(x) / 24)} 天`, color: h(x) >= 12 ? "#64d2ff" : "#3a3a3c" })), { signed: false });
}
// 補助徵件：類別占比＋截止日時間軸
const GR_C = { "文化藝術與設計": "#bf5af2", "數位與 AI": "#64d2ff", "新創與產業": "#30d158", "青年與就業": "#ffd60a", "地方與社區": "#ff9f0a", "農業與環境": "#5e5ce6", "其他": "#8e8e93" };
function grantsViz(xs) {
  const cnt = {}; xs.forEach(x => { const k = x.cat || "其他"; cnt[k] = (cnt[k] || 0) + 1; });
  const now = Date.now(), d = x => x.due ? Math.ceil((new Date(x.due + "T23:59:59+08:00") - now) / 864e5) : null, due = xs.filter(x => d(x) != null && d(x) >= 0 && d(x) <= 30);
  const W = 320, H = 54, X = v => 10 + v / 30 * (W - 20);
  const tl = due.length ? `<div class="nvh">30 天內截止（${due.length}）</div><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="截止日"><line x1="10" x2="${W - 10}" y1="26" y2="26" stroke="rgba(255,255,255,.2)"/>`
    + [0, 7, 14, 21, 30].map(v => `<line x1="${X(v)}" x2="${X(v)}" y1="22" y2="30" stroke="rgba(255,255,255,.25)"/><text x="${X(v)}" y="46" text-anchor="middle" class="vzt">${v ? v + " 天" : "今天"}</text>`).join("")
    + due.map((x, i) => `<circle cx="${X(d(x)).toFixed(1)}" cy="${26 - (i % 3) * 7}" r="${(x.fit || 0) >= 2 ? 5.5 : 4}" fill="${GR_C[x.cat] || "#8e8e93"}" stroke="#121317" stroke-width="1"/>`).join("") + `</svg>` : "";
  return vzDonut(Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ name: k, v, color: GR_C[k] || "#636366" })), `${xs.length}`, "個徵件中") + tl;
}
// 美國政策：近 30 天每個來源一條泳道，台灣相關的標黃
function uspViz(D) {
  const I = (D.items || []).concat((D.bills || []).map(b => ({ src: "國會", date: b.date, tw: b.tw, hot: b.moved })));
  const lanes = ["USTR", "BIS", "ITA", "國會"], lane = s => s.startsWith("USTR") ? 0 : s === "BIS" ? 1 : s === "ITA" ? 2 : s === "國會" ? 3 : -1;
  const now = Date.parse(new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10)), W = 320, H = 116, L = 46, X = dd => L + (1 - Math.min(30, Math.max(0, (now - Date.parse(dd)) / 864e5)) / 30) * (W - L - 8);
  const pts = I.filter(x => x.date && lane(x.src) >= 0 && (now - Date.parse(x.date)) / 864e5 <= 30);
  if (!pts.length) return "";
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="近 30 天美國政策動作">` + lanes.map((n, i) => `<text x="0" y="${18 + i * 24}" class="vzt">${n}</text><line x1="${L}" x2="${W - 8}" y1="${14 + i * 24}" y2="${14 + i * 24}" stroke="rgba(255,255,255,.08)"/>`).join("")
    + pts.map((x, i) => `<circle cx="${X(x.date).toFixed(1)}" cy="${14 + lane(x.src) * 24 + ((i * 5) % 3 - 1) * 3}" r="${x.tw ? 5.5 : x.hot ? 4.2 : 3}" fill="${x.tw ? "#ffd60a" : x.hot ? "#ff9f0a" : "#636366"}" stroke="#121317" stroke-width="1" opacity=".95"/>`).join("")
    + `<text x="${L}" y="${H - 4}" class="vzt">30 天前</text><text x="${W - 8}" y="${H - 4}" text-anchor="end" class="vzt">今天</text></svg>`;
}

/* ---- 民調：持續追蹤的走勢＋各選區最新一筆 ---- */
function pollsCard() {
  const D = P.polls || {}, T = D.tracks || [], R = D.races || {}, L = (D.latest || []).filter(x => !x.race);
  if (!T.length && !Object.keys(R).length && !L.length) return { html: sideHTML({ eyebrow: "輿情 · 民調", title: "抽樣民意怎麼說？", body: '<p class="empty">民調下一輪更新後出現（每 3 小時一次）。</p>' }) };
  const t0 = T[0], last = t0 ? t0.pts[t0.pts.length - 1] : null;
  const trk = T.slice(0, 4).map(t => { const v = t.pts.map(p => p.v), l = t.pts[t.pts.length - 1];
    return `<div class="vzr-r"><span class="vzr-n">${esc(t.subject)}・${esc(t.metric)}</span>${vzSpark(v, v[v.length - 1] >= v[0] ? UPH : DNH, 90, 24)}<b>${l.v}%</b></div>`; }).join("");
  const rc = Object.entries(R).slice(0, 5).map(([k, v]) => { const sh = v.filter(x => x.kind !== "差距").slice(0, 2), gp = v.find(x => x.kind === "差距");
    return { t: k, s: [sh.map(x => `${x.subject} ${x.value}%`).join(" vs "), gp ? `${gp.subject}領先${gp.vs || ""} ${gp.value} 個百分點` : "", (v[0] || {}).org].filter(Boolean).join("・"), url: (v[0] || {}).url }; });
  return { html: sideHTML({ eyebrow: "輿情 · 民調（新聞標題 AI 擷取）", title: "抽樣民意怎麼說？", big: last ? `${t0.subject}${t0.metric} ${last.v}%` : `${L.length} 則民調`, color: "#64d2ff",
    body: (trk ? `<div class="nvh">持續追蹤（同一題出現 3 次以上）</div><div class="vzr">${trk}</div>` : "")
      + (rc.length ? `<div class="nvh">選舉</div>` + listHTML(rc) : "")
      + (L.length ? `<div class="nvh">最新議題民調</div>` + listHTML(L.slice(0, 6).map(x => ({ t: `${x.subject}・${x.metric} ${x.value}${x.kind === "差距" ? " 個百分點" : "%"}`, s: [x.org || x.src, (x.at || "").slice(5, 10).replace("-", "/")].filter(Boolean).join("・"), url: x.url }))) : "")
      + `<p class="why">社群情緒是會說話的人，民調是抽樣過的全體。兩邊方向不一樣時最值得注意。不同調查單位的題目和方法不同，跨單位不能直接比數字。</p>`,
    foot: '<a href="/terminal/#p-polls">終端機 ›</a>' }) };
}

/* ---- 台灣隱形冠軍：各經濟體近 3 月年增（正負長條）＋非 AI 指數走勢 ---- */
function champCard() {
  const D = P.champions || {}, R = D.rows || [];
  if (!R.length) return { html: sideHTML({ eyebrow: "總經 · 台灣隱形冠軍", title: "非 AI 的台商做得怎樣？", body: '<p class="empty">資料載入中。</p>' }) };
  const v = D.index || 0;
  return { html: sideHTML({ eyebrow: `總經 · 台灣隱形冠軍 · ${ymTxt(D.month)}`, title: "非 AI 的台商做得怎樣？", big: `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`, chg: `${D.up_n}／${D.n} 類成長`, color: v >= 0 ? UPH : DNH,
    body: vzDivBars(R.map(r => ({ name: r.name + (r.ai ? "＊" : ""), v: r.yoy3, color: r.ai ? "#636366" : null })))
      + `<div class="nvh">非 AI 指數近 3 年（近 3 月年增）</div>` + vzFig(vzDiverge(D.index_spark || [], { min: 3, from: (D.index_t || [])[0] || "", to: ymTxt(D.month) }))
      + `<p class="why">運動鞋、自行車、高爾夫、汽車零件這些台灣稱霸全球的製造業，工廠多在越南、印尼、中國，出口統計看不到，看台商自己的營收才看得到。＊被動元件近期被 AI 伺服器拉抬，照列但不算進指數。</p>`,
    foot: '<a href="/terminal/#p-champions">終端機看每家公司 ›</a>' }) };
}

/* ---- 台灣內需產業：營業額（錢）× 新設（人）的四象限 ---- */
function sectorsViz(R) {
  R = R.filter(r => r.yoy3 != null && r.new_yoy != null); if (!R.length) return "";
  const W = 320, H = 210, c = 160, m = 103, sx = Math.max(10, ...R.map(r => Math.abs(r.yoy3))) * 1.15, sy = Math.max(10, ...R.map(r => Math.abs(r.new_yoy))) * 1.15;
  const X = v => c + v / sx * (c - 14), Y = v => m - v / sy * (m - 16);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="各產業的錢和人"><line x1="8" x2="${W - 8}" y1="${m}" y2="${m}" stroke="rgba(255,255,255,.2)"/><line x1="${c}" x2="${c}" y1="6" y2="${H - 6}" stroke="rgba(255,255,255,.2)"/>`
    + `<text x="${W - 8}" y="16" text-anchor="end" class="vzt">錢和人都進來</text><text x="8" y="${H - 8}" class="vzt">錢和人都退</text><text x="${W - 8}" y="${H - 8}" text-anchor="end" class="vzt">錢進、人沒跟上</text><text x="8" y="16" class="vzt">人進、錢沒跟上</text>`
    + R.map(r => `<circle cx="${X(r.yoy3).toFixed(1)}" cy="${Y(r.new_yoy).toFixed(1)}" r="5" fill="${r.yoy3 >= 0 ? UPH : DNH}" stroke="#121317" stroke-width="1"/>${X(r.yoy3) > W - 80 ? `<text x="${(X(r.yoy3) - 7).toFixed(1)}" y="${(Y(r.new_yoy) + 4).toFixed(1)}" text-anchor="end" class="vzl2">${esc(r.name)}</text>` : `<text x="${(X(r.yoy3) + 7).toFixed(1)}" y="${(Y(r.new_yoy) + 4).toFixed(1)}" class="vzl2">${esc(r.name)}</text>`}`).join("")
    + `<text x="${c + 4}" y="${H - 20}" class="vzt">→ 營業額</text><text x="${c + 4}" y="28" class="vzt">↑ 新設</text></svg>`;
}
function sectorsCard() {
  const D = P.twsectors || {}, R = D.rows || [];
  if (!R.length) return { html: sideHTML({ eyebrow: "總經 · 台灣內需產業", title: "錢和人往哪個產業走？", body: '<p class="empty">資料載入中。</p>' }) };
  return { html: sideHTML({ eyebrow: `總經 · 台灣內需產業 · 發票 ${ymTxt(D.month)}`, title: "錢和人往哪個產業走？",
    body: vzFig(sectorsViz(R), "橫軸：營業額近 3 月年增（錢）　縱軸：新設登記近 6 月（人，已扣掉全體）")
      + listHTML(R.map(r => ({ t: `${r.name}　${r.yoy3 != null ? pct(r.yoy3, 1) : "—"}・${r.verdict}`, s: [(r.parts || []).length > 1 ? r.parts.map(p => `${p.name} ${p.yoy3 != null ? pct(p.yoy3, 0) : "—"}`).join("、") : "", ...(r.extra || [])].filter(Boolean).join(" · ") }))),
    foot: '<a href="/terminal/#p-sectors">終端機 ›</a>' }) };
}
