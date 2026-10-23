
/* ---- 分層地圖（自己逛）：台灣 → 城市 → 街道，每一層只回答一個問題；下方選的分類決定問什麼（視角） ----
   台灣：今天哪裡不對勁？（縣市依示警、地震、路況事件上色）
   城市：這座城市哪一區在動？（各區實價登錄，用光柱高度表示）
   街道：這裡此刻怎樣？（附近的路況事件、新設立公司、藝文活動、房價）
   拉近拉遠就自動換層；上方麵包屑可以一鍵回到上一層；也可以搜尋縣市、行政區、地標。 */
const NAV = { level: -1, key: "", county: null, town: null, towns: null, g: new THREE.Group(), t: 0, lock: 0 };
scene.add(NAV.g);
const LVL_NAME = ["台灣", "城市", "街道"];
const SEV_C = [new THREE.Color(0x8e8e93), new THREE.Color(0xffd60a), new THREE.Color(0xff9f0a), new THREE.Color(0xff453a)];
async function navTowns() {
  if (NAV.towns) return NAV.towns;
  try { const j = await (await fetch("towns.json?v=" + ASSET_V)).json();
    NAV.towns = j.towns.map(t => { let bb = [999, 999, -999, -999], cx = 0, cy = 0, n = 0;
      for (const r of t.r) for (const [x, y] of r) { bb = [Math.min(bb[0], x), Math.min(bb[1], y), Math.max(bb[2], x), Math.max(bb[3], y)]; cx += x; cy += y; n++; }
      return { county: t.c, name: t.t, rings: t.r, bbox: bb, c: [cx / n, cy / n] }; });
  } catch (e) { NAV.towns = []; }
  return NAV.towns;
}
const townAt = (lon, lat) => (NAV.towns || []).find(t => lon >= t.bbox[0] && lon <= t.bbox[2] && lat >= t.bbox[1] && lat <= t.bbox[3] && t.rings.some(r => inRing(lon, lat, r)));
const sameC = (a, b) => norm(a) === norm(b) || norm(a).startsWith(norm(b)) || norm(b).startsWith(norm(a));
const kmBetween = (a, b) => Math.hypot((a[0] - b[0]) * KX, (a[1] - b[1]) * KY);
// 各縣市今天的「異常」：示警、近 48 小時地震、路況事件
function countySeverity() {
  const S = {}, add = (c, pts, why) => { if (!c) return; const k = c.name; (S[k] = S[k] || { s: 0, why: [] }).s += pts; if (!S[k].why.includes(why)) S[k].why.push(why); };
  for (const w of ((P.weather || {}).warnings || [])) add(COUNTIES.find(c => sameC(c.name, w.where)), 2, w.what + (w.level || ""));
  for (const a of ((P.alerts || {}).alerts || [])) { const area = [].concat(a.where || a.area || a.areaDesc || "").join(" "), what = a.cat || a.event || a.title || "示警";
    for (const c of COUNTIES) if (area.includes(norm(c.name).slice(0, 2)) && !((S[c.name] || {}).why || []).some(w => w.includes(what) || what.includes(w))) add(c, 2, what + "特報"); }
  const now = Date.now();
  for (const q of ((P.quake || {}).items || [])) if (q.mag >= 4 && now - new Date(q.at) < 48 * 3600e3) add(countyAt(q.lon, q.lat) || COUNTIES.slice().sort((a, b) => kmBetween(a.c, [q.lon, q.lat]) - kmBetween(b.c, [q.lon, q.lat]))[0], q.mag >= 5 ? 3 : 1, "地震 M" + q.mag);
  const ev = {}; for (const e of (((P.roads || {}).events) || [])) if (e.ll) { const c = countyAt(e.ll[0], e.ll[1]); if (c) ev[c.name] = (ev[c.name] || 0) + 1; }
  for (const [k, n] of Object.entries(ev)) add(COUNTIES.find(c => c.name === k), Math.min(2, n * 0.5), `路況事件 ${n} 起`);
  return S;
}
function navClear() { FATM.length = 0; NAV.pins = []; while (NAV.g.children.length) { const o = NAV.g.children.pop(); o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); } clearLabels("nav"); }
function navLine(ring, col, op, lift) { const pts = ring.map(([lo, la]) => gp(lo, la, lift)); const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: op, depthTest: false })); l.renderOrder = 8; l.userData.key = NAV._tag || null; l.userData.op = op; NAV.g.add(l); return l; }
const pill = (name, sub, dot) => `<span class="nvp">${dot ? `<i style="background:${dot}"></i>` : ""}<b>${esc(name)}</b>${sub ? `<em>${esc(sub)}</em>` : ""}</span>`;
// ---- 視角：下方選的分類決定地圖「看什麼」，拉近拉遠決定「看多細」 ----
// 現場（預設）／房價／新公司／地方新聞；市場、走向這類沒有地點的資訊，地圖維持現場、只換卡片
const LENS = { now: { n: "現場", c: "#ff9f0a" }, house: { n: "房價", c: "#64d2ff" }, biz: { n: "新公司", c: "#30d158" }, news: { n: "地方新聞", c: "#bf5af2" }, traffic: { n: "車流", c: "#ff9f0a" }, stock: { n: "個股", c: "#64d2ff" }, elect: { n: "選戰", c: "#bf5af2" }, macro: { n: "景氣", c: "#ff453a" }, mood: { n: "情緒", c: "#ffd60a" }, power: { n: "電力", c: "#30d158" }, jobs: { n: "職缺", c: "#5e9cff" }, tender: { n: "標案", c: "#ffd60a" } };
NAV.lens = "now"; NAV.quiet = null;
function navSetLens(lens, keepCard) { NAV.lens = LENS[lens] ? lens : "now"; NAV.quiet = keepCard ? true : null; NAV.bare = false; NAV.key = ""; NAV.t = 0; }
const p1 = v => (+v).toFixed(1);
const navAgo = at => { const m = (Date.now() - new Date(at)) / 6e4; return !isFinite(m) ? "" : m < 60 ? Math.max(1, Math.round(m)) + " 分鐘前" : m < 1440 ? Math.round(m / 60) + " 小時前" : Math.round(m / 1440) + " 天前"; };
const dist = d => d < 1 ? Math.round(d * 1000) + " 公尺" : d.toFixed(1) + " 公里";
const inT = (place, T) => norm(place).startsWith(norm(T.county)) && String(place).includes(T.name);   // 同名行政區很多（信義區、中正區…），要連縣市一起比
const inC = (place, C) => sameC(String(place || "").slice(0, 3), C.name);
const cOf = k => { const o = k || {}, key = Object.keys(o).find(x => sameC(x, NAV.county ? NAV.county.name : "")); return key ? o[key] : null; };
const pin = (it, prio) => addLabel(`<span class="nvpin" data-pin="${(NAV.pins = NAV.pins || []).push(it) - 1}" style="--c:${it.c}"><i></i><b>${esc(String(it.t).slice(0, 16))}</b></span>`, gp(it.ll[0], it.ll[1], 0.05), "nv", "nav", prio);
const tw = () => [controls.target.x / KX + LONC, -controls.target.z / KY + LATC];
function navCol(lon, lat, k, view, label, sub, prio, hex) {
  const hh = view * (0.03 + 0.22 * k), base = gp(lon, lat, 0.2), col = hex ? new THREE.Color(hex) : new THREE.Color().setHSL(0.55 - 0.55 * k, 0.85, 0.6);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(view * 0.006, view * 0.006, hh, 12), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 1 }));
  m.userData.key = norm(label); m.userData.op = 1;
  m.position.copy(base).add(V(0, hh / 2, 0)); m.renderOrder = 9; NAV.g.add(m);
  const ring = new THREE.Mesh(new THREE.RingGeometry(view * 0.008, view * 0.016, 32), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false }));
  ring.rotation.x = -Math.PI / 2; ring.position.copy(base); ring.renderOrder = 9; ring.userData.key = norm(label); ring.userData.op = 0.5; NAV.g.add(ring);
  addLabel(pill(label, sub, "#" + col.getHexString()), base.clone().add(V(0, hh + view * 0.01, 0)), "nv", "nav", prio);
}
// 縣市外框＋名牌，顏色和副標由各視角決定
function navCounties(f) {
  for (const c of COUNTIES) { const o = f(c) || {}, col = o.col || SEV_C[0];
    NAV._tag = norm(c.name); for (const r of c.rings) if (r.length > 30) navLine(r, col, o.op ?? 0.25, 1.2); NAV._tag = null;
    addLabel(pill(norm(c.name), o.sub || "", o.dot || null), gp(c.c[0], c.c[1], 2.5), o.dim ? "nv dim" : "nv", "nav", o.prio ?? (/[市]$/.test(c.name) ? 1 : 0));
  }
}
const navOutline = C => { for (const r of C.rings) if (r.length > 30) navLine(r, 0xffffff, 0.55, 1.2); const ts = (NAV.towns || []).filter(t => sameC(t.county, C.name)); for (const t of ts) { NAV._tag = t.name; for (const r of t.rings) navLine(r, 0x64d2ff, 0.28, 1.0); } NAV._tag = null; return ts; };
const townPills = (ts, skip) => { for (const t of ts) if (!skip.has(t.name)) addLabel(pill(t.name), gp(t.c[0], t.c[1], 1.5), "nv dim", "nav", -2); };
const rankRows = (rows, attr) => rows.map(([k, sub, dot], i) => `<li data-${attr}="${esc(k)}" style="cursor:pointer">${dot ? `<span class="sdot" style="background:${dot}"></span>` : `${i + 1}. `}${esc(norm(k))}<span>${esc(sub)}</span></li>`).join("");
const wxLine = C => { const W = ((P.weather || {}).items || []).find(w => norm(C.name).startsWith(norm(w.city))), warn = ((P.weather || {}).warnings || []).filter(w => sameC(w.where, C.name)).map(w => w.what);
  return W || warn.length ? `<p class="why">${W ? `${esc(W.weather)} ${(+W.temp).toFixed(1)}°C` : ""}${warn.length ? `・<b style="color:#ff9f0a">${esc(warn.join("、"))}</b>` : ""}</p>` : ""; };
const BRANDS = () => ((P.mapfeed || {}).brands) || [];
const NEWS_AG = /俄新社|中新社|法新社|新華社|共同社|路透社?|美聯社|韓聯社|塔斯社|德新社/;   // 「據俄新社」被誤認成台中新社區之類的國際新聞，不放在地圖上
// 地方新聞排序：「值不值得知道」（開店、建設、交通、活動、政策、災害 3 分；政治口水 1 分；社會案件 0 分）為主，越舊越後面（每 12 小時約扣 1 分）
const newsScore = x => (x.v != null ? x.v : 1.5) - Math.max(0, (Date.now() - new Date(x.at)) / 432e5);
const NEWS = () => (NAV._nw && NAV._nw.src === (P.mapfeed || {}).news ? NAV._nw.out : (NAV._nw = { src: (P.mapfeed || {}).news, out: (((P.mapfeed || {}).news) || [])
  .filter(x => !(x.lvl === "town" && NEWS_AG.test(x.t || ""))).map(x => x.kc && !x._k ? { ...x, _k: 1, s: `${x.kc}｜${x.s || ""}` } : x).sort((a, b) => newsScore(b) - newsScore(a)) }).out);
// 新公司：每月登記資料依地址歸到鄉鎮（biz_towns.json，資料分支）；還沒產生前退回只有幾十家的舊點位
NAV.bt = undefined;
function navBiz() { if (NAV.bt !== undefined) return NAV.bt; NAV.bt = null;
  fetch(RAW + "biz_towns.json?h=" + Math.floor(Date.now() / 36e5), { cache: "no-store" }).then(r => r.ok ? r.json() : false).then(j => { NAV.bt = j && j.towns ? j : false; if (NAV.lens === "biz" || NAV.lens === "area") NAV.key = ""; }).catch(() => { NAV.bt = false; });
  return null; }
