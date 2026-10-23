
/* ---- 開場動畫：整座島冒出情報站的數字，最後收成五件事 ----
   有地點的數字長在它的地點上（各縣市氣溫、鄉鎮房價、選戰、機場、電力）；
   沒有地點的數字（台股、匯率、原物料⋯）浮在島外圍的一圈軌道上，不假裝屬於某個地方。 */
const INTRO = { on: false, t0: 0, chips: [], g: null, done: false, T: { cam: 2.6, scan0: 0.3, scan1: 2.9, hold: 5.4, fly: 6.4 } };
const SCAN_LAT = [21.6, 25.6];
const INTRO_SLOW = +(new URLSearchParams(location.search).get("slow") || 1);   // 測試用：放慢開場
const INTRO_CAM = { tgt: V(0, 0, -20), pos: MOBILE ? V(0, 2300, 900) : V(-120, 1900, 1300) };
const easeIO = k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
function introChips() {
  const L = [], add = (o) => L.push(o);
  // 有地點的
  for (const it of ((P.weather || {}).items || [])) { const c = COUNTIES.find(c => norm(c.name).startsWith(norm(it.city))); if (c && isFinite(it.temp)) add({ geo: c.c, v: it.temp, dec: 0, unit: "°", lab: it.city, color: NEU }); }
  const perCity = {}, towns = (((P.house || {}).towns) || []).filter(t => t[4] > 0 && t[5] >= 20).sort((a, b) => b[5] - a[5]).filter(t => (perCity[t[2]] = (perCity[t[2]] || 0) + 1) <= 2).slice(0, 18);   // 每個縣市最多兩個鄉鎮，免得全擠在台北
  for (const t of towns) add({ geo: [t[0], t[1]], v: t[4], dec: 0, unit: " 萬/坪", lab: t[3], color: "#bfe6ff" });
  for (const c of (((P.elect || {}).cities) || [])) { const POS = { "台北": [121.56, 25.06], "新北": [121.45, 24.99], "桃園": [121.3, 24.98], "台中": [120.68, 24.15], "台南": [120.22, 23.0], "高雄": [120.32, 22.64] }, top = (c.cands || []).slice().sort((a, b) => b.p - a.p)[0];
    if (top && POS[c.city]) add({ geo: [POS[c.city][0] + 0.05, POS[c.city][1] + 0.05], v: top.p, dec: 0, unit: "%", lab: top.name, color: NEU }); }
  { const d = (P.airport || {}).dep || {}; if (d.total) add({ geo: [121.233, 25.077], v: d.total, dec: 0, unit: " 班", lab: "桃機離境", color: NEU }); }
  { const r = (P.power || {}).reserve_pct; if (r != null) add({ geo: [120.48, 24.21], v: r, dec: 1, unit: "%", lab: "備轉", color: r < 10 ? "#ff9f0a" : UPH }); }
  const q = (((P.quake || {}).items) || [])[0]; if (q && isFinite(q.mag)) add({ geo: [q.lon, q.lat], v: q.mag, dec: 1, unit: "", pre: "M", lab: "地震", color: YLH });
  // 沒有地點的：繞在島外圍
  const pool = (ST.all || []).slice().sort((a, b) => b.score - a.score), seen = new Set(), halo = [];
  for (const t of ST.top || []) { halo.push(t); seen.add(t); }
  for (const t of pool) { if (halo.length >= (MOBILE ? 16 : 26)) break; if (seen.has(t) || !isFinite(t.value)) continue; if (halo.filter(h => h.grp === t.grp).length >= 2) continue; halo.push(t); seen.add(t); }
  halo.forEach((t, k) => {
    const a = -Math.PI * 0.62 + k / halo.length * Math.PI * 2, R = (MOBILE ? 118 : 205) + (k % 3) * (MOBILE ? 16 : 24);
    const isTop = (ST.top || []).includes(t);
    add({ pos: V(Math.sin(a) * R * 0.78, 18 + (k % 4) * 10, -20 - Math.cos(a) * R), v: t.grp === "inst" ? Math.abs(t.value) : t.value, dec: Math.abs(t.value) >= 1000 ? 0 : Math.abs(t.value) >= 100 ? 1 : Math.abs(t.value) >= 1 ? 2 : 3,
      unit: t.iunit != null ? t.iunit : t.grp === "inst" ? " 億" : "", lab: t.name, chg: t.chgTxt, color: t.color, top: isTop ? (ST.top || []).indexOf(t) : -1, halo: true });
  });
  return L;
}
function buildIntro() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const box = $("intro"), list = introChips(); INTRO.g = new THREE.Group(); SG.add(INTRO.g);
  const N = list.length;
  list.forEach((o, k) => {
    o.anchor = o.pos || gp(o.geo[0], o.geo[1], 0.3);
    if (o.geo) { const top = o.anchor.clone().add(V(0, 9, 0)), l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([o.anchor, top]), lineM(new THREE.Color(o.color), 0.8)); l.material.opacity = 0; INTRO.g.add(l); o.line = l; o.anchor = top; }
    const el = document.createElement("div"); el.className = "ic" + (o.halo ? " halo" : "") + (o.top >= 0 ? " top" : "");
    el.innerHTML = `<b style="color:${o.color}"><i>${o.pre || ""}</i><span class="num">0</span><i>${esc(o.unit || "")}</i></b><small>${esc(o.lab)}${o.chg ? ` <em style="color:${o.color}">${esc(o.chg)}</em>` : ""}</small>`;
    box.appendChild(el); o.el = el; o.num = el.querySelector(".num");
    // 先跑地圖上的，再跑外圍的；前五名最後出現
    const T = INTRO.T, lat = o.geo ? o.geo[1] : null;
    o.at = o.top >= 0 ? 3.9 + o.top * 0.14 : lat != null ? T.scan0 + (lat - SCAN_LAT[0]) / (SCAN_LAT[1] - SCAN_LAT[0]) * (T.scan1 - T.scan0) + 0.05 : 2.4 + (k / N) * 1.3 + Math.random() * 0.2;
  });
  INTRO.chips = list; INTRO.on = true; INTRO.t0 = performance.now();
  document.body.classList.add("intro");
  const skip = () => { if (INTRO.on) endIntro(true); };
  ["wheel", "touchstart", "keydown", "pointerdown"].forEach(ev => addEventListener(ev, skip, { once: true, passive: true }));
  ST.replay = () => { scrollTo(0, 0); box.innerHTML = ""; if (INTRO.g) { SG.remove(INTRO.g); } INTRO.done = false; buildIntro(); };
}
function endIntro(skipped) {
  INTRO.on = false; INTRO.done = true; document.body.classList.remove("intro");
  uni.uScanOn.value = 0; const cv = $("ihud"); if (cv) cv.getContext("2d").clearRect(0, 0, cv.width, cv.height); $("ihudTxt").innerHTML = "";
  const box = $("intro");
  if (skipped) { box.innerHTML = ""; if (INTRO.g) SG.remove(INTRO.g); return; }
  // 前五名飛進開場清單
  const rows = document.querySelectorAll(".ch.hero .toc li .v");
  INTRO.chips.forEach(o => {
    if (o.top >= 0 && rows[o.top]) {
      const a = o.el.getBoundingClientRect(), b = rows[o.top].getBoundingClientRect();
      o.el.animate([{ transform: o.el.style.transform, opacity: 1 }, { transform: `translate(${b.left + b.width / 2}px, ${b.top + b.height / 2}px) translate(-50%,-50%) scale(.55)`, opacity: 0 }], { duration: 900, easing: "cubic-bezier(.5,0,.2,1)", fill: "forwards" });
    } else o.el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 500, fill: "forwards" });
  });
  setTimeout(() => { box.innerHTML = ""; if (INTRO.g) SG.remove(INTRO.g); }, 1000);
}
const _ip = new THREE.Vector3();
function introTick() {
  if (!INTRO.on) return 1;
  const raw = (performance.now() - INTRO.t0) / 1000 / INTRO_SLOW, T = INTRO.T, ET = typeof EARTH_T === "number" ? EARTH_T : 0;
  INTRO.ek = ET ? Math.min(1, raw / ET) : 1;
  const t = raw - ET;   // 先播地球段落，掃描與數字往後延
  if (t < 0) { uni.uScanOn.value = 0; return 0; }
  const placed = [];
  for (const o of INTRO.order || (INTRO.order = INTRO.chips.slice().sort((a, b) => (b.top >= 0) - (a.top >= 0) || (b.halo === true) - (a.halo === true)))) {
    const k = Math.min(1, Math.max(0, (t - o.at) / 0.9)), e = 1 - Math.pow(1 - k, 3);
    _ip.copy(o.anchor).project(camera);
    const x = (_ip.x + 1) / 2 * innerWidth, y = (1 - _ip.y) / 2 * innerHeight;
    if (!o.w) { o.w = o.el.offsetWidth || 60; o.h = o.el.offsetHeight || 30; }
    const r = [x - o.w / 2 - 2, y - o.h - 2, x + o.w / 2 + 2, y + 2], hit = k > 0 && placed.some(p => r[0] < p[2] && r[2] > p[0] && r[1] < p[3] && r[3] > p[1]);
    if (k > 0 && !hit) placed.push(r);
    o.sx = x; o.sy = y; o.shown = k > 0 && !hit && _ip.z < 1; if (o.ph == null) o.ph = Math.random();
    const vis = _ip.z < 1 && k > 0 && !hit;
    const fade = o.top >= 0 ? 1 : 1 - Math.min(1, Math.max(0, (t - T.hold) / 0.7));
    o.el.style.opacity = vis ? (e * fade).toFixed(3) : 0;
    o.el.style.transform = `translate(${x.toFixed(1)}px, ${(y + (1 - e) * 14).toFixed(1)}px) translate(-50%,-100%) scale(${(0.7 + 0.3 * e).toFixed(3)})`;
    if (k > 0 && !o.fin) {
      const fin = (o.ftxt = o.ftxt || o.v.toLocaleString("en-US", { minimumFractionDigits: o.dec, maximumFractionDigits: o.dec })), p = Math.min(1, (t - o.at) / 0.9);
      const lock = Math.floor(p * fin.length);   // 由左往右一位一位鎖定
      o.num.textContent = fin.split("").map((ch, j) => j < lock || !/[0-9]/.test(ch) ? ch : "0123456789"[(Math.random() * 10) | 0]).join("");
      if (p >= 1) { o.num.textContent = fin; o.fin = true; o.el.classList.add("lock"); }
    }
    if (o.line) o.line.material.opacity = 0.8 * e * fade;
  }
  hudTick(t, placed);
  if (t >= T.fly) endIntro(false);
  return Math.min(1, t / T.cam);
}

