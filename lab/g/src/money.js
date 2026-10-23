
/* ---- 錢花在哪、生意與人口的生滅：刷卡（全國、各縣市、網購）、公司生滅、新車、出生 ---- */
LENS.cards = { n: "刷卡", c: "#ffd60a" };
LENS.birth = { n: "出生", c: "#ff9ec7" };
const CD = () => P.cards || {};
const cdC = name => (CD().counties || []).find(r => sameC(r.c, name));
const cdTot = () => ((CD().rows || []).find(r => r.cat === "總計") || {}).yoy3;
const nI = v => Math.round(+v || 0).toLocaleString("en-US");
const ymTxt = ym => { const s = String(ym || "").replace("-", ""); return s.length >= 6 ? `${s.slice(0, 4)}/${+s.slice(4, 6)}` : ""; };
const cdEmpty = () => ({ eyebrow: "台灣 · 刷卡", title: "錢花在哪裡？", big: "載入中", color: LENS.cards.c, body: '<p class="empty">刷卡資料下一輪更新後出現（每天一次）。</p>' });
TW_VIEW.cards = () => {
  const D = CD(), R = D.counties || [], tot = cdTot();
  if (!(D.rows || []).length) { navCounties(() => ({ op: 0.2 })); return cdEmpty(); }
  if (R.length) { const mx = Math.max(1, ...R.map(r => Math.abs(r.y3 - (tot || 0))));
    navCounties(c => { const r = cdC(c.name); if (!r) return { dim: true, op: 0.12 }; const d = r.y3 - (tot || 0);
      return { col: new THREE.Color(d >= 0 ? UPH : DNH), op: 0.2 + 0.7 * Math.sqrt(Math.abs(d) / mx), sub: pct(r.y3, 1), dot: d >= 0 ? UPH : DNH, prio: 2 + r.amt / 400 }; }); }
  else navCounties(() => ({ op: 0.2 }));
  const rows = (D.rows || []).filter(r => r.cat !== "總計"), ec = D.ec || [], ect = ec.find(r => r.cat === "總計");
  return { eyebrow: `台灣 · 信用卡消費 · ${ymTxt(D.month)}`, title: "錢花在哪裡？", big: tot != null ? `近 3 月 ${pct(tot, 1)}` : "", color: LENS.cards.c,
    body: `<p class="why">聯合信用卡中心的全台刷卡金額，近 3 個月合計比去年同期（避開單月大額）。刷卡每年本來就在長，所以地圖顏色看「比全台多長或少長」：綠＝比全台熱、紅＝比全台冷。縣市依持卡人帳單地址。</p>`
      + `<div class="nvh">各類別 · 比全台多長幾個百分點</div>` + barsHTML(rows.map(r => ({ name: r.cat, v: r.rel, txt: `${pct(r.yoy3, 1)}（${r.rel >= 0 ? "+" : "−"}${Math.abs(r.rel).toFixed(1)}）` })))
      + (ec.length ? `<div class="nvh">網購（信用卡付款）${ect && ect.share != null ? ` · 占刷卡 ${ect.share}%` : ""}</div>` + barsHTML(ec.filter(r => r.cat !== "總計").map(r => ({ name: r.cat, v: r.yoy3, txt: `${pct(r.yoy3, 1)}・${r.share != null ? "占 " + r.share + "%" : ""}` }))) : "")
      + (R.length ? `<div class="nvh">各縣市（點進去看類別）</div><ul class="lst nvl">${rankRows(R.map(r => [r.c, `${pct(r.y3, 1)}・${nf(r.amt)} 億／月${r.hot ? `・${r.hot[0]} 長最快` : ""}`, r.y3 >= (tot || 0) ? UPH : DNH]), "nc")}</ul>` : "") };
};
CITY_VIEW.cards = C => {
  navOutline(C); const r = cdC(C.name), tot = cdTot();
  if (!r) return { eyebrow: `${norm(C.name)} · 刷卡`, title: "這裡的人錢花在哪？", big: "", color: LENS.cards.c, body: `<p class="empty">${CD().counties ? "沒有這個縣市的資料。" : "資料載入中。"}</p>` };
  const cs = Object.entries(r.cats || {}).sort((a, b) => b[1] - a[1]), rk = (CD().counties || []).indexOf(r) + 1;
  return { eyebrow: `${norm(C.name)} · 信用卡消費 · 到 ${ymTxt(r.month)}`, title: "這裡的人錢花在哪？", big: `近 3 月 ${pct(r.y3, 1)}`, color: r.y3 >= (tot || 0) ? UPH : DNH,
    body: `<p class="why">帳單地址在${esc(norm(C.name))}的持卡人，每月刷 ${nf(r.amt)} 億；近 3 個月比去年同期 ${pct(r.y3, 1)}，全台是 ${tot != null ? pct(tot, 1) : "—"}，成長排第 ${rk}／${(CD().counties || []).length}。刷卡地點不一定在本縣市（網購、出差、旅遊都算）。</p>`
      + barsHTML(cs.map(([k, v]) => ({ name: k, v, txt: pct(v, 1) }))) };
};

