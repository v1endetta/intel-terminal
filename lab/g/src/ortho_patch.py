# ===== 真實航照：市區地面與屋頂（預先烘焙在 3d/ortho/） =====
# 1) 背景執行緒：建物依所在航照塊分組，屋頂頂點帶航照座標，外牆帶「建物中心」的航照座標（取整棟主色）
rep('  const { key, c, base, T, BEX } = m;', '''  const { key, c, base, T, BEX } = m; const OC = m.chunks || [];
  const mY = la => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
  const ochunk = (lo, la) => { for (let i = 0; i < OC.length; i++) { const q = OC[i]; if (lo >= q.w && lo < q.e && la <= q.n && la > q.s) return i; } return -1; };
  const ouv = (q, lo, la) => [(lo - q.w) / (q.e - q.w), (mY(la) - mY(q.s)) / (mY(q.n) - mY(q.s))];''')
rep('  const P = [], N = [], I = [];', '''  const BK = new Map(); let P, N, I, R, C;
  const bk = i => { let b = BK.get(i); if (!b) { b = { P: [], N: [], I: [], R: [], C: [] }; BK.set(i, b); } return b; };''')
rep('    for (let k = 0; k < n; k++) { pts.push(toS(cx + dv.getInt16(o, true) / 4, cz + dv.getInt16(o + 2, true) / 4)); o += 4; }',
    '''    const raw = [];
    for (let k = 0; k < n; k++) { const lx = cx + dv.getInt16(o, true) / 4, lz = cz + dv.getInt16(o + 2, true) / 4; raw.push([c.bbox[0] + lx / c.kx, c.bbox[1] + lz / c.ky]); pts.push(toS(lx, lz)); o += 4; }
    const clo = c.bbox[0] + cx / c.kx, cla = c.bbox[1] + cz / c.ky, ci = ochunk(clo, cla), oq = OC[ci], cuv = oq ? ouv(oq, clo, cla) : [0, 0];
    ({ P, N, I, R, C } = bk(ci));''')
rep('      for (let q = 0; q < 6; q++) { N.push(nx, 0, nz); I.push(gy, rnd); }', '      for (let q = 0; q < 6; q++) { N.push(nx, 0, nz); I.push(gy, rnd); R.push(0, 0); C.push(cuv[0], cuv[1]); }')
rep('    for (const t of tri) for (const ix of t) { P.push(pts[ix][0], y1, pts[ix][1]); N.push(0, 1, 0); I.push(gy, rnd); }',
    '    for (const t of tri) for (const ix of t) { P.push(pts[ix][0], y1, pts[ix][1]); N.push(0, 1, 0); I.push(gy, rnd); const u = oq ? ouv(oq, raw[ix][0], raw[ix][1]) : [0, 0]; R.push(u[0], u[1]); C.push(cuv[0], cuv[1]); }')
rep('  const out = { key, nb, P: f(P), N: f(N), I: f(I), RP: f(RP), RC: f(RC), AP: f(AP), AK: f(AK) };',
    '''  const keys = [...BK.keys()].sort((a, b) => a - b), G = []; let nvAll = 0;
  for (const k of keys) nvAll += BK.get(k).P.length / 3;
  const PP = new Float32Array(nvAll * 3), NN = new Float32Array(nvAll * 3), II = new Float32Array(nvAll * 2), RR = new Float32Array(nvAll * 2), CC = new Float32Array(nvAll * 2); let v0 = 0;
  for (const k of keys) { const b = BK.get(k), nv = b.P.length / 3; G.push([v0, nv, k]);
    PP.set(b.P, v0 * 3); NN.set(b.N, v0 * 3); II.set(b.I, v0 * 2); RR.set(b.R, v0 * 2); CC.set(b.C, v0 * 2); v0 += nv; }
  const out = { key, nb, G, P: PP, N: NN, I: II, RU: RR, CU: CC, RP: f(RP), RC: f(RC), AP: f(AP), AK: f(AK) };''')
rep('  postMessage(out, [out.P.buffer, out.N.buffer, out.I.buffer, out.RP.buffer,', '  postMessage(out, [out.P.buffer, out.N.buffer, out.I.buffer, out.RU.buffer, out.CU.buffer, out.RP.buffer,')
rep('  cityWorker().postMessage({ key, c, base: document.baseURI, T, BEX });', '  cityWorker().postMessage({ key, c, base: document.baseURI, T, BEX, chunks: (ORTHO.idx && ORTHO.idx.cities[key]) || [] });')

