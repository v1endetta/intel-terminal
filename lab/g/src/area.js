
/* ---- 區域報告：選一個鄉鎮 → 這一區的所有數字，跟隔壁幾區、全縣市平均、縣市排名比（全部用現有資料，不估算） ---- */
LENS.area = { n: "區域報告", c: "#f5f5f7" };
const AR = {
  // 每一項：怎麼從各資料拿到「某縣市每個鄉鎮的數值」→ [{town, v, sub}]
  move: { n: "人口淨流入", u: "人", sgn: 1, rows: C => (((P.migration || {}).towns) || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[5], sub: `外縣市搬來 ${r[6].toLocaleString("en-US")}` })),
    per: () => `近 ${(P.migration || {}).n_months || 12} 個月` },
  biz: { n: "新設公司", u: "家", rows: C => ((NAV.bt || {}).towns || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[2], sub: [r[3] ? `比上月 ${chgTxt(r[2], r[3])}` : "", r[4].slice(0, 2).map(c => c[0]).join("、")].filter(Boolean).join("・") })),
    per: () => (NAV.bt && NAV.bt.month) ? String(NAV.bt.month).replace("-", "/") : "當月" },
  clinic: { n: "診所淨增", u: "家", sgn: 1, rows: C => (((P.clinics || {}).towns) || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[2] - r[3], sub: `新開 ${r[2]}・歇業 ${r[3]}・現有 ${r[4]}` })),
    per: () => "近 12 個月" },
  aes: { n: "醫美診所", u: "家", rows: C => (((P.aesthetic || {}).towns) || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[2], sub: `另有自費西醫 ${r[3]}` })),
    per: () => (P.aesthetic || {}).asof ? `${String(P.aesthetic.asof).slice(0, 4)} 年底` : "" },
  house: { n: "房價", u: "萬／坪", dec: 1, rows: C => (((P.house || {}).towns) || []).filter(h => sameC(h[2], C)).map(h => ({ t: h[3], v: h[4], sub: `${h[5]} 筆成交` })),
    per: () => String((P.house || {}).season || "").replace(/^(\d+)S(\d)$/, "$1 年第 $2 季") },
  jobs: { n: "104 職缺", u: "個", rows: C => (((P.jobtowns || {}).towns) || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[2], sub: r[3] != null ? `7 天 ${pctTxt(r[3])}` : "" })),
    per: () => "現在刊登中" },
  gone: { n: "公司淨增", u: "家", sgn: 1, rows: C => ((NAV.bt || {}).towns || []).filter(r => sameC(r[0], C) && r[8] != null).map(r => ({ t: r[1], v: r[7] - r[8], sub: `新設公司 ${r[7]}・解散 ${r[8]}（不含商號）` })),
    per: () => (NAV.bt && NAV.bt.gone_month) ? String(NAV.bt.gone_month).replace("-", "/") : "當月" },
  birth: { n: "出生", u: "人", rows: C => (((P.births || {}).towns) || []).filter(r => sameC(r[0], C)).map(r => ({ t: r[1], v: r[2], sub: (P.births || {}).prev_ok && r[3] ? `比前 12 個月 ${pctTxt((r[2] / r[3] - 1) * 100)}` : "" })),
    per: () => (P.births || {}).n_months >= 12 ? "近 12 個月" : `近 ${(P.births || {}).n_months || 0} 個月` },
  presale: { n: "預售屋成交", u: "件", rows: C => { const R = lazyJSON("presale", "presale_towns.json", 1440); if (!R || !R.towns) return [];
      return Object.entries(R.towns).filter(([k]) => sameC(k.slice(0, 3), C)).map(([k, v]) => ({ t: k.slice(3), v: v[0],
        sub: [v[1] ? `住宅 ${v[1]} 件・${v[2].toLocaleString("en-US")} 坪` : "", v[3] ? `每坪中位 ${v[3]} 萬` : "", (v[4] || []).length ? `主要建案：${v[4].slice(0, 2).map(p => p[0].replace(/[?？]/g, "")).join("、")}` : ""].filter(Boolean).join("・") })); },
    per: () => { const R = lazyJSON("presale", "presale_towns.json", 1440); return R && R.season ? String(R.season).replace(/^(\d+)S(\d)$/, "$1 年第 $2 季・兩到四年後交屋") : ""; } },
  renewal: { n: "都更重建核定", u: "件", rows: C => Object.entries(((P.renewal || {}).towns) || {}).filter(([k]) => sameC(k.slice(0, 3), C)).map(([k, v]) => ({ t: k.slice(3), v: v[0],
      sub: [`歷年 ${v[1]} 件`, v[2] ? `最新：${String(v[2][0]).replace(/^擬訂/, "").slice(0, 26)}${v[2][1] ? "（" + v[2][1] + "）" : ""}・${String(v[2][2]).slice(0, 7).replace("-", "/")}` : ""].filter(Boolean).join("・") })),
    per: () => `近 3 年・新北到 ${String((P.renewal || {}).asof || "").slice(0, 7).replace("-", "/")}、其他到 ${String((P.renewal || {}).nat_asof || "").slice(0, 7).replace("-", "/")}` },
  rent: { n: "住家租金", u: "元／坪・月", neu: 1, rows: C => arRent("towns", C), per: () => arRentPer() },
  shop: { n: "店面租金", u: "元／坪・月", neu: 1, rows: C => arRent("shops", C), per: () => arRentPer() },
};
// 租金：實價登錄租賃（每坪月租中位數；住家 5 筆以上、店面 3 筆以上才列）
function arRent(kind, C) { const R = lazyJSON("rent", "rent_towns.json", 1440); if (!R || !R[kind]) return [];
  return Object.entries(R[kind]).filter(([k]) => sameC(k.slice(0, 3), C)).map(([k, v]) => ({ t: k.slice(3), v: v[0], sub: `${v[1]} 筆租約` })); }
