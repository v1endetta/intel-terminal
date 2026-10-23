
/* ---- 地面氣壓圖：東亞海平面氣壓 → 等壓線（每 4 百帕一條，每 20 一條粗線）＋ 高低壓中心＋颱風 ----
   資料 Open-Meteo 2.5 度網格，前端先內插成 0.5 度再畫線；卡片可以切換現在到 72 小時後。 */
const PRS = { f: 0 };
const kmGC = (a, b) => { const r = Math.PI / 180, s1 = Math.sin((b[1] - a[1]) * r / 2), s2 = Math.sin((b[0] - a[0]) * r / 2); return 12742 * Math.asin(Math.sqrt(s1 * s1 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * s2 * s2)); };
function prsGrid(fi) {   // 內插成 0.5 度
  const PR = P.pressure, F = PR.frames[fi], W = PR.lon.length, H = PR.lat.length, K = 5, w = (W - 1) * K + 1, h = (H - 1) * K + 1, g = new Float32Array(w * h);
  const v = (i, j) => { i = Math.max(0, Math.min(W - 1, i)); j = Math.max(0, Math.min(H - 1, j)); const x = F.p[j * W + i]; return x == null ? 1012 : x; };
  const cr = (a, b, c, d, t) => b + 0.5 * t * (c - a + t * (2 * a - 5 * b + 4 * c - d + t * (3 * (b - c) + d - a)));   // Catmull-Rom：曲線平滑，不會出現菱形
  for (let J = 0; J < h; J++) for (let I = 0; I < w; I++) {
    const i = Math.min(W - 2, Math.floor(I / K)), j = Math.min(H - 2, Math.floor(J / K)), u = I / K - i, t = J / K - j, row = [];
    for (let y = -1; y <= 2; y++) row.push(cr(v(i - 1, j + y), v(i, j + y), v(i + 1, j + y), v(i + 2, j + y), u));
    g[J * w + I] = cr(row[0], row[1], row[2], row[3], t);
  }
  return { g, w, h, lon0: PR.lon[0], lat0: PR.lat[0], d: (PR.lon[1] - PR.lon[0]) / K };
}
function prsAt(G, lon, lat) { const x = (lon - G.lon0) / G.d, y = (lat - G.lat0) / G.d, i = Math.max(0, Math.min(G.w - 2, Math.floor(x))), j = Math.max(0, Math.min(G.h - 2, Math.floor(y))), u = x - i, t = y - j, a = G.g;
  return a[j * G.w + i] * (1 - u) * (1 - t) + a[j * G.w + i + 1] * u * (1 - t) + a[(j + 1) * G.w + i] * (1 - u) * t + a[(j + 1) * G.w + i + 1] * u * t; }