# 1b) 建物、道路的地面高度改成跟地形網格一模一樣（地形是每 S 格一點的三角網，不是逐點取樣），照片和建物才會貼齊
rep('  const g = (x, z) => hAt(c.bbox[0] + x / c.kx, c.bbox[1] + z / c.ky);', """  const tH = (lon, lat) => { const S = DM.S || 2, dl = (DM.lon1 - DM.lon0) / (DM.w - 1) * S, dt = (DM.lat1 - DM.lat0) / (DM.h - 1) * S;
    const fi = (lon - DM.lon0) / dl, fj = (DM.lat1 - lat) / dt, i = Math.floor(fi), j = Math.floor(fj), u = fi - i, v = fj - j, W = Math.floor((DM.w - 1) / S) + 1, H = Math.floor((DM.h - 1) / S) + 1;
    if (i < 0 || j < 0 || i + 1 >= W || j + 1 >= H) return 0;
    const e = (ii, jj) => Math.max(DEM[(jj * S) * DM.w + ii * S], 0) / 1000 * DM.ex * 0.42;
    const a = e(i, j), b = e(i + 1, j), c2 = e(i, j + 1), d = e(i + 1, j + 1);
    return u + v <= 1 ? a + u * (b - a) + v * (c2 - a) : d + (1 - u) * (c2 - d) + (1 - v) * (b - d); };
  const g = (x, z) => tH(c.bbox[0] + x / c.kx, c.bbox[1] + z / c.ky);""")
rep('WORKER.postMessage({ dem: DEM.slice(), meta: { ...META, ex: EX } });', 'WORKER.postMessage({ dem: DEM.slice(), meta: { ...META, ex: EX, S: MOBILE ? 3 : 2 } });')

# 2) 主執行緒：每個航照塊一個材質（屋頂直接用照片、外牆取整棟主色加上樓層玻璃帶）
rep('  grp.add(new THREE.Mesh(bg, pMat));', '''  if (d.RU) { bg.setAttribute("aRUV", new THREE.BufferAttribute(d.RU, 2)); bg.setAttribute("aCUV", new THREE.BufferAttribute(d.CU, 2)); }
  if (d.G && d.G.length) {
    const mats = [];
    for (const [start, count, ci] of d.G) { bg.addGroup(start, count, mats.length); mats.push(ci >= 0 ? orthoBMat(d.key, ci) : pMat); }
    grp.add(new THREE.Mesh(bg, mats));
  } else grp.add(new THREE.Mesh(bg, pMat));''')