const arRentPer = () => { const R = lazyJSON("rent", "rent_towns.json", 1440); return R && R.season ? String(R.season).replace(/^(\d+)S(\d)$/, "$1 年第 $2 季") : ""; };
const arFmt = (k, v) => v == null ? "—" : (AR[k].sgn && v > 0 ? "+" : v < 0 ? "−" : "") + (AR[k].dec ? Math.abs(+v).toFixed(AR[k].dec) : Math.abs(Math.round(v)).toLocaleString("en-US"));
// 隔壁幾區：中心點 9 公里內（跨縣市也算，例如林口和龜山）
const arNear = T => (NAV.towns || []).filter(t => t !== T && kmBetween(t.c, T.c) < 9).sort((a, b) => kmBetween(a.c, T.c) - kmBetween(b.c, T.c)).slice(0, 5);
function arReport(T) {
  const out = [], near = arNear(T);
  for (const k of ["move", "birth", "biz", "gone", "clinic", "aes", "house", "presale", "renewal", "rent", "shop", "jobs"].filter(k => AR[k])) {
    const R = AR[k].rows(T.county); if (!R.length) continue;
    const me = R.find(r => r.t === T.name), sorted = R.slice().sort((a, b) => b.v - a.v);
    const avg = R.reduce((a, r) => a + r.v, 0) / R.length;
    const nv = near.map(t => (AR[k].rows(t.county).find(r => r.t === t.name) || {}).v).filter(v => v != null);
    const navg = nv.length ? nv.reduce((a, b) => a + b, 0) / nv.length : null;
    out.push({ k, me, avg, navg, rank: me ? sorted.indexOf(me) + 1 : null, n: R.length });
  }
  return { rows: out, near };
}
const arEmpty = msg => ({ eyebrow: "區域報告", title: "這一區值不值得進？", big: "", color: LENS.area.c, body: `<p class="why">${msg}</p>` });
TW_VIEW.area = () => {
  navCounties(c => ({ op: 0.3, sub: "", prio: /[市]$/.test(c.name) ? 1 : 0 }));
  navBiz();
  return { eyebrow: "區域報告", title: "這一區值不值得進？", big: "點一個縣市", color: LENS.area.c,
    body: `<p class="why">選一個鄉鎮，就會列出那一區的人口流向、出生、新公司與解散、診所和醫美、房價、預售屋、都更、住家與店面租金、職缺、在地新聞，跟隔壁幾區、全縣市平均比，並標出在縣市裡排第幾。所有數字都是政府開放資料原值，沒有估算。</p><p class="why">點地圖上的縣市，或用上方 ⌕ 搜尋行政區。看到想留的，按「分享」就能把這一區的報告傳出去。</p>`
      + `<ul class="lst nvl">${rankRows(["臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市"].map(k => [k, "點進去選區"]), "nc")}</ul>` };
};
CITY_VIEW.area = C => {
  const ts = navOutline(C); navBiz();
  for (const t of ts) addLabel(pill(t.name), gp(t.c[0], t.c[1], 1.5), "nv", "nav", 1);
  const mv = AR.move.rows(C.name).sort((a, b) => b.v - a.v);
  return { eyebrow: `${norm(C.name)} · 區域報告`, title: "選一個區看報告", big: norm(C.name), color: LENS.area.c,
    body: `<p class="why">點地圖上的區，或從下面挑。先照人口淨流入排（${AR.move.per()}），人往哪裡走，生意通常跟著走。</p>`
      + `<ul class="lst nvl">${rankRows((mv.length ? mv : ts.map(t => ({ t: t.name, v: null }))).slice(0, 14).map(r => [r.t, r.v != null ? `${arFmt("move", r.v)} 人` : ""]), "nt")}</ul>` };
};
STREET_VIEW.area = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.9, 0.15);
  if (!NAV.bt) navBiz();
  const { rows, near } = arReport(T);
  for (const t of near) { for (const r of t.rings) navLine(r, 0x64d2ff, 0.35, 0.12); addLabel(pill(t.name, "隔壁"), gp(t.c[0], t.c[1], 1.2), "nv dim", "nav", 0); }
  if (!rows.length) return arEmpty("資料載入中。");
  const circ = arCircle(T);
  const good = [], weak = [];
  for (const r of rows) { if (!r.me || r.n < 4 || r.k === "house" || AR[r.k].neu) continue; const q = r.rank / r.n;
    if (q <= 0.15 || (r.avg > 0 && r.me.v >= r.avg * 1.8)) good.push(`${AR[r.k].n}排第 ${r.rank}`); else if (q >= 0.85) weak.push(`${AR[r.k].n}排倒數`); }
  const NW = NEWS().filter(x => inT(x.place, T)).slice(0, 4);
  const li = r => { const A = AR[r.k], v = r.me ? r.me.v : null, up = v != null && r.avg != null ? v >= r.avg : null;
    const cmp = [r.navg != null ? `隔壁平均 ${arFmt(r.k, r.navg)}` : "", `${esc(norm(T.county))}平均 ${arFmt(r.k, r.avg)}`, r.rank ? `第 ${r.rank}／${r.n}` : ""].filter(Boolean).join("・");
    return `<li><b class="arn">${A.n}<small>${esc(A.per())}</small></b><b class="arv" style="color:${v == null ? "#8e8e93" : r.k === "house" || A.neu ? NEU : up ? UPH : DNH}">${v == null ? "沒有資料" : arFmt(r.k, v) + " " + A.u}</b><span>${cmp}${r.me && r.me.sub ? `<br>${esc(r.me.sub)}` : ""}</span></li>`; };
  return { eyebrow: `${norm(T.county)} › ${T.name} · 區域報告`, title: "這一區值不值得進？", big: T.name, color: LENS.area.c,
    body: circ + `<div class="nvh">整個${esc(T.name)}</div><p class="why">${good.length ? `突出的：${esc(good.join("、"))}。` : "沒有特別突出的項目。"}${weak.length ? `偏弱的：${esc(weak.join("、"))}。` : ""}${(() => { const h = rows.find(r => r.k === "house" && r.me); return h ? `房價在${esc(norm(T.county))}排第 ${h.rank}／${h.n}。` : ""; })()}綠＝高於全縣市平均、紅＝低於（房價、租金不分好壞，白字）。隔壁＝中心 9 公里內的 ${near.length} 區（${esc(near.map(t => t.name).join("、"))}）。</p>`
      + `<ul class="lst arl">${rows.map(li).join("")}</ul>`
      + (NW.length ? `<div class="nvh">最近的在地新聞</div>` + listHTML(NW.map(x => ({ t: x.t, s: `${x.s || ""}・${navAgo(x.at)}`, url: x.u }))) : "")
      + (near.length ? `<div class="nvh">換一區看</div><ul class="lst nvl">${near.map(t => `<li data-ar="${esc(t.county)}|${esc(t.name)}" style="cursor:pointer">${esc(norm(t.county))} ${esc(t.name)}<span>${kmBetween(t.c, T.c).toFixed(1)} 公里</span></li>`).join("")}</ul>` : "") };
};
document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("#side [data-ar]"); if (!b) return; const [c, n] = b.dataset.ar.split("|"); const t = (NAV.towns || []).find(x => x.name === n && x.county === c); if (t) navGoTown(t); });

