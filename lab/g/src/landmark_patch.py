# ===== 101、85 大樓的外觀：藍綠玻璃帷幕、樓層與直向窗框；晚上 101 照「一週七色」亮燈 =====
rep('const lmMat = new THREE.MeshStandardMaterial({ color: 0x6d8684, roughness: 0.3, metalness: 0.35, emissive: 0xbfe3ff, emissiveIntensity: 0 });', r'''const lmMat = new THREE.MeshStandardMaterial({ color: 0x6d8684, roughness: 0.3, metalness: 0.35, emissive: 0xbfe3ff, emissiveIntensity: 0 });
// 101 晚上的燈色：週一紅、週二橙、週三黃、週四綠、週五藍、週六靛、週日紫
const WEEK101 = [0x9a4dff, 0xff2a1a, 0xff7a14, 0xffd31a, 0x2fe05a, 0x2f7dff, 0x4b3dff];
const _wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei", weekday: "short" }));
const uWeek = { value: new THREE.Color(WEEK101[Math.max(0, _wd)]) };
lmMat.onBeforeCompile = sh => {
  sh.uniforms.uWeek = uWeek; sh.uniforms.uNight = uni.uNight; sh.uniforms.u101 = { value: new THREE.Vector2(...toXZ(121.5645, 25.034)) };
  sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vWP3;").replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvWP3 = (modelMatrix * vec4(transformed, 1.0)).xyz;");
  sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vWP3; uniform vec3 uWeek; uniform float uNight; uniform vec2 u101; float _lmMull; float _lmWin; float _lm101;")
    .replace("#include <color_fragment>", `#include <color_fragment>
      { float K = 2.5 / 1000.0; float fl = vWP3.y / (4.2 * K), ff = fract(fl);
        float hc = (vWP3.x + vWP3.z) * 1000.0 / 1.6, hf = fract(hc);
        float mull = max(step(0.88, ff), step(0.92, hf));
        float shade = diffuseColor.r / 0.42;   // 夜晚壓暗（主迴圈在調材質顏色）
        vec3 glass = vec3(0.24, 0.40, 0.42) * (0.9 + 0.1 * fract(sin(floor(fl) * 3.1) * 43758.5));
        diffuseColor.rgb = mix(glass, vec3(0.62, 0.68, 0.68), mull * 0.85) * shade;
        _lmMull = mull; _lmWin = step(0.62, fract(sin(floor(fl) * 12.3 + floor(hc) * 7.1) * 43758.5453)) * (1.0 - mull);
        _lm101 = 1.0 - step(0.35, length(vWP3.xz - u101)); }`)
    .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(0.12, 0.5, _lmMull);")
    .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
      totalEmissiveRadiance = (mix(vec3(1.0, 0.88, 0.62), uWeek, _lm101) * (0.16 + 0.75 * _lmMull) + vec3(1.0, 0.92, 0.78) * _lmWin * 0.35) * uNight;`);
};
lmMat.customProgramCacheKey = () => "lm101";''')
# 主迴圈原本把 101 晚上的顏色改成淡藍，不需要了（發光改由上面的著色器處理）
rep('lmMat.emissiveIntensity = uni.uNight.value * 0.16;', 'lmMat.emissiveIntensity = 0;')
# ===== 照真實比例重做 101 =====
# 結構（公尺，高度再乘上全城一致的垂直誇張）：裙樓商場約 60 m；1～26 樓斗狀基座往內收；27～90 樓 8 節「竹節」每節 8 層、往外張；
# 平面是四角雙層退縮的方形；基座頂四面各一個如意；91～101 樓分三階收窄；最上面尖塔到 508 m
rep('    for (const [geo, y] of parts) { const m = new THREE.Mesh(geo, lmMat); m.position.y = y; g.add(m); }',
    '    for (const [geo, y, mat] of parts) { const m = new THREE.Mesh(geo, mat || lmMat); m.position.y = y; m.castShadow = m.receiveShadow = true; g.add(m); }')
rep('    const g = new THREE.Group(), [x, z] = toXZ(lon, lat); g.position.set(x, hAt(lon, lat), z);', '    const g = new THREE.Group(), [x, z] = toXZ(lon, lat); g.position.set(x, hAt(lon, lat) * 0.42, z);')
rep('''  const t101 = [[new THREE.BoxGeometry(0.16, 60 * K, 0.1), 30 * K], [sq(0.05, 0.05, 90 * K), 45 * K]];
  for (let i = 0; i < 8; i++) { const y0 = 90 + i * 33; t101.push([sq(0.047, 0.036, 33 * K), (y0 + 16.5) * K]); }
  t101.push([sq(0.024, 0.03, 54 * K), (354 + 27) * K], [new THREE.CylinderGeometry(0.0015, 0.004, 100 * K, 6), (408 + 50) * K]);
  mk(121.5645, 25.0340, t101);''', '''  mk(121.5645, 25.0340, build101(K));''')
