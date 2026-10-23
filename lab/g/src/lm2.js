const box = (w, h, d, x, y, z, ry = 0) => { const g = new THREE.BoxGeometry(w / 1000, h, d / 1000); if (ry) g.rotateY(ry); g.translate(x / 1000, y + h / 2, z / 1000); return g; };
// 中式屋頂：四坡（廡殿／歇山簡化），屋簷四角往上翹、正脊兩端燕尾
function cnRoof(w, d, h, x, y, z, flare = 0.18, swallow = true) {
  const g = new THREE.BufferGeometry(), W = w / 2000, D = d / 2000, rw = W * (d > w ? 0.12 : 0.62), rd = D * (d > w ? 0.62 : 0.12), N = 6, pos = [], idx = [];
  // 屋簷是一圈向下彎的曲面：從屋脊（高 h）往外到屋簷（高 0），中間下凹，四角上翹
  for (let s = 0; s <= N; s++) { const u = s / N, k = u * u;   // 下凹的屋面
    for (const [cx, cz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      const ex = cx * W * (1 + 0.02), ez = cz * D * (1 + 0.02), rx = cx * rw, rz = cz * rd;
      pos.push(rx + (ex - rx) * u, h * (1 - k) + (u > 0.85 ? flare * h * (u - 0.85) / 0.15 : 0), rz + (ez - rz) * u); } }
  for (let s = 0; s < N; s++) for (let c = 0; c < 4; c++) { const a = s * 4 + c, b = s * 4 + (c + 1) % 4, a2 = a + 4, b2 = b + 4; idx.push(a, a2, b, b, a2, b2); }
  idx.push(0, 1, 2, 0, 2, 3);
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals(); g.translate(x / 1000, y, z / 1000);
  const parts = [g];
  if (swallow) { const L = (d > w ? rd : rw) * 2 + 0.0004, ridge = new THREE.BoxGeometry(d > w ? 0.0006 : L, h * 0.12, d > w ? L : 0.0006); ridge.translate(x / 1000, y + h * 1.05, z / 1000); parts.push(ridge);
    for (const s of [-1, 1]) { const t = new THREE.BoxGeometry(0.0006, h * 0.32, 0.0006); t.rotateZ(s * (d > w ? 0 : 0.7)); t.rotateX(s * (d > w ? 0.7 : 0)); t.translate(x / 1000 + (d > w ? 0 : s * L / 2), y + h * 1.2, z / 1000 + (d > w ? s * L / 2 : 0)); parts.push(t); } }
  return parts;
}
// 共用的立面著色：依世界座標畫樓層、柱、窗、陽台；晚上窗戶亮燈
function facadeMat(o) {
  const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: o.rough ?? 0.6, metalness: o.metal ?? 0.05 }); m.userData.y0 = { value: 0 };
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, { uNight: uni.uNight, uFH: { value: o.fh * BEX / 1000 }, uBW: { value: o.bw / 1000 }, uWall: { value: new THREE.Color(o.wall) }, uCol: { value: new THREE.Color(o.col) }, uWin: { value: new THREE.Color(o.win) }, uBand: { value: new THREE.Color(o.band) }, uY0: m.userData.y0, uLit: { value: o.lit ?? 0.5 } });
    m.userData.sh = sh;
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vWPf; varying vec3 vNf;").replace("#include <worldpos_vertex>", "#include <worldpos_vertex>\nvWPf = (modelMatrix * vec4(transformed, 1.0)).xyz; vNf = normalize(mat3(modelMatrix) * objectNormal);");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vWPf; varying vec3 vNf; uniform float uNight, uFH, uBW, uY0, uLit; uniform vec3 uWall, uCol, uWin, uBand; float _fwin;")
      .replace("#include <color_fragment>", `#include <color_fragment>
        { float side = 1.0 - step(0.7, abs(vNf.y));
          float hz = abs(vNf.z) > abs(vNf.x) ? vWPf.x : vWPf.z, fl = (vWPf.y - uY0) / uFH, ff = fract(fl), bf = fract(hz / uBW);
          float colm = step(0.86, bf), band = step(0.84, ff), win = (1.0 - colm) * step(0.12, ff) * step(ff, 0.8);
          vec3 c = mix(uWall, uWin, win); c = mix(c, uBand, band); c = mix(c, uCol, colm * (1.0 - band));
          float far = smoothstep(0.25, 0.6, fwidth(fl)); c = mix(c, mix(uWall, uWin, 0.4) * 0.5 + uCol * 0.3 + uBand * 0.2, far);
          diffuseColor.rgb = mix(diffuseColor.rgb, c, side) * (1.0 - 0.88 * uNight);
          _fwin = win * side * (1.0 - far) * step(1.0 - uLit, fract(sin(floor(fl) * 12.9 + floor(hz / uBW) * 78.2) * 43758.5)) + side * far * uLit * 0.15; }`)
      .replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\ntotalEmissiveRadiance += vec3(1.0, 0.82, 0.55) * _fwin * uNight * 0.38;");
  };
  m.customProgramCacheKey = () => "fac" + o.key;
  return m;
}
const lmGold = new THREE.MeshStandardMaterial({ color: 0xd9a531, roughness: 0.32, metalness: 0.35, emissive: 0xffb84a, emissiveIntensity: 0 }),
  lmRoofT = new THREE.MeshStandardMaterial({ color: 0x9a4a2a, roughness: 0.55, side: THREE.DoubleSide }), lmWhite = new THREE.MeshStandardMaterial({ color: 0xe9e6de, roughness: 0.7 }),
  lmStone = new THREE.MeshStandardMaterial({ color: 0xb7b0a2, roughness: 0.85 }), lmBrick = new THREE.MeshStandardMaterial({ color: 0x9c4b36, roughness: 0.9 });
