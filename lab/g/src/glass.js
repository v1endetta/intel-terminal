
/* ---- 玻璃風（B）：整套地圖一致的霧面灰藍，資料用系統色疊在上面 ----
   地形：依高度由霧灰藍到淺灰藍；海：深藍；建物：霧面白玻璃量體（屋頂最亮、牆面隨日照）；道路：淡淡的淺灰線。
   沒有衛星照片、窗戶貼圖、招牌、夜光，小車也收起來，讓畫面只剩「地形＋資料」。 */
if (GLASS) {
  const glassBuild = mat => { const ob = mat.onBeforeCompile; mat.onBeforeCompile = sh => { ob && ob(sh);
    const side = /varying float vSide;/.test(sh.fragmentShader);
    // 要在光照材質讀取 diffuseColor 之前改（lights_physical_fragment 會先把顏色存起來）
    sh.fragmentShader = sh.fragmentShader.replace("#include <lights_physical_fragment>",
      `diffuseColor.rgb = ${side ? "mix(vec3(0.84, 0.87, 0.92), vec3(0.62, 0.67, 0.75), vSide)" : "vec3(0.80, 0.84, 0.90)"} * mix(1.0, 0.42, uNight);\n#include <lights_physical_fragment>`)
      .replace("#include <lights_fragment_begin>", "totalEmissiveRadiance = vec3(0.0);\n#include <lights_fragment_begin>"); };
    const ck = mat.customProgramCacheKey && mat.customProgramCacheKey.bind(mat); mat.customProgramCacheKey = () => "glass-" + (ck ? ck() : mat.uuid); mat.needsUpdate = true; };
  glassBuild(pMat); glassBuild(bMat);
  // 道路：淺灰細線，晚上不發光
  { const ob = rMat.onBeforeCompile; rMat.onBeforeCompile = sh => { ob && ob(sh);
      sh.fragmentShader = sh.fragmentShader.replace("#include <lights_lambert_fragment>", "diffuseColor.rgb = vec3(0.80, 0.83, 0.88) * mix(1.0, 0.5, uNight);\n#include <lights_lambert_fragment>").replace("#include <lights_fragment_begin>", "totalEmissiveRadiance = vec3(0.0);\n#include <lights_fragment_begin>"); };
    rMat.customProgramCacheKey = () => "glass-road"; rMat.opacity = 0.55; rMat.transparent = true; rMat.needsUpdate = true; }
  // 河與公園：河是深藍、公園只比地面淡一點的灰綠（不跟車流的綠搶）
  { const ob = aMat.onBeforeCompile; aMat.onBeforeCompile = sh => { ob && ob(sh);
      sh.fragmentShader = sh.fragmentShader.replace("#include <lights_physical_fragment>", "diffuseColor.rgb = mix(vec3(0.44, 0.50, 0.52), vec3(0.17, 0.27, 0.42), isW) * mix(1.0, 0.45, uNight); roughnessFactor = 0.9;\n#include <lights_physical_fragment>")
        .replace("#include <lights_fragment_begin>", "totalEmissiveRadiance = vec3(0.0);\n#include <lights_fragment_begin>"); };
    aMat.customProgramCacheKey = () => "glass-area"; aMat.roughness = 0.9; aMat.needsUpdate = true; }
  // 天空與遠處霧：中性的深灰藍，不再是藍天和橘色光害
  queueMicrotask(() => {   // 天空和霧的程式在這段之後才定義，等整支程式跑完再改
  HAZE_DAY.setRGB(0.20, 0.24, 0.31); HAZE_NIGHT.setRGB(0.06, 0.08, 0.12);
  SKY.material.fragmentShader = `uniform vec3 uSun; uniform float uNight; uniform float uVis; varying vec3 vD;
    void main(){ vec3 d = normalize(vD); float h = clamp(d.y, 0.0, 1.0);
      vec3 c = mix(mix(vec3(0.24, 0.28, 0.36), vec3(0.07, 0.09, 0.13), pow(h, 0.5)), mix(vec3(0.08, 0.10, 0.15), vec3(0.015, 0.02, 0.035), pow(h, 0.5)), uNight);
      gl_FragColor = vec4(c, uVis); }`;
  SKY.material.needsUpdate = true; });
}
// 粗線：螢幕上固定幾個像素寬，遠看近看都清楚（取代 1 像素的細線）
const FATM = [];
function fatSegs(pos, col, px, op = 1) {
  const g = new LineSegmentsGeometry(); g.setPositions(pos); g.setColors(col);
  const m = new LineMaterial({ vertexColors: true, linewidth: px, transparent: true, opacity: op, depthTest: false, worldUnits: false });
  m.resolution.set(innerWidth, innerHeight); FATM.push(m);
  const l = new LineSegments2(g, m); l.renderOrder = 8; l.frustumCulled = false; return l;
}
addEventListener("resize", () => { for (let i = FATM.length - 1; i >= 0; i--) { if (!FATM[i].userData.gone) FATM[i].resolution.set(innerWidth, innerHeight); } });