// 公司生滅：全台每月新設與解散（經濟部），加上大類行業的淨增
function bizlifeCard() {
  const B = P.bizlife || {}; if (!B.month) return { html: sideHTML({ eyebrow: "訊號 · 公司生滅", title: "開的多還是關的多？", body: '<p class="empty">資料載入中。</p>' }) };
  const net = B.new - B.close, ind = (B.ind_major || []).filter(x => x.new + x.close >= 20);
  return { html: sideHTML({ eyebrow: `訊號 · 公司登記 · ${ymTxt(B.month)}`, title: "開的多還是關的多？", big: `淨增 ${nI(net)} 家`, color: net >= 0 ? UPH : DNH,
    body: `<p class="why">這個月新設 ${nI(B.new)} 家、解散撤銷 ${nI(B.close)} 家。近 3 個月新設比去年同期 ${B.new_y3 != null ? pct(B.new_y3, 1) : "—"}、解散 ${B.close_y3 != null ? pct(B.close_y3, 1) : "—"}；近 3 個月淨增 ${nI(B.net3)} 家，去年同期 ${nI(B.net3_ly)} 家。</p>`
      + `<div class="nvh">新設（綠）與解散（紅），近 36 個月</div>` + lineSVG(B.new_spark || [], UPH) + lineSVG(B.close_spark || [], DNH)
      + (ind.length ? `<div class="nvh">各行業淨增（${ymTxt(B.ind_month)}）</div>` + barsHTML(ind.slice(0, 6).concat(ind.slice(-3)).filter((x, i, a) => a.indexOf(x) === i).map(x => ({ name: x.name.replace(/業$/, ""), v: x.net, txt: `${x.net >= 0 ? "+" : "−"}${Math.abs(x.net)}` }))) : "")
      + `<p class="note">要看哪一區開、哪一區關，用「新公司」或「區域報告」。</p>`, foot: `<span>${esc(B.src || "")}</span>` }) };
}

// 新車領牌：自用小客車、機車
function carsCard() {
  const D = P.cars || {}, c = D.car, m = D.moto; if (!c) return { html: sideHTML({ eyebrow: "總經 · 新車", title: "大家還買車嗎？", body: '<p class="empty">資料載入中。</p>' }) };
  return { html: sideHTML({ eyebrow: `總經 · 新車領牌 · ${ymTxt(D.month)}`, title: "大家還買車嗎？", big: `自用小客車 ${c.y3 != null ? pct(c.y3, 1) : ""}`, color: tone(c.y3 || 0),
    body: `<p class="why">這個月自用小客車領牌 ${nI(c.v)} 輛（比去年同月 ${c.yoy != null ? pct(c.yoy, 1) : "—"}）${m ? `、機車 ${nI(m.v)} 輛（${m.yoy != null ? pct(m.yoy, 1) : "—"}）` : ""}。大筆消費最先縮手的就是買車，看近 3 個月合計比去年同期：小客車 ${c.y3 != null ? pct(c.y3, 1) : "—"}${m && m.y3 != null ? `、機車 ${pct(m.y3, 1)}` : ""}。</p>`
      + `<div class="nvh">自用小客車，近 25 個月</div>` + lineSVG((c.spark || []).filter(v => v != null), tone(c.y3 || 0))
      + (m ? `<div class="nvh">機車</div>` + lineSVG((m.spark || []).filter(v => v != null), tone(m.y3 || 0)) : ""), foot: `<span>${esc(D.src || "")}</span>` }) };
}