const chgTxt = (n, p) => p ? `${n >= p ? "+" : "−"}${Math.abs(Math.round((n / p - 1) * 100))}%` : "";
const chgCol = (n, p) => !p ? "#8e8e93" : n >= p ? UPH : DNH;   // 漲綠跌紅
const capTxt = c => c >= 1e8 ? `${(c / 1e8).toFixed(c >= 1e9 ? 0 : 1)} 億` : `${Math.round(c / 1e4).toLocaleString("en-US")} 萬`;
const btTowns = C => ((NAV.bt || {}).towns || []).filter(r => sameC(r[0], C.name || C));
const btLine = r => `${r[2].toLocaleString("en-US")} 家${r[3] ? `・比上月 ${chgTxt(r[2], r[3])}` : ""}${r[4].length ? `・${r[4].map(c => c[0]).slice(0, 2).join("、")}` : ""}`;
// 職缺（104）：縣市來自 jobs.areas（新竹、嘉義縣市合計），六都＋新竹有分區（jobtowns）
const pctTxt = v => v == null ? "" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
const pctCol = v => v == null ? "#8e8e93" : v >= 0 ? UPH : DNH;
const jobArea = name => (((P.jobs || {}).areas) || []).find(a => (a.counties || []).some(c => sameC(c, name)));
const jobTowns = name => (((P.jobtowns || {}).towns) || []).filter(r => sameC(r[0], name));
const jobLatest = (C, T) => (((P.jobs || {}).latest) || []).filter(x => norm(x.place).startsWith(norm(C).slice(0, 3)) && (!T || String(x.place).includes(T)));
const jobRow = x => ({ t: `${x.t}`, s: `${x.co}・${x.place}${x.sal && x.sal[0] ? `・${Math.round(x.sal[0] / 1000)}K${x.sal[1] ? "–" + Math.round(x.sal[1] / 1000) + "K" : "+"}` : ""}`, url: x.u });
// 標案：近 7 天各縣市新招標／決標（tendermap，依發包機關歸類）
const TM = () => P.tendermap || {};
const tmC = name => { const C = TM().counties || {}, k = Object.keys(C).find(x => sameC(x, name)); return k ? C[k] : null; };
const tmTowns = name => (TM().towns || []).filter(r => sameC(r[0], name));
const tmDays = () => { const d = TM().days || []; return d.length ? `${d[0].slice(4, 6)}/${d[0].slice(6)}–${d[1].slice(4, 6)}/${d[1].slice(6)}` : ""; };
const tmRecent = arr => listHTML((arr || []).map(r => ({ t: r[0], s: r[1], url: r[2] })));
// 車流：高公局國道（465 段）＋公路局省道（約 6,800 段）的即時車速，依路段中點歸到縣市；路況事件另外算
const TR = { seg: null, at: null };
function trSegs() {
  if (!ROADS_GEO || !ROADS_LIVE) return [];
  if (TR.seg && TR.at === ROADS_LIVE.at) return TR.seg;
  const out = [], add = (k, geo, sp) => (geo.c || []).forEach((flat, i) => { if (!flat || flat.length < 4) return;
    const m = Math.floor(flat.length / 4) * 2, ll = [flat[m] / 1e4, flat[m + 1] / 1e4], v = sp[i], c = countyAt(ll[0], ll[1]);
    out.push({ k, n: geo.n[i] || "", s: v == null || v <= 0 ? null : v, flat, ll, c: c ? c.name : null }); });
  add("fw", ROADS_GEO.fw, ROADS_LIVE.fw || []); add("thb", ROADS_GEO.thb, ROADS_LIVE.thbS || []);
  TR.at = ROADS_LIVE.at; return (TR.seg = out);
}
const trSlow = x => x.s != null && (x.k === "fw" ? x.s < 40 : x.s < 20);   // 國道低於 40、省道低於 20 算塞
const trCol = x => x.s == null ? 0x636366 : x.k === "fw" ? (x.s >= 80 ? 0x30d158 : x.s >= 50 ? 0xffd60a : 0xff453a) : (x.s >= 50 ? 0x30d158 : x.s >= 25 ? 0xffd60a : 0xff453a);
const trName = x => x.n.replace(/^國道/, "國").replace(/\s+/g, " ");
const trEvents = f => (((P.roads || {}).events) || []).filter(e => e.ll && f(e));
function trDraw(segs, lift) {   // 國道（粗）、省道（細）依車速上色：綠順、黃車多、紅塞；粗線遠看近看都清楚
  for (const kind of ["thb", "fw"]) {
    const pos = [], col = [], C = new THREE.Color();
    for (const x of segs) { if (x.k !== kind || x.s == null) continue; C.setHex(trCol(x));
      for (let k = 0; k + 3 < x.flat.length; k += 2) { const a = gp(x.flat[k] / 1e4, x.flat[k + 1] / 1e4, lift), b = gp(x.flat[k + 2] / 1e4, x.flat[k + 3] / 1e4, lift); pos.push(a.x, a.y, a.z, b.x, b.y, b.z); col.push(C.r, C.g, C.b, C.r, C.g, C.b); } }
    if (pos.length) NAV.g.add(fatSegs(pos, col, kind === "fw" ? (MOBILE ? 4 : 5) : (MOBILE ? 2.5 : 3), 0.95));
  }
}
const trStats = segs => { const f = segs.filter(x => x.k === "fw" && x.s != null), t = segs.filter(x => x.k === "thb" && x.s != null);
  return { fwN: f.length, fwAvg: f.length ? Math.round(f.reduce((a, x) => a + x.s, 0) / f.length) : null, fwSlow: f.filter(trSlow), thbN: t.length, thbSlow: t.filter(trSlow) }; };
const trRow = x => ({ t: x.k === "vd" ? x.n : trName(x), s: `${x.k === "fw" ? "國道" : x.k === "vd" ? "市區" : "省道"}・${x.s} km/h${x.d != null ? `・${dist(x.d)}` : ""}` });
// 公路攝影機（data/cctv.json）與台北市區 VD 路段（data/tpe_vd.json），需要時才載
const lazyJSON = (key, file, ttlMin) => { if (NAV[key] !== undefined) return NAV[key]; NAV[key] = null;
  fetch(RAW + file + "?t=" + Math.floor(Date.now() / (ttlMin * 6e4)), { cache: "no-store" }).then(r => r.ok ? r.json() : false).then(j => { NAV[key] = j || false; NAV.key = ""; }).catch(() => { NAV[key] = false; });
  return null; };
const camsNear = (ll, km) => (((lazyJSON("cam", "cctv.json", 720) || {}).cams) || []).map(c => ({ c, d: kmBetween([c[0], c[1]], ll) })).filter(x => x.d < km).sort((a, b) => a.d - b.d);
function vdSegs() { const j = lazyJSON("vd", "tpe_vd.json", 5); return j && j.s ? j.s : []; }
const vdCol = v => v >= 40 ? 0x30d158 : v >= 20 ? 0xffd60a : 0xff453a;
function vdDraw(segs, lift) {
  const pos = [], col = [], C = new THREE.Color();
  for (const x of segs) { C.setHex(vdCol(x[4])); const a = gp(x[0], x[1], lift), b = gp(x[2], x[3], lift); pos.push(a.x, a.y, a.z, b.x, b.y, b.z); col.push(C.r, C.g, C.b, C.r, C.g, C.b); }
  if (pos.length) NAV.g.add(fatSegs(pos, col, MOBILE ? 2.5 : 3.5, 0.95));
}
const CAMK = { fw: "國道", thb: "省道", tc: "台中市區", tn: "台南市區" };
const camName = c => String(c[3] || CAMK[c[2]] || "攝影機").replace(/ S /, " 南向 ").replace(/ N /, " 北向 ").replace(/ E /, " 東向 ").replace(/ W /, " 西向 ");
const camHTML = list => list.length ? `<div class="nvh">附近的攝影機（${list.length}）</div><ul class="lst nvl cams">${list.slice(0, 6).map(({ c, d }) => `<li><button class="cam" ${camAttrs(c)}>▶ ${esc(camName(c))}</button><span>${CAMK[c[2]] || ""}・${dist(d)}</span></li>`).join("")}</ul>` : "";
const camAttrs = c => `data-cam="${esc(c[4])}" data-camn="${esc(camName(c))}" data-ll="${c[0]},${c[1]}"`;
const trAt = () => ROADS_LIVE && ROADS_LIVE.at ? ROADS_LIVE.at.slice(11, 16) : "";
// 個股：總部地址（listed_basic.json）→ 鄉鎮中心；重大訊息（mops）本來就有座標
function stockPts() {
  const lb = lazyJSON("lb", "listed_basic.json", 1440), map = (lb && lb.map) || {}, out = [];
  for (const x of items("tw_stocks")) { const a = map[x.code]; if (!a || /^00/.test(x.code)) continue;
    const addr = norm(a[0]).replace(/^\d+/, ""), C = COUNTIES.find(c => addr.startsWith(norm(c.name))); if (!C) continue;
    const T = (NAV.towns || []).find(t => sameC(t.county, C.name) && addr.includes(t.name)), base = T ? T.c : C.c, j = (parseInt(x.code, 10) % 7 - 3) * 0.004;
    const v = x.pct != null ? x.pct : (x.price && x.chg != null ? x.chg / (x.price - x.chg) * 100 : 0);
    out.push({ ll: [base[0] + j, base[1] - j], name: x.name, v, C, T, addr: a[0], x }); }
  return out;
}
const MOPS = () => (((P.mops || {}).items) || []).filter(x => x.ll);
// 全島動畫：景氣燈號、台灣情緒、電力，把整座島染成那個狀態，線條的呼吸快慢＝緊張程度
NAV.anim = null;
function islandTint(hex, speed, label, sub) {
  const col = new THREE.Color(hex), mats = [], fills = [];
  for (const c of COUNTIES) for (const r of c.rings) if (r.length > 30) {
    mats.push(navLine(r, col, 0.9, 1.2).material);
    const sh = new THREE.Shape(r.map(([lo, la]) => { const [x, z] = toXZ(lo, la); return new THREE.Vector2(x, -z); }));
    const m = new THREE.Mesh(new THREE.ShapeGeometry(sh), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.18, depthTest: false, depthWrite: false, side: THREE.DoubleSide }));
    m.rotation.x = -Math.PI / 2; m.position.y = 0.5; m.renderOrder = 7; NAV.g.add(m); fills.push(m.material); }
  addLabel(`<span class="nvp big"><i style="background:${hex}"></i><b>${esc(label)}</b>${sub ? `<em>${esc(sub)}</em>` : ""}</span>`, gp(121.0, 23.7, 4), "nv", "nav", 9);
  NAV.anim = t => { const w = 0.5 + 0.5 * Math.sin(t * speed); for (const m of mats) m.opacity = 0.45 + 0.5 * w; for (const m of fills) m.opacity = 0.08 + 0.16 * w; };
}
const bizSub = b => `${b.cat || ""}${b.cap ? `・資本 ${Math.round(b.cap / 1e4).toLocaleString("en-US")} 萬` : ""}${b.date ? `・${b.date.slice(5).replace("-", "/")} 登記` : ""}`;