rep('function addLandmarks() {', r'''// 四角雙層退縮的方形平面（半寬 a，每階退 d）
function notchSq(a, d) { const q = [[a, -a + 2 * d], [a, a - 2 * d], [a - d, a - 2 * d], [a - d, a - d], [a - 2 * d, a - d], [a - 2 * d, a]], pts = [];
  for (let r = 0; r < 4; r++) { const c = Math.cos(r * Math.PI / 2), s = Math.sin(r * Math.PI / 2); for (const [x, y] of q) pts.push([x * c - y * s, x * s + y * c]); } return pts; }
// 把平面從 y0（縮放 s0）拉到 y1（縮放 s1）：側面是平的四邊形，上下封蓋
function loft(prof, s0, s1, y0, y1) {
  const n = prof.length, pos = [], idx = [], P = (k, s, y) => [prof[k][0] * s, y, prof[k][1] * s];
  for (let k = 0; k < n; k++) { const a = P(k, s0, y0), b = P((k + 1) % n, s0, y0), c = P((k + 1) % n, s1, y1), d = P(k, s1, y1), v = pos.length / 3; pos.push(...a, ...b, ...c, ...d); idx.push(v, v + 1, v + 2, v, v + 2, v + 3); }
  const tri = THREE.ShapeUtils.triangulateShape(prof.map(p => new THREE.Vector2(p[0], p[1])), []);
  for (const [y, s, flip] of [[y1, s1, false], [y0, s0, true]]) { const v = pos.length / 3; for (const p of prof) pos.push(p[0] * s, y, p[1] * s); for (const t of tri) idx.push(...(flip ? [v + t[0], v + t[1], v + t[2]] : [v + t[0], v + t[2], v + t[1]])); }
  const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals(); return g;
}
function build101(K) {
  const M = 1 / 1000, prof = notchSq(1, 0.11), parts = [];
  const seg = (a0, a1, h0, h1) => parts.push([loft(prof, a0 * M, a1 * M, h0 * K, h1 * K), 0]);
  // 裙樓商場（偏東、兩段高度）
  const mall = new THREE.BoxGeometry(0.15, 58 * K, 0.095); mall.translate(0.05, 29 * K, 0.012); parts.push([mall, 0, mallMat]);
  const mall2 = new THREE.BoxGeometry(0.06, 40 * K, 0.12); mall2.translate(0.1, 20 * K, 0.0); parts.push([mall2, 0, mallMat]);
  // 斗狀基座：地面半寬 35 m，往上收到 27 m（約 1～26 樓）
  seg(35, 27, 0, 101);
  // 8 節竹節：每節 8 層（33.6 m），下窄上寬，節與節之間一圈深色腰帶
  for (let i = 0; i < 8; i++) { const y0 = 101 + i * 33.6; seg(25.5, 31, y0, y0 + 32.4); seg(24.5, 24.5, y0 + 32.4, y0 + 33.6); }
  // 頂部 91～101 樓三階收窄，再接尖塔
  const yT = 101 + 8 * 33.6; seg(21, 21, yT, yT + 22); seg(16.5, 16.5, yT + 22, yT + 44); seg(11, 10, yT + 44, yT + 62);
  const spire = new THREE.CylinderGeometry(0.5 * M, 3.2 * M, (508 - yT - 62) * K, 8); spire.translate(0, (yT + 62 + (508 - yT - 62) / 2) * K, 0); parts.push([spire, 0, spireMat]);
  for (let k = 0; k < 5; k++) { const r = new THREE.TorusGeometry((3.4 - k * 0.5) * M, 0.35 * M, 6, 16); r.rotateX(Math.PI / 2); r.translate(0, (yT + 70 + k * 9) * K, 0); parts.push([r, 0, spireMat]); }
  // 如意：基座頂端四面各一個金色圓形
  for (let r = 0; r < 4; r++) { const g = new THREE.TorusGeometry(7 * M, 1.6 * M, 8, 28), c = Math.cos(r * Math.PI / 2), s = Math.sin(r * Math.PI / 2);
    g.rotateY(r * Math.PI / 2 + Math.PI / 2); g.translate(c * 28.5 * M, 92 * K, s * 28.5 * M); parts.push([g, 0, ruyiMat]); }
  return parts;
}
const mallMat = new THREE.MeshStandardMaterial({ color: 0x8fa3a6, roughness: 0.25, metalness: 0.45 });
const spireMat = new THREE.MeshStandardMaterial({ color: 0x9aa1a6, roughness: 0.35, metalness: 0.8 });
const ruyiMat = new THREE.MeshStandardMaterial({ color: 0xc9a24a, roughness: 0.3, metalness: 0.9, emissive: 0xffc35a, emissiveIntensity: 0 });
function addLandmarks() {''')
# 晚上：如意與尖塔微微發光、商場暗下來
rep('lmMat.emissiveIntensity = 0;', 'lmMat.emissiveIntensity = 0; ruyiMat.emissiveIntensity = uni.uNight.value * 0.9; mallMat.color.setHex(0x8fa3a6).multiplyScalar(1 - uni.uNight.value * 0.85); spireMat.emissive.setHex(0xffffff); spireMat.emissiveIntensity = uni.uNight.value * 0.25;')
# ===== 85 大樓照真實重做；再加各城市地標（圓山大飯店、台中國家歌劇院、赤崁樓） =====
# 地標位置附近的一般建物（OSM）不畫，免得跟手做模型重疊
LMX = '[[121.5262, 25.0787, 140], [120.6406, 24.1627, 100], [120.2025, 22.9975, 70]]'
rep('    ({ P, N, I, R, C, B } = bk(ci));', '    ({ P, N, I, R, C, B } = bk(ci));\n    if (' + LMX + '.some(q => Math.hypot((clo - q[0]) * c.kx, (cla - q[1]) * c.ky) < q[2])) continue;')
rep('      const lon = c.bbox[0] + x / c.kx, lat = c.bbox[1] + z / c.ky, [sx, sz] = toXZ(lon, lat);',
    '      const lon = c.bbox[0] + x / c.kx, lat = c.bbox[1] + z / c.ky, [sx, sz] = toXZ(lon, lat);\n      if (' + LMX + '.some(q => Math.hypot((lon - q[0]) * c.kx, (lat - q[1]) * c.ky) < q[2])) { mesh.setMatrixAt(i, new THREE.Matrix4().makeScale(0, 0, 0)); continue; }')