rep('const rMat = new THREE.MeshLambertMaterial(', r'''const ORTHO = { idx: null, lo: new Map(), hi: new Map(), u: new Map(), patches: new Map() };
fetch("ortho/index.json?v=" + ASSET_V).then(r => r.ok ? r.json() : null).then(j => { ORTHO.idx = j; }).catch(() => {});
const OTEX_LOADER = new THREE.TextureLoader();
function _otex(url) { const t = OTEX_LOADER.load(url); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy()); return t; }
// 每塊照片兩種解析度：2048（常駐，屋頂和手機用）、4096（電腦版只給鏡頭附近幾塊，離開就釋放）
function orthoQ(key) { const [tier, i] = key.split(":"); return tier === "base" ? ORTHO.idx.base.chunks[+i] : ORTHO.idx.cities[tier][+i]; }
function orthoDir(key) { const [tier] = key.split(":"); return tier; }
function orthoLo(key) { if (!ORTHO.lo.has(key)) ORTHO.lo.set(key, _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}_m.jpg?v=${ASSET_V}`)); return ORTHO.lo.get(key); }
function orthoUni(key) { if (!ORTHO.u.has(key)) ORTHO.u.set(key, { value: ORTHO.hi.get(key) || orthoLo(key) }); return ORTHO.u.get(key); }
function orthoSetHi(key, on) {
  if (on && !ORTHO.hi.has(key)) { const t = _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}.jpg?v=${ASSET_V}`); ORTHO.hi.set(key, t); orthoUni(key).value = t; const p = ORTHO.patches.get(key); if (p) p.material.map = t; }
  if (!on && ORTHO.hi.has(key)) { const t = ORTHO.hi.get(key); ORTHO.hi.delete(key); orthoUni(key).value = orthoLo(key); const p = ORTHO.patches.get(key); if (p) p.material.map = orthoLo(key); t.dispose(); }
}
function orthoBMat(city, ci) {
  const u = orthoUni(city + ":" + ci), m = pMat.clone(), base = pMat.onBeforeCompile;
  m.onBeforeCompile = sh => { base(sh); sh.uniforms.uOrtho = u;
    sh.vertexShader = sh.vertexShader.replace("varying float vSide;", "varying float vSide; attribute vec2 aRUV; attribute vec2 aCUV; varying vec2 vRUV; varying vec2 vCUV;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvRUV = aRUV; vCUV = aCUV;");
    sh.fragmentShader = sh.fragmentShader.replace("uniform float uNight;", "uniform float uNight; uniform sampler2D uOrtho; varying vec2 vRUV; varying vec2 vCUV;")
      .replace("diffuseColor.rgb *= mix(1.0, 0.035, uNight);", `
        { vec3 roofC = texture2D(uOrtho, vRUV).rgb;
          vec3 bodyC = texture2D(uOrtho, vCUV, 3.0).rgb;   // 整棟的主色：取建物中心附近、稍微糊掉的屋頂色
          float lum2 = dot(bodyC, vec3(0.3, 0.59, 0.11));
          vec3 fac = mix(vec3(lum2), bodyC, 0.5) * 0.9 + vec3(0.07, 0.07, 0.075);
          float hh2 = vY - vInfo.x, fl2 = hh2 / (3.3 / 1000.0 * 2.5), band2 = step(0.35, fract(fl2)) * step(fract(fl2), 0.8) * step(0.8, fl2);
          fac = mix(fac, vec3(0.32, 0.4, 0.46), clamp(hh2 * 4.0, 0.0, 1.0) * 0.55 * step(0.4, vInfo.y));   // 高樓多半是玻璃帷幕
          fac = mix(fac, fac * 0.62 + vec3(0.02, 0.035, 0.05), band2 * 0.5);
          fac *= mix(0.6, 1.0, clamp(hh2 * 60.0, 0.0, 1.0)) * (0.72 + 0.3 * vInfo.y);
          diffuseColor.rgb = mix(roofC * 1.08, fac, vSide); }
        diffuseColor.rgb *= mix(1.0, 0.035, uNight);`); };
  m.customProgramCacheKey = () => "orthoB";
  return m;
}
// 地面航照：貼著地形的網格，跟地形一樣拉近時壓扁；白天用照片，晚上壓暗交給路燈和窗戶。市區那層蓋在全島那層上面
function orthoGroundMat(tex, city) {   // 晚上：照片壓成冷色月光（看得到街廓、河、山），再疊上跟地形一樣的夜光
  const m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.96, metalness: 0, emissive: 0xffffff, transparent: true, opacity: 0, depthWrite: true, polygonOffset: true, polygonOffsetFactor: city ? -3 : -2, polygonOffsetUnits: city ? -12 : -6 });
  m.onBeforeCompile = sh => { for (const k of ["uClose", "uNight", "uLights", "uHasLights", "uLightK"]) sh.uniforms[k] = uni[k];
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nuniform float uClose; attribute vec2 aTUV; attribute vec2 aLL; varying vec2 vTUV; varying vec2 vLL2;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\ntransformed.y *= mix(1.0, 0.42, uClose); vTUV = aTUV; vLL2 = aLL;");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nuniform float uNight; uniform float uClose; uniform sampler2D uLights; uniform float uHasLights; uniform float uLightK; varying vec2 vTUV; varying vec2 vLL2; vec3 _photo;")
      .replace("#include <color_fragment>", "#include <color_fragment>\nif (vMapUv.x < 0.0 || vMapUv.x > 1.0 || vMapUv.y < 0.0 || vMapUv.y > 1.0) discard;\n_photo = diffuseColor.rgb;\ndiffuseColor.rgb *= 1.0 - 0.94 * uNight;")
      .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
        {
          float lum = dot(_photo, vec3(0.3, 0.59, 0.11));
          float sat = max(_photo.r, max(_photo.g, _photo.b)) - min(_photo.r, min(_photo.g, _photo.b));
          vec3 moon = vec3(0.07, 0.095, 0.15) * pow(lum, 1.15) * 1.6;                    // 月光底：冷色、保留明暗
          float urban = smoothstep(0.38, 0.68, lum) * (1.0 - clamp(sat * 3.0, 0.0, 1.0)); // 水泥、柏油：城市的輪廓
          vec3 wash = vec3(1.0, 0.62, 0.3) * urban * mix(0.0, 0.09, smoothstep(0.6, 1.0, uClose));            // 路燈打在地面的暖光
          float dens = uHasLights > 0.5 ? texture2D(uLights, vTUV).r : 0.0;
          float I = clamp(pow(dens, 0.9), 0.0, 1.0);
          vec2 cell = floor(vLL2 * 1200.0);
          float n = fract(sin(dot(cell, vec2(12.9898, 78.233))) * 43758.5453);
          float spark = step(1.0 - I * 0.9, n);
          vec3 lc = mix(vec3(1.0, 0.5, 0.16), vec3(1.0, 0.9, 0.74), I);
          vec3 lights = lc * (spark * (0.12 + 1.9 * I) + pow(I, 2.0) * 1.1) * (1.0 - smoothstep(0.1, 0.55, uClose)) * uLightK;
          totalEmissiveRadiance = (moon + wash * (0.4 + I) + lights) * uNight;
        }`); };
  m.customProgramCacheKey = () => "orthoG2";
  return m;
}
const _mY = la => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
function orthoPatch(key) {   // 直接沿用地形網格的點和三角形，所以跟地形完全貼合；照片範圍外的部分在著色器裡丟掉
  const q = orthoQ(key), city = !key.startsWith("base:"), S = MOBILE ? 3 : 2, dl = (META.lon1 - META.lon0) / (META.w - 1) * S, dt = (META.lat1 - META.lat0) / (META.h - 1) * S;
  const i0 = Math.max(0, Math.floor((q.w - META.lon0) / dl)), i1 = Math.min(Math.floor((META.w - 1) / S), Math.ceil((q.e - META.lon0) / dl)), j0 = Math.max(0, Math.floor((META.lat1 - q.n) / dt)), j1 = Math.min(Math.floor((META.h - 1) / S), Math.ceil((META.lat1 - q.s) / dt));
  const W = i1 - i0 + 1, pos = [], uv = [], el = [], idx = [], tuv = [], ll = [], my0 = _mY(q.s), my1 = _mY(q.n);
  for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
    const lon = META.lon0 + i * dl, lat = META.lat1 - j * dt, e = DEM[(j * S) * META.w + i * S], [x, z] = toXZ(lon, lat);
    pos.push(x, Math.max(e, 0) / 1000 * EX, z); uv.push((lon - q.w) / (q.e - q.w), (_mY(lat) - my0) / (my1 - my0)); el.push(e);
    tuv.push((lon - META.lon0) / (META.lon1 - META.lon0), (lat - META.lat0) / (META.lat1 - META.lat0)); ll.push(lon, lat);
  }
  for (let j = 0; j < j1 - j0; j++) for (let i = 0; i < W - 1; i++) { const a = j * W + i, b = a + 1, c2 = a + W, d2 = c2 + 1;   // 跟地形一樣：全是海的三角形不畫
    if (el[a] > 0 || el[b] > 0 || el[c2] > 0) idx.push(a, c2, b); if (el[b] > 0 || el[c2] > 0 || el[d2] > 0) idx.push(b, c2, d2); }
  const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); g.setAttribute("aTUV", new THREE.Float32BufferAttribute(tuv, 2)); g.setAttribute("aLL", new THREE.Float32BufferAttribute(ll, 2)); g.setIndex(idx); g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, orthoGroundMat(ORTHO.hi.get(key) || orthoLo(key), city)); mesh.renderOrder = city ? 2 : 1; mesh.userData.city = city; scene.add(mesh); return mesh;
}
function orthoDrop(key) {   // 離開太遠：拆掉地面網格，全島那層連照片一起釋放（市區照片屋頂還在用就留著）
  const m = ORTHO.patches.get(key); if (m) { scene.remove(m); m.geometry.dispose(); m.material.dispose(); ORTHO.patches.delete(key); }
  orthoSetHi(key, false);
  if (key.startsWith("base:") && ORTHO.lo.has(key)) { ORTHO.lo.get(key).dispose(); ORTHO.lo.delete(key); ORTHO.u.delete(key); }
}
let _otT = 0, _baseOp = 0;
function orthoTick(dt) {
  if (!ORTHO.idx) return;
  const close = uni.uClose.value, t = controls.target, lon = t.x / KX + LONC, lat = -t.z / KY + LATC, cd = camera.position.distanceTo(t);
  const dist = q => Math.hypot(((q.w + q.e) / 2 - lon) * KX, ((q.s + q.n) / 2 - lat) * KY);
  _otT -= dt;
  if (_otT <= 0) { _otT = 0.5;
    const want = new Set(), hi = new Set();
    // 全島底圖：拉到縣市尺度才出現，只載鏡頭附近幾塊
    if (ORTHO.idx.base && cd < 240) {
      ORTHO.idx.base.chunks.map((q, i) => ({ k: "base:" + i, d: dist(q) })).filter(o => o.d < Math.max(45, cd * 0.7)).sort((a, b) => a.d - b.d).slice(0, MOBILE ? 4 : 9).forEach(o => want.add(o.k));
    }
    // 市區：z16，鏡頭最近的 4 塊在電腦上換成 4096 版
    if (close > 0.05) {
      let city = null; for (const k in ORTHO.idx.cities) { const b = (BMETA && BMETA.cities[k] && BMETA.cities[k].bbox) || (() => { const c = ORTHO.idx.cities[k]; return c.length ? [Math.min(...c.map(q => q.w)), Math.min(...c.map(q => q.s)), Math.max(...c.map(q => q.e)), Math.max(...c.map(q => q.n))] : null; })(); if (b && lon > b[0] - 0.08 && lon < b[2] + 0.08 && lat > b[1] - 0.08 && lat < b[3] + 0.08) city = k; }
      if (city) ORTHO.idx.cities[city].map((q, i) => ({ k: city + ":" + i, d: dist(q) })).filter(o => o.d < 14).sort((a, b) => a.d - b.d).slice(0, MOBILE ? 4 : 9)
        .forEach((o, n) => { want.add(o.k); if (!MOBILE && n < 4 && cd < 40) hi.add(o.k); });
    }
    for (const k of want) if (!ORTHO.patches.has(k)) ORTHO.patches.set(k, orthoPatch(k));
    for (const k of [...ORTHO.patches.keys()]) if (!want.has(k)) orthoDrop(k);
    for (const k of [...ORTHO.hi.keys()]) if (!hi.has(k)) orthoSetHi(k, false);
    for (const k of hi) orthoSetHi(k, true);
  }
  const op = Math.min(1, Math.max(0, (close - 0.12) / 0.35));
  _baseOp = Math.min(1, Math.max(0, (240 - cd) / 80));
  for (const m of ORTHO.patches.values()) { const o = m.userData.city ? op : _baseOp; m.material.opacity = o; m.visible = o > 0.01; }
  const day = uni.uNight.value < 0.5, has = [...ORTHO.patches.values()].some(m => m.userData.city) && op > 0.5;
  rMat.visible = !(day && has); aMat.visible = !(day && has);   // 白天照片裡已經有路和公園
}
const rMat = new THREE.MeshLambertMaterial(''')
rep('  lodTick(dt);', '  lodTick(dt); orthoTick(dt);')
rep('<div id="credit">地形 Mapzen Terrarium · 衛星與夜光 NASA · 行政區 內政部</div>', '<div id="credit">地形 Mapzen Terrarium · 衛星與夜光 NASA · 航照 內政部國土測繪中心 · 行政區 內政部 · 建物 © OpenStreetMap</div>')
# 101、85 用藍綠玻璃色，不再是白模
rep('const lmMat = new THREE.MeshStandardMaterial({ color: 0xf6f5f1, roughness: 0.6, metalness: 0.1,', 'const lmMat = new THREE.MeshStandardMaterial({ color: 0x6d8684, roughness: 0.3, metalness: 0.35,')
rep('lmMat.color.setScalar(1 - uni.uNight.value * 0.88);', 'lmMat.color.setRGB(0.42, 0.52, 0.51).multiplyScalar(1 - uni.uNight.value * 0.88); lmMat.envMapIntensity = 1 - 0.85 * uni.uNight.value;')
# 沒有航照屋頂的建物（手機版方塊、航照範圍外）預設用寫實配色，不再是白模
rep('const BSTYLE = +(new URLSearchParams(location.search).get("bs") || 0);', 'const BSTYLE = +(new URLSearchParams(location.search).get("bs") ?? 1);')
