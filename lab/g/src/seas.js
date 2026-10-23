
/* ---- 醫美（衛福部全機構名冊對健保名冊）、台海（國防部每日動態）、海纜（TeleGeography） ---- */
LENS.aes = { n: "醫美", c: "#ff9ec7" };
LENS.cable = { n: "海纜", c: "#64d2ff" };
const AE = () => P.aesthetic || {};
const aeTowns = C => ((AE().towns) || []).filter(r => sameC(r[0], C.name || C));
const aeBig = (cty, town) => ((AE().big) || []).filter(r => sameC(r[1], cty) && (!town || r[2] === town));
const aeAsof = () => AE().asof ? `資料到 ${AE().asof.slice(0, 4)} 年底` : "";
const aeWhy = '<p class="why">醫美＝名稱有醫美、美學、整形等字，或沒簽健保的整形外科、皮膚科診所。衛福部名冊一年一版，看的是分布，不是最近的開關店。</p>';
const aeEmpty = () => ({ eyebrow: "台灣 · 醫美", title: "醫美診所集中在哪？", big: "載入中", color: LENS.aes.c, body: '<p class="empty">醫美資料下一輪更新後出現。</p>' });
TW_VIEW.aes = () => {
  const D = AE(), Cs = D.counties || {}, ks = Object.keys(Cs);
  if (!ks.length) { navCounties(() => ({ op: 0.2 })); return aeEmpty(); }
  const mx = Math.max(1, ...ks.map(k => Cs[k][0])), col = new THREE.Color(LENS.aes.c);
  navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true, op: 0.12 }; const v = Cs[k];
    return { col, op: 0.2 + 0.75 * Math.sqrt(v[0] / mx), sub: `醫美 ${v[0]}`, dot: LENS.aes.c, prio: 2 + v[0] / mx * 4 }; });
  const rows = ks.sort((a, b) => Cs[b][0] - Cs[a][0]), tops = (D.towns || []).slice(0, 6);
  return { eyebrow: `台灣 · 醫美 · ${aeAsof()}`, title: "醫美診所集中在哪？", big: `${(D.n_clear || 0).toLocaleString("en-US")} 家`, color: LENS.aes.c,
    body: aeWhy + `<p class="why">另有 ${(D.n_self || 0).toLocaleString("en-US")} 家沒簽健保的西醫診所（多數做醫美、健檢、減重），名稱看不出來的醫美在這一群裡。${D.diff ? `跟 ${D.diff.from.slice(0, 4)} 年比：新出現 ${D.diff.new} 家、消失 ${D.diff.gone} 家。` : ""}</p>`
      + `<div class="nvh">最集中的鄉鎮</div><ul class="lst nvl">${tops.map(t => `<li data-nc="${esc(t[0])}" style="cursor:pointer"><span class="sdot" style="background:${LENS.aes.c}"></span>${esc(norm(t[0]))} ${esc(t[1])}<span>醫美 ${t[2]}・其他自費 ${t[3]}</span></li>`).join("")}</ul>`
      + `<div class="nvh">各縣市</div><ul class="lst nvl">${rankRows(rows.slice(0, 12).map(k => [k, `醫美 ${Cs[k][0]}・其他自費 ${Cs[k][1]}`]), "nc")}</ul>` };
};
CITY_VIEW.aes = C => {
  const ts = navOutline(C), R = aeTowns(C), view = NAV.viewD || 60, mx = Math.max(1, ...R.map(r => r[2]));
  if (!AE().towns) return aeEmpty();
  R.forEach((r, i) => { const t = ts.find(t => t.name === r[1]); if (t && r[2]) navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `醫美 ${r[2]}`, 6 - i * 0.2, LENS.aes.c); });
  townPills(ts, new Set(R.map(r => r[1])));
  const v = (AE().counties || {})[Object.keys(AE().counties || {}).find(k => sameC(k, C.name))] || [0, 0], big = aeBig(C.name);
  return { eyebrow: `${norm(C.name)} · 醫美 · ${aeAsof()}`, title: "醫美開在哪一區？", big: `${v[0]} 家`, color: LENS.aes.c,
    body: `<p class="why">光柱越高醫美診所越多。另有其他自費西醫診所 ${v[1]} 家。</p><ul class="lst nvl">${rankRows(R.slice(0, 8).map(r => [r[1], `醫美 ${r[2]}・其他自費 ${r[3]}・醫師 ${r[4]} 位`]), "nt")}</ul>`
      + (big.length ? `<div class="nvh">規模較大的（醫師 3 位以上）</div>` + listHTML(big.slice(0, 8).map(r => ({ t: r[0], s: `${r[2]}・醫師 ${r[3]}・護理 ${r[4]}`, url: `https://www.google.com/search?q=${encodeURIComponent(r[0] + " " + r[2])}` }))) : "") };
};
STREET_VIEW.aes = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
  const R = aeTowns(T.county), me = R.find(r => r[1] === T.name), big = aeBig(T.county, T.name);
  if (!me) return { eyebrow: `${norm(T.county)} › ${T.name} · 醫美`, title: "這一區有多少醫美？", big: T.name, color: LENS.aes.c, body: `<p class="empty">${AE().towns ? "這一區名冊上沒有醫美或自費西醫診所。" : "資料載入中。"}</p>` };
  return { eyebrow: `${norm(T.county)} › ${T.name} · 醫美 · ${aeAsof()}`, title: "這一區有多少醫美？", big: `${me[2]} 家`, color: LENS.aes.c,
    body: `<p class="why">在${esc(norm(T.county))}排第 ${R.indexOf(me) + 1}／${R.length}。醫師共 ${me[4]} 位；另有其他自費西醫診所 ${me[3]} 家。</p>`
      + (big.length ? `<div class="nvh">規模較大的</div>` + listHTML(big.map(r => ({ t: r[0], s: `醫師 ${r[3]}・護理 ${r[4]}`, url: `https://www.google.com/search?q=${encodeURIComponent(r[0] + " " + T.name)}` }))) : "") };
};

