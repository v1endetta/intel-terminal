/* ---------- 捲動劇本（方向 G）----------
   頁面往下捲，鏡頭一章一章移動。章節：開場 → 今天三件事（自動排名）→ 此刻的台灣（真正的地理資料）→ 自己逛。
   地圖上只放發生在那裡的事；全國性的數字有自己的章節，不釘在假地點上。 */
const ST = { on: true, explore: false, c: 0, chapters: [], H: null, active: -1 };
const SG = new THREE.Group(); scene.add(SG);
const CY = new THREE.Color(0x64d2ff), WH = new THREE.Color(0xffffff), YL = new THREE.Color(0xffd60a);
camera.far = 90000; camera.updateProjectionMatrix();
const FOG = scene.fog;
let SEA = null;

// 材質：記住原本的透明度，淡入淡出時乘上章節權重
const fm = (m, op) => { m.transparent = true; m.depthWrite = false; m.userData.op = op; return m; };
const addM = (c, op = 1, dt = false) => fm(new THREE.MeshBasicMaterial({ color: c, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthTest: dt }), op);
const lineM = (c, op = 1, dt = false) => fm(new THREE.LineBasicMaterial({ color: c, blending: THREE.AdditiveBlending, depthTest: dt }), op);
const gp = (lon, lat, lift = 0.25) => { const [x, z] = toXZ(lon, lat); return new THREE.Vector3(x, hAt(lon, lat) + lift, z); };
function sLine(g, pts, c, op = 1, dt = false) { const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineM(c, op, dt)); g.add(l); return l; }
function sSegs(g, pts, c, op = 1, dt = false) { const l = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), lineM(c, op, dt)); g.add(l); return l; }
function sGrad(g, pts, c, op = 1, dt = false) {
  const geo = new THREE.BufferGeometry().setFromPoints(pts), col = [];
  pts.forEach((_, i) => { const k = Math.pow(i / (pts.length - 1), 1.5); col.push(c.r * k, c.g * k, c.b * k); });
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  const l = new THREE.Line(geo, fm(new THREE.LineBasicMaterial({ vertexColors: true, blending: THREE.AdditiveBlending, depthTest: dt }), op)); g.add(l); return l;
}
function flatRing(g, lon, lat, r0, r1, c, op = 1, lift = 0.3) { const m = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 96), addM(c, op)); m.rotation.x = -Math.PI / 2; m.position.copy(gp(lon, lat, lift)); g.add(m); return m; }
function circlePts(c, r, a0 = 0, a1 = Math.PI * 2, n = 96) { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; p.push(new THREE.Vector3(c.x + Math.cos(a) * r, c.y, c.z + Math.sin(a) * r)); } return p; }
function groundText(g, lines, lon, lat, width, yaw, opt = {}) {
  const fs = opt.fs || 64, pad = 24, cv = document.createElement("canvas"), cx = cv.getContext("2d");
  const font = (w, s) => `${w} ${s}px -apple-system, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif`;
  let W = 0; lines.forEach((l, i) => { cx.font = font(i ? 400 : 700, i ? fs * 0.5 : fs); W = Math.max(W, cx.measureText(l).width); });
  cv.width = Math.ceil(W + pad * 2); cv.height = Math.ceil(fs * 1.25 + (lines.length - 1) * fs * 0.7 + pad * 2);
  lines.forEach((l, i) => { cx.font = font(i ? 400 : 700, i ? fs * 0.5 : fs); cx.fillStyle = i ? "rgba(200,235,255,0.85)" : (opt.color || "#bfefff"); cx.textBaseline = "top"; cx.fillText(l, pad, pad + (i ? fs * 1.15 + (i - 1) * fs * 0.7 : 0)); });
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(width, width * cv.height / cv.width), fm(new THREE.MeshBasicMaterial({ map: t, blending: THREE.AdditiveBlending, depthTest: false }), 1));
  m.rotation.x = -Math.PI / 2; m.rotation.z = yaw; m.position.copy(gp(lon, lat, opt.lift ?? 0.4)); g.add(m); return m;
}
const yawOf = cam => { const d = cam.tgt.clone().sub(cam.pos); return Math.atan2(-d.x, -d.z); };
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const camAt = (lon, lat, off, lift = 0) => { const t = gp(lon, lat, lift); return { tgt: t, pos: t.clone().add(off) }; };
const UPC2 = "#5df08a", DNC2 = "#ff6b60";