rep('''  const t85 = [[new THREE.BoxGeometry(0.03, 150 * K, 0.045), 75 * K], [new THREE.BoxGeometry(0.03, 150 * K, 0.045), 75 * K],
    [new THREE.BoxGeometry(0.095, 110 * K, 0.05), 205 * K], [new THREE.BoxGeometry(0.035, 87 * K, 0.035), (260 + 43.5) * K], [new THREE.CylinderGeometry(0.002, 0.004, 31 * K, 6), (347 + 15.5) * K]];
  const g85 = mk(120.3007, 22.6116, t85); g85.children[0].position.x = -0.03; g85.children[1].position.x = 0.03;''',
'''  mk(120.3007, 22.6116, build85(K));
  mk(121.5262, 25.0787, buildGrandHotel(K));
  mk(120.6406, 24.1627, buildOpera(K));
  mk(120.2025, 22.9975, buildChihkan(K));''')
rep('function addLandmarks() {', open(G + '/lm2.js').read() + '\nfunction addLandmarks() {')
# 晚上地標壓暗
rep('lmMat.emissiveIntensity = 0; ruyiMat.emissiveIntensity', 'lmMat.emissiveIntensity = 0; lmGold.emissiveIntensity = uni.uNight.value * 0.1; for (const [m, c] of LM_MATS) m.color.setHex(c).multiplyScalar(1 - uni.uNight.value * 0.85); ruyiMat.emissiveIntensity')
rep('    scene.add(g); return g;\n  };', '    scene.add(g); (window.__LMG = window.__LMG || []).push(g); return g;\n  };')
# 地標貼地：用跟畫面上地形一樣的三角網內插（原本取最近的高程點，山坡上會浮起來）
rep('g.position.set(x, hAt(lon, lat) * 0.42, z);', 'g.position.set(x, terrH(lon, lat) * 0.42 - 0.002, z);')
rep('function addLandmarks() {', '''function terrH(lon, lat) { const S = MOBILE ? 3 : 2, dl = (META.lon1 - META.lon0) / (META.w - 1) * S, dt = (META.lat1 - META.lat0) / (META.h - 1) * S;
  const fi = (lon - META.lon0) / dl, fj = (META.lat1 - lat) / dt, i = Math.floor(fi), j = Math.floor(fj), u = fi - i, v = fj - j, e = (ii, jj) => Math.max(DEM[(jj * S) * META.w + ii * S], 0) / 1000 * EX;
  const a = e(i, j), b = e(i + 1, j), c = e(i, j + 1), d = e(i + 1, j + 1); return u + v <= 1 ? a + u * (b - a) + v * (c - a) : d + (1 - u) * (c - d) + (1 - v) * (b - d); }
function addLandmarks() {''')

rep('    scene.add(g); (window.__LMG', '    g.children.forEach(m => { if (m.material.userData.y0) m.material.userData.y0.value = g.position.y; });\n    scene.add(g); (window.__LMG')