/* 台海：國防部每天公布前一天 06 時到今天 06 時的共機、共艦 */
function plaCard() {
  const D = P.plaact || {}, L = D.latest, days = D.days || [];
  if (!L) return { html: sideHTML({ eyebrow: "現場 · 台海", title: "共機共艦今天多不多？", body: '<p class="empty">國防部資料下一輪更新後出現（第一次要分幾輪補齊半年）。</p>' }) };
  const a7 = (D.avg7 || {}).air, a30 = (D.avg30 || {}).air, hot = a30 ? L.air / a30 : 1, col = hot >= 2 ? DNH : hot >= 1.2 ? "#ff9f0a" : NEU;
  const md = s => `${+s.slice(5, 7)}/${+s.slice(8, 10)}`, M = D.max90 || {};
  const tail = days.slice(-90);
  return { html: sideHTML({ eyebrow: `現場 · 台海 · ${md(L.date)} 06 時前 24 小時`, title: "共機共艦今天多不多？", big: `共機 ${L.air}・共艦 ${L.ship}`, color: col,
    chg: L.cross ? `越中線 ${L.cross}` : "",
    body: `<p class="why">國防部每天早上公布。今天共機是近 30 天平均（${a30} 架次）的 ${hot.toFixed(1)} 倍；近 7 天平均 ${a7} 架次。${L.off ? `另有公務船 ${L.off} 艘。` : ""}${L.balloon ? `氣球 ${L.balloon} 顆。` : ""}數字突然跳高通常是演習或政治事件前後，常常比新聞先反映到股市和匯率。</p>`
      + `<div class="nvh">共機架次・近 ${tail.length} 天</div>` + lineSVG(tail.map(d => d[1]), "#ff9f0a")
      + `<div class="nvh">共艦艘數・近 ${tail.length} 天</div>` + lineSVG(tail.map(d => d[3]), "#64d2ff")
      + `<p class="why">近 90 天最多：共機 ${M.air} 架次（${M.air_date ? md(M.air_date) : ""}）、共艦 ${M.ship} 艘（${M.ship_date ? md(M.ship_date) : ""}）。</p>`
      + (L.img ? `<a href="${esc(L.url)}" target="_blank" rel="noopener"><img class="plaimg" src="${esc(L.img)}" alt="國防部臺海周邊海、空域活動示意圖" loading="lazy" referrerpolicy="no-referrer"></a>` : "")
      + ((D.events || []).length ? `<div class="nvh">其他公告</div>` + listHTML(D.events.slice(0, 4).map(e => ({ t: e.title, s: md(e.date), url: e.url }))) : ""),
    foot: `<a href="${esc(L.url)}" target="_blank" rel="noopener">國防部原文 ›</a>` }) };
}