// ---- 第 0 層：台灣 ----
const TW_VIEW = {
  now() {
    const S = countySeverity(), list = Object.entries(S).sort((a, b) => b[1].s - a[1].s);
    navCounties(c => { const sv = S[c.name], lv = sv ? (sv.s >= 3 ? 3 : sv.s >= 2 ? 2 : 1) : 0; return { col: SEV_C[lv], op: lv ? 0.9 : 0.25, sub: sv ? sv.why[0] : "", dot: lv ? "#" + SEV_C[lv].getHexString() : null, prio: lv * 3 + (/[市]$/.test(c.name) ? 1 : 0) }; });
    const rows = rankRows(list.slice(0, 6).map(([k, v]) => [k, v.why.join("・"), "#" + SEV_C[v.s >= 3 ? 3 : v.s >= 2 ? 2 : 1].getHexString()]), "nc");
    // 標題放「最值得注意的那一件事」：大地震 > 影響最多縣市的特報 > 路況最多的縣市；縣市數放到副標
    const ev = {}; for (const [k, v] of list) for (const w of v.why) if (!/^路況/.test(w)) (ev[w] = ev[w] || []).push(k);
    const qm = w => { const m = /^地震 M([\d.]+)/.exec(w); return m ? +m[1] : 0; };
    const top = Object.entries(ev).sort((a, b) => ((qm(b[0]) >= 5) - (qm(a[0]) >= 5)) || b[1].length - a[1].length || qm(b[0]) - qm(a[0]))[0];
    const nm = ks => ks.slice(0, 4).map(norm).join("、") + (ks.length > 4 ? " 等" : "");
    const big = top ? top[0] : list.length ? `${norm(list[0][0])}路況最多` : "全台平靜";
    const lead = top ? `${top[1].length} 個縣市：${nm(top[1])}。` : list.length ? `${list[0][1].why.join("・")}。` : "";
    return { eyebrow: "台灣 · 今天", title: "今天哪裡不對勁？", big, color: list.length ? "#ff9f0a" : UPH,
      body: list.length ? `<p class="why">${esc(lead)}下面依示警、近兩天地震、路況事件排序，點縣市或拉近看那裡此刻怎樣。</p><ul class="lst nvl">${rows}</ul>` : `<p class="why">目前沒有示警、明顯地震或路況事件。拉近任一縣市，看那裡此刻怎樣。</p>` };
  },
  house() {
    const H = (P.house || {}).city || {}, N = (P.house || {}).cityN || {}, ks = Object.keys(H).sort((a, b) => H[b] - H[a]), rk = k => ks.length > 1 ? 1 - ks.indexOf(k) / (ks.length - 1) : 0.5;
    navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true }; const col = new THREE.Color().setHSL(0.55 - 0.55 * rk(k), 0.85, 0.6);
      return { col, op: 0.85, sub: `${p1(H[k])} 萬`, dot: "#" + col.getHexString(), prio: 2 + rk(k) * 4 }; });
    return { eyebrow: `台灣 · 實價登錄 ${((P.house || {}).season) || ""}`, title: "哪裡最貴？", big: ks.length ? `${norm(ks[0])} ${p1(H[ks[0]])} 萬／坪` : "—", color: LENS.house.c,
      body: `<p class="why">各縣市成交均價，顏色越紅越貴。點縣市或拉近，看哪一區在漲。</p><ul class="lst nvl">${rankRows(ks.map(k => [k, `${p1(H[k])} 萬／坪・${(N[k] || 0).toLocaleString("en-US")} 筆`]), "nc")}</ul>` };
  },
  biz() {
    const BT = navBiz();
    if (BT) {
      const C = BT.counties || {}, ks = Object.keys(C).sort((a, b) => C[b].n - C[a].n), mx = Math.max(1, ...ks.map(k => C[k].n)), G = new THREE.Color(LENS.biz.c);
      navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true, op: 0.15 }; const v = C[k];
        return { col: G, op: 0.25 + 0.7 * Math.sqrt(v.n / mx), sub: `${v.n.toLocaleString("en-US")} 家 ${chgTxt(v.n, v.p)}`, dot: chgCol(v.n, v.p), prio: 2 + v.n / mx * 4 }; });
      const tot = ks.reduce((a, k) => a + C[k].n, 0), totp = ks.reduce((a, k) => a + C[k].p, 0);
      return { eyebrow: `台灣 · 新設立公司與商號 · ${BT.month}`, title: "新公司開在哪裡？", big: `${tot.toLocaleString("en-US")} 家`, chg: chgTxt(tot, totp) ? `比上月 ${chgTxt(tot, totp)}` : "", color: LENS.biz.c,
        body: `<p class="why">經濟部這個月的公司、商業登記，依地址歸到縣市與鄉鎮。綠點＝比上月多、紅點＝比上月少。</p><ul class="lst nvl">${ks.map(k => `<li data-nc="${esc(k)}" style="cursor:pointer"><span class="sdot" style="background:${chgCol(C[k].n, C[k].p)}"></span>${esc(norm(k))}<span>${C[k].n.toLocaleString("en-US")} 家・比上月 ${chgTxt(C[k].n, C[k].p) || "—"}</span></li>`).join("")}</ul>` };
    }
    const B = BRANDS(), n = {}; for (const b of B) { const c = COUNTIES.find(x => sameC(x.name, b.city || b.place)); if (c) n[c.name] = (n[c.name] || 0) + 1; }
    const mx = Math.max(1, ...Object.values(n)), list = Object.entries(n).sort((a, b) => b[1] - a[1]), G = new THREE.Color(LENS.biz.c);
    navCounties(c => n[c.name] ? { col: G, op: 0.35 + 0.6 * n[c.name] / mx, sub: `${n[c.name]} 家`, dot: LENS.biz.c, prio: 2 + n[c.name] / mx * 4 } : { dim: true, op: 0.15 });
    return { eyebrow: "台灣 · 新設立公司", title: "新公司開在哪裡？", big: `${B.length} 家`, color: LENS.biz.c,
      body: `<p class="why">完整的鄉鎮統計載入中；先顯示找得到地址的 ${B.length} 家。</p><ul class="lst nvl">${rankRows(list.map(([k, v]) => [k, `${v} 家`]), "nc")}</ul>` };
  },
  stock() {
    const S = stockPts(), M = MOPS(), byC = {};
    for (const m of M) { const c = countyAt(m.ll[0], m.ll[1]); if (c) byC[c.name] = (byC[c.name] || 0) + 1; }
    const mx = Math.max(1, ...Object.values(byC)), B = new THREE.Color(LENS.stock.c);
    navCounties(c => byC[c.name] ? { col: B, op: 0.25 + 0.7 * Math.sqrt(byC[c.name] / mx), sub: `重大訊息 ${byC[c.name]}`, dot: LENS.stock.c, prio: 1 + byC[c.name] / mx * 3 } : { dim: true, op: 0.15 });
    S.forEach(x => addLabel(pill(x.name, pct(x.v), x.v >= 0 ? UPH : DNH), gp(x.ll[0], x.ll[1], 2), "nv", "nav", 5 + Math.abs(x.v), () => stockInfo(x)));
    const cats = {}; for (const m of M) cats[m.cat] = (cats[m.cat] || 0) + 1;
    return { eyebrow: "台灣 · 上市櫃公司", title: "公司在哪裡、發生了什麼？", big: `${M.length} 則重大訊息`, color: LENS.stock.c,
      body: `<p class="why">標籤是關注個股的總部位置與最近收盤漲跌；縣市越亮，那裡的上市櫃公司最近發的重大訊息越多（${esc(Object.entries(cats).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => `${k} ${v}`).join("・"))}）。</p>`
        + barsHTML(S.slice().sort((a, b) => b.v - a.v).map(x => ({ name: x.name, v: x.v, txt: pct(x.v) })))
        + `<div class="nvh">值得注意的重大訊息</div>` + listHTML(M.filter(m => /事故|併購|澄清|法律|營運/.test(m.cat)).slice(0, 5).map(m => ({ t: `${m.short || m.name}：${m.t}`, s: `${m.cat}・${m.place || ""}・${m.d}`, url: m.u }))) };
  },
  elect() {
    const E = ((P.elect || {}).cities) || [], PC = { 國民黨: "#4f8cff", 民進黨: "#30d158", 民眾黨: "#64d2ff" };
    const lead = c => (c.cands || []).slice().sort((a, b) => b.p - a.p)[0] || {};
    navCounties(c => { const e = E.find(e => norm(c.name).startsWith(e.city)); if (!e) return { dim: true, op: 0.12 }; const L = lead(e), col = PC[L.party] || "#aeaeb2";
      return { col: new THREE.Color(col), op: 0.35 + 0.6 * Math.min(1, Math.abs(L.p - 50) / 40), sub: `${L.name} ${Math.round(L.p)}%`, dot: col, prio: 6 }; });
    return { eyebrow: "現場 · 2026 五都市長", title: "誰領先？", big: `${E.length} 都`, color: LENS.elect.c,
      body: `<p class="why">預測市場報價換算的當選機率；縣市越亮，領先越穩。點縣市看候選人和最近被討論的議題。</p><ul class="lst nvl">${E.map(e => { const L = lead(e); return `<li data-nc="${esc(COUNTIES.find(c => norm(c.name).startsWith(e.city))?.name || "")}" style="cursor:pointer"><span class="sdot" style="background:${PC[L.party] || "#aeaeb2"}"></span>${esc(e.city)}　${esc(L.name || "")}<span>${esc(L.party || "")}・${Math.round(L.p || 0)}%${L.d7 != null ? `・7 天 ${L.d7 >= 0 ? "+" : "−"}${Math.abs(L.d7)}` : ""}</span></li>`; }).join("")}</ul>` };
  },
  macro() {
    const M = items("macro"), sig = (M.find(x => /景氣燈號/.test(x.label)) || {}).value || "", hex = /紅/.test(sig) ? "#ff453a" : /黃紅/.test(sig) ? "#ff9f0a" : /綠/.test(sig) ? "#30d158" : /黃藍/.test(sig) ? "#64d2ff" : /藍/.test(sig) ? "#0a84ff" : "#aeaeb2";
    islandTint(hex, /紅|藍/.test(sig) ? 2.2 : 1.2, `景氣${sig}`, "國發會景氣對策信號");
    return { eyebrow: "總經 · 國發會・主計總處・央行", title: "台灣景氣現在幾度？", big: sig || "—", color: hex,
      body: `<p class="why">整座島染成景氣燈號的顏色：紅＝過熱、黃紅＝轉熱、綠＝穩定、黃藍＝轉冷、藍＝低迷。呼吸越快代表越偏離穩定。</p>` + listHTML(M.map(x => ({ t: `${x.label}　${x.value}`, s: `${x.period || ""}${x.prev ? ` · 前期 ${x.prev}` : ""}` }))) };
  },
  mood() {
    const m = (P.mood || {}).taiwan || {}, sc = m.score || 0, hex = sc <= -0.25 ? "#ff453a" : sc < -0.05 ? "#ff9f0a" : sc < 0.1 ? "#ffd60a" : "#30d158";
    islandTint(hex, 1 + Math.abs(sc) * 4, m.label || "情緒", (m.themes || []).slice(0, 2).join("・"));
    return { eyebrow: "輿情 · 社群與新聞標題", title: "台灣人今天的心情", big: m.label || "—", color: hex,
      body: moodViz() + `<p class="why">${esc(m.line || "")}</p>` + listHTML((m.themes || []).map(t => ({ t: "· " + t }))) + (P.mood && P.mood.watch ? `<p class="why">${esc(P.mood.watch)}</p>` : "") };
  },
  power() {
    const pw = P.power || {}, r = pw.reserve_pct || 0, hex = { 綠: "#30d158", 黃: "#ffd60a", 橘: "#ff9f0a", 紅: "#ff453a", 黑: "#8e8e93" }[pw.level] || (r < 6 ? "#ff453a" : r < 10 ? "#ffd60a" : "#30d158");
    islandTint(hex, 0.8 + Math.max(0, 15 - r) * 0.5, `備轉 ${nf(r)}%`, `供電${pw.level || ""}燈`);
    return { eyebrow: "現場 · 台電", title: "今天電夠不夠？", big: `${nf(r)}%`, chg: pw.yday_reserve_pct != null ? `昨天 ${nf(pw.yday_reserve_pct)}%` : "", color: hex,
      body: `<p class="why">備轉容量率 10% 以上算充裕（綠燈），6% 以下就要限電警戒。島的呼吸越急，電越吃緊。</p>`
        + listHTML([{ t: `目前用電 ${nf(pw.curr_mw / 10)} 萬瓩`, s: `使用率 ${nf(pw.util_pct || 0)}%` }, { t: `今天尖峰預估 ${nf(pw.peak_mw / 10)} 萬瓩`, s: `尖峰時段 ${pw.peak_hours || ""}` }]) + lineSVG(pw.spark, hex) };
  },
  traffic() {
    const S = trSegs(), by = {};
    trDraw(S.filter(x => x.k === "fw"), 1.2);   // 全台看國道：粗線依車速上色
    for (const x of S) if (x.c) (by[x.c] = by[x.c] || []).push(x);
    const ev = {}; for (const e of trEvents(() => true)) { const c = countyAt(e.ll[0], e.ll[1]); if (c) ev[c.name] = (ev[c.name] || 0) + 1; }
    const rows = COUNTIES.map(c => { const st = trStats(by[c.name] || []), sc = st.fwSlow.length * 2 + st.thbSlow.length + (ev[c.name] || 0); return { c, st, ev: ev[c.name] || 0, sc }; }).sort((a, b) => b.sc - a.sc);
    navCounties(c => { const r = rows.find(r => r.c === c), lv = r.sc >= 6 ? 3 : r.sc >= 3 ? 2 : r.sc >= 1 ? 1 : 0;
      const sub = r.st.fwSlow.length ? `國道塞 ${r.st.fwSlow.length} 段` : r.st.thbSlow.length ? `省道慢 ${r.st.thbSlow.length} 段` : r.ev ? `事件 ${r.ev}` : r.st.fwAvg ? `國道 ${r.st.fwAvg} km/h` : "";
      return { col: SEV_C[lv], op: lv ? 0.9 : 0.3, sub, dot: lv ? "#" + SEV_C[lv].getHexString() : UPH, prio: lv * 3 + 1 }; });
    const all = trStats(S), hot = rows.filter(r => r.sc > 0);
    return { eyebrow: `台灣 · 即時車流 · ${trAt()}`, title: "哪裡在塞？", big: all.fwSlow.length ? `國道 ${all.fwSlow.length} 段在塞` : "國道順暢", chg: all.fwAvg ? `平均 ${all.fwAvg} km/h` : "", color: LENS.traffic.c,
      body: `<p class="why">國道低於 40、省道低於 20 km/h 算塞；再加上施工、事故等路況事件。點縣市看哪幾條路。</p>`
        + (hot.length ? `<ul class="lst nvl">${hot.slice(0, 10).map(r => `<li data-nc="${esc(r.c.name)}" style="cursor:pointer"><span class="sdot" style="background:#${SEV_C[r.sc >= 6 ? 3 : r.sc >= 3 ? 2 : 1].getHexString()}"></span>${esc(norm(r.c.name))}<span>${[r.st.fwSlow.length ? `國道塞 ${r.st.fwSlow.length} 段` : "", r.st.thbSlow.length ? `省道慢 ${r.st.thbSlow.length} 段` : "", r.ev ? `事件 ${r.ev} 起` : ""].filter(Boolean).join("・")}</span></li>`).join("")}</ul>` : `<p class="empty">全台國道、省道目前都順。</p>`) };
  },
  jobs() {
    const A = ((P.jobs || {}).areas) || [], mx = Math.max(1, ...A.map(a => a.n)), B = new THREE.Color(LENS.jobs.c);
    navCounties(c => { const a = jobArea(c.name); if (!a) return { dim: true, op: 0.15 };
      return { col: B, op: 0.25 + 0.7 * Math.sqrt(a.n / mx), sub: `${(a.n / 1e3).toFixed(a.n >= 1e4 ? 0 : 1)}K ${pctTxt(a.chg7)}`, dot: pctCol(a.chg7), prio: 2 + a.n / mx * 4 }; });
    const j = P.jobs || {};
    return { eyebrow: "台灣 · 104 刊登中職缺", title: "哪裡在找人？", big: `${(j.total || 0).toLocaleString("en-US")} 個`, chg: j.chg7 != null ? `7 天 ${pctTxt(j.chg7)}` : "", color: LENS.jobs.c,
      body: `<p class="why">各縣市刊登中的職缺數，綠＝7 天內變多、紅＝變少。新竹、嘉義的縣和市在 104 是合併計算。</p><ul class="lst nvl">${A.slice().sort((a, b) => b.n - a.n).map(a => `<li data-nc="${esc(a.counties[0])}" style="cursor:pointer"><span class="sdot" style="background:${pctCol(a.chg7)}"></span>${esc(a.name)}<span>${a.n.toLocaleString("en-US")} 個・7 天 ${pctTxt(a.chg7) || "—"}</span></li>`).join("")}</ul>` };
  },
  tender() {
    const C = TM().counties || {}, ks = Object.keys(C).filter(k => k !== "中央").sort((a, b) => (C[b].n + C[b].a) - (C[a].n + C[a].a)), mx = Math.max(1, ...ks.map(k => C[k].n)), Y = new THREE.Color(LENS.tender.c);
    navCounties(c => { const v = tmC(c.name); if (!v) return { dim: true, op: 0.15 };
      return { col: Y, op: 0.25 + 0.7 * Math.sqrt(v.n / mx), sub: `${v.n} 件 ${chgTxt(v.n, v.np)}`, dot: chgCol(v.n, v.np), prio: 2 + v.n / mx * 4 }; });
    const cen = C["中央"], tot = ks.reduce((a, k) => a + C[k].n, 0), totp = ks.reduce((a, k) => a + C[k].np, 0);
    if (!ks.length) return { eyebrow: "台灣 · 政府標案", title: "哪裡在發包？", big: "整理中", color: LENS.tender.c, body: `<p class="empty">各縣市的標案統計第一次產生需要一輪資料更新，稍後再看。</p>` };
    return { eyebrow: `台灣 · 政府標案 · ${tmDays()}`, title: "哪裡在發包？", big: `${tot.toLocaleString("en-US")} 件新招標`, chg: totp ? `比前一週 ${chgTxt(tot, totp)}` : "", color: LENS.tender.c,
      body: `<p class="why">近 7 個工作天各縣市機關（縣市政府、公所、市立學校等）的新招標，依發包機關歸類，不是工程地點。${cen ? `部會、國營事業等中央機關另有 ${cen.n.toLocaleString("en-US")} 件，沒有放上地圖。` : ""}</p><ul class="lst nvl">${ks.map(k => `<li data-nc="${esc(k)}" style="cursor:pointer"><span class="sdot" style="background:${chgCol(C[k].n, C[k].np)}"></span>${esc(norm(k))}<span>${C[k].n} 件招標・${C[k].a} 件決標・比前一週 ${chgTxt(C[k].n, C[k].np) || "—"}</span></li>`).join("")}</ul>` };
  },
  news() {
    const N = NEWS(), top = {}; for (const x of N) { const c = COUNTIES.find(k => sameC(k.name, String(x.place).slice(0, 3))); if (c && !top[c.name]) top[c.name] = x; }
    const Pu = new THREE.Color(LENS.news.c);
    navCounties(c => { const x = top[c.name]; if (!x) return { dim: true }; const h = (Date.now() - new Date(x.at)) / 36e5, fresh = h < 6;
      return { col: Pu, op: fresh ? 0.9 : 0.35, sub: x.t.slice(0, 12) + (x.t.length > 12 ? "…" : ""), dot: fresh ? LENS.news.c : "#8e8e93", prio: 2 + Math.max(0, 6 - h) }; });
    const list = Object.entries(top).sort((a, b) => newsScore(b[1]) - newsScore(a[1]));
    return { eyebrow: "台灣 · 地方新聞", title: "各地在發生什麼？", big: `${list.length} 個縣市`, color: LENS.news.c,
      body: newsViz(list) + `<p class="why">每個縣市最值得知道的一則：開店、建設、交通、活動、政策優先，政治口水和社會新聞往後放。紫點＝6 小時內。點縣市看那裡的新聞。</p><ul class="lst nvl">${list.map(([k, x]) => `<li data-nc="${esc(k)}" style="cursor:pointer"><b style="font-weight:600">${esc(norm(k))}</b>　${esc(x.t)}<span>${esc(x.s || "")}・${navAgo(x.at)}</span></li>`).join("")}</ul>` };
  },
};
// ---- 第 1 層：城市 ----
const CITY_VIEW = {
  now(C) {
    const ts = navOutline(C), here = [], cnt = {};
    for (const e of (((P.roads || {}).events) || [])) if (e.ll && countyAt(e.ll[0], e.ll[1]) === C) here.push({ k: "路況", c: "#ff9f0a", ll: e.ll, t: `${e.road || ""} ${e.kind || ""}`, s: e.impact || e.dir || "" });
    for (const p of (((P.culture || {}).points) || [])) if (countyAt(p[0], p[1]) === C) here.push({ k: "藝文", c: "#bf5af2", ll: [p[0], p[1]], t: p[2], s: `${p[3]}・${p[4]}` });
    for (const it of here) { const t = townAt(it.ll[0], it.ll[1]); if (t) { it.town = t.name; (cnt[t.name] = cnt[t.name] || { r: 0, a: 0, t }); cnt[t.name][it.k === "路況" ? "r" : "a"]++; } }
    here.filter(i => i.k === "路況").forEach(i => pin(i, 4)); here.filter(i => i.k === "藝文").slice(0, 20).forEach(i => pin(i, 1));
    const rank = Object.values(cnt).sort((a, b) => (b.r * 3 + b.a) - (a.r * 3 + a.a));
    for (const x of rank.slice(0, 10)) addLabel(pill(x.t.name, [x.r ? `路況 ${x.r}` : "", x.a ? `藝文 ${x.a}` : ""].filter(Boolean).join("・"), x.r ? "#ff9f0a" : "#bf5af2"), gp(x.t.c[0], x.t.c[1], 1.5), "nv", "nav", 3);
    townPills(ts, new Set(rank.slice(0, 10).map(x => x.t.name)));
    const by = k => here.filter(i => i.k === k);
    return { eyebrow: `${norm(C.name)} · 此刻`, title: "這座城市此刻怎樣？", big: `${by("路況").length} 起路況・${by("藝文").length} 檔藝文`, color: LENS.now.c,
      body: wxLine(C) + (rank.length ? `<div class="nvh">哪一區最熱鬧</div><ul class="lst nvl">${rankRows(rank.slice(0, 6).map(x => [x.t.name, [x.r ? `路況 ${x.r}` : "", x.a ? `藝文 ${x.a}` : ""].filter(Boolean).join("・")]), "nt")}</ul>` : "")
        + (by("路況").length ? `<div class="nvh">路況</div>` + listHTML(by("路況").slice(0, 4).map(i => ({ t: i.t, s: `${i.town || ""}${i.s ? "・" + i.s : ""}` }))) : "")
        + (!here.length ? `<p class="empty">這裡目前沒有路況事件或藝文活動。</p>` : "") };
  },
  house(C) {
    const ts = navOutline(C), H = ((P.house || {}).towns || []).filter(h => sameC(h[2], C.name)).sort((a, b) => b[4] - a[4]);
    const mx = Math.max(1, ...H.map(h => h[4])), mn = Math.min(...H.map(h => h[4]), mx), view = NAV.viewD || 60;
    H.forEach((h, i) => navCol(h[0], h[1], (h[4] - mn) / Math.max(1e-6, mx - mn), view, h[3], `${p1(h[4])} 萬`, 6 - i * 0.2));
    townPills(ts, new Set(H.map(h => h[3])));
    const avg = cOf((P.house || {}).city);
    return { eyebrow: `${norm(C.name)} · 實價登錄 ${((P.house || {}).season) || ""}`, title: "這座城市哪一區最貴？", big: avg ? `${p1(avg)} 萬／坪` : norm(C.name), color: LENS.house.c,
      body: wxLine(C) + (H.length ? `<div class="nvh">各區成交均價（光柱越高越貴）</div><ul class="lst nvl">${rankRows(H.slice(0, 10).map(h => [h[3], `${p1(h[4])} 萬／坪・${h[5]} 筆`]), "nt")}</ul>` : `<p class="empty">這個縣市本季成交太少，沒有分區均價。</p>`) };
  },
  biz(C) {
    const ts = navOutline(C), BT = navBiz();
    if (BT) {
      const R = btTowns(C), mx = Math.max(1, ...R.map(r => r[2])), view = NAV.viewD || 60;
      R.forEach((r, i) => { const t = ts.find(t => t.name === r[1]); if (t) navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `${r[2]} 家 ${chgTxt(r[2], r[3])}`, 6 - i * 0.2, chgCol(r[2], r[3])); });
      townPills(ts, new Set(R.map(r => r[1])));
      const v = (BT.counties || {})[Object.keys(BT.counties || {}).find(k => sameC(k, C.name))] || { n: 0, p: 0 }, des = R.reduce((a, r) => a + r[5], 0);
      const top = R.flatMap(r => r[6].map(x => [...x, r[1]])).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 6);
      return { eyebrow: `${norm(C.name)} · 新設立 · ${BT.month}`, title: "新公司開在哪一區？", big: `${v.n.toLocaleString("en-US")} 家`, chg: v.p ? `比上月 ${chgTxt(v.n, v.p)}` : "", color: LENS.biz.c,
        body: `<p class="why">光柱越高開越多；綠＝比上月多、紅＝比上月少。其中設計創意類 ${des} 家。</p><ul class="lst nvl">${rankRows(R.slice(0, 8).map(r => [r[1], btLine(r)]), "nt")}</ul>`
          + (top.length ? `<div class="nvh">資本額最大的幾家</div>` + listHTML(top.map(x => ({ t: x[0], s: `${x[4]}・${x[2]}・資本 ${capTxt(x[1] || 0)}`, url: `https://www.google.com/search?q=${encodeURIComponent(x[0])}` }))) : "") };
    }
    const B = BRANDS().filter(b => sameC(b.city || "", C.name) || inC(b.place, C)), cnt = {};
    for (const b of B) { const t = ts.find(t => String(b.place || "").includes(t.name)) || (b.ll && townAt(b.ll[0], b.ll[1])); if (t) (cnt[t.name] = cnt[t.name] || { n: 0, t }).n++; }
    const rank = Object.values(cnt).sort((a, b) => b.n - a.n);
    for (const x of rank) addLabel(pill(x.t.name, `${x.n} 家`, LENS.biz.c), gp(x.t.c[0], x.t.c[1], 1.5), "nv", "nav", 3 + x.n);
    townPills(ts, new Set(rank.map(x => x.t.name)));
    return { eyebrow: `${norm(C.name)} · 新設立公司`, title: "新公司開在哪一區？", big: `${B.length} 家`, color: LENS.biz.c,
      body: rank.length ? `<ul class="lst nvl">${rankRows(rank.slice(0, 6).map(x => [x.t.name, `${x.n} 家`]), "nt")}</ul>` : `<p class="empty">完整的鄉鎮統計載入中。</p>` };
  },
  stock(C) {
    navOutline(C);
    const S = stockPts().filter(x => x.C === C), M = MOPS().filter(m => countyAt(m.ll[0], m.ll[1]) === C);
    S.forEach(x => addLabel(pill(x.name, pct(x.v), x.v >= 0 ? UPH : DNH), gp(x.ll[0], x.ll[1], 1), "nv", "nav", 6, () => stockInfo(x)));
    M.slice(0, 30).forEach(m => pin({ c: LENS.stock.c, ll: m.ll, t: `${m.short || m.name}・${m.cat}`, k: "重大訊息", s: `${m.name}（${m.code}）・${m.mk || ""}・${m.d || ""}`, d2: m.t, desc: m.desc, url: m.code ? `https://mops.twse.com.tw/mops/#/web/t05st01?companyId=${m.code}` : "" }, 1));
    return { eyebrow: `${norm(C.name)} · 上市櫃公司`, title: "這裡的公司發生了什麼？", big: `${M.length} 則重大訊息`, color: LENS.stock.c,
      body: (S.length ? barsHTML(S.map(x => ({ name: x.name, v: x.v, txt: pct(x.v) }))) : "") + listHTML(M.slice(0, 8).map(m => ({ t: `${m.short || m.name}：${m.t}`, s: `${m.cat}・${m.place || ""}・${m.d}`, url: m.u }))) };
  },
  elect(C) {
    navOutline(C);
    const e = (((P.elect || {}).cities) || []).find(e => norm(C.name).startsWith(e.city));
    if (!e) return { eyebrow: `${norm(C.name)} · 選戰`, title: "這裡不在五都預測範圍", big: norm(C.name), color: LENS.elect.c, body: `<p class="why">預測市場只有五都市長的盤口。</p>` };
    const cs = (e.cands || []).slice().sort((a, b) => b.p - a.p);
    return { eyebrow: `${norm(C.name)} · 市長選戰`, title: `${cs[0] ? cs[0].name : ""} 領先`, big: cs[0] ? `${Math.round(cs[0].p)}%` : "—", color: LENS.elect.c,
      body: cs.map(c => `<div class="nvh">${esc(c.name)}・${esc(c.party || "")}・${Math.round(c.p)}%${c.d7 != null ? `（7 天 ${c.d7 >= 0 ? "+" : "−"}${Math.abs(c.d7)}）` : ""}</div>` + (c.spark ? lineSVG(c.spark, c.d7 >= 0 ? UPH : DNH) : "") + (c.topics && c.topics.length ? `<p class="why">被討論最多：${esc(c.topics.slice(0, 4).map(t => t[0]).join("、"))}</p>` : "")).join("") };
  },
  traffic(C) {
    const ts = navOutline(C), S = trSegs().filter(x => x.c === C.name), st = trStats(S), E = trEvents(e => countyAt(e.ll[0], e.ll[1]) === C);
    trDraw(S, 0.5);
    const vd = sameC(C.name, "臺北市") ? vdSegs() : [];
    vdDraw(vd, 0.4);
    const vdSlow = vd.filter(x => x[4] < 15 && x[5] >= 10).map(x => ({ k: "vd", n: x[6], s: x[4], ll: [(x[0] + x[2]) / 2, (x[1] + x[3]) / 2] }));
    const slow = [...st.fwSlow, ...st.thbSlow, ...vdSlow].sort((a, b) => a.s - b.s);
    slow.slice(0, 10).forEach(x => pin({ c: "#ff453a", ll: x.ll, t: `${x.s} km/h ${trName(x)}`, k: "塞車路段", s: `${x.n}・現在 ${x.s} km/h`, cam: 1 }, 4));
    E.forEach(e => pin({ c: "#ff9f0a", ll: e.ll, t: `${e.road || ""} ${e.kind || ""}`, k: "路況事件", s: [e.title, e.impact && e.impact !== "無影響" ? "影響：" + e.impact : "", e.at ? navAgo(e.at) : ""].filter(Boolean).join("・"), cam: 1 }, 2));
    townPills(ts, new Set());
    return { eyebrow: `${norm(C.name)} · 即時車流 · ${trAt()}`, title: "哪幾條路在塞？", big: slow.length ? `${slow.length} 段在塞` : "目前順暢", chg: st.fwAvg ? `國道平均 ${st.fwAvg} km/h` : "", color: LENS.traffic.c,
      body: `<p class="why">線條依車速上色（綠順、黃車多、紅塞），國道是流動的光點。${vd.length ? `台北市區 ${vd.length} 段路口偵測器車速也畫上了。` : st.thbN ? `省道有車速的 ${st.thbN} 段。` : "這裡沒有省道即時車速。"}</p>`
        + (slow.length ? `<div class="nvh">最慢的路段</div>` + listHTML(slow.slice(0, 8).map(x => trRow({ ...x, d: null }))) : "")
        + (E.length ? `<div class="nvh">路況事件（${E.length}）</div>` + listHTML(E.slice(0, 6).map(e => ({ t: e.title || `${e.road || ""} ${e.kind || ""}`, s: e.impact || "", url: /^國道/.test(e.road || "") ? "https://1968.freeway.gov.tw/" : "" }))) : "")
        + (() => { const seen = new Set(), near = [];   // 塞的地方（或事件）旁邊最近的攝影機，直接點來看
          for (const x of [...slow.slice(0, 4), ...E.slice(0, 3)]) { const c = camsNear(x.ll, 1.5)[0]; if (c && !seen.has(c.c[4])) { seen.add(c.c[4]); near.push(c); } }
          camSetList(near.map(x => x.c), { auto: false, where: norm(C.name) + "塞車點" });
          return near.length ? camHTML(near).replace("附近的攝影機", "塞車點旁的攝影機") : ""; })() };
  },
  jobs(C) {
    const ts = navOutline(C), R = jobTowns(C.name), a = jobArea(C.name), L = jobLatest(C.name), view = NAV.viewD || 60;
    const mx = Math.max(1, ...R.map(r => r[2]));
    R.forEach((r, i) => { const t = ts.find(t => t.name === r[1]); if (t) navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `${r[2].toLocaleString("en-US")} ${pctTxt(r[3])}`, 6 - i * 0.2, r[3] == null ? LENS.jobs.c : pctCol(r[3])); });
    townPills(ts, new Set(R.map(r => r[1])));
    return { eyebrow: `${norm(C.name)} · 104 刊登中職缺`, title: "哪一區在找人？", big: a ? `${a.n.toLocaleString("en-US")} 個` : norm(C.name), chg: a && a.chg7 != null ? `7 天 ${pctTxt(a.chg7)}` : "", color: LENS.jobs.c,
      body: (a && a.counties.length > 1 ? `<p class="why">104 把${esc(a.name)}合併計算。</p>` : "")
        + (R.length ? `<p class="why">光柱越高職缺越多；綠＝7 天內變多、紅＝變少。</p><ul class="lst nvl">${rankRows(R.slice(0, 10).map(r => [r[1], `${r[2].toLocaleString("en-US")} 個・7 天 ${pctTxt(r[3]) || "—"}`]), "nt")}</ul>` : `<p class="why">分區統計只做六都和新竹。</p>`)
        + (L.length ? `<div class="nvh">剛刊登的</div>` + listHTML(L.slice(0, 5).map(jobRow)) : "") };
  },
  tender(C) {
    const ts = navOutline(C), v = tmC(C.name), R = tmTowns(C.name), mx = Math.max(1, ...R.map(r => r[2] + r[3])), view = NAV.viewD || 60;
    R.forEach((r, i) => { const t = ts.find(t => t.name === r[1]); if (t) navCol(t.c[0], t.c[1], (r[2] + r[3]) / mx, view, r[1], `${r[2] + r[3]} 件`, 6 - i * 0.2, r[4] ? chgCol(r[2], r[4]) : LENS.tender.c); });
    townPills(ts, new Set(R.map(r => r[1])));
    if (!v) return { eyebrow: `${norm(C.name)} · 政府標案`, title: "這裡在發包什麼？", big: norm(C.name), color: LENS.tender.c, body: `<p class="empty">最近一週沒有歸到這個縣市的標案，或統計還在整理中。</p>` };
    return { eyebrow: `${norm(C.name)} · 政府標案 · ${tmDays()}`, title: "這裡在發包什麼？", big: `${v.n} 件招標`, chg: v.np ? `比前一週 ${chgTxt(v.n, v.np)}` : "", color: LENS.tender.c,
      body: `<p class="why">另有 ${v.a} 件決標。看得出區的（公所、區立或市立學校）才分區，縣市政府本身不分區。</p>`
        + ((v.units || []).length ? `<div class="nvh">發包最多的機關</div><ul class="lst nvl">${v.units.slice(0, 4).map(([n, c]) => `<li>${esc(n)}<span>${c} 件</span></li>`).join("")}</ul>` : "")
        + (v.win.length ? `<div class="nvh">得標最多的廠商</div><ul class="lst nvl">${v.win.map(([n, c]) => `<li>${esc(n)}<span>${c} 件</span></li>`).join("")}</ul>` : "")
        + (R.length ? `<div class="nvh">哪一區發包最多</div><ul class="lst nvl">${rankRows(R.slice(0, 6).map(r => [r[1], `${r[2]} 件招標・${r[3]} 件決標`]), "nt")}</ul>` : "")
        + (v.recent.length ? `<div class="nvh">最新招標</div>` + tmRecent(v.recent) : "") };
  },
  news(C) {
    const ts = navOutline(C), N = NEWS().filter(x => inC(x.place, C)), T = N.filter(x => x.lvl === "town" && x.ll);
    const tc = {}; for (const x of T) { const k = String(x.place).slice(3); tc[k] = (tc[k] || 0) + 1; }
    T.slice(0, 16).forEach(x => pin({ c: LENS.news.c, ll: x.ll, t: x.t, k: "地方新聞", s: [String(x.place || "").slice(0, 6), x.s, x.at ? navAgo(x.at) : ""].filter(Boolean).join("・"), url: x.u }, 1));
    for (const t of ts) if (tc[t.name]) addLabel(pill(t.name, `${tc[t.name]} 則`, LENS.news.c), gp(t.c[0], t.c[1], 1.5), "nv", "nav", 3 + tc[t.name]);
    const tn = new Set(Object.keys(tc)); townPills(ts, tn);
    const more = ((cOf((P.localnews || {}).counties)) || []).filter(n => !N.some(x => x.t === n.title));
    return { eyebrow: `${norm(C.name)} · 地方新聞`, title: "這裡在發生什麼？", big: `${N.length + more.length} 則`, color: LENS.news.c,
      body: wxLine(C) + (T.length ? `<div class="nvh">標得出行政區的（${T.length}）</div>` + listHTML(T.slice(0, 5).map(x => ({ t: x.t, s: `${String(x.place).slice(3)}・${x.s || ""}・${navAgo(x.at)}`, url: x.u }))) : "")
        + `<div class="nvh">全縣市</div>` + listHTML([...N.filter(x => x.lvl !== "town").map(x => ({ t: x.t, s: `${x.s || ""}・${navAgo(x.at)}`, url: x.u })), ...more.map(n => ({ t: n.title, s: n.source, url: n.url }))].slice(0, 6)) };
  },
};
// ---- 第 2 層：街道 ----
const STREET_VIEW = {
  now(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const here = tw(), R = 2.2, items = [];
    for (const e of (((P.roads || {}).events) || [])) if (e.ll && kmBetween(e.ll, here) < R * 2) items.push({ k: "路況", c: "#ff9f0a", ll: e.ll, t: `${e.road || ""} ${e.kind || ""}`, s: [e.title, e.impact && e.impact !== "無影響" ? "影響：" + e.impact : "", e.at ? navAgo(e.at) : ""].filter(Boolean).join("・"), cam: 1 });
    for (const p of (((P.culture || {}).points) || [])) if (kmBetween([p[0], p[1]], here) < R) items.push({ k: "藝文", c: "#bf5af2", ll: [p[0], p[1]], t: p[2], s: [p[3], p[4], p[5]].filter(Boolean).join("・"), url: [p[6], p[7]].find(u => /^https?:/.test(u || "")) || "" });
    for (const x of NEWS()) if (x.lvl === "town" && x.ll && (kmBetween(x.ll, here) < R || inT(x.place, T))) items.push({ k: "新聞", c: "#bf5af2", ll: x.ll, t: x.t, s: x.s || "", url: x.u });
    items.forEach(it => { it.d = kmBetween(it.ll, here); }); items.sort((a, b) => a.d - b.d);
    for (const it of items.slice(0, 24)) pin(it, 3 - it.d);
    const by = k => items.filter(i => i.k === k), sec = (k, arr) => arr.length ? `<div class="nvh">${k}（${arr.length}）</div>` + listHTML(arr.slice(0, 4).map(i => ({ t: i.t, s: `${i.s}${i.s ? "・" : ""}${dist(i.d)}`, url: i.url }))) : "";
    return { eyebrow: `${norm(T.county)} › ${T.name} · 此刻`, title: "這裡此刻怎樣？", big: T.name, color: LENS.now.c,
      body: wxLine(C) + `<p class="why">附近 ${R} 公里內：</p>` + (items.length ? sec("路況", by("路況")) + sec("藝文活動", by("藝文")) + sec("在地新聞", by("新聞")) : `<p class="empty">這附近目前沒有路況事件或藝文活動。</p>`) };
  },
  house(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const all = ((P.house || {}).towns || []).filter(h => sameC(h[2], T.county)).sort((a, b) => b[4] - a[4]), me = all.find(h => h[3] === T.name), avg = cOf((P.house || {}).city), view = NAV.viewD || 10;
    const near = all.filter(h => h !== me && kmBetween([h[0], h[1]], T.c) < 9).sort((a, b) => kmBetween([a[0], a[1]], T.c) - kmBetween([b[0], b[1]], T.c)).slice(0, 5);
    const grp = me ? [me, ...near] : near, mx = Math.max(1, ...grp.map(h => h[4])), mn = Math.min(...grp.map(h => h[4]), mx);
    grp.forEach(h => navCol(h[0], h[1], (h[4] - mn) / Math.max(1e-6, mx - mn), view, h[3], `${p1(h[4])} 萬`, h === me ? 9 : 4));
    const vs = me && avg ? (me[4] / avg - 1) * 100 : null;
    return { eyebrow: `${norm(T.county)} › ${T.name} · 實價登錄 ${((P.house || {}).season) || ""}`, title: "這一區的房價", big: me ? `${p1(me[4])} 萬／坪` : T.name, color: LENS.house.c,
      body: me ? `<p class="why">${me[5]} 筆成交均價，在${esc(norm(T.county))}排第 ${all.indexOf(me) + 1}／${all.length}${vs != null ? `，比全縣市均價${vs >= 0 ? "高" : "低"} ${Math.abs(vs).toFixed(0)}%` : ""}。</p>`
        + (near.length ? `<div class="nvh">隔壁幾區</div><ul class="lst nvl">${rankRows(near.map(h => [h[3], `${p1(h[4])} 萬／坪・${h[5]} 筆`]), "nt")}</ul>` : "") : `<p class="empty">這一區本季成交太少，沒有均價。</p>` };
  },
  biz(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const BT = navBiz(), R = BT ? btTowns(T.county) : [], me = R.find(r => r[1] === T.name), view = NAV.viewD || 10, towns = NAV.towns || [];
    const near = R.filter(r => r !== me).map(r => [r, towns.find(t => t.name === r[1] && sameC(t.county, T.county))]).filter(([, t]) => t && kmBetween(t.c, T.c) < 9).sort((a, b) => kmBetween(a[1].c, T.c) - kmBetween(b[1].c, T.c)).slice(0, 5);
    const grp = [...(me ? [[me, T]] : []), ...near], mx = Math.max(1, ...grp.map(([r]) => r[2]));
    grp.forEach(([r, t]) => navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `${r[2]} 家 ${chgTxt(r[2], r[3])}`, r === me ? 9 : 4, chgCol(r[2], r[3])));
    if (!me) return { eyebrow: `${norm(T.county)} › ${T.name} · 新設立`, title: "這一區開了什麼公司？", big: T.name, color: LENS.biz.c, body: `<p class="empty">${BT ? "這一區這個月沒有新登記的公司或商號。" : "鄉鎮統計載入中。"}</p>` };
    const rk = R.indexOf(me) + 1;
    return { eyebrow: `${norm(T.county)} › ${T.name} · 新設立 · ${BT.month}`, title: "這一區開了什麼公司？", big: `${me[2]} 家`, chg: me[3] ? `比上月 ${chgTxt(me[2], me[3])}` : "", color: LENS.biz.c,
      body: `<p class="why">在${esc(norm(T.county))}排第 ${rk}／${R.length}。${me[4].length ? "主要是" + esc(me[4].map(c => `${c[0]} ${c[1]} 家`).join("、")) + "。" : ""}${me[5] ? `設計創意類 ${me[5]} 家。` : ""}${me[8] != null ? `同月解散 ${me[8]} 家公司（新設公司 ${me[7]} 家，淨${me[7] - me[8] >= 0 ? "增" : "減"} ${Math.abs(me[7] - me[8])}）。` : ""}</p>`
        + (me[6].length ? `<div class="nvh">資本額最大的幾家</div>` + listHTML(me[6].map(x => ({ t: x[0], s: `${x[2]}・資本 ${capTxt(x[1] || 0)}・${(x[3] || "").slice(5).replace("-", "/")} 登記`, url: `https://www.google.com/search?q=${encodeURIComponent(x[0])}` }))) : "")
        + (near.length ? `<div class="nvh">隔壁幾區</div><ul class="lst nvl">${rankRows(near.map(([r]) => [r[1], btLine(r)]), "nt")}</ul>` : "") };
  },
  stock(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const here = tw(), M = MOPS().map(m => ({ m, d: kmBetween(m.ll, here) })).filter(o => o.d < 3).sort((a, b) => a.d - b.d);
    M.slice(0, 20).forEach(({ m }) => pin({ c: LENS.stock.c, ll: m.ll, t: m.short || m.name, k: "重大訊息", s: `${m.name}（${m.code}）・${m.mk || ""}・${m.d || ""}`, d2: m.t, desc: m.desc, url: m.code ? `https://mops.twse.com.tw/mops/#/web/t05st01?companyId=${m.code}` : "" }, 2));
    return { eyebrow: `${norm(T.county)} › ${T.name} · 上市櫃公司`, title: "附近的公司發生了什麼？", big: `${M.length} 則`, color: LENS.stock.c,
      body: M.length ? listHTML(M.slice(0, 8).map(({ m, d }) => ({ t: `${m.short || m.name}：${m.t}`, s: `${m.cat}・${dist(d)}・${m.d}`, url: m.u }))) : `<p class="empty">附近 3 公里沒有上市櫃公司發重大訊息。</p>` };
  },
  traffic(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const here = tw(), R = 4, S = trSegs().filter(x => (x.d = kmBetween(x.ll, here)) < R).sort((a, b) => a.d - b.d), E = trEvents(e => kmBetween(e.ll, here) < R);
    trDraw(S, 0.12);
    const vd = sameC(T.county, "臺北市") ? vdSegs().map(x => ({ x, d: kmBetween([(x[0] + x[2]) / 2, (x[1] + x[3]) / 2], here) })).filter(o => o.d < 2.5) : [];
    vdDraw(vd.map(o => o.x), 0.1);
    const vdRows = vd.sort((a, b) => a.x[4] - b.x[4]).map(({ x, d }) => ({ k: "vd", n: x[6], s: x[4], d, ll: [(x[0] + x[2]) / 2, (x[1] + x[3]) / 2] }));
    const cams = camsNear(here, R);
    cams.slice(0, 12).forEach(({ c }) => addLabel(`<span class="nvcam" ${camAttrs(c)} title="${esc(camName(c))}">◉</span>`, gp(c[0], c[1], 0.08), "nv campin", "nav", 1));
    camSetList(cams.map(x => x.c), { auto: !MOBILE, where: T.name });
    const withS = [...S.filter(x => x.s != null), ...vdRows.filter(x => x.s < 25)], slow = withS.filter(x => x.k === "vd" ? x.s < 15 : trSlow(x));
    slow.slice(0, 8).forEach(x => pin({ c: "#ff453a", ll: x.ll, t: `${x.s} km/h`, k: "塞車路段", s: `${x.n}・現在 ${x.s} km/h`, cam: 1 }, 4));
    E.forEach(e => pin({ c: "#ff9f0a", ll: e.ll, t: `${e.road || ""} ${e.kind || ""}`, k: "路況事件", s: [e.title, e.impact && e.impact !== "無影響" ? "影響：" + e.impact : "", e.at ? navAgo(e.at) : ""].filter(Boolean).join("・"), cam: 1 }, 3));
    return { eyebrow: `${norm(T.county)} › ${T.name} · 即時車流 · ${trAt()}`, title: "這附近順不順？", big: !withS.length ? T.name : slow.length ? `${slow.length} 段在塞` : "順暢", color: LENS.traffic.c,
      body: `<p class="why">附近 ${R} 公里內的國道、省道路段${vd.length ? `，加上台北市區 ${vd.length} 段路口偵測器` : "；市區一般道路只有台北有公開即時車速"}。</p>`
        + (withS.length ? listHTML(withS.sort((a, b) => a.s - b.s).slice(0, 8).map(trRow)) : `<p class="empty">附近沒有即時車速。</p>`)
        + camHTML(cams)
        + (E.length ? `<div class="nvh">路況事件</div>` + listHTML(E.slice(0, 5).map(e => ({ t: e.title || `${e.road || ""} ${e.kind || ""}`, s: `${e.impact || ""}・${dist(kmBetween(e.ll, here))}`, url: /^國道/.test(e.road || "") ? "https://1968.freeway.gov.tw/" : "" }))) : "") };
  },
  jobs(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const R = jobTowns(T.county), me = R.find(r => r[1] === T.name), L = jobLatest(T.county, T.name), view = NAV.viewD || 10, towns = NAV.towns || [];
    const near = R.filter(r => r !== me).map(r => [r, towns.find(t => t.name === r[1] && sameC(t.county, T.county))]).filter(([, t]) => t && kmBetween(t.c, T.c) < 9).sort((a, b) => kmBetween(a[1].c, T.c) - kmBetween(b[1].c, T.c)).slice(0, 5);
    const grp = [...(me ? [[me, T]] : []), ...near], mx = Math.max(1, ...grp.map(([r]) => r[2]));
    grp.forEach(([r, t]) => navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `${r[2].toLocaleString("en-US")} ${pctTxt(r[3])}`, r === me ? 9 : 4, r[3] == null ? LENS.jobs.c : pctCol(r[3])));
    return { eyebrow: `${norm(T.county)} › ${T.name} · 104 職缺`, title: "這一區在找什麼人？", big: me ? `${me[2].toLocaleString("en-US")} 個` : T.name, chg: me && me[3] != null ? `7 天 ${pctTxt(me[3])}` : "", color: LENS.jobs.c,
      body: (me ? `<p class="why">在${esc(norm(T.county))}排第 ${R.indexOf(me) + 1}／${R.length}。</p>` : `<p class="why">分區職缺數只做六都和新竹。</p>`)
        + (L.length ? `<div class="nvh">剛刊登的</div>` + listHTML(L.slice(0, 6).map(jobRow)) : "")
        + (near.length ? `<div class="nvh">隔壁幾區</div><ul class="lst nvl">${rankRows(near.map(([r]) => [r[1], `${r[2].toLocaleString("en-US")} 個・7 天 ${pctTxt(r[3]) || "—"}`]), "nt")}</ul>` : "") };
  },
  tender(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const R = tmTowns(T.county), me = R.find(r => r[1] === T.name), v = tmC(T.county);
    return { eyebrow: `${norm(T.county)} › ${T.name} · 政府標案 · ${tmDays()}`, title: "這一區在發包什麼？", big: me ? `${me[2]} 件招標` : T.name, chg: me && me[4] ? `比前一週 ${chgTxt(me[2], me[4])}` : "", color: LENS.tender.c,
      body: (me ? `<p class="why">公所、學校等看得出在這一區的機關：${me[2]} 件招標、${me[3]} 件決標。</p>` + (me[5].length ? tmRecent(me[5]) : "") : `<p class="why">最近一週沒有看得出在這一區的機關發包。</p>`)
        + (v && v.recent.length ? `<div class="nvh">${esc(norm(T.county))}最新招標</div>` + tmRecent(v.recent.slice(0, 4)) : "") };
  },
  news(T, C) {
    for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
    const N = NEWS(), mine = N.filter(x => inT(x.place, T) || (x.lvl === "town" && x.ll && kmBetween(x.ll, tw()) < 3)), cty = N.filter(x => x.lvl !== "town" && inC(x.place, C));
    mine.forEach(x => x.ll && pin({ c: LENS.news.c, ll: x.ll, t: x.t, k: "地方新聞", s: [String(x.place || "").slice(0, 6), x.s, x.at ? navAgo(x.at) : ""].filter(Boolean).join("・"), url: x.u }, 3));
    return { eyebrow: `${norm(T.county)} › ${T.name} · 地方新聞`, title: "這裡在發生什麼？", big: mine.length ? `${mine.length} 則在地` : T.name, color: LENS.news.c,
      body: (mine.length ? `<div class="nvh">${esc(T.name)}</div>` + listHTML(mine.slice(0, 5).map(x => ({ t: x.t, s: `${x.s || ""}・${navAgo(x.at)}`, url: x.u }))) : `<p class="why">這一區最近沒有標得出地點的新聞，先看全縣市的：</p>`)
        + `<div class="nvh">${esc(norm(C.name))}</div>` + listHTML(cty.slice(0, 5).map(x => ({ t: x.t, s: `${x.s || ""}・${navAgo(x.at)}`, url: x.u }))) };
  },
};
// ---- 時間開關：「現況」看量，「變化」看跟上一期比（房價上季、新公司上月、標案前一週、職缺 7 天前） ----
NAV.delta = false; NAV.hd = {};
const DELTA_OK = { house: "比上季", biz: "比上月", tender: "比前一週", jobs: "比 7 天前" };
function houseDetail(cname) { const k = norm(cname).replace(/^台/, "臺"); if (NAV.hd[k] !== undefined) return NAV.hd[k]; NAV.hd[k] = null;
  fetch(RAW + "house/" + encodeURIComponent(k) + ".json?d=" + Math.floor(Date.now() / 864e5), { cache: "no-store" }).then(r => r.ok ? r.json() : false).then(j => { NAV.hd[k] = j || false; NAV.key = ""; }).catch(() => { NAV.hd[k] = false; });
  return null; }