function prsContours(G) {   // 等壓線：marching squares，回傳 { level: [lon,lat, lon,lat, ...] }
  let lo = 1e9, hi = -1e9; for (const x of G.g) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
  const out = {}, P2 = (I, J) => [G.lon0 + I * G.d, G.lat0 + J * G.d];
  for (let L = Math.ceil(lo / 4) * 4; L <= hi; L += 4) {
    const seg = [];
    for (let J = 0; J < G.h - 1; J++) for (let I = 0; I < G.w - 1; I++) {
      const a = G.g[J * G.w + I], b = G.g[J * G.w + I + 1], c = G.g[(J + 1) * G.w + I + 1], d = G.g[(J + 1) * G.w + I];
      const pts = [], e = (v0, v1, p0, p1) => { const t = (L - v0) / (v1 - v0); pts.push([p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t]); };
      const A = P2(I, J), B = P2(I + 1, J), C = P2(I + 1, J + 1), D = P2(I, J + 1);
      if ((a < L) !== (b < L)) e(a, b, A, B); if ((b < L) !== (c < L)) e(b, c, B, C); if ((c < L) !== (d < L)) e(c, d, C, D); if ((d < L) !== (a < L)) e(d, a, D, A);
      if (pts.length >= 2) seg.push(...pts[0], ...pts[1]); if (pts.length === 4) seg.push(...pts[2], ...pts[3]);
    }
    if (seg.length) out[L] = seg;
  }
  return out;
}
function prsCenters(G) {   // 高低壓中心：周圍 4 度內最高／最低，而且跟周圍差 2 百帕以上
  const R = Math.round(4 / G.d), out = [];
  for (let J = R; J < G.h - R; J++) for (let I = R; I < G.w - R; I++) {
    const v = G.g[J * G.w + I]; let mx = true, mn = true, sum = 0, n = 0;
    for (let y = -R; y <= R && (mx || mn); y++) for (let x = -R; x <= R; x++) { if (!x && !y) continue; const u = G.g[(J + y) * G.w + I + x]; if (u > v) mx = false; if (u < v) mn = false; if (x * x + y * y >= R * R - 2) { sum += u; n++; } }
    const ring = sum / Math.max(1, n);
    if (mx && v - ring > 2) out.push({ k: "H", v, ll: [G.lon0 + I * G.d, G.lat0 + J * G.d] });
    if (mn && ring - v > 2) out.push({ k: "L", v, ll: [G.lon0 + I * G.d, G.lat0 + J * G.d] });
  }
  return out;
}
function gxPress() {
  clearLabels("gx"); GX.lbls = []; GX.rings = [];
  const PR = P.pressure; if (!PR || !PR.frames || !PR.frames.length || !GLOBE) return;
  const G = prsGrid(Math.min(PRS.f, PR.frames.length - 1)), C = prsContours(G), thin = [], bold = [];
  for (const [L, seg] of Object.entries(C)) { const arr = +L % 20 === 0 ? bold : thin;
    for (let k = 0; k < seg.length; k += 2) { const p = GLOBE.G(seg[k], seg[k + 1], 14); arr.push(p.x, p.y, p.z); } }
  const mk = (pos, px, op) => { if (!pos.length) return; const g = new LineSegmentsGeometry(); g.setPositions(pos);
    const m = new LineMaterial({ color: 0xffffff, linewidth: px, transparent: true, opacity: op, depthTest: true, worldUnits: false }); m.resolution.set(innerWidth, innerHeight); FATM.push(m);
    const l = new LineSegments2(g, m); l.renderOrder = 3; l.frustumCulled = false; GX.g.add(l); };
  mk(thin, 1.2, 0.55); mk(bold, 2.2, 0.9);
  // 數字：等壓線穿過東經 117.5 度的地方（台灣西邊）標上氣壓值
  for (const [L, seg] of Object.entries(C)) { let best = null;
    for (let k = 0; k < seg.length; k += 4) { const [x0, y0, x1, y1] = seg.slice(k, k + 4); if ((x0 - 117.5) * (x1 - 117.5) <= 0 && y0 > 8 && y0 < 42) { const y = y0 + (y1 - y0) * ((117.5 - x0) / ((x1 - x0) || 1e-9)); if (!best || Math.abs(y - 24) < Math.abs(best - 24)) best = y; } }
    if (best != null) GX.lbls.push([addLabel(`<span class="prl${+L % 20 === 0 ? " b" : ""}">${L}</span>`, GLOBE.G(117.5, best, 60), "gx", "gx", 1, () => ({ html: `<i class="lp-k">等壓線</i><b>${L} 百帕</b><p>這條線上每個地方的海平面氣壓都是 ${L} 百帕。${+L % 20 === 0 ? "粗線每 20 百帕一條。" : ""}</p><p>線越密，氣壓變化越快、風越大。</p>` })), GLOBE.G(117.5, best, 0)]); }
  for (const c of prsCenters(G)) GX.lbls.push([addLabel(`<span class="prc ${c.k}"><b>${c.k}</b>${Math.round(c.v)}</span>`, GLOBE.G(c.ll[0], c.ll[1], 80), "gx", "gx", 6, () => ({ html: `<i class="lp-k" style="color:${c.k === "H" ? "#64d2ff" : "#ff453a"}">${c.k === "H" ? "高氣壓中心" : "低氣壓中心"}</i><b>${Math.round(c.v)} 百帕</b><p>北緯 ${c.ll[1].toFixed(1)}・東經 ${c.ll[0].toFixed(1)}・離台灣約 ${Math.round(kmGC(c.ll, [121, 23.7]))} 公里</p><p>${c.k === "H" ? "高壓附近空氣下沉，天氣通常晴朗穩定；冬天大陸高壓南下就是寒流、東北季風。" : "低壓附近空氣上升，雲多、容易下雨；很強的熱帶低壓就是颱風。"}</p>` })), GLOBE.G(c.ll[0], c.ll[1], 0)]);
  for (const t of (((P.typhoon || {}).items) || [])) { const f = (t.past || [])[t.past.length - 1]; if (!f) continue;
    const dot = new THREE.Mesh(new THREE.SphereGeometry(70, 16, 12), fm(new THREE.MeshBasicMaterial({ color: 0xff453a, depthTest: true }), 1)); dot.position.copy(GLOBE.G(f.ll[0], f.ll[1], 30)); GX.g.add(dot);
    const pts = (t.fc || []).map(x => GLOBE.G(x.ll[0], x.ll[1], 25)); if (pts.length) { const g = new THREE.BufferGeometry().setFromPoints([GLOBE.G(f.ll[0], f.ll[1], 25), ...pts]); GX.g.add(new THREE.Line(g, new THREE.LineDashedMaterial({ color: 0xff453a, dashSize: 60, gapSize: 40 })).computeLineDistances()); }
    GX.lbls.push([addLabel(`<span class="prc T"><b>颱風 ${esc(t.name || "")}</b>${f.p ? f.p + " hPa" : ""}</span>`, GLOBE.G(f.ll[0], f.ll[1], 120), "gx", "gx", 9, () => ({ html: `<i class="lp-k" style="color:#ff453a">颱風・氣象署</i><b>${esc(t.name || "")}${t.en ? " " + esc(t.en) : ""}</b><p>${f.t ? f.t.slice(5, 16).replace("T", " ") + " 的位置" : ""}・中心氣壓 ${f.p ?? "—"} 百帕</p><p>最大風速 ${f.wind ?? "—"} m/s・陣風 ${f.gust ?? "—"} m/s</p><p>${f.mv ? `往 ${esc(f.dir)} 移動，時速 ${f.mv} 公里` : ""}${f.r15 ? `・七級風暴風半徑 ${f.r15} 公里` : ""}</p><p>離台灣約 ${Math.round(kmGC(f.ll, [121, 23.7]))} 公里</p><a href="https://www.cwa.gov.tw/V8/C/P/Typhoon/TY_NEWS.html" target="_blank" rel="noopener">氣象署颱風消息 ›</a>` })), GLOBE.G(f.ll[0], f.ll[1], 0)]); }
  const tw = new THREE.Mesh(new THREE.SphereGeometry(45, 16, 12), fm(new THREE.MeshBasicMaterial({ color: 0x64d2ff }), 1)); tw.position.copy(GLOBE.G(TW_LL[0], TW_LL[1], 30)); GX.g.add(tw);
  GX.lbls.push([addLabel(`<span class="gxl tw"><b>台灣 ${Math.round(prsAt(G, 121, 23.7))}</b></span>`, GLOBE.G(TW_LL[0], TW_LL[1], 160), "gx", "gx", 9, () => { const PR = P.pressure, seq = PR.frames.map((_, i) => [PR.frames[i].t, prsAt(prsGrid(i), 121, 23.7)]).filter((_, i) => i % 2 === 0).slice(0, 7);
    return { html: `<b>台灣附近的氣壓</b><p>${seq.map(([t, v]) => `${t.slice(8, 10)}日${t.slice(11, 13)}時 ${Math.round(v)}`).join("　")}</p><p>氣壓一路往下掉，通常代表低壓或颱風在靠近；往上升，代表高壓（例如東北季風）南下。</p>` }; }), GLOBE.G(TW_LL[0], TW_LL[1], 0)]);
}
function prsCard() {
  const PR = P.pressure;
  if (!PR || !PR.frames || !PR.frames.length) return { layer: "gx", gx: "press", html: sideHTML({ eyebrow: "現場 · 氣壓圖", title: "地面氣壓圖", body: '<p class="empty">氣壓資料下一輪更新後出現（每 6 小時一次）。</p>' }) };
  const f = Math.min(PRS.f, PR.frames.length - 1), G = prsGrid(f), tp = prsAt(G, 121, 23.7), cs = prsCenters(G), T = PR.frames[f].t;
  const steps = [[0, "現在"], [2, "12 小時"], [4, "24 小時"], [8, "48 小時"], [12, "72 小時"]].filter(([i]) => i < PR.frames.length);
  const ty = (((P.typhoon || {}).items) || []).filter(t => (t.past || []).length);
  const near = cs.filter(c => Math.hypot(c.ll[0] - 121, c.ll[1] - 23.7) < 18).sort((a, b) => Math.hypot(a.ll[0] - 121, a.ll[1] - 23.7) - Math.hypot(b.ll[0] - 121, b.ll[1] - 23.7)).slice(0, 4);
  return { layer: "gx", gx: "press", html: sideHTML({ eyebrow: `現場 · 地面氣壓 · ${T.slice(5, 10).replace("-", "/")} ${T.slice(11, 16)}`, title: "地面氣壓圖", big: `台灣 ${Math.round(tp)} 百帕`, color: tp < 1005 ? "#ff9f0a" : "#64d2ff",
    body: `<div class="mkt">${steps.map(([i, l]) => `<button data-pf="${i}" class="${i === f ? "on" : ""}">${l}</button>`).join("")}</div>`
      + (ty.length ? `<p class="why" style="color:#ff453a">颱風 ${ty.map(t => esc(t.name)).join("、")}：紅點是現在位置，虛線是氣象署的預測路徑。</p>` : "")
      + (near.length ? listHTML(near.map(c => ({ t: `${c.k === "H" ? "高壓" : "低壓"} ${Math.round(c.v)} 百帕`, s: `北緯 ${c.ll[1].toFixed(0)}・東經 ${c.ll[0].toFixed(0)}` }))) : "")
      + `<p class="why">藍色 H 是高壓、紅色 L 是低壓（國際天氣圖的標法）。白線是等壓線，每 4 百帕一條、粗線每 20 百帕；線越密，風越大。高壓附近天氣通常穩定，低壓附近雲雨多，颱風就是很強的低壓。</p>` }) };
}
document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("[data-pf]"); if (!b) return; PRS.f = +b.dataset.pf;
  if (GX.key === "press" && GX.g) { GX.g.traverse(o => { o.geometry && o.geometry.dispose(); }); GX.g.clear(); gxPress(); GX.g.visible = true; }
  const r = prsCard(); showSide(r.html + provHTML("氣壓圖"), null); });