// 出生：各鄉鎮最近 12 個月出生登記，比前 12 個月
const BR = () => P.births || {};
const brTowns = C => (BR().towns || []).filter(r => sameC(r[0], C.name || C));
const brChg = r => r[3] ? Math.round((r[2] / r[3] - 1) * 1000) / 10 : null;
const brPer = () => BR().n_months >= 12 ? "近 12 個月" : `近 ${BR().n_months || 0} 個月`;
const brEmpty = () => ({ eyebrow: "台灣 · 出生", title: "哪裡還在生小孩？", big: "載入中", color: LENS.birth.c, body: '<p class="empty">出生資料第一次要分幾輪補齊，下一輪更新後出現。</p>' });
TW_VIEW.birth = () => {
  const T = BR().towns || []; if (!T.length) { navCounties(() => ({ op: 0.2 })); return brEmpty(); }
  const Cs = {}; for (const r of T) { const c = Cs[r[0]] = Cs[r[0]] || { n: 0, p: 0, ok: true }; c.n += r[2]; if (r[3] == null) c.ok = false; else c.p += r[3]; }
  const ks = Object.keys(Cs), ch = k => Cs[k].ok && Cs[k].p ? (Cs[k].n / Cs[k].p - 1) * 100 : null, mx = Math.max(1, ...ks.map(k => Math.abs(ch(k) || 0)));
  navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true, op: 0.12 }; const v = ch(k);
    return { col: new THREE.Color(v == null ? LENS.birth.c : v >= 0 ? UPH : DNH), op: 0.2 + 0.7 * Math.sqrt(Math.abs(v || 0) / mx), sub: `${nI(Cs[k].n)} 人${v != null ? " " + pct(v, 1) : ""}`, dot: v == null ? null : v >= 0 ? UPH : DNH, prio: 2 + Cs[k].n / 2e4 }; });
  const tot = ks.reduce((a, k) => a + Cs[k].n, 0), totp = ks.reduce((a, k) => a + Cs[k].p, 0), ok = BR().prev_ok;
  const up = ok ? T.filter(r => r[3] >= 100).map(r => [r, brChg(r)]).filter(x => x[1] > 0).sort((a, b) => b[1] - a[1]) : [];
  return { eyebrow: `台灣 · 出生登記 · ${brPer()}（到 ${ymTxt(BR().month)}）`, title: "哪裡還在生小孩？", big: `${nI(tot)} 人${ok && totp ? " " + pct((tot / totp - 1) * 100, 1) : ""}`, color: LENS.birth.c,
    body: `<p class="why">戶政事務所的出生登記，依登記地歸到鄉鎮。${ok ? "百分比是跟前 12 個月比；綠＝生得比去年多。" : "前 12 個月的資料還在補，暫時只有數量。"}新生兒多的地方，接下來幾年的托嬰、幼兒園、兒科、親子消費需求就在那裡。</p>`
      + (up.length ? `<div class="nvh">逆勢增加（前一年 100 人以上）</div><ul class="lst nvl">${up.slice(0, 6).map(([r, v]) => `<li data-nc="${esc(r[0])}" style="cursor:pointer"><span class="sdot" style="background:${v >= 0 ? UPH : DNH}"></span>${esc(norm(r[0]))} ${esc(r[1])}<span>${nI(r[2])} 人・${pct(v, 1)}</span></li>`).join("")}</ul>` : "")
      + `<div class="nvh">生最多的鄉鎮</div><ul class="lst nvl">${T.slice(0, 8).map(r => `<li data-nc="${esc(r[0])}" style="cursor:pointer">${esc(norm(r[0]))} ${esc(r[1])}<span>${nI(r[2])} 人${brChg(r) != null && ok ? "・" + pct(brChg(r), 1) : ""}</span></li>`).join("")}</ul>` };
};
CITY_VIEW.birth = C => {
  const ts = navOutline(C), R = brTowns(C), view = NAV.viewD || 60;
  if (!BR().towns) return brEmpty();
  const mx = Math.max(1, ...R.map(r => r[2])), ok = BR().prev_ok;
  R.forEach((r, i) => { const t = ts.find(x => x.name === r[1]); const v = brChg(r); if (t && r[2]) navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `${nI(r[2])} 人`, 6 - i * 0.2, !ok || v == null ? LENS.birth.c : v >= 0 ? UPH : DNH); });
  townPills(ts, new Set(R.map(r => r[1])));
  const n = R.reduce((a, r) => a + r[2], 0), p = R.reduce((a, r) => a + (r[3] || 0), 0);
  return { eyebrow: `${norm(C.name)} · 出生登記 · ${brPer()}`, title: "哪一區生最多？", big: `${nI(n)} 人${ok && p ? " " + pct((n / p - 1) * 100, 1) : ""}`, color: LENS.birth.c,
    body: `<p class="why">光柱越高生越多${ok ? "；綠＝比前 12 個月多、紅＝比較少" : ""}。</p><ul class="lst nvl">${rankRows(R.slice(0, 12).map(r => [r[1], `${nI(r[2])} 人${ok && brChg(r) != null ? "・" + pct(brChg(r), 1) : ""}・上個月 ${r[4]} 人`]), "nt")}</ul>` };
};
STREET_VIEW.birth = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
  const R = brTowns(T.county), me = R.find(r => r[1] === T.name), ok = BR().prev_ok;
  if (!me) return { eyebrow: `${norm(T.county)} › ${T.name} · 出生`, title: "這一區生多少？", big: T.name, color: LENS.birth.c, body: `<p class="empty">${BR().towns ? "這一區沒有資料。" : "資料載入中。"}</p>` };
  const v = brChg(me);
  return { eyebrow: `${norm(T.county)} › ${T.name} · 出生登記 · ${brPer()}`, title: "這一區生多少？", big: `${nI(me[2])} 人`, chg: ok && v != null ? `比前 12 個月 ${pct(v, 1)}` : "", color: ok && v != null ? tone(v) : LENS.birth.c,
    body: `<p class="why">在${esc(norm(T.county))}排第 ${R.indexOf(me) + 1}／${R.length}；最近一個月 ${me[4]} 人。</p>` };
};