const dPct = v => v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
// 一組「地點＋變化％」畫成光柱：高度＝變化幅度，綠漲紅跌
function deltaCols(rows, view, prio) { const mx = Math.max(1, ...rows.map(r => Math.abs(r.v)));
  rows.forEach((r, i) => navCol(r.ll[0], r.ll[1], Math.abs(r.v) / mx, view, r.name, dPct(r.v), (prio || 6) - i * 0.2, r.v >= 0 ? UPH : DNH)); }
const deltaList = (rows, attr, sub) => `<ul class="lst nvl">${rows.map(r => `<li data-${attr}="${esc(r.key || r.name)}" style="cursor:pointer"><span class="sdot" style="background:${r.v >= 0 ? UPH : DNH}"></span>${esc(norm(r.name))}<span>${dPct(r.v)}${sub ? "・" + sub(r) : ""}</span></li>`).join("")}</ul>`;
const DELTA_TW = {
  house() { navCounties(() => ({ op: 0.25 })); return { eyebrow: "台灣 · 實價登錄 · 比上季", title: "哪裡在漲？", big: "選一個縣市", color: LENS.house.c, body: `<p class="why">各區的季變化在縣市層：點一個縣市或拉近，就看得到哪一區比上季漲、哪一區在跌。</p>` }; },
  biz() { const C = (NAV.bt || {}).counties || {}, rows = Object.entries(C).filter(([, v]) => v.p >= 20).map(([k, v]) => ({ key: k, name: k, v: (v.n / v.p - 1) * 100, n: v.n })).sort((a, b) => b.v - a.v);
    navCounties(c => { const r = rows.find(r => sameC(r.key, c.name)); return r ? { col: new THREE.Color(r.v >= 0 ? UPH : DNH), op: 0.3 + 0.6 * Math.min(1, Math.abs(r.v) / 30), sub: dPct(r.v), dot: r.v >= 0 ? UPH : DNH, prio: 2 + Math.abs(r.v) / 10 } : { dim: true, op: 0.12 }; });
    return { eyebrow: `台灣 · 新設立 · ${(NAV.bt || {}).month || ""} 比上月`, title: "哪裡開公司變熱、變冷？", big: rows[0] ? `${norm(rows[0].name)} ${dPct(rows[0].v)}` : "—", color: LENS.biz.c, body: `<p class="why">上月少於 20 家的縣市不比，避免小數字放大。</p>` + deltaList(rows, "nc", r => `${r.n} 家`) }; },
  tender() { const C = TM().counties || {}, rows = Object.entries(C).filter(([k, v]) => k !== "中央" && v.np >= 10).map(([k, v]) => ({ key: k, name: k, v: (v.n / v.np - 1) * 100, n: v.n })).sort((a, b) => b.v - a.v);
    navCounties(c => { const r = rows.find(r => sameC(r.key, c.name)); return r ? { col: new THREE.Color(r.v >= 0 ? UPH : DNH), op: 0.3 + 0.6 * Math.min(1, Math.abs(r.v) / 40), sub: dPct(r.v), dot: r.v >= 0 ? UPH : DNH, prio: 2 } : { dim: true, op: 0.12 }; });
    return { eyebrow: `台灣 · 政府標案 · 比前一週`, title: "哪裡發包變多？", big: rows.length ? `${norm(rows[0].name)} ${dPct(rows[0].v)}` : "資料累積中", color: LENS.tender.c, body: rows.length ? deltaList(rows, "nc", r => `${r.n} 件`) : `<p class="empty">前一週的資料還在補，一兩天內就能比。</p>` }; },
  jobs() { const A = ((P.jobs || {}).areas) || [], rows = A.filter(a => a.chg7 != null).map(a => ({ key: a.counties[0], name: a.name, v: a.chg7, n: a.n })).sort((a, b) => b.v - a.v);
    navCounties(c => { const a = jobArea(c.name); return a && a.chg7 != null ? { col: new THREE.Color(a.chg7 >= 0 ? UPH : DNH), op: 0.3 + 0.6 * Math.min(1, Math.abs(a.chg7) / 3), sub: dPct(a.chg7), dot: a.chg7 >= 0 ? UPH : DNH, prio: 2 } : { dim: true, op: 0.12 }; });
    return { eyebrow: "台灣 · 104 職缺 · 比 7 天前", title: "哪裡開始搶人、哪裡收手？", big: rows[0] ? `${rows[0].name} ${dPct(rows[0].v)}` : "—", color: LENS.jobs.c, body: deltaList(rows, "nc", r => `${r.n.toLocaleString("en-US")} 個`) }; },
};
const DELTA_CITY = {
  house(C) { const ts = navOutline(C), hd = houseDetail(C.name), view = NAV.viewD || 60;
    if (!hd) return { eyebrow: `${norm(C.name)} · 實價登錄 · 比上季`, title: "哪一區在漲？", big: hd === false ? "沒有資料" : "載入中…", color: LENS.house.c, body: "" };
    const rows = hd.towns.filter(t => t.chg != null && t.n >= 10).map(t => { const T = ts.find(x => x.name === t.town); return T ? { name: t.town, ll: T.c, v: t.chg, med: t.med, n: t.n } : null; }).filter(Boolean).sort((a, b) => b.v - a.v);
    deltaCols(rows, view); townPills(ts, new Set(rows.map(r => r.name)));
    return { eyebrow: `${norm(C.name)} · 實價登錄 ${hd.season} · 比上季`, title: "哪一區在漲？", big: rows[0] ? `${rows[0].name} ${dPct(rows[0].v)}` : "—", color: LENS.house.c,
      body: `<p class="why">光柱高度＝每坪均價比上一季的變化幅度，綠漲紅跌；成交少於 10 筆的區不比。</p>` + deltaList(rows.slice(0, 12), "nt", r => `${p1(r.med)} 萬／坪・${r.n} 筆`) }; },
  biz(C) { const ts = navOutline(C), view = NAV.viewD || 60, rows = btTowns(C).filter(r => r[3] >= 5).map(r => { const T = ts.find(t => t.name === r[1]); return T ? { name: r[1], ll: T.c, v: (r[2] / r[3] - 1) * 100, n: r[2] } : null; }).filter(Boolean).sort((a, b) => b.v - a.v);
    deltaCols(rows, view); townPills(ts, new Set(rows.map(r => r.name)));
    return { eyebrow: `${norm(C.name)} · 新設立 · 比上月`, title: "哪一區開公司變熱？", big: rows[0] ? `${rows[0].name} ${dPct(rows[0].v)}` : "—", color: LENS.biz.c, body: `<p class="why">上月少於 5 家的區不比。</p>` + deltaList(rows.slice(0, 12), "nt", r => `${r.n} 家`) }; },
  tender(C) { const ts = navOutline(C), view = NAV.viewD || 60, rows = tmTowns(C.name).filter(r => r[4] >= 3).map(r => { const T = ts.find(t => t.name === r[1]); return T ? { name: r[1], ll: T.c, v: (r[2] / r[4] - 1) * 100, n: r[2] } : null; }).filter(Boolean).sort((a, b) => b.v - a.v);
    deltaCols(rows, view); townPills(ts, new Set(rows.map(r => r.name)));
    return { eyebrow: `${norm(C.name)} · 政府標案 · 比前一週`, title: "哪一區發包變多？", big: rows[0] ? `${rows[0].name} ${dPct(rows[0].v)}` : "資料累積中", color: LENS.tender.c, body: rows.length ? deltaList(rows.slice(0, 12), "nt", r => `${r.n} 件`) : `<p class="empty">前一週的分區資料還不夠，一兩天內就能比。</p>` }; },
  jobs(C) { const ts = navOutline(C), view = NAV.viewD || 60, rows = jobTowns(C.name).filter(r => r[3] != null).map(r => { const T = ts.find(t => t.name === r[1]); return T ? { name: r[1], ll: T.c, v: r[3], n: r[2] } : null; }).filter(Boolean).sort((a, b) => b.v - a.v);
    deltaCols(rows, view); townPills(ts, new Set(rows.map(r => r.name)));
    return { eyebrow: `${norm(C.name)} · 104 職缺 · 比 7 天前`, title: "哪一區開始搶人？", big: rows[0] ? `${rows[0].name} ${dPct(rows[0].v)}` : "資料累積中", color: LENS.jobs.c, body: rows.length ? deltaList(rows.slice(0, 12), "nt", r => `${r.n.toLocaleString("en-US")} 個`) : `<p class="empty">分區職缺從今天開始記錄，要滿 7 天才能比（六都＋新竹）。</p>` }; },
};
// ---- 聚焦（學 Apple）：講重點的時候，其他東西退到後面 ----
// 1. 底圖蓋一層淡淡的暗幕（衛星照、建築、小車都在幕後），資料的線、光柱、標籤在幕前
// 2. 卡片清單的前三名在地圖上最清楚，其他縣市、行政區淡一點、微微模糊
// 3. 滑鼠移到清單某一項：只有那一項是亮的，其他都退到很淡
const VEIL = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({ transparent: true, depthTest: false, depthWrite: false, uniforms: { uV: { value: 0 } },
  vertexShader: "varying vec2 vP; void main(){ vP = position.xy; gl_Position = vec4(position.xy, 0.0, 1.0); }",
  fragmentShader: "uniform float uV; varying vec2 vP; void main(){ float e = smoothstep(0.35, 1.45, length(vP)); gl_FragColor = vec4(0.0, 0.0, 0.0, uV * (0.7 + 0.5 * e)); }" }));