/* ---- 第二版：在地圖上點一下 → 畫半徑，圈內村里的人口流向（村里中心點落在圈內就算） ---- */
const ARP = { pin: null };
const arKey = (c, t, v) => norm(c) + "|" + t + "|" + v;
function arVill() {
  const V = lazyJSON("vil", "villages.json", 1440), M = lazyJSON("mvv", "mig_villages.json", 360);
  if (!V || !M) return null;
  if (!ARP._vj || ARP._vj[0] !== V || ARP._vj[1] !== M) {
    const mm = new Map((M.v || []).map(r => [arKey(r[0], r[1], r[2]), r]));
    ARP._vj = [V, M, (V.v || []).map(r => ({ ll: [r[3], r[4]], c: r[0], t: r[1], v: r[2], m: mm.get(arKey(r[0], r[1], r[2])) }))];
  }
  return { list: ARP._vj[2], M };
}
function arCircle(T) {
  if (!ARP.pin) return `<p class="why arhint">◎ 在地圖上點一下任何地方（例如店址），就會畫出半徑，算圈內的人口流向。</p>`;
  const { ll, r } = ARP.pin, ring = [];
  for (let i = 0; i <= 64; i++) { const a = i / 64 * Math.PI * 2; ring.push([ll[0] + Math.cos(a) * r / KX, ll[1] + Math.sin(a) * r / KY]); }
  { const hMax = Math.max(...ring.map(([lo, la]) => hAt(lo, la))) + 0.3;   // 平的圈：用圈上最高的地面高度，不跟著地形起伏
    const pts = ring.map(([lo, la]) => { const [x, z] = toXZ(lo, la); return new THREE.Vector3(x, hMax, z); });
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xffd60a, transparent: true, opacity: 0.95, depthTest: false }));
    l.renderOrder = 9; NAV.g.add(l); }
  addLabel(`<span class="nvpin" style="--c:#ffd60a"><i></i><b>這裡</b></span>`, gp(ll[0], ll[1], 0.1), "nv", "nav", 9);
  const btn = `<span class="arr">${[0.5, 1, 2].map(k => `<button data-arr="${k}" class="${k === r ? "on" : ""}">${k < 1 ? k * 1000 + " 公尺" : k + " 公里"}</button>`).join("")}<button data-arr="x">清掉</button></span>`;
  const D = arVill();
  if (!D) return `<div class="nvh">半徑 ${r} 公里內</div>${btn}<p class="why">${NAV.vil === false || NAV.mvv === false ? "村里資料還在準備，第一次要等台灣抓取站把村里界抓回來、遷徙資料補齊 12 個月。" : "村里資料載入中…"}</p>`;
  const inV = D.list.filter(x => kmBetween(x.ll, ll) <= r), withM = inV.filter(x => x.m);
  const sum = i => withM.reduce((a, x) => a + x.m[i], 0), inn = sum(3), out = sum(4), ext = sum(5), net = inn - out;
  const cams = camsNear(ll, r), NW = NEWS().filter(x => x.ll && x.lvl !== "town" && kmBetween(x.ll, ll) <= r);   // 只算定位到地標或路的，鄉鎮中心點的不算
  const top = withM.slice().sort((a, b) => (b.m[3] - b.m[4]) - (a.m[3] - a.m[4]));
  const per = D.M.n_months ? `近 ${D.M.n_months} 個月` : "";
  return `<div class="nvh">半徑 ${r} 公里內・${per}</div>${btn}`
    + (withM.length ? `<ul class="lst arl"><li><b class="arn">人口淨流入<small>${withM.length} 個村里（中心點在圈內）</small></b><b class="arv" style="color:${net >= 0 ? UPH : DNH}">${net >= 0 ? "+" : "−"}${Math.abs(net).toLocaleString("en-US")} 人</b><span>遷入 ${inn.toLocaleString("en-US")}・遷出 ${out.toLocaleString("en-US")}・從外縣市搬來 ${ext.toLocaleString("en-US")}（占遷入 ${inn ? Math.round(ext / inn * 100) : 0}%）</span></li>`
      + arPoints(ll, r)
      + `<li><b class="arn">攝影機<small>國道、省道、台中台南市區</small></b><b class="arv">${cams.length} 支</b>${cams.length ? `<span>最近一支 ${dist(cams[0].d)}</span>` : ""}</li>`
      + `<li><b class="arn">在地新聞<small>標得出地點的</small></b><b class="arv">${NW.length} 則</b></li></ul>`
      + (top.length > 1 ? `<div class="nvh">圈內移入最多的村里</div><ul class="lst nvl">${top.slice(0, 4).map(x => `<li>${esc(x.t)} ${esc(x.v)}<span>${(x.m[3] - x.m[4]) >= 0 ? "+" : "−"}${Math.abs(x.m[3] - x.m[4]).toLocaleString("en-US")} 人・${dist(kmBetween(x.ll, ll))}</span></li>`).join("")}</ul>` : "")
      + (NW.length ? listHTML(NW.slice(0, 3).map(x => ({ t: x.t, s: `${x.s || ""}・${navAgo(x.at)}`, url: x.u }))) : "")
      : `<p class="why">圈內沒有村里中心點，把半徑加大試試。</p>`)
    + `<p class="why">${(() => { const g = P.geocode || {}; return g.items ? `地址轉座標進度：${Math.round((g.located || 0) / g.items * 100)}%（門牌級 ${(g.doorplate || 0).toLocaleString("en-US")} 家）。` : ""; })()}門牌級＝高雄、桃園、台南、新竹市、苗栗、台東的公開門牌座標；其他縣市是路段中心，標「約略」，可能差幾百公尺。新公司還沒接。</p>`;
}
const _arClick = navClickAt;
navClickAt = function (lon, lat, c) {
  if (NAV.lens === "area" && NAV.level === 2) { ARP.pin = { ll: [lon, lat], r: (ARP.pin && ARP.pin.r) || 1 }; NAV.key = ""; return; }
  return _arClick(lon, lat, c);
};
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("#side [data-arr]"); if (!b) return;
  if (b.dataset.arr === "x") ARP.pin = null; else if (ARP.pin) ARP.pin.r = +b.dataset.arr;
  NAV.key = "";
});