lmGold.side = THREE.DoubleSide;
const lmRed = new THREE.MeshStandardMaterial({ color: 0xa5291d, roughness: 0.6 });
const LM_MATS = [[lmGold, 0xd9a531], [lmRoofT, 0x9a4a2a], [lmWhite, 0xe9e6de], [lmStone, 0xb7b0a2], [lmBrick, 0x9c4b36], [lmRed, 0xa5291d]];
const GH_FAC = facadeMat({ key: "gh", fh: 3.6, bw: 4.2, wall: 0xa5291d, col: 0xb8301f, win: 0x2b2a2a, band: 0xd8cfbf, lit: 0.6 });   // 圓山：紅柱、米白陽台欄杆
const K85_FAC = facadeMat({ key: "85", fh: 3.9, bw: 1.6, wall: 0x2e4552, col: 0x7d9aa6, win: 0x23384a, band: 0x5b7482, rough: 0.2, metal: 0.5, lit: 0.45 });   // 85：深藍綠玻璃、淺色直向鋁框
const PV_FAC = facadeMat({ key: "pv", fh: 4.5, bw: 2.4, wall: 0xa8301f, col: 0x7a1c12, win: 0x5a2a1c, band: 0x7a1c12, lit: 0.3 });   // 赤崁樓：紅牆紅柱、木格窗
// 高雄 85：「高」字——兩支腳到 35 樓（約 150 m），中間挖空 26 m；上面合成主體逐段收進；頂部塔冠與天線到 378 m。腳與主體正面有斜切
function build85(K) {
  const P = [], M = 1 / 1000, rect = (w, d) => [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]];
  const seg = (w, d, w1, d1, h0, h1, x = 0) => { const g = loft(rect(w, d), M, M, h0 * K, h1 * K); const a = g.attributes.position;   // 上下不同寬度
    for (let i = 0; i < a.count; i++) if (Math.abs(a.getY(i) - h1 * K) < 1e-6) { a.setX(i, a.getX(i) * w1 / w); a.setZ(i, a.getZ(i) * d1 / d); } g.computeVertexNormals(); g.translate(x * M, 0, 0); P.push([g, 0, K85_FAC]); };
  seg(30, 50, 26, 46, 0, 150, -28); seg(30, 50, 26, 46, 0, 150, 28);        // 兩支腳（往上微收）
  seg(86, 50, 80, 46, 150, 190); seg(80, 46, 70, 42, 190, 240); seg(62, 40, 54, 36, 240, 280);
  seg(46, 34, 40, 30, 280, 315); seg(34, 28, 26, 22, 315, 347);
  const sp = new THREE.CylinderGeometry(0.6 * M, 2.4 * M, 31 * K, 8); sp.translate(0, 362.5 * K, 0); P.push([sp, 0, spireMat]);
  return P;
}
// 圓山大飯店：主樓 14 層（含屋頂約 87 m）、東西長約 150 m；金黃琉璃瓦重簷屋頂；兩翼較低；正面紅柱一整排、每層米白欄杆
function buildGrandHotel(K) {
  const P = [], R = (g, m) => P.push([g, 0, m]), RS = (gs, m) => gs.forEach(g => R(g, m));
  R(box(176, 26 * K, 54, 0, -20 * K, 0), lmStone);                          // 台基（往下延伸，山坡上不會浮空）
  R(box(150, 44 * K, 28, 0, 6 * K, 0), GH_FAC);                             // 主樓 12 層
  RS(cnRoof(162, 40, 9 * K, 0, 50 * K, 0), lmGold);                         // 下簷
  R(box(118, 7 * K, 20, 0, 55 * K, 0), GH_FAC);                             // 重簷之間的樓層
  RS(cnRoof(132, 30, 12 * K, 0, 62 * K, 0, 0.25), lmGold);                  // 上簷（主脊）
  for (const s of [-1, 1]) { R(box(30, 30 * K, 40, s * 88, 6 * K, 4), GH_FAC); RS(cnRoof(40, 50, 8 * K, s * 88, 36 * K, 4, 0.2, false), lmGold); }   // 兩翼
  R(box(46, 14 * K, 14, 0, 6 * K, 21), GH_FAC); RS(cnRoof(54, 20, 5 * K, 0, 20 * K, 21, 0.2, false), lmGold);   // 正門門廊
  return P;
}
// 台中國家歌劇院（伊東豊雄）：約 110 × 60 m、高 36 m 的量體，四面都是從地面拱起的大型曲面洞口（洞裡是玻璃），牆是白灰色
const OPERA_MAT = new THREE.MeshStandardMaterial({ color: 0xe6e3dc, roughness: 0.75 });
OPERA_MAT.onBeforeCompile = sh => { sh.uniforms.uNight = uni.uNight;
  sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vLP; varying vec3 vLN;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvLP = position; vLN = normal;");
  sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vLP; varying vec3 vLN; uniform float uNight; float _hole;")
    .replace("#include <color_fragment>", `#include <color_fragment>
      { float side = 1.0 - step(0.7, abs(vLN.y)); float u = (abs(vLN.z) > 0.5 ? vLP.x / 0.055 : vLP.z / 0.03) + (vLN.x + vLN.z) * 0.37, v = vLP.y;
        float H = 0.09;                                                 // 36 m × 2.5
        float a1 = abs(fract(u * 1.6 + 0.2) - 0.5) * 2.0, a2 = abs(fract(u * 2.3 + 0.55) - 0.5) * 2.0;
        float top1 = H * (0.82 - 0.55 * a1 * a1), top2 = H * (0.55 - 0.5 * a2 * a2) + H * 0.32;   // 從地面拱起的洞，第二排從中段開
        float hole = max(step(v, top1) * step(0.12, 1.0 - a1), step(H * 0.35, v) * step(v, top2) * step(0.3, 1.0 - a2) * step(0.5, fract(u * 0.8)));
        _hole = hole * side;
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.16, 0.2, 0.24), _hole) * (1.0 - 0.85 * uNight); }`)
    .replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\ntotalEmissiveRadiance += vec3(1.0, 0.85, 0.6) * _hole * uNight * 0.75;");
};
function buildOpera(K) {
  const P = [], g = new THREE.BoxGeometry(0.11, 36 * K, 0.06); g.translate(0, 18 * K, 0); P.push([g, 0, OPERA_MAT]);
  const r = new THREE.BoxGeometry(0.114, 0.6 * K, 0.064); r.translate(0, 36 * K, 0); P.push([r, 0, lmWhite]);
  return P;
}
// 赤崁樓：紅磚台基（普羅民遮城遺構，正面有拱門）上兩座二層樓閣：前方海神廟、後方文昌閣，都是重簷歇山、燕尾脊
function buildChihkan(K) {
  const P = [], R = (g, m) => P.push([g, 0, m]), RS = (gs, m) => gs.forEach(g => R(g, m));
  R(box(62, 12 * K, 40, 0, -6 * K, 0), lmBrick);
  for (const [x, z, s] of [[-13, 6, 1], [14, -6, 0.92]]) {
    R(box(15 * s, 5 * K, 11 * s, x, 6 * K, z), PV_FAC); RS(cnRoof(22 * s, 17 * s, 2.6 * K, x, 11 * K, z, 0.3, false), lmRoofT);
    R(box(10 * s, 4 * K, 7.5 * s, x, 13.6 * K, z), PV_FAC); RS(cnRoof(16 * s, 12.5 * s, 3.2 * K, x, 17.6 * K, z, 0.35), lmRoofT);
  }
  return P;
}