VEIL.renderOrder = 6; VEIL.frustumCulled = false; scene.add(VEIL); NAV.veil = 0;
const navKeyOf = L => { const b = L.el.querySelector(".nvp b"); return b ? norm(b.textContent) : null; };
function navFocus(set, strong) {
  NAV.fset = set; NAV.fstrong = !!strong;
  const S = set ? new Set([...set].map(norm)) : null;
  for (const o of NAV.g.children) { const k = o.userData.key; if (!k || !o.material) continue;
    o.material.opacity = (o.userData.op ?? 1) * (!S || S.has(k) ? 1 : strong ? 0.12 : 0.4); }
  for (const L of LBL) if (L.group === "nav") { const k = navKeyOf(L), off = !!S && (!k || !S.has(k)), hit = !!S && !!k && S.has(k);
    if (L.prio0 == null) L.prio0 = L.prio; L.prio = L.prio0 + (hit ? 100 : off ? -50 : 0);   // 重點的標籤優先占位，不會被旁邊的擋掉
    L.el.classList.toggle("defocus", off && !strong); L.el.classList.toggle("defocus2", off && !!strong); }
}
function navDefaultFocus() {   // 清單有 5 項以上時，預設只讓前三名最清楚
  const items = [...document.querySelectorAll("#side [data-nc], #side [data-nt]")];
  NAV.dfset = items.length >= 5 ? new Set(items.slice(0, 3).map(b => b.dataset.nc || b.dataset.nt)) : null;
  navFocus(NAV.dfset, false);
}
document.addEventListener("mouseover", e => { const b = e.target.closest && e.target.closest("#side [data-nc], #side [data-nt]"); if (!b || NAV.level < 0) return; navFocus(new Set([b.dataset.nc || b.dataset.nt]), true); NAV.veilHot = 1; });
document.addEventListener("mouseout", e => { const b = e.target.closest && e.target.closest("#side [data-nc], #side [data-nt]"); if (!b) return; const to = e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest("#side [data-nc], #side [data-nt]"); if (to) return; navFocus(NAV.dfset || null, false); NAV.veilHot = 0; });
function veilTick(dt, on) {
  const target = on ? (NAV.veilHot ? 0.55 : 0.32) * (uni.uNight.value ? 0.7 : 1) : 0;
  NAV.veil += (target - NAV.veil) * Math.min(1, dt * 4); VEIL.material.uniforms.uV.value = NAV.veil; VEIL.visible = NAV.veil > 0.005;
}
// ---- 層級切換：依鏡頭距離自動判斷；中間留一段緩衝，避免在邊界來回跳 ----
function navTick(dt) {
  const on = ST.explore && !ST.globeForce && (!cur || cur === "wx" || (cur === "traffic" && NAV.lens === "traffic"));
  document.body.classList.toggle("nav-on", on);
  veilTick(dt || 0.016, on && NAV.level >= 0 && !NAV.quiet);
  if (!on) document.body.classList.remove("nav-quiet");
  if (!on) { if (NAV.level !== -1) { NAV.level = -1; NAV.key = ""; navClear(); camHide(); } return; }
  if (NAV.lens !== "traffic" && (CAM.open || CAM.list.length)) { CAM.list = []; camHide(); }
  if (NAV.anim) NAV.anim(performance.now() / 1000);
  NAV.t -= dt; if (NAV.t > 0) return; NAV.t = 0.35;
  if (!NAV.towns) { navTowns(); navBiz(); return; }   // 新公司的鄉鎮統計順便先載，切過去時不用等
  const t = controls.target, cd = camera.position.distanceTo(t), lon = t.x / KX + LONC, lat = -t.z / KY + LATC;
  const L = NAV.level, up = [230, 28], lv = cd > up[0] * (L === 0 ? 0.9 : 1.1) ? 0 : cd > up[1] * (L === 2 ? 1.25 : 0.85) ? 1 : 2;
  const C = lv >= 1 ? countyAt(lon, lat) : null, T = lv >= 2 ? townAt(lon, lat) : null;
  const level = lv >= 1 && !C ? 0 : lv === 2 && !T ? 1 : lv;
  const pk = level + "|" + (C ? C.name : "") + "|" + (T ? T.name : ""), key = pk + "|" + NAV.lens + (NAV.delta ? "|d" : "");
  if (key === NAV.key) return;
  if (NAV.quiet === true) NAV.quiet = pk;                 // 剛選了沒有地點的資訊：這一次只換地圖、不蓋掉它的卡片；換層或換地方才換卡片
  const quiet = NAV.quiet === pk; if (!quiet) NAV.quiet = null;
  document.body.classList.toggle("nav-quiet", quiet && NAV.bare && NAV.lens === "now");   // 沒有地點的資訊：地圖只留地形，不放無關的現場標籤
  NAV.key = key; NAV.level = level; NAV.county = C; NAV.town = T; NAV.viewD = cd;
  navClear();
  NAV.anim = null;
  // 全島型的視角（景氣、情緒、電力）每一層都一樣；選戰沒有街道層，就用城市層
  const TWONLY = { macro: 1, mood: 1, power: 1, cable: 1, pla: 1 }, lz = NAV.lens, at = [[], [C], [T, C]];
  let fn, args;
  if (TWONLY[lz]) { fn = TW_VIEW[lz]; args = []; }
  else if (NAV.delta && DELTA_OK[lz] && (level === 0 ? DELTA_TW[lz] : DELTA_CITY[lz])) { fn = level === 0 ? DELTA_TW[lz] : DELTA_CITY[lz]; args = level === 0 ? [] : [C]; }
  else { const VW = [TW_VIEW, CITY_VIEW, STREET_VIEW][level];
    if (VW[lz]) { fn = VW[lz]; args = at[level]; } else if (level === 2 && CITY_VIEW[lz]) { fn = CITY_VIEW[lz]; args = [C]; } else { fn = VW.now; args = at[level]; } }
  let o = null; try { o = fn(...args); } catch (e) { console.warn("nav", e); }
  if (!quiet && o) {
    const sel = document.querySelector("#chips button[aria-selected=true]");
    if (sel && sel.dataset.lens !== NAV.lens) document.querySelectorAll("#chips button").forEach(b => b.setAttribute("aria-selected", "false"));   // 地圖卡片接手時，不相干的分類不再標示選取
    showSide(sideHTML(o) + provHTML("lens:" + NAV.lens), null);
  }
  NAV.veilHot = 0; setTimeout(navDefaultFocus, 60);
  if (!NAV.mo) { NAV.mo = new MutationObserver(() => { clearTimeout(NAV._dfT); NAV._dfT = setTimeout(() => { if (!NAV.veilHot && NAV.level >= 0) navDefaultFocus(); }, 40); });
    NAV.mo.observe($("side"), { childList: true, subtree: true }); }   // 卡片換完內容才決定前三名（卡片有淡入動畫，60ms 時可能還是舊清單）
  navCrumb();
}
// 飛到某一層：縣市或行政區整個放進畫面
function navFlyBox(bb, minD, ctr) {
  const cx = ctr ? ctr[0] : (bb[0] + bb[2]) / 2, cy = ctr ? ctr[1] : (bb[1] + bb[3]) / 2, size = Math.max((bb[2] - bb[0]) * KX, (bb[3] - bb[1]) * KY), d = Math.max(minD, size * (MOBILE ? 1.6 : 1.15));
  const tgt = gp(cx, cy, 0); flyTo(tgt.clone().add(V(0, d * 0.78, d * 0.62)), tgt, 1.6);
}
const navGoTaiwan = () => flyTo(ISLAND.pos, ISLAND.tgt, 1.6);
const navGoCounty = c => c && navFlyBox(c.bbox, 40);
const navGoTown = t => t && navFlyBox(t.bbox, 9, t.c);
function navClickAt(lon, lat, c) {
  if (NAV.level <= 0) return navGoCounty(c);
  if (NAV.level === 1) { const t = townAt(lon, lat); return t ? navGoTown(t) : navGoCounty(c); }
  const t = townAt(lon, lat); if (t && NAV.town && t.name !== NAV.town.name) navGoTown(t);
}
// ---- 麵包屑＋搜尋 ----
function navCrumb() {
  let el = $("crumb");
  if (!el) { el = document.createElement("nav"); el.id = "crumb"; el.setAttribute("aria-label", "地圖層級"); document.body.appendChild(el);
    el.addEventListener("click", e => { const b = e.target.closest("[data-go]"); if (!b) return; const g = b.dataset.go;
      if (g === "d0" || g === "d1") { NAV.delta = g === "d1"; NAV.key = ""; NAV.t = 0; } else if (g === "lz") { navSetLens("now"); document.querySelectorAll("#chips button").forEach(b => b.setAttribute("aria-selected", "false")); } else if (g === "earth") ST.goEarth && ST.goEarth(); else if (g === "tw") navGoTaiwan(); else if (g === "c") navGoCounty(NAV.county); else if (g === "s") { el.classList.toggle("searching"); const i = el.querySelector("input"); if (i) { i.value = ""; i.focus(); navSearch(""); } } });
    el.addEventListener("input", e => navSearch(e.target.value));
    el.addEventListener("keydown", e => { if (e.key === "Escape") el.classList.remove("searching"); if (e.key === "Enter") { const f = el.querySelector(".res [data-r]"); f && f.click(); } });
    el.addEventListener("pointerdown", e => e.stopPropagation());
    addEventListener("keydown", e => { if (e.key === "Escape" && ST.explore && !el.classList.contains("searching")) { if (NAV.level === 2) navGoCounty(NAV.county); else if (NAV.level === 1) navGoTaiwan(); } });
  }
  const parts = [`<button data-go="earth" class="earth" aria-label="回到地球">地球</button>`, `<button data-go="tw" class="${NAV.level === 0 ? "on" : ""}">台灣</button>`];
  if (NAV.county) parts.push(`<button data-go="c" class="${NAV.level === 1 ? "on" : ""}">${esc(norm(NAV.county.name))}</button>`);
  if (NAV.town && NAV.level === 2) parts.push(`<button class="on">${esc(NAV.town.name)}</button>`);
  const srch = el.querySelector(".srch"), LZ = LENS[NAV.lens];
  const badge = NAV.lens !== "now" ? `<button data-go="lz" class="lz" style="--c:${LZ.c}" aria-label="地圖視角：${LZ.n}，點一下回到現場"><i></i>${LZ.n}<span>×</span></button>` : NAV.quiet && NAV.bare ? `<span class="lz q" title="這則資訊沒有地點，地圖先只留地形；拉近或點縣市就回到現場">這則沒有地點</span>` : "";
  const dt = DELTA_OK[NAV.lens] ? `<span class="dt"><button data-go="d0" class="${NAV.delta ? "" : "on"}">現況</button><button data-go="d1" class="${NAV.delta ? "on" : ""}">${DELTA_OK[NAV.lens]}</button></span>` : "";
  el.innerHTML = `<div class="path">${parts.join('<span class="sep">›</span>')}</div>${badge}${dt}<button data-go="share" class="shr" aria-label="複製這個畫面的連結">分享</button><button data-go="s" class="sbtn" aria-label="搜尋">⌕</button><div class="srch"><input type="search" placeholder="搜尋縣市、行政區、地標" aria-label="搜尋地點"><div class="res"></div></div>`;
  if (srch && el.classList.contains("searching")) { const i = el.querySelector("input"); i.value = srch.querySelector("input").value; navSearch(i.value); }
}
const NAV_LM = [["台北 101", 121.5645, 25.034], ["高雄 85 大樓", 120.3007, 22.6116], ["圓山大飯店", 121.5262, 25.0785], ["台中國家歌劇院", 120.6406, 24.1627], ["赤崁樓", 120.2025, 22.9975]];
function navSearch(q) {
  const box = document.querySelector("#crumb .res"); if (!box) return; q = norm(q.trim());
  if (!q) { box.innerHTML = ""; return; }
  const out = [];
  for (const c of COUNTIES) if (norm(c.name).includes(q)) out.push({ t: norm(c.name), s: "縣市", go: () => navGoCounty(c) });
  for (const t of (NAV.towns || [])) if (t.name.includes(q) || (norm(t.county) + t.name).includes(q)) out.push({ t: t.name, s: norm(t.county), go: () => navGoTown(t) });
  for (const [n, lo, la] of NAV_LM) if (norm(n).replace(/\s/g, "").includes(q.replace(/\s/g, ""))) out.push({ t: n, s: "地標", go: () => { const g = gp(lo, la, 0); flyTo(g.clone().add(V(0.9, 0.8, 1.3)), g.clone().add(V(0, 0.3, 0)), 1.8); } });
  NAV.res = out.slice(0, 8);
  box.innerHTML = NAV.res.length ? NAV.res.map((r, i) => `<button data-r="${i}">${esc(r.t)}<span>${esc(r.s)}</span></button>`).join("") : `<p>找不到「${esc(q)}」</p>`;
  box.onclick = e => { const b = e.target.closest("[data-r]"); if (!b) return; NAV.res[+b.dataset.r].go(); $("crumb").classList.remove("searching"); };
}
// 卡片裡的清單也可以點：縣市 → 飛過去；行政區 → 飛過去
document.addEventListener("click", e => {
  const c = e.target.closest && e.target.closest("#side [data-nc]"); if (c) { navGoCounty(COUNTIES.find(x => x.name === c.dataset.nc)); return; }
  const t = e.target.closest && e.target.closest("#side [data-nt]"); if (t && NAV.county) navGoTown((NAV.towns || []).find(x => x.name === t.dataset.nt && sameC(x.county, NAV.county.name)));
});
window.__nav = { NAV, navSetLens, navGoCounty, navGoTown, townAt, COUNTIES: () => COUNTIES };