/* ---- 地球（外資、外銷用）---- */
let GLOBE = null;
async function buildGlobe() {
  const g = new THREE.Group(), R = 6371, D = Math.PI / 180, L0 = LONC * D, B0 = LATC * D;
  const E = [-Math.sin(L0), Math.cos(L0), 0], N = [-Math.sin(B0) * Math.cos(L0), -Math.sin(B0) * Math.sin(L0), Math.cos(B0)], U = [Math.cos(B0) * Math.cos(L0), Math.cos(B0) * Math.sin(L0), Math.sin(B0)];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const ecef = (lon, lat) => [Math.cos(lat * D) * Math.cos(lon * D), Math.cos(lat * D) * Math.sin(lon * D), Math.sin(lat * D)];
  const toS = (e, alt = 0) => { const r = R + alt; return V(r * dot(e, E), r * dot(e, U) - R, -r * dot(e, N)); };
  const G = (lon, lat, alt = 0) => toS(ecef(lon, lat), alt);
  const C0 = V(0, -R, 0);
  const sph = new THREE.Mesh(new THREE.SphereGeometry(R - 40, 96, 64), fm(new THREE.MeshBasicMaterial({ color: 0x03060a, depthTest: true }), 1)); sph.material.depthWrite = true; sph.material.transparent = false; sph.position.copy(C0); g.add(sph);
  // 有顏色的地球：NASA Blue Marble 白天照片，調暗一點讓上面的線和光點跳出來；邊緣再暗一些，看起來是立體的球
  // 鏡頭還在台灣上空（離地 900 公里內）時不畫，等拉到太空才淡入，避免飛行途中在地圖邊緣冒出色塊
  let GMAT = null;
  { const NX = MOBILE ? 128 : 256, NY = MOBILE ? 64 : 128, pos = [], uv = [], idx = [];
    for (let j = 0; j <= NY; j++) for (let i = 0; i <= NX; i++) { const p = G(-180 + 360 * i / NX, 90 - 180 * j / NY, -1); pos.push(p.x, p.y, p.z); uv.push(i / NX, 1 - j / NY); }
    for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) { const a = j * (NX + 1) + i, b = a + 1, c = a + NX + 1, d = c + 1; idx.push(a, c, b, b, c, d); }
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); geo.setIndex(idx);
    const TL = new THREE.TextureLoader(), sfx = MOBILE ? "_m" : "", ld = n => { const t = TL.load(`earth_${n}${sfx}.jpg?v=${ASSET_V}`); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
    const GS = { a: 0, b: 1, c: 2 }[new URLSearchParams(location.search).get("gs")] ?? (GLASS ? 1 : 0);   // 地球風格（試看用）：a 衛星統一調色、b 玻璃、c 夜晚光點
    const mat = fm(new THREE.ShaderMaterial({ depthTest: true, uniforms: { uDay: { value: ld("day") }, uNight: { value: ld("night") }, k: { value: 1 }, uC: { value: C0 }, uS: { value: GS }, uSunN: { value: V(0, 1, 0) }, uTerm: { value: 0 } },
      vertexShader: "varying vec2 vUv; varying vec3 vN; varying vec3 vW; uniform vec3 uC; void main(){ vUv = uv; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vN = normalize(w.xyz - uC); gl_Position = projectionMatrix * viewMatrix * w; }",
      fragmentShader: `uniform sampler2D uDay; uniform sampler2D uNight; uniform float k; uniform float uS; uniform vec3 uC; uniform vec3 uSunN; uniform float uTerm; varying vec2 vUv; varying vec3 vN; varying vec3 vW;
        void main(){
          vec3 d = texture2D(uDay, vUv).rgb, n = texture2D(uNight, vUv).rgb; float l = dot(d, vec3(0.299, 0.587, 0.114));
          float ocean = 0.0; { vec3 dm = texture2D(uDay, vUv, 1.5).rgb; float lm = dot(dm, vec3(0.299, 0.587, 0.114)); ocean = smoothstep(0.85, 1.0, (dm.b + 0.003) / (max(dm.r, dm.g) + 0.003)) * (1.0 - smoothstep(0.30, 0.45, lm));   /* 深海在照片裡幾乎是全黑，要算成海（之前被當成陸地，台灣看起來跟大陸連在一起） */ }   // 用稍微模糊的那層判斷海陸，海岸線不會一格一格   // 照片在線性色彩空間：海＝偏藍又暗
          vec3 v = normalize(cameraPosition - vW); float f = max(dot(v, vN), 0.0), rim = pow(1.0 - f, 2.5);
          vec3 c;
          if (uS < 0.5) { c = mix(vec3(l), d, 1.15) * 0.85; c *= mix(vec3(1.0), vec3(0.86, 0.95, 1.12), 0.6); c += vec3(0.01, 0.05, 0.13) * ocean; c *= 0.55 + 0.45 * pow(f, 0.5); }
          else if (uS < 1.5) { float lonT = vUv.x * 360.0 - 180.0, latT = vUv.y * 180.0 - 90.0; float twm = step(119.3, lonT) * step(lonT, 122.15) * step(21.85, latT) * step(latT, 25.35) * (1.0 - step(24.75, latT) * step(lonT, 120.6)); ocean = max(ocean, twm);   /* 台灣由立體地形畫，照片裡的台灣比海岸線胖一圈，換成海 */ vec3 land = mix(vec3(0.38, 0.43, 0.52), vec3(0.62, 0.67, 0.76), smoothstep(0.04, 0.45, l)); vec3 sea = mix(vec3(0.02, 0.045, 0.10), vec3(0.05, 0.10, 0.19), f);
            c = mix(land * (0.7 + 0.3 * f), sea, ocean) + vec3(0.6, 0.8, 1.0) * rim * 0.35; }
          else { vec3 land = vec3(0.09, 0.11, 0.15) + d * 0.07, sea = vec3(0.015, 0.03, 0.07); c = mix(land, sea, ocean) + pow(n, vec3(1.5)) * vec3(1.0, 0.78, 0.45) * 1.5 + vec3(0.3, 0.55, 1.0) * rim * 0.25; }
          if (uTerm > 0.0) { float nt = 1.0 - smoothstep(-0.10, 0.06, dot(vN, uSunN)); c = mix(c, c * 0.3 + pow(n, vec3(1.6)) * vec3(1.0, 0.8, 0.5) * 1.7, nt * uTerm); }   // 市場時鐘：晨昏線，夜裡看得到城市燈光
          float alt = length(cameraPosition - uC) - 6371.0; gl_FragColor = vec4(c, k * smoothstep(600.0, 1500.0, alt)); }` }), 1);
    const earth = new THREE.Mesh(geo, mat); earth.renderOrder = -1; g.add(earth); GMAT = mat; }
  const atm = new THREE.Mesh(new THREE.SphereGeometry(R * 1.02, 96, 64), fm(new THREE.ShaderMaterial({ side: THREE.BackSide, blending: THREE.AdditiveBlending, uniforms: { k: { value: 1 } },
    vertexShader: "varying vec3 vN; varying vec3 vP; void main(){ vN = normalize(normalMatrix*normal); vec4 mv = modelViewMatrix*vec4(position,1.0); vP = mv.xyz; gl_Position = projectionMatrix*mv; }",
    fragmentShader: "uniform float k; varying vec3 vN; varying vec3 vP; void main(){ float f = pow(1.0 - abs(dot(normalize(-vP), vN)), 3.0); gl_FragColor = vec4(0.25,0.7,1.0,1.0)*f*0.9*k; }" }), 1));
  atm.position.copy(C0); g.add(atm);
  const gr = []; for (let lo = -180; lo < 180; lo += 10) for (let la = -80; la < 80; la += 2) gr.push(G(lo, la, 5), G(lo, la + 2, 5));
  for (let la = -80; la <= 80; la += 10) for (let lo = -180; lo < 180; lo += 2) gr.push(G(lo, la, 5), G(lo + 2, la, 5));
  sSegs(g, gr, CY, 0.035, true);
  try {
    const land = await (await fetch("land110.json?v=" + ASSET_V)).json(), cl = [];
    for (const r of land) for (let i = 0; i < r.length - 1; i++) { if (Math.abs(r[i][0] - r[i + 1][0]) > 90) continue; cl.push(G(r[i][0], r[i][1], 10), G(r[i + 1][0], r[i + 1][1], 10)); }
    sSegs(g, cl, CY, 0.16, true);
  } catch (e) { }
  const arc = (a, b, k = 0.22, n = 96) => { const ea = V(...ecef(...a)), eb = V(...ecef(...b)), ang = ea.angleTo(eb), pts = [];
    for (let i = 0; i <= n; i++) { const u = i / n, s = Math.sin(ang); const v = ea.clone().multiplyScalar(Math.sin((1 - u) * ang) / s).add(eb.clone().multiplyScalar(Math.sin(u * ang) / s)); pts.push(toS([v.x, v.y, v.z], Math.sin(Math.PI * u) * Math.min(ang * R * k, 1500 + ang * 400))); } return pts; };
  const node = (lon, lat) => { const m = new THREE.Mesh(new THREE.SphereGeometry(16, 10, 8), fm(new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: true }), 1)); m.position.copy(G(lon, lat, 20)); g.add(m); };
  for (let i = 0; i < 3; i++) { const r = new THREE.Mesh(new THREE.RingGeometry(240 + i * 130, 248 + i * 130, 96), addM(CY, 0.8 - i * 0.25)); r.rotation.x = -Math.PI / 2; r.position.y = 3; g.add(r); }
  GLOBE = { g, G, arc, node, mat: GMAT };
  return GLOBE;
}