function arPoints(ll, r) {
  const G = lazyJSON("gpt", "geo_points.json", 60); if (!G) return "";
  const d365 = (() => { const d = new Date(Date.now() - 365 * 864e5); return d.toISOString().slice(0, 10).replace(/-/g, ""); })(), today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const inR = x => kmBetween([x[0], x[1]], ll) <= r;
  const C = (G.clinic || []).filter(inR), A = (G.aes || []).filter(inR);
  const act = C.filter(x => !x[4] || x[4] > today), nw = C.filter(x => x[3] >= d365), cl = C.filter(x => x[4] && x[4] >= d365 && x[4] <= today);
  const prec = (L, i) => { const b = L.filter(x => x[i] === 1).length; return L.length ? (b === L.length ? "門牌級" : b ? `${b} 家門牌級、${L.length - b} 家約略` : "約略位置") : ""; };
  const grp = {}; for (const x of nw) grp[x[2]] = (grp[x[2]] || 0) + 1;
  const gtxt = Object.entries(grp).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([g, n]) => `${g} ${n} 家`).join("、");
  const aes = A.filter(x => x[2] === "醫美");
  return `<li><b class="arn">健保診所<small>${prec(act, 5)}</small></b><b class="arv">${act.length} 家</b><span>近 12 個月新開 ${nw.length}・歇業 ${cl.length}${gtxt ? `・新開以${gtxt}為主` : ""}</span></li>`
    + `<li><b class="arn">醫美診所<small>${(P.aesthetic || {}).asof ? String(P.aesthetic.asof).slice(0, 4) + " 年底・" : ""}${prec(aes, 4)}</small></b><b class="arv">${aes.length} 家</b><span>另有其他自費西醫 ${A.length - aes.length} 家${aes.length ? "・" + aes.slice().sort((a, b) => b[3] - a[3]).slice(0, 3).map(x => x[5]).join("、") : ""}</span></li>`;
}