// ---- 地球 ↔ 台灣：跟地圖 App 一樣，拉遠就回到地球、在地球上對著台灣拉近就進到台灣地圖 ----
// 地球模式時上方也有一條路徑「地球 › 台灣」，點台灣就回地圖（手機沒有滾輪，靠這個）
function gNav() {
  let el = $("gcrumb");
  if (!el) { el = document.createElement("nav"); el.id = "gcrumb"; el.setAttribute("aria-label", "地圖層級");
    el.innerHTML = `<button class="on" tabindex="-1">地球</button><span class="sep">›</span><button data-g="tw">台灣</button>`;
    el.addEventListener("click", e => { if (e.target.closest("[data-g=tw]")) ST.goMap && ST.goMap(); });
    el.addEventListener("pointerdown", e => e.stopPropagation()); document.body.appendChild(el); }
  return el;
}
const ZM = { acc: 0, t: 0 };
renderer.domElement.addEventListener("wheel", e => {
  const now = performance.now(); if (now - ZM.t > 700) ZM.acc = 0; ZM.t = now;
  if (fly) return;   // 飛行中不判斷，避免連續觸發
  if (GD.on && e.deltaY < 0) {   // 地球：拉到最近、台灣在畫面中間附近 → 進台灣地圖
    const v = camera.position.clone().sub(_gC), alt = v.length() - 6371, tw = GLOBE.G(TW_LL[0], TW_LL[1], 0).sub(_gC);
    if (alt < 3200 && v.angleTo(tw) < 0.9) { ZM.acc -= e.deltaY; if (ZM.acc > 240) { ZM.acc = 0; ST.goMap && ST.goMap(); } }
  } else if (!GD.on && ST.explore && !ST.globeForce && NAV.level === 0 && e.deltaY > 0 && camera.position.distanceTo(controls.target) > controls.maxDistance * 0.93) {
    ZM.acc += e.deltaY; if (ZM.acc > 320) { ZM.acc = 0; ST.goEarth && ST.goEarth(); }   // 台灣：已經拉到最遠還繼續拉 → 回到地球
  }
}, { passive: true });
addEventListener("keydown", e => { if (e.key === "Escape" && GD.on && ST.explore && !/input|textarea/i.test((e.target || {}).tagName || "")) ST.goMap && ST.goMap(); });
gNav();

