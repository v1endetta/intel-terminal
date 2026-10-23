
/* ---- 航班：桃園今天飛去哪 ----
   平常：所有航線都很淡，只看得出「線往哪些方向散出去」；光點＝依起飛時間推估、此刻在空中的班機；飛機圖示＝台灣周邊即時飛機（跟終端機同樣式）。
   點一下（地圖上的目的地、飛機，或右邊清單）才亮出那一條：飛去哪、幾班、此刻幾架在空中。 */
const FL = window.__FL = { g: null, built: false, AP: null, legs: [], live: [], R: {}, sel: null, lbl: null };
const TPE_LL = [121.233, 25.077];
const gcKm = (a, b) => { const D = Math.PI / 180, s = Math.sin((b[1] - a[1]) * D / 2) ** 2 + Math.cos(a[1] * D) * Math.cos(b[1] * D) * Math.sin((b[0] - a[0]) * D / 2) ** 2; return 12742 * Math.asin(Math.min(1, Math.sqrt(s))); };
async function flAirports() { if (!FL.AP) { try { FL.AP = await (await fetch("airports.json?v=" + ASSET_V)).json(); } catch (e) { FL.AP = { A: {}, I: {} }; } } return FL.AP; }
const flName = (code, fallback) => { const a = FL.AP.A[code]; return (a && a[3]) || fallback || (a && a[2]) || code; };
const arcAt = (pts, u) => { const f = Math.min(pts.length - 1.001, Math.max(0, u * (pts.length - 1))), i = Math.floor(f); return pts[i].clone().lerp(pts[i + 1], f - i); };
function liveDest(it) {   // 即時飛機：從航線（ICAO 串）找出它這一段要飛去的機場
  const codes = (it[8] || "").split("-").map(c => FL.AP.I[c]).filter(Boolean); if (codes.length < 2) return null;
  let best = null;
  for (let k = 0; k + 1 < codes.length; k++) { const a = FL.AP.A[codes[k]], b = FL.AP.A[codes[k + 1]]; if (!a || !b) continue;
    const here = [it[0], it[1]], ex = gcKm(a, here) + gcKm(here, b) - gcKm(a, b);
    if (!best || ex < best.ex) best = { ex, to: codes[k + 1], from: codes[k] }; }
  return best && best.ex < 900 ? best : null;
}
const dotTex = (() => { let t = null; return () => { if (t) return t; const c = document.createElement("canvas"); c.width = c.height = 64; const x = c.getContext("2d"), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.3, "rgba(255,250,235,0.9)"); gr.addColorStop(0.55, "rgba(120,220,255,0.3)"); gr.addColorStop(1, "rgba(0,0,0,0)"); x.fillStyle = gr; x.fillRect(0, 0, 64, 64); return (t = new THREE.CanvasTexture(c)); }; })();
function dotsObj(n, size, op) { const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(Math.max(1, n) * 3), 3));
  const p = new THREE.Points(g, fm(new THREE.PointsMaterial({ map: dotTex(), size, sizeAttenuation: false, blending: THREE.AdditiveBlending, depthTest: true }), op)); p.frustumCulled = false; p.renderOrder = 5; return p; }