/* 海纜：台灣上岸的國際海纜（只畫台灣附近），上岸站、受損新聞 */
const CB = () => P.cables || {};
TW_VIEW.cable = () => {
  const D = CB(), cs = D.cables || [];
  navCounties(() => ({ op: 0.12, dim: true }));
  if (!cs.length) return { eyebrow: "現場 · 海纜", title: "台灣靠哪幾條海纜連上世界？", big: "載入中", color: LENS.cable.c, body: '<p class="empty">海纜資料下一輪更新後出現。</p>' };
  const hit = new Set();
  for (const n of D.news || []) for (const c of cs) if (n.title.toLowerCase().includes(String(c.name).toLowerCase().replace(/\s*\(.*\)/, ""))) hit.add(c.id);
  for (const c of cs) { const col = hit.has(c.id) ? 0xff453a : new THREE.Color(c.color || LENS.cable.c); for (const seg of c.lines || []) navLine(seg, col, c.planned ? 0.35 : 0.85, 0.3); }
  const by = {}; for (const c of cs) for (const l of c.tw_lp || []) (by[l] = by[l] || []).push(c.name);
  for (const [name, lo, la] of D.landing || []) addLabel(pill(name, `${(by[name] || []).length} 條`, LENS.cable.c), gp(lo, la, 1.2), "nv", "nav", 3 + (by[name] || []).length / 3);
  const live = cs.filter(c => !c.planned), intl = live.filter(c => !c.domestic), dom = live.filter(c => c.domestic), plan = cs.filter(c => c.planned), old = live.filter(c => c.rfs && c.rfs <= new Date().getFullYear() - 20);
  const lps = Object.entries(by).sort((a, b) => b[1].length - a[1].length);
  return { eyebrow: "現場 · 海纜 · TeleGeography", title: "台灣靠哪幾條海纜連上世界？", big: `國際海纜 ${intl.length} 條`, color: LENS.cable.c, chg: [dom.length ? `外島 ${dom.length}` : "", plan.length ? `建設中 ${plan.length}` : ""].filter(Boolean).join("・"),
    body: `<p class="why">國際網路九成以上走海纜。上岸站越集中，一個地方出事影響越大；用超過 20 年的海纜（${old.length} 條）比較容易故障。紅線＝最近新聞有點名的海纜。馬祖、金門、澎湖靠的國內海纜條數少，一斷就是整個島網路變慢。</p>`
      + (old.length ? `<p class="why">用超過 20 年的：${esc(old.map(c => c.name).join("、"))}。</p>` : "")
      + `<div class="nvh">上岸站</div>` + barsHTML(lps.map(([k, v]) => ({ name: k, v: v.length, txt: `${v.length} 條` })), { signed: false })
      + ((D.news || []).length ? `<div class="nvh">海纜新聞・近 60 天</div>` + listHTML(D.news.slice(0, 6).map(n => ({ t: n.title, s: `${n.source || ""}・${navAgo(n.at)}`, url: n.url }))) : `<p class="why">近 60 天沒有海纜受損或中斷的新聞。</p>`)
      + `<div class="nvh">海纜（新到舊）</div>` + listHTML(cs.slice().sort((a, b) => (b.rfs || 0) - (a.rfs || 0)).map(c => ({ t: `${c.name}${c.planned ? "（建設中）" : ""}`, s: [c.rfs ? `${c.rfs} 年啟用` : "", c.length, (c.tw_lp || []).join("、"), c.owners ? c.owners.split(",").slice(0, 3).join("、") : ""].filter(Boolean).join("・") }))) };
};

/* 台海地圖（示意）：國防部只公布「進入哪幾個空域」，沒有座標；空域位置、海峽中線都是示意 */
LENS.pla = { n: "台海", c: "#ff453a" };
const PLA_Z = { "北部": [121.55, 25.85], "東北": [122.35, 25.35], "中部": [119.7, 24.4], "西南": [119.85, 22.35], "南部": [120.8, 21.55], "東南": [121.75, 21.85], "東部": [122.25, 23.2] };
const ICON_JET = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M12 2l1.6 6.2 7.4 4.3v2l-7.2-2.2-.5 5.2 2.4 1.8v1.7L12 20l-3.7 1v-1.7l2.4-1.8-.5-5.2L3 14.5v-2l7.4-4.3z"/></svg>';
const ICON_SHIP = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M11 3h2v3h4l1 5h3l-2.5 6.5c-.6.2-1.3.5-2.5.5-1.7 0-2.6-1-4-1s-2.3 1-4 1c-1.2 0-1.9-.3-2.5-.5L3 11h3l1-5h4zM6 21c1.7 0 2.6-1 4-1s2.3 1 4 1 2.6-1 4-1v-1.5c-1.4 0-2.3 1-4 1s-2.6-1-4-1-2.3 1-4 1-2.6-1-4-1V20c1.4 0 2.3 1 4 1z"/></svg>';
TW_VIEW.pla = () => {
  navCounties(() => ({ op: 0.15, dim: true }));
  const L = (P.plaact || {}).latest;
  const ml = [[121.75, 26.55], [118.4, 23.25]]; navLine(ml, 0xffffff, 0.45, 0.2);
  addLabel(`<span class="nvp plz"><b>海峽中線（示意）</b></span>`, gp(120.15, 24.95, 1), "nv dim", "nav", 1);
  const hit = new Set((L && L.zones) || []);
  for (const [z, ll] of Object.entries(PLA_Z)) {
    const on = hit.has(z), ring = [];
    for (let i = 0; i <= 48; i++) { const a = i / 48 * Math.PI * 2; ring.push([ll[0] + Math.cos(a) * 28 / KX, ll[1] + Math.sin(a) * 28 / KY]); }
    navLine(ring, on ? 0xff453a : 0x8e8e93, on ? 0.9 : 0.25, 0.3);
    addLabel(`<span class="nvp plz ${on ? "on" : ""}">${on ? `<span class="pli">${ICON_JET}</span>` : ""}<b>${z}空域</b>${on ? "<em>有共機進入</em>" : ""}</span>`, gp(ll[0], ll[1], 1), on ? "nv" : "nv dim", "nav", on ? 6 : 0);
  }
  if (L) addLabel(`<span class="nvp plz on"><span class="pli">${ICON_SHIP}</span><b>共艦 ${L.ship}・公務船 ${L.off}</b><em>位置未公布</em></span>`, gp(119.25, 23.55, 1), "nv", "nav", 5);
  return null;   // 卡片沿用台海卡（地圖只畫示意）
};