// ---- 停班停課（人事總處）：縣市依停班停課程度上色，點縣市看哪幾區、什麼時候 ----
LENS.stop = { n: "停班停課", c: "#ff453a" };
const STOP = () => (((P.alerts || {}).stopwork) || {});
function stopLevel(txt) {   // 3 全停、2 停課（照常上班）、1 部分地區、0 照常
  const t = String(txt || ""), part = /部分|[鄉鎮區里]|山區|離島|地區/.test(t.replace(/全[縣市]/g, ""));
  if (/停止上班/.test(t) && /停止上課/.test(t)) return part ? 1.5 : 3;
  if (/停止上課/.test(t)) return part ? 1 : 2;
  if (/停止上班/.test(t)) return part ? 1 : 2;
  return 0;
}
const STOP_C = l => l >= 3 ? "#ff453a" : l >= 2 ? "#ff9f0a" : l >= 1 ? "#ffd60a" : "#30d158";
const stopShort = t => (/明天|明日/.test(t) ? "明天" : /今天|今日/.test(t) ? "今天" : "") + (/停止上班/.test(t) && /停止上課/.test(t) ? "停班停課" : /停止上課/.test(t) ? "停課" : /停止上班/.test(t) ? "停班" : "照常");
const stopOf = name => (STOP().items || []).filter(x => sameC(x.area, name));
TW_VIEW.stop = function () {
  const S = STOP(), items = S.items || [];
  navCounties(c => { const its = stopOf(c.name); if (!its.length) return { dim: true, op: 0.1 };
    const l = Math.max(...its.map(x => stopLevel(x.text))); return { col: new THREE.Color(STOP_C(l)), op: 0.4 + 0.15 * l, sub: stopShort(its.map(x => x.text).join(" ")), dot: STOP_C(l), prio: 5 + l }; });
  const n = new Set(items.filter(x => stopLevel(x.text) > 0).map(x => norm(x.area))).size;
  return { eyebrow: `現場 · 人事總處${S.updated ? " · " + S.updated.slice(5, 16) + " 更新" : ""}`, title: "要不要上班上課？", big: items.length ? (n ? `${n} 個縣市停班或停課` : "各縣市照常") : "全台照常上班上課", color: n ? LENS.stop.c : "#30d158",
    body: items.length ? `<ul class="lst nvl">${items.map(x => `<li data-nc="${esc((COUNTIES.find(c => sameC(c.name, x.area)) || {}).name || x.area)}" style="cursor:pointer"><span class="sdot" style="background:${STOP_C(stopLevel(x.text))}"></span>${esc(norm(x.area))}<span>${esc(x.text)}</span></li>`).join("")}</ul><p class="why">紅＝停班停課、橘＝停課或停班、黃＝部分地區。以人事總處公告為準，颱風期間通常晚上 8 點前後公布隔天的決定。</p><p><a href="https://www.dgpa.gov.tw/typh/daily/nds.html" target="_blank" rel="noopener">人事總處公告原文 ›</a></p>`
      : `<p class="why">人事總處目前沒有任何停班停課公告。颱風或豪雨期間，各縣市通常在晚上 8 點前後公布隔天是否停班停課，這裡會自動更新、地圖上會標出來。</p><p><a href="https://www.dgpa.gov.tw/typh/daily/nds.html" target="_blank" rel="noopener">人事總處公告原文 ›</a></p>` };
};
CITY_VIEW.stop = function (C) {
  const ts = navOutline(C), its = stopOf(C.name), txt = its.map(x => x.text).join(" "), l = its.length ? Math.max(...its.map(x => stopLevel(x.text))) : 0;
  const hit = ts.filter(t => txt.includes(t.name.replace(/[區鄉鎮市]$/, "")));
  for (const t of hit) addLabel(pill(t.name, stopShort(txt), STOP_C(l)), gp(t.c[0], t.c[1], 1.5), "nv", "nav", 5);
  townPills(ts, new Set(hit.map(t => t.name)));
  return { eyebrow: `${norm(C.name)} · 停班停課 · 人事總處`, title: "要不要上班上課？", big: its.length ? stopShort(txt) : "照常上班上課", color: STOP_C(l),
    body: its.length ? listHTML(its.map(x => ({ t: x.text, s: x.area, url: "https://www.dgpa.gov.tw/typh/daily/nds.html" }))) + (hit.length ? `<p class="why">地圖上標出公告裡提到的行政區。</p>` : "") : `<p class="why">人事總處目前沒有${esc(norm(C.name))}的停班停課公告。</p>` };
};

// 個股：價格、漲跌、成交量、總部地址、最近一則重大訊息
function stockInfo(s) {
  const x = s.x || {}, m = MOPS().filter(m => m.name === x.name || m.code === x.code).sort((a, b) => String(b.d).localeCompare(String(a.d)))[0];
  return { html: `<i class="lp-k" style="color:${LENS.stock.c}">個股・${esc(x.code || "")}</i><b>${esc(s.name)}</b><p class="${s.v >= 0 ? "up" : "dn"}">${x.price != null ? x.price + " 元　" : ""}${pct(s.v)}</p>`
    + `<p>${[x.sec, x.value ? "成交金額 " + (x.value / 1e8).toFixed(1) + " 億" : "", x.date ? x.date.slice(5).replace("-", "/") + " 收盤" : ""].filter(Boolean).map(esc).join("・")}</p><p>總部：${esc(s.addr || "")}</p>`
    + (m ? `<p>最近重大訊息（${esc(m.d || "")}）：${esc(m.t || "")}</p>` : ""), go: () => flyNear(gp(s.ll[0], s.ll[1], 0), 4), goTxt: "拉近到總部" };
}
