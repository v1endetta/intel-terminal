# ===== 玻璃風（B）：整個地圖改成乾淨的霧面灰藍，資料在上面最清楚 =====
# 開關：網址加 ?style=glass（試看）；確定後改成預設
rep('let dimTo = 0;', '''let dimTo = 0;
const GLASS = (() => { const q = new URLSearchParams(location.search).get("style"); return q ? q === "glass" : true; })();   // 預設玻璃風；?style=photo 看舊的衛星照片風
if (GLASS) document.documentElement.classList.add("glass");''')

# 粗線（螢幕寬度固定幾個像素，遠近都看得清楚）
rep('import { OrbitControls } from "three/addons/controls/OrbitControls.js";', '''import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";''')

# 地形：依高度從霧灰藍到淺灰藍，光影交給太陽（山的立體感）；不再有衛星照片和夜光
rep('  terrain = new THREE.Mesh(g, terrainMat);', '''  if (GLASS) { const tb = terrainMat.onBeforeCompile;
    // 城市範圍：全台 OSM 建物每 100 公尺一格的覆蓋率（3d/urban.png），拉遠時看得到城市的形狀
    const UB = { uUrban: { value: null }, uHasUrban: { value: 0 }, uUrbanB: { value: new THREE.Vector4(119.25, 21.85, 122.10, 25.35) } };
    new THREE.TextureLoader().load("urban.png?v=" + ASSET_V, t => { t.anisotropy = 4; UB.uUrban.value = t; UB.uHasUrban.value = 1; });
    terrainMat.onBeforeCompile = sh => { tb(sh); Object.assign(sh.uniforms, UB);
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", "#include <common>\\nuniform sampler2D uUrban; uniform float uHasUrban; uniform vec4 uUrbanB;")
      .replace("#include <roughnessmap_fragment>", `#include <roughnessmap_fragment>
        {   // 高度分三段：平地深灰藍 → 丘陵 → 高山接近白，山的高低一眼看得出來
          float e1 = smoothstep(0.0, 1200.0, vElev), e2 = smoothstep(1000.0, 3300.0, vElev);
          vec3 g0 = mix(mix(vec3(0.29, 0.33, 0.40), vec3(0.50, 0.55, 0.63), e1), vec3(0.90, 0.92, 0.96), e2);
          if (uHasUrban > 0.5) { vec2 uu = vec2((vLL.x - uUrbanB.x) / (uUrbanB.z - uUrbanB.x), (vLL.y - uUrbanB.y) / (uUrbanB.w - uUrbanB.y));
            float ub = texture2D(uUrban, uu).r; g0 = mix(g0, vec3(0.72, 0.76, 0.83), smoothstep(0.06, 0.55, ub) * 0.8 * (1.0 - e1)); }
          diffuseColor.rgb = g0 * mix(1.0, 0.55, uNight) * mix(1.0, 0.75, uDim); }`)
      .replace("* uNight * (1.0 - smoothstep(0.25, 0.85, uClose)) * uLightK;", "* 0.0;");   // 玻璃風不畫夜光（雷達、掃描、等高線照常）
    }; terrainMat.customProgramCacheKey = () => "terrainGlass"; terrainMat.roughness = 0.75; terrainMat.metalness = 0.0; }
  terrain = new THREE.Mesh(g, terrainMat);''')
# 海：深藍，不要格線
rep('  sea.material.map.offset.set(0, 0);\n  scene.add(sea);', '''  sea.material.map.offset.set(0, 0);
  if (GLASS) { sea.material.map = null; sea.material.color.set(0x0a1424); sea.material.opacity = 1; sea.material.fog = true; sea.material.needsUpdate = true; }
  scene.add(sea);''')

# 衛星照片不載（省下大量流量），小車隱藏（看資料不需要）
rep('function orthoTick(dt) {\n  if (!ORTHO.idx) return;', 'function orthoTick(dt) {\n  if (GLASS || !ORTHO.idx) return;')

# 標籤重疊時藏起來的那個要真的消失（聚焦時的淡化樣式用了 !important，會把「藏起來」蓋掉，變成兩層字疊在一起）
rep('''    if (!L.on || L.hide) { L.el.style.opacity = 0; continue; }''', '''    if (!L.on || L.hide) { L.el.style.opacity = 0; if (L._h !== true) { L._h = true; L.el.classList.add("lhid"); } continue; }''')
rep('''    L.el.style.opacity = hit ? 0 : (L.op ?? 1);''', '''    L.el.style.opacity = hit ? 0 : (L.op ?? 1); if (L._h !== hit) { L._h = hit; L.el.classList.toggle("lhid", hit); }''')
# 玻璃風：拉近時霧淡一點（城市不會被一層灰蓋住），背景用霧的顏色（不會在地形邊緣看到黑洞）
rep('''    FOG.color.copy(_blk).lerp(_hz, k); FOG.near = 1100 + (cd * 1.6 + 1.5 - 1100) * k; FOG.far = 2800 + (cd * 7 + 14 - 2800) * k; }''', '''    FOG.color.copy(_blk).lerp(_hz, k); FOG.near = 1100 + (cd * 1.6 + 1.5 - 1100) * k; FOG.far = 2800 + (cd * 7 + 14 - 2800) * k;
    if (GLASS) { FOG.near = 1100 + (cd * 3.2 + 3 - 1100) * k; FOG.far = 2800 + (cd * 16 + 30 - 2800) * k; } }
  if (GLASS) { const kk = (globe || ST.earthOn) ? 0 : Math.min(1, Math.max(0, (close - 0.04) / 0.3)); _hz.copy(HAZE_DAY).lerp(HAZE_NIGHT, uni.uNight.value); renderer.setClearColor(_gcl.copy(_blk).lerp(_hz, kk), 1); }''')

rep('const HAZE_DAY = new THREE.Color(0.74, 0.8, 0.87),', 'const _gcl = new THREE.Color(), HAZE_DAY = new THREE.Color(0.74, 0.8, 0.87),')