// 建照（未來要蓋的量）與使照（蓋好可交屋的量）：全台，近 3 個月合計比去年同期，依用途分樓地板面積
function permitsCard() {
  const D = P.permits || {}, B = D.build || [], U = D.use || [];
  if (!B.length) return { html: sideHTML({ eyebrow: "總經 · 建照", title: "接下來要蓋多少？", body: '<p class="empty">資料載入中。</p>' }) };
  const g = (L, h) => L.find(x => x.h === h) || {}, bn = g(B, "件數(件)"), ba = g(B, "總樓地板面積(平方公尺)"), un = g(U, "件數(件)"), ua = g(U, "總樓地板面積(平方公尺)"), bh = g(B, "住宿類(H類)/住宅");
  const SH = h => h.replace(/^住宿類\(H類\)\//, "").replace(/\(.類\)|（.類）/, "").replace("(含農業設施)", "").replace("、福利、更生類", "福利").replace("類", "");
  const types = L => L.filter(x => !/件數|總樓地板|工程造價/.test(x.h) && x.y3 != null && x.v >= 5000);
  const y = v => v == null ? "—" : pct(v, 1);
  return { html: sideHTML({ eyebrow: `總經 · 建照與使照 · ${ymTxt(D.month)}`, title: "接下來要蓋多少？", big: `建照面積 ${y(ba.y3)}`, color: tone(ba.y3 || 0),
    body: `<p class="why">建照是「準備要蓋」：發照後一兩年才完工，是營建、建材、家具家電、搬家裝修需求的領先指標；使照是「蓋好可以交屋」。近 3 個月合計比去年同期：建照 ${y(bn.y3)}（件數）、樓地板面積 ${y(ba.y3)}，其中住宅 ${y(bh.y3)}；使照面積 ${y(ua.y3)}。</p>`
      + `<div class="nvh">建照樓地板面積・依用途</div>` + barsHTML(types(B).sort((a, b) => b.y3 - a.y3).map(x => ({ name: SH(x.h), v: x.y3, txt: `${y(x.y3)}・${nI(x.v / 3.30579)} 坪` })))
      + `<div class="nvh">建照件數，近 36 個月</div>` + lineSVG((bn.spark || []).filter(v => v != null), tone(bn.y3 || 0))
      + (U.length ? `<div class="nvh">使照樓地板面積・依用途</div>` + barsHTML(types(U).sort((a, b) => b.y3 - a.y3).map(x => ({ name: SH(x.h), v: x.y3, txt: `${y(x.y3)}・${nI(x.v / 3.30579)} 坪` }))) : "")
      + `<p class="note">坪數是最新一個月；百分比是近 3 個月合計比去年同期，單月件數起伏大。</p>`, foot: `<span>${esc(D.src || "")}</span>` }) };
}

// 台灣還沒報：國外產業與日本消費媒體的新東西，台灣中文新聞近 30 天幾乎沒報
function gapCard() {
  const D = P.gap || {}, xs = D.items || [];
  if (!xs.length) return { html: sideHTML({ eyebrow: "走向 · 資訊落差", title: "國外在發生、台灣還沒報的", body: `<p class="empty">${D.n_read ? "這一輪沒有找到台灣幾乎沒報的新東西。" : "第一次判讀中，下一輪更新後出現。"}</p>` }) };
  const badge = n => n === 0 ? "台灣 0 則" : `台灣僅 ${n} 則`;
  const cats = [...new Set(xs.map(x => x.cat))];
  const li = x => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.zh || x.kw)}</a><b class="gapb${x.tw_n === 0 ? " z" : ""}">${badge(x.tw_n)}</b>`
    + `<span>${esc(x.src)}・${esc(navAgo(x.at))}・搜「${esc(x.kw)}」</span>`
    + (x.what ? `<span class="gapw">新在：${esc(x.what)}</span>` : "") + (x.land ? `<span>台灣缺：${esc(x.land)}</span>` : "") + `</li>`;
  return { html: sideHTML({ eyebrow: "走向 · 資訊落差 · 近 14 天", title: "國外在發生、台灣還沒報的", big: `${xs.length} 則`, color: "#64d2ff",
    body: gapViz(xs) + `<p class="why">從日本與歐美的產業、消費媒體挑出有新意的產品、服務和做法，再查台灣中文新聞近 30 天報過幾次，報得越少排越前面。沒人報不代表會紅，「台灣缺」那一行是落地前要先過的關。</p>`
      + cats.map(c => `<div class="nvh">${esc(c)}</div><ul class="lst gapl">${xs.filter(x => x.cat === c).slice(0, 6).map(li).join("")}</ul>`).join(""),
    foot: `<span>${esc(D.src || "")}</span>` }) };
}

// 用得上的開源：GitHub、Hugging Face 熱門裡，跟創意工作有關的
function ossCard() {
  const D = P.ossuse || {}, H = D.hot || [], PA = D.papers || [];
  if (!H.length && !PA.length) return { html: sideHTML({ eyebrow: "訊號 · AI 與開源", title: "AI 與開源這兩週", body: '<p class="empty">第一次判讀中，下一輪更新後出現。</p>' }) };
  const li = x => ({ t: (x.sig >= 3 ? "【重要】" : "") + (x.zh || x.name), s: `${x.src}・${x.cat || ""}${x.why ? `｜${x.why}` : ""}`, url: x.url });
  const pli = x => ({ t: x.zh || x.name, s: `▲${x.stars || 0}${x.org ? "・" + x.org : ""}${x.why ? `｜${x.why}` : ""}`, url: x.url });
  const top = H.filter(x => x.sig >= 3).length;
  return { html: sideHTML({ eyebrow: "訊號 · AI 與開源 · 近 14 天", title: "AI 與開源這兩週", big: top ? `${top} 件重要的事` : `${H.length} 個值得注意`, color: "#64d2ff",
    body: `<p class="why">GitHub 和 Hugging Face 的熱門，依對市場的意義排：大廠發布、新能力、爆紅被大量採用的在前面。論文是 HF Daily Papers 近 7 天讚數最高的。</p>`
      + (H.length ? `<div class="nvh">熱門專案</div>` + listHTML(H.slice(0, 8).map(li)) : "")
      + (PA.length ? `<div class="nvh">論文</div>` + listHTML(PA.slice(0, 5).map(pli)) : ""),
    foot: `<a href="/terminal/#p-ossuse">終端機看完整清單 ›</a>` }) };
}

// ---- 錢往哪走、哪裡會先斷 ----
// 信用利差：ICE 授權只放百分位
function creditCard() {
  const D = P.credit || {}, R = D.rows || [];
  if (!R.length) return { html: sideHTML({ eyebrow: "總經 · 信用利差", title: "借錢的人要多付多少？", body: '<p class="empty">資料載入中。</p>' }) };
  const hy = R.find(r => r.id === "BAMLH0A0HYM2") || R[0], col = p => p >= 70 ? DNH : p <= 30 ? UPH : NEU;
  return { html: sideHTML({ eyebrow: `總經 · 美國公司債利差 · 資料到 ${(hy.asof || "").slice(5).replace("-", "/")}`, title: "借錢的人要多付多少？", big: `第 ${hy.pct} 百分位`, color: col(hy.pct),
    body: `<p class="why">${esc(D.verdict || "")}。百分位是現在的利差在近 ${Math.round(hy.n_years || 3)} 年裡排第幾：越高＝市場越不敢借錢給體質差的公司，通常比股市先反應。</p>`
      + barsHTML(R.map(r => ({ name: r.name, v: r.pct, txt: `第 ${r.pct}（月前 ${r.pct20}）`, color: col(r.pct) })), { signed: false })
      + `<div class="nvh">高收益債百分位，近半年</div>` + lineSVG(hy.trend || [], col(hy.pct))
      + listHTML(R.map(r => ({ t: `${r.name}・${r.state}${r.fast ? "・短期快速擴大" : ""}`, s: r.what }))),
    foot: `<span>ICE BofA（經 FRED）；依授權只顯示百分位</span>` }) };
}
// 企業壓力：退票、減班休息
function stressCard() {
  const D = P.stress || {}, b = D.bounce || {}, f = D.furlough || {}, L = f.latest || {};
  if (!b.month && !L.v) return { html: sideHTML({ eyebrow: "總經 · 企業壓力", title: "哪裡先撐不住？", body: '<p class="empty">資料載入中。</p>' }) };
  return { html: sideHTML({ eyebrow: `總經 · 企業壓力`, title: "哪裡先撐不住？", big: L.v ? `減班休息 ${nI(L.v)} 人` : `退票比率 ${b.ratio_amt}%`, color: (D.signals || []).length ? "#ff9f0a" : UPH,
    body: `<p class="why">${esc(D.verdict || "")}。退票是公司付不出錢最早的痕跡；減班休息是工廠訂單不夠、先讓員工放無薪假。</p>`
      + (b.month ? `<div class="nvh">退票金額比率，近 24 個月（${ymTxt(b.month)} ${b.ratio_amt}%，比去年同月 ${b.amt_yoy != null ? pct(b.amt_yoy, 0) : "—"}）</div>` + lineSVG(b.spark || [], b.hi12 ? DNH : NEU) : "")
      + (L.v ? `<div class="nvh">減班休息${f.chg != null ? `（比上期 ${f.chg > 0 ? "+" : ""}${nI(f.chg)} 人）` : ""}</div>` + listHTML((f.news || []).slice(0, 3).map(x => ({ t: x.title, s: x.source, url: x.url }))) : ""),
    foot: `<span>${esc(D.src || "")}</span>` }) };
}
// 全球物流：風暴對港口、運價、物流新聞
function logisticsCard() {
  const D = P.logistics || {}, S = D.storms || [], Dl = (D.drewry || {}).lanes || [], F = D.fbx || [], N = D.news || [], LV = { Red: "紅色", Orange: "橙色", Green: "綠色" };
  const th = D.threat || [];
  return { html: sideHTML({ eyebrow: "市場 · 全球物流", title: "貨卡在哪裡？", big: th.length ? `${th[0].storm} 逼近${th[0].port}` : S.length ? `${S.length} 個熱帶氣旋` : "港口沒有風暴威脅", color: th.length ? DNH : UPH,
    body: (S.length ? `<div class="nvh">熱帶氣旋（GDACS 警戒等級）</div>` + listHTML(S.slice(0, 5).map(s => ({ t: `${s.name}・${LV[s.level] || s.level}`, s: (s.near || []).length ? `離${s.near[0].port} ${nI(s.near[0].km)} 公里` : "附近沒有主要貨櫃港", url: s.url }))) : "")
      + (Dl.length ? `<div class="nvh">Drewry 貨櫃運價（週變動）</div>` + barsHTML(Dl.map(x => ({ name: x.name, v: x.chg, txt: `${x.v ? "$" + nI(x.v) + "・" : ""}${pct(x.chg, 0)}` }))) : "")
      + (F.length ? `<div class="nvh">Freightos FBX（日變動）</div>` + barsHTML(F.slice(0, 6).map(x => ({ name: x.name, v: x.chg, txt: pct(x.chg, 1) }))) : "")
      + (N.length ? `<div class="nvh">物流新聞</div>` + listHTML(N.slice(0, 5).map(x => ({ t: x.zh || x.title, s: x.source, url: x.url }))) : ""),
    foot: `<a href="/terminal/#p-logistics">終端機看完整清單 ›</a>` }) };
}
// 美國政策源頭
function uspolicyCard() {
  const D = P.uspolicy || {}, I = D.items || [], B = D.bills || [];
  if (!I.length && !B.length) return { html: sideHTML({ eyebrow: "訊號 · 美國政策", title: "美國在改什麼規則？", body: '<p class="empty">資料載入中。</p>' }) };
  return { html: sideHTML({ eyebrow: "訊號 · USTR・商務部・國會", title: "美國在改什麼規則？", big: `近 7 天 ${D.n_week || 0} 件`, color: (D.n_hot_week || 0) ? "#ff9f0a" : NEU,
    body: vzFig(uspViz(D), `<i class="vzk" style="background:#ffd60a"></i>點名台灣　<i class="vzk" style="background:#ff9f0a"></i>重點規則・法案有新動作　<i class="vzk" style="background:#636366"></i>其他`) + `<p class="why">關稅、出口管制、實體清單在這裡先出現，新聞通常晚一兩天。標「台灣」的是內容直接點名台灣。</p>`
      + (B.length ? `<div class="nvh">國會法案</div>` + listHTML(B.slice(0, 4).map(x => ({ t: x.zh || x.title, s: `${x.kind}・${(x.date || "").slice(5).replace("-", "/")} ${x.action_zh || x.action || ""}`, url: x.url }))) : "")
      + `<div class="nvh">行政部門</div>` + listHTML(I.slice(0, 7).map(x => ({ t: (x.tw ? "【台灣】" : x.hot ? "【重點】" : "") + (x.zh || x.title), s: `${x.src}・${x.kind}・${(x.date || "").slice(5).replace("-", "/")}`, url: x.url }))),
    foot: `<a href="/terminal/#p-uspolicy">終端機看完整清單 ›</a>` }) };
}
// dalta 領先指標：7 個訊號合成，2019–2026 考試贏國發會 3～6 個月後的相關與出來的時間
function dleadCard() {
  const D = P.dlead || {}, S = D.series || {}, C = D.components || [], th = D.turn_hit || {};
  if (!S.B) return { html: sideHTML({ eyebrow: "總經 · dalta 領先指標", title: "半年後景氣會更好嗎？", body: '<p class="empty">資料載入中。</p>' }) };
  const v = D.value || 0;
  return { html: sideHTML({ eyebrow: `總經 · dalta 領先指標 · ${ymTxt(D.month)}`, title: "半年後景氣會更好嗎？", big: `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}`, color: v >= 0 ? UPH : DNH,
    body: `<p class="why">${esc(D.status || "")}。0＝1990–2018 平均，越高代表 3～6 個月後景氣越熱。2019–2026 的考試裡，它對 4～6 個月後景氣的相關贏國發會領先指標，轉折平均早 5.3 個月抓到，但假警報比較多。</p>`
      + `<div class="nvh">近 4 年走勢</div>` + lineSVG(S.B.slice(-48), v >= 0 ? UPH : DNH)
      + `<div class="nvh">7 個成分（正＝偏熱）</div>` + barsHTML(C.map(c => ({ name: c.name, v: c.z, txt: `${c.z >= 0 ? "+" : "−"}${Math.abs(c.z || 0).toFixed(2)}` })))
      + (th.n ? `<p class="why">1990 年以來它發出的 ${th.n} 次轉折訊號，${th.hit} 次在 0～12 個月內等到景氣同方向轉折（${Math.round((th.rate || 0) * 100)}%）。3 個成分是股價，會受股市情緒影響。</p>` : ""),
    foot: `<a href="/terminal/#p-dlead">終端機看和國發會的比較 ›</a>` }) };
}
// 論點追蹤：押的方向，每輪對一次證據；主圖是子彈圖（現在的位置 vs 推翻線）
function thSL() { return { ok: ["成立中", "#64d2ff"], mixed: ["分歧", "#ffd60a"], weak: ["動搖中", "#ff9f0a"], kill: ["已推翻", "#ff453a"], pending: ["資料待補", "#8e8e93"] }; }
function thesesSum() { const R = ((P.theses || {}).rows || []).filter(r => r.tier === "main"), c = {}; R.forEach(r => { c[r.status] = (c[r.status] || 0) + 1; });
  const S = thSL(); return Object.keys(S).filter(k => c[k]).map(k => `${S[k][0]} ${c[k]}`).join("・"); }
function thesesCard() {
  const D = P.theses || {}, R = D.rows || [];
  if (!R.length) return { html: sideHTML({ eyebrow: "走向 · 論點追蹤", title: "押的方向還站得住嗎？", body: '<p class="empty">資料載入中。</p>' }) };
  const SL = thSL(), sl = k => SL[k] || SL.pending, M = R.filter(r => r.tier === "main"), bad = M.some(r => r.status === "kill");
  const blk = r => `<div class="vzth"><div class="vzth-h"><i style="background:${sl(r.status)[1]}"></i><b>${esc(r.title)}</b><em style="color:${sl(r.status)[1]}">${sl(r.status)[0]}</em></div>${r.gauge ? vzBullet(r.gauge, sl(r.status)[1]) : `<span class="vzg-l">${esc(r.note || "")}</span>`}${r.hint ? `<span class="vzg-l" style="color:#ffd60a">${esc(r.hint)}</span>` : ""}</div>`;
  return { html: sideHTML({ eyebrow: `走向 · 論點追蹤 · 下次季度檢討 ${String(D.next_review || "").slice(5).replace("-", "/")}`, title: "押的方向還站得住嗎？", big: thesesSum(), color: bad ? DNH : "#64d2ff",
    body: `<p class="why">點是現在的位置，紅線是推翻線，淡色那一側代表論點還站得住。點離紅線越遠越穩；碰到紅線才發 Slack（只限主論點）。</p>`
      + `<div class="nvh">主論點</div>` + M.map(blk).join("") + `<div class="nvh">觀察</div>` + R.filter(r => r.tier === "watch").map(blk).join("")
      + `<div class="nvh">保留</div>` + R.filter(r => r.tier === "keep").map(blk).join(""),
    foot: `<a href="/terminal/#p-theses">終端機看每條證據 ›</a>` }) };
}
// AI 循環：雲端業者資本支出 → 台灣 AI 供應鏈營收 → DRAM
function aicycleCard() {
  const D = P.aicycle || {}, C = (D.capex || {}).rows || [], G = D.guide || [], T = D.tw || {}, last = C[C.length - 1] || {};
  if (!C.length && !T.month) return { html: sideHTML({ eyebrow: "總經 · AI 循環", title: "台灣這台單引擎還能跑多久？", body: '<p class="empty">資料載入中。</p>' }) };
  return { html: sideHTML({ eyebrow: `總經 · AI 循環 · ${last.q || ""}`, title: "台灣這台單引擎還能跑多久？", big: last.yoy != null ? `資本支出 ${pct(last.yoy, 0)}` : "", color: D.tone === "red" ? DNH : D.tone === "amber" ? "#ff9f0a" : UPH,
    body: `<p class="why">${esc(D.verdict || "")}。微軟、Google、亞馬遜、Meta、甲骨文每季花在機房設備的錢，是台灣伺服器、晶片訂單的源頭；2014 年以來它大約領先台灣供應鏈營收一季。</p>`
      + `<div class="nvh">每季資本支出（億美元）</div>` + barsHTML(C.slice(-6).map(r => ({ name: r.q, v: r.total * 10, txt: `${nI(r.total * 10)}・${pct(r.yoy, 0)}` })), { signed: false })
      + (G.length ? `<div class="nvh">最新指引（新聞整理）</div>` + listHTML(G.map(g => ({ t: `${g.name}：${g.dir}${g.amount ? `至 ${nI(g.amount * 10)} 億美元` : ""}${g.year ? `（${g.year}）` : ""}`, s: (g.at || "").slice(0, 10), url: g.url }))) : "")
      + (T.month ? `<div class="nvh">台灣 AI 供應鏈月營收（${ymTxt(T.month)}，近 3 月年增）</div>` + barsHTML((T.firms || []).map(f => ({ name: f.name, v: f.yoy3, txt: pct(f.yoy3, 0) }))) : ""),
    foot: `<a href="/terminal/#p-aicycle">終端機看完整 ›</a>` }) };
}