/* ---- 科技感：掃描線、HUD 讀數、資料連線 ---- */
const HUD = { cv: null, cx: null };
function hudTick(t, placed) {
  const T = INTRO.T, sp = Math.min(1, Math.max(0, (t - T.scan0) / (T.scan1 - T.scan0)));
  const fade = 1 - Math.min(1, Math.max(0, (t - T.hold) / 0.8));
  uni.uScanOn.value = fade; uni.uScan.value = SCAN_LAT[0] + (SCAN_LAT[1] - SCAN_LAT[0]) * easeIO(sp);
  const cv = HUD.cv || (HUD.cv = $("ihud")), cx = HUD.cx || (HUD.cx = cv.getContext("2d")), dpr = Math.min(2, devicePixelRatio || 1);
  if (cv.width !== innerWidth * dpr) { cv.width = innerWidth * dpr; cv.height = innerHeight * dpr; }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, innerWidth, innerHeight);
  // 從島的中心拉線到外圍的數字，上面跑一個光點
  _ip.copy(gp(120.95, 23.7, 2)).project(camera);
  const ox = (_ip.x + 1) / 2 * innerWidth, oy = (1 - _ip.y) / 2 * innerHeight;
  cx.lineWidth = 1;
  for (const o of INTRO.chips) {
    if (!o.halo || !o.shown) continue;
    const k = Math.min(1, (t - o.at) / 0.6), x = o.sx, y = o.sy - o.h / 2;
    cx.strokeStyle = `rgba(100,210,255,${0.22 * k * fade})`; cx.beginPath(); cx.moveTo(ox, oy); cx.lineTo(ox + (x - ox) * k, oy + (y - oy) * k); cx.stroke();
    const u = ((t * 0.7 + o.ph) % 1), px = ox + (x - ox) * u, py = oy + (y - oy) * u;
    cx.fillStyle = `rgba(160,235,255,${0.9 * k * fade})`; cx.beginPath(); cx.arc(px, py, 1.6, 0, 7); cx.fill();
  }
  // 畫面四角的取景框
  const m = 22, L = 26, a = 0.55 * fade * Math.min(1, t / 0.4);
  cx.strokeStyle = `rgba(255,255,255,${a})`; cx.lineWidth = 1.2; cx.beginPath();
  for (const [x, y, sx, sy] of [[m, m + 44, 1, 1], [innerWidth - m, m + 44, -1, 1], [m, innerHeight - m, 1, -1], [innerWidth - m, innerHeight - m, -1, -1]]) { cx.moveTo(x + sx * L, y); cx.lineTo(x, y); cx.lineTo(x, y + sy * L); }
  cx.stroke();
  // 讀數
  const n = INTRO.chips.filter(o => o.fin).length, lat = uni.uScan.value;
  $("ihudTxt").style.opacity = fade;
  $("ihudTxt").innerHTML = `<div class="r1">SCANNING TAIWAN</div><div class="r2">${Math.min(25.3, Math.max(21.9, lat)).toFixed(2)}°N · 120.95°E</div><div class="r3">${String(n).padStart(3, "0")} / ${String(INTRO.chips.length).padStart(3, "0")} 筆即時資料</div><div class="bar"><i style="width:${(n / INTRO.chips.length * 100).toFixed(1)}%"></i></div>`;
}