async function buildFlights() {
  await flAirports(); const AP = FL.AP.A, ap = P.airport || {}, g = new THREE.Group(); FL.g = g; SG.add(g); g.visible = false;
  const o = AP.TPE ? [AP.TPE[0], AP.TPE[1]] : TPE_LL, routes = ((ap.routes || {}).dep || []).filter(r => AP[r[0]]);
  const maxN = Math.max(1, ...routes.map(r => r[1]));
  for (const r of routes) {   // 每條航線兩種樣子：平常一條很淡的細線；選到時換成發亮的粗管
    const d = AP[r[0]], pts = GLOBE.arc(o, [d[0], d[1]], 0.1, 80), k = r[1] / maxN;
    const faint = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), fm(new THREE.LineBasicMaterial({ color: 0x64d2ff, blending: THREE.AdditiveBlending, depthTest: true }), 0.07 + 0.2 * Math.sqrt(k)));
    const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 80, 8 + Math.sqrt(k) * 14, 6, false), fm(new THREE.MeshBasicMaterial({ color: 0xbff0ff, blending: THREE.AdditiveBlending, depthTest: true, depthWrite: false }), 0.75));
    tube.visible = false;
    const node = new THREE.Mesh(new THREE.SphereGeometry(10 + 14 * Math.sqrt(k), 10, 8), fm(new THREE.MeshBasicMaterial({ color: 0x9fe6ff, depthTest: true }), 0.55)); node.position.copy(GLOBE.G(d[0], d[1], 25));
    g.add(faint, tube, node);
    FL.R[r[0]] = { code: r[0], n: r[1], late: r[2], cx: r[3], zh: r[4], pts, faint, tube, node, ll: [d[0], d[1]] };
  }
  // 此刻在空中的班機（依表訂／預計時間推估）
  FL.legs = (ap.legs || []).map(l => {
    const d = AP[l[2]]; if (!d || l[5] === "X") return null;
    const dur = (gcKm(o, d) / 800 + 0.5) * 60, pts = l[0] === "D" ? (FL.R[l[2]] || {}).pts || GLOBE.arc(o, [d[0], d[1]], 0.1, 80) : GLOBE.arc([d[0], d[1]], o, 0.1, 80);
    return { kind: l[0], code: l[2], fl: l[1], t: l[4] || l[3], st: l[5], dur, pts };
  }).filter(Boolean);
  FL.dots = dotsObj(FL.legs.length, MOBILE ? 7 : 8, 0.55); FL.hot = dotsObj(FL.legs.length, MOBILE ? 14 : 16, 1); g.add(FL.dots, FL.hot);
  // 台灣周邊的即時飛機（目的地虛線平常不畫，點了才出現）
  // 飛機圖示：跟終端機同一個剪影，平貼在地球表面、機頭朝航向；低空（一萬呎以下）琥珀色，高空淡藍
  const sh = new THREE.Shape(); [[16, 2], [19, 13], [30, 19], [30, 22], [19, 19], [18.5, 26], [22, 29], [22, 30.5], [16, 29], [10, 30.5], [10, 29], [13.5, 26], [13, 19], [2, 22], [2, 19], [13, 13]].forEach((q, i) => i ? sh.lineTo((q[0] - 16), (16 - q[1])) : sh.moveTo((q[0] - 16), (16 - q[1])));
  const planeGeo = new THREE.ShapeGeometry(sh); planeGeo.rotateX(Math.PI / 2); planeGeo.scale(MOBILE ? 2.2 : 1.7, 1, MOBILE ? 2.2 : 1.7);
  const planeLow = fm(new THREE.MeshBasicMaterial({ color: 0xe0a23a, side: THREE.DoubleSide, depthTest: false }), 0.95), planeHigh = fm(new THREE.MeshBasicMaterial({ color: 0x9fb4ff, side: THREE.DoubleSide, depthTest: false }), 0.95);
  FL.live = [];
  for (const it of ((P.flights || {}).items || [])) {
    const m = new THREE.Mesh(planeGeo, it[3] < 10000 ? planeLow : planeHigh), p0 = GLOBE.G(it[0], it[1], 40), a = it[2] * Math.PI / 180;
    m.position.copy(p0); m.up.copy(p0).sub(V(0, -6371, 0)).normalize(); m.lookAt(GLOBE.G(it[0] + Math.sin(a) * 0.2, it[1] + Math.cos(a) * 0.2, 40)); m.renderOrder = 6; g.add(m);
    const dst = liveDest(it); let ln = null;
    if (dst) { const b = AP[dst.to]; ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(GLOBE.arc([it[0], it[1]], [b[0], b[1]], 0.06, 60).map(v => v.add(V(0, 8, 0)))), fm(new THREE.LineDashedMaterial({ color: 0xffd60a, dashSize: 50, gapSize: 40, blending: THREE.AdditiveBlending, depthTest: true }), 0.9));
      ln.computeLineDistances(); ln.visible = false; g.add(ln); }
    FL.live.push({ it, dst, m, ln, p0 });
  }
  FL.lbl = addLabel("", V(0, 0, 0), "flt sel", "flights", 50); FL.lbl.hide = true;
  FL.built = true; flightsTick(true);
}
// 同一時間只建一次（進航班、5 分鐘資料更新可能同時要建）
function flBuild() { return FL.building || (FL.building = buildFlights().finally(() => { FL.building = null; })); }
// 資料每 5 分鐘更新：航班原地重建；正在看的人鏡頭不動，選到的那條航線新資料裡還有就繼續亮著
function flRefresh() {
  if (!FL.built || FL.building) return;
  const old = FL.g, keep = FL.sel && FL.sel.code;
  FL.built = false; FL.R = {}; FL.sel = null; clearLabels("flights");
  return flBuild().then(() => {
    if (old) { SG.remove(old); old.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); }
    if (cur === "flights") { FL.g.visible = true; flSelect(keep && FL.R[keep] ? { code: keep } : null); }
  });
}
// 選取：一條航線（代碼）或一架即時飛機（物件）；null＝全部回到淡淡的樣子
function flSelect(s) {
  FL.sel = s;
  for (const R of Object.values(FL.R)) { const on = !!(s && s.code === R.code); R.tube.visible = on; R.faint.material.userData.op = s ? (on ? 0 : 0.035) : 0.07 + 0.2 * Math.sqrt(R.n / Math.max(...Object.values(FL.R).map(x => x.n))); R.node.material.userData.op = on ? 1 : s ? 0.25 : 0.55; }
  for (const L of FL.live) { if (L.ln) L.ln.visible = !!(s && s.live === L); }
  if (!s) { FL.lbl.hide = true; } else if (s.code) { const R = FL.R[s.code], air = FL.legs.filter(l => l.code === s.code && l.inAir).length;
    FL.lbl.el.innerHTML = `<b>${esc(flName(R.code, R.zh))}</b> 今天 ${R.n} 班${R.late ? `・延誤 ${R.late}` : ""}<br><span>此刻約 ${air} 架在空中</span>`; FL.lbl.pos = GLOBE.G(...R.ll, 80); FL.lbl.w = 0; }
  else { const it = s.live.it, ft = Math.round(it[3] / 100) * 100;
    FL.lbl.el.innerHTML = `<b>${esc(it[4] || it[6] || "飛機")}</b> → ${esc(s.live.dst ? flName(s.live.dst.to) : "目的地不明")}<br><span>${esc(it[5] || "")}${it[5] ? "・" : ""}高度 ${nf(ft)} 呎・${Math.round(it[7] * 1.852)} 公里/時</span>`; FL.lbl.pos = s.live.p0.clone().add(V(0, 40, 0)); FL.lbl.w = 0; }
  // 右邊清單同步標示
  document.querySelectorAll("#side [data-fl]").forEach(li => li.classList.toggle("on", !!(s && s.code === li.dataset.fl)));
}
function flightsSide() {
  const ap = P.airport || {}, dep = ap.dep || {}, routes = ((ap.routes || {}).dep || []).filter(r => FL.R[r[0]]);
  const rows = routes.slice(0, 12).map(r => `<li data-fl="${esc(r[0])}" style="cursor:pointer">${esc(flName(r[0], r[4]))}<span>${r[1]} 班${r[2] ? `・延誤 ${r[2]}` : ""}${r[3] ? `・取消 ${r[3]}` : ""}</span></li>`).join("");
  return sideHTML({ eyebrow: "現場 · 桃園機場 · ADS-B", title: "今天飛去哪裡", big: `${routes.length} 個航點`, color: "#64d2ff",
    body: `<p class="why">今天 ${dep.total || 0} 班離境，此刻約 ${FL.inAir || 0} 架在空中。點一個城市、地圖上的光點或飛機，看它飛去哪。</p><ul class="lst">${rows}</ul>` });
}
// 光點沿航線移動；選到的那條另外畫一層亮的；被地球擋住的標籤藏起來
const _fc = new THREE.Vector3(), _fn = new THREE.Vector3();
function flightsTick(force) {
  if (!FL.built || (!FL.g.visible && !force)) return;
  const now = Date.now() / 60000, A = FL.dots.geometry.attributes.position.array, B = FL.hot.geometry.attributes.position.array; let n = 0, h = 0;
  for (const l of FL.legs) {
    let u; l.inAir = false;
    if (l.kind === "D") { if (l.st !== "D" && l.t > now) continue; u = (now - l.t) / l.dur; }
    else { if (l.st === "L") continue; u = 1 - (l.t - now) / l.dur; }
    if (!(u > 0 && u < 1)) continue;
    l.inAir = true; const p = arcAt(l.pts, u);
    if (FL.sel && FL.sel.code === l.code) { B[h * 3] = p.x; B[h * 3 + 1] = p.y + 6; B[h * 3 + 2] = p.z; h++; }
    else { A[n * 3] = p.x; A[n * 3 + 1] = p.y + 6; A[n * 3 + 2] = p.z; n++; }
  }
  FL.inAir = n + h; FL.dots.geometry.setDrawRange(0, n); FL.hot.geometry.setDrawRange(0, h);
  FL.dots.geometry.attributes.position.needsUpdate = true; FL.hot.geometry.attributes.position.needsUpdate = true;
  FL.dots.material.userData.op = FL.sel ? 0.2 : 0.55;
  if (FL.sel) { const C = V(0, -6371, 0); _fc.copy(camera.position).sub(C).normalize(); _fn.copy(FL.lbl.pos).sub(C).normalize(); FL.lbl.hide = _fn.dot(_fc) < 0.1; }
  // 材質透明度（fm 記住的值）直接套用；地球圖層不經過章節淡入淡出
  FL.g.traverse(o => { if (o.material && o.material.userData.op != null) o.material.opacity = o.material.userData.op; });
}
// 點地圖：找螢幕上最近的目的地或飛機（手指不用點很準）
const _fp = new THREE.Vector3();
function flPick(x, y) {
  let best = null, bd = MOBILE ? 36 : 24;
  const C = V(0, -6371, 0); _fc.copy(camera.position).sub(C).normalize();
  const test = (p, s) => { _fn.copy(p).sub(C).normalize(); if (_fn.dot(_fc) < 0.05) return; _fp.copy(p).project(camera); if (_fp.z > 1) return;
    const sx = (_fp.x + 1) / 2 * innerWidth, sy = (1 - _fp.y) / 2 * VH(), d = Math.hypot(sx - x, sy - y); if (d < bd) { bd = d; best = s; } };
  for (const R of Object.values(FL.R)) test(R.node.position, { code: R.code });
  for (const L of FL.live) test(L.p0, { live: L });
  for (const l of FL.legs) if (l.inAir) test(arcAt(l.pts, Math.min(0.999, Math.max(0, l.kind === "D" ? (Date.now() / 60000 - l.t) / l.dur : 1 - (l.t - Date.now() / 60000) / l.dur))), { code: l.code });
  return best;
}
let _flDown = null;
renderer.domElement.addEventListener("pointerdown", e => { _flDown = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener("pointerup", e => {
  if (cur !== "flights" || !FL.built || !_flDown || Math.hypot(e.clientX - _flDown[0], e.clientY - _flDown[1]) > 8) return;
  const s = flPick(e.clientX, e.clientY); flSelect(s && FL.sel && ((s.code && s.code === FL.sel.code) || (s.live && s.live === FL.sel.live)) ? null : s);
});
document.addEventListener("click", e => { const li = e.target.closest && e.target.closest("#side [data-fl]"); if (!li || cur !== "flights" || !FL.built) return; e.stopPropagation(); if (!FL.R[li.dataset.fl]) return; flSelect(FL.sel && FL.sel.code === li.dataset.fl ? null : { code: li.dataset.fl }); }, true);
// 地球拖曳：像轉地球儀一樣——左右拖＝沿經度轉、上下拖＝往南北看，北方永遠朝上；放手有慣性；滾輪／雙指縮放
const GD = { on: false, ptrs: new Map(), vx: 0, vy: 0, pinch: 0 };
const _gC = new THREE.Vector3(0, -6371, 0), _gN = new THREE.Vector3(), _gv = new THREE.Vector3(), _gA = new THREE.Vector3(), _gq = new THREE.Quaternion();
function gdAxis() { if (!_gN.lengthSq()) _gN.copy(GLOBE.G(0, 90, 0)).sub(_gC).normalize(); return _gN; }
function gdRotate(dx, dy) {
  const N = gdAxis(); _gv.copy(camera.position).sub(_gC); const dist = _gv.length(), k = Math.max(0.0004, (dist - 6371) / 6371) * 0.0016;
  _gq.setFromAxisAngle(N, -dx * k); _gv.applyQuaternion(_gq);
  _gA.crossVectors(_gv, N).normalize(); const lat0 = Math.PI / 2 - _gv.angleTo(N), dLat = dy * k, lat1 = Math.max(-1.2, Math.min(1.25, lat0 + dLat));
  _gq.setFromAxisAngle(_gA, lat1 - lat0); _gv.applyQuaternion(_gq);
  camera.position.copy(_gC).add(_gv); camera.up.copy(N); camera.lookAt(_gC);
}
function gdZoom(f) { _gv.copy(camera.position).sub(_gC); const d = Math.max(6371 + 3000, Math.min(6371 + 42000, 6371 + (_gv.length() - 6371) * f)); _gv.setLength(d); camera.position.copy(_gC).add(_gv); camera.lookAt(_gC); }
const gdEl = renderer.domElement;
gdEl.addEventListener("pointerdown", e => { if (!GD.on || fly) return;   /* 飛往地球途中按到畫面不要把飛行打斷（會停在半空中、地球還沒淡入，看起來像卡住） */ GD.ptrs.set(e.pointerId, [e.clientX, e.clientY]); GD.vx = GD.vy = 0; GD.pinch = 0; gdEl.setPointerCapture && gdEl.setPointerCapture(e.pointerId); });
gdEl.addEventListener("pointermove", e => { if (!GD.on || !GD.ptrs.has(e.pointerId)) return; if (e.pointerType === "mouse" && !e.buttons) { gdUp(e); return; }   /* 放開的事件沒收到（滑鼠在視窗外放開）：不能讓地球一直黏著游標 */ const p = GD.ptrs.get(e.pointerId), dx = e.clientX - p[0], dy = e.clientY - p[1]; GD.ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  if (GD.ptrs.size >= 2) { const [a, b] = [...GD.ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]); if (GD.pinch) gdZoom(GD.pinch / d); GD.pinch = d; return; }
  gdRotate(dx, dy); GD.vx = Math.max(-30, Math.min(30, dx)); GD.vy = Math.max(-30, Math.min(30, dy)); GD.t = performance.now(); });
const gdUp = e => { if (!GD.ptrs.has(e.pointerId)) return; GD.ptrs.delete(e.pointerId); GD.pinch = 0; if (GD.ptrs.size || performance.now() - (GD.t || 0) > 80) GD.vx = GD.vy = 0; };   // 停住再放手就不滑
gdEl.addEventListener("pointerup", gdUp); gdEl.addEventListener("pointercancel", gdUp); gdEl.addEventListener("lostpointercapture", gdUp);
gdEl.addEventListener("wheel", e => { if (!GD.on) return; e.preventDefault(); if (fly) return; gdZoom(Math.exp(e.deltaY * 0.0012)); }, { passive: false });
function gdTick(dt) { if (!GD.on || GD.ptrs.size || (Math.abs(GD.vx) < 0.05 && Math.abs(GD.vy) < 0.05)) return; const f = Math.min(3, (dt || 0.016) * 60); gdRotate(GD.vx * f, GD.vy * f); const d = Math.pow(0.88, f); GD.vx *= d; GD.vy *= d; }   // 放手後的慣性，跟畫面格數無關
layers.flights = {
  get g() { return FL.g || new THREE.Group(); },
  on() {
    ST.globeForce = true; document.body.classList.add("fl-on");
    // 地球模式：鏡頭繞著地心轉，手指拖到哪地球就轉到哪，雙指／滾輪縮放
    const C = V(0, -6371, 0), look = GLOBE.G(MOBILE ? 122 : 129, MOBILE ? 21 : 25, 0).sub(C).normalize();
    controls.enabled = false; controls.autoRotate = false; GD.on = true; GD.vx = GD.vy = 0;
    controls.minDistance = 0; controls.maxDistance = Infinity; controls.minPolarAngle = 0; controls.maxPolarAngle = Math.PI;
    camera.up.copy(gdAxis()); camera.near = 20; camera.far = 300000; camera.updateProjectionMatrix(); flyTo(C.clone().addScaledVector(look, 6371 + (MOBILE ? 10500 : 8000)), C, 2.2);
    const show = () => { FL.g.visible = true; flSelect(null); };
    if (FL.built) show(); else flBuild().then(() => { if (cur === "flights") { show(); showSide(flightsSide(), null); } })
      .catch(e => { console.warn("flights", e); if (cur === "flights") showSide(sideHTML({ eyebrow: "現場 · 桃園機場", title: "今天飛去哪裡", body: '<p class="empty">航線暫時讀不到。點上方「台灣」或下面任何一個項目都能離開。</p>' }), null); });
  },
  off() {
    ST.globeForce = false; document.body.classList.remove("fl-on"); if (FL.g) FL.g.visible = false; if (FL.lbl) FL.lbl.hide = true;
    GD.on = false; GD.ptrs.clear(); camera.up.set(0, 1, 0); controls.enabled = ST.explore; controls.minDistance = 0.25; controls.maxPolarAngle = Math.PI * 0.46;
    if (ST.explore) { controls.maxDistance = 1600; camera.near = 1; camera.updateProjectionMatrix(); flyTo(ISLAND.pos, ISLAND.tgt, 1.8); }
  },
  tick(T, dt) { gdTick(dt); flightsTick(); },
};
