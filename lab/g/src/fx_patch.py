# ===== 渲染精修 =====
rep('import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";', '''import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";''')
rep('/* ---------- 啟動 ---------- */', '''/* ---------- 發光後製：亮的東西（掃描線、燈光、資料線、窗戶）暈開；手機用半解析度 ---------- */
const FX = { on: new URLSearchParams(location.search).get("fx") !== "0" };
let composer = null, bloom = null;
try {
  composer = new EffectComposer(renderer); composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(innerWidth, innerHeight);
  composer.addPass(new RenderPass(scene, camera));
  bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth * (MOBILE ? 0.5 : 1), innerHeight * (MOBILE ? 0.5 : 1)), 0.5, 0.55, 0.82);
  composer.addPass(bloom); composer.addPass(new OutputPass());
} catch (e) { FX.on = false; }
addEventListener("resize", () => { if (composer) { composer.setSize(innerWidth, innerHeight); bloom.resolution.set(innerWidth * (MOBILE ? 0.5 : 1), innerHeight * (MOBILE ? 0.5 : 1)); } });
function present() {
  if (FX.on && composer) {
    const nt = uni.uNight.value; bloom.threshold = nt ? 0.78 : 0.99; bloom.strength = (nt ? 0.85 : 0.08) + 0.22 * uni.uScanOn.value + 0.25 * uni.uClose.value * nt;
    composer.render();
  } else renderer.render(scene, camera);
}
/* ---------- 啟動 ---------- */''')
rep('  renderer.render(scene, camera); placeLabels();', '  present(); placeLabels();')
rep('const pMat = new THREE.MeshStandardMaterial({ color: 0xdfddd7, roughness: 0.85, metalness: 0,', 'const pMat = new THREE.MeshStandardMaterial({ color: 0xdfddd7, roughness: 0.72, metalness: 0.04, envMapIntensity: 0.7,')
rep(r'"#include <color_fragment>\nfloat hh = vY - vInfo.x;\ndiffuseColor.rgb *= mix(0.55, 1.0, clamp(hh * 90.0 + (1.0 - vSide), 0.0, 1.0));\ndiffuseColor.rgb *= mix(1.0, 0.035, uNight);"',
    r'"#include <color_fragment>\nfloat hh = vY - vInfo.x;\nfloat flc = hh / (3.3 / 1000.0 * 2.5);\nfloat gband = step(0.35, fract(flc)) * step(fract(flc), 0.8) * step(0.8, flc) * vSide;\ndiffuseColor.rgb *= mix(0.42, 1.0, clamp(hh * 60.0 + (1.0 - vSide), 0.0, 1.0));\ndiffuseColor.rgb *= 1.0 - gband * 0.2;\ndiffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.84, 0.89, 0.97), clamp(hh * 3.0, 0.0, 0.4) * vSide);\ndiffuseColor.rgb *= 1.0 + (1.0 - vSide) * 0.1;\ndiffuseColor.rgb *= mix(1.0, 0.035, uNight);"')
import os
if not os.environ.get('NOAMAT'): rep('''aMat.onBeforeCompile = sh => {
  sh.uniforms.uNight = uni.uNight;
  sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\\nuniform float uNight;")
    .replace("#include <color_fragment>", "#include <color_fragment>\\ndiffuseColor.rgb *= mix(1.0, 0.12, uNight);");
};''', '''aMat.onBeforeCompile = sh => {   // 水面：白天反天空，晚上倒映城市燈光的碎光
  sh.uniforms.uNight = uni.uNight; sh.uniforms.uTime = uni.uTime;
  sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\\nvarying vec3 vWP;").replace("#include <project_vertex>", "#include <project_vertex>\\nvWP = (modelMatrix * vec4(transformed, 1.0)).xyz;");
  sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\\nuniform float uNight; uniform float uTime; varying vec3 vWP;")
    .replace("#include <color_fragment>", "#include <color_fragment>\\nfloat isW = step(diffuseColor.r + 0.05, diffuseColor.b);\\ndiffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.42, 0.52, 0.62), isW * 0.7);\\ndiffuseColor.rgb *= mix(1.0, 0.12, uNight);")
    .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\\nroughnessFactor = mix(roughnessFactor, 0.25, step(diffuseColor.r + 0.03, diffuseColor.b));")
    .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
      {
        vec3 vd = normalize(vViewPosition);
        float fr = pow(1.0 - clamp(abs(vd.z), 0.0, 1.0), 2.0);
        float rip = sin(vWP.x * 900.0 + uTime * 1.4) * sin(vWP.z * 760.0 - uTime * 1.1);
        float glint = pow(max(rip, 0.0), 10.0);
        totalEmissiveRadiance += isW * ((1.0 - uNight) * (vec3(0.1, 0.16, 0.24) + vec3(0.5, 0.62, 0.78) * fr) * 0.6 + uNight * vec3(1.0, 0.72, 0.42) * glint * 0.9);
      }`);
};''')
# 河床在海平面以下會被當成海挖掉，市區看起來有黑洞：拉近時放寬到 -4 公尺，低窪處畫成水面
rep('if (vElev < 0.0) discard;', 'if (vElev < mix(0.0, -4.0, step(0.3, uClose))) discard;')
rep('diffuseColor.rgb *= mix(vec3(1.0), vec3(0.16, 0.19, 0.27), uNight);")', 'diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.2, 0.27, 0.35), (1.0 - smoothstep(0.0, 2.0, vElev)) * 0.85 * uClose);\\ndiffuseColor.rgb *= mix(vec3(1.0), vec3(0.16, 0.19, 0.27), uNight);")')
# 綠地與水面改用 Standard 材質（Lambert 在部分顯示卡上會算成全黑），水面粗糙度低一點、會反光
rep('const aMat = new THREE.MeshLambertMaterial({ side: THREE.DoubleSide, vertexColors: true,', 'const aMat = new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0, envMapIntensity: 0.8, side: THREE.DoubleSide, vertexColors: true,')
if not os.environ.get('NOAMAT'): rep('totalEmissiveRadiance += isW * ((1.0 - uNight)', 'totalEmissiveRadiance += isW * ((1.0 - uNight)')
# 白天市區：地面壓暗，白模建築才跳得出來；公園更綠
rep('diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.24, 0.25, 0.27) + diffuseColor.rgb * 0.18, uClose * 0.8);', 'diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.13, 0.14, 0.16) + diffuseColor.rgb * 0.12, uClose * 0.85);')
if not os.environ.get('NOAMAT'): rep('diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.42, 0.52, 0.62), isW * 0.7);', 'diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.42, 0.52, 0.62), isW * 0.7);\\ndiffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.3, 0.46, 0.28), (1.0 - isW) * 0.6);')
# 建物風格（測試用 ?bs=0 白模、1 寫實、2 暗玻璃科技）
rep('const rMat = new THREE.MeshLambertMaterial(', '''const BSTYLE = +(new URLSearchParams(location.search).get("bs") || 0);
{ const _pob = pMat.onBeforeCompile; pMat.onBeforeCompile = sh => { _pob(sh); sh.uniforms.uBS = { value: BSTYLE }; sh.uniforms.uTime = uni.uTime;
  sh.vertexShader = sh.vertexShader.replace("varying float vSide;", "varying float vSide; varying float vH;").replace("vSide = 1.0 - step(0.9, abs(normal.y));", "vSide = 1.0 - step(0.9, abs(normal.y)); vH = (position.x * abs(normal.z) + position.z * abs(normal.x));");
  sh.fragmentShader = sh.fragmentShader.replace("uniform float uNight;", "uniform float uNight; uniform float uBS; uniform float uTime; varying float vH;")
    .replace("diffuseColor.rgb *= mix(1.0, 0.035, uNight);", `
      float col = step(0.45, fract(vH * 1000.0 / 3.2));   // 每 3.2 公尺一扇窗
      float rnd = vInfo.y; float tall = clamp(hh * 8.0, 0.0, 1.0);
      if (uBS > 0.5 && uBS < 1.5) {   // 寫實：混凝土、磁磚、灰色、高樓玻璃帷幕
        vec3 c1 = rnd < 0.3 ? vec3(0.62, 0.61, 0.6) : rnd < 0.55 ? vec3(0.84, 0.79, 0.69) : rnd < 0.75 ? vec3(0.7, 0.55, 0.46) : rnd < 0.9 ? vec3(0.76, 0.75, 0.72) : vec3(0.55, 0.58, 0.6);   // 灰泥、米色磁磚、紅磚、白磁磚、深灰
        vec3 glass = vec3(0.3, 0.42, 0.54);
        vec3 fac = mix(c1, glass, tall * step(0.35, rnd));
        float win = gband * col;
        fac = mix(fac, vec3(0.16, 0.2, 0.25), win * 0.7);
        vec3 roof = mix(vec3(0.52, 0.52, 0.5), vec3(0.4, 0.46, 0.44), step(0.7, rnd));
        diffuseColor.rgb = mix(roof, fac, vSide) * mix(0.42, 1.0, clamp(hh * 60.0 + (1.0 - vSide), 0.0, 1.0));
      } else if (uBS > 1.5) {   // 暗玻璃科技：深色玻璃塊，樓層線與屋頂邊緣發青光
        diffuseColor.rgb = mix(vec3(0.07, 0.085, 0.11), vec3(0.11, 0.13, 0.16), vSide) * (1.0 + gband * col * 0.6);
      }
      diffuseColor.rgb *= mix(1.0, 0.035, uNight);`)
    .replace("totalEmissiveRadiance *= vSide * win * lit * (0.45 + 0.75 * vInfo.y) * uNight * 1.25;", `totalEmissiveRadiance *= vSide * win * lit * (0.45 + 0.75 * vInfo.y) * uNight * 1.25;
      if (uBS > 1.5) { float fl10 = smoothstep(0.44, 0.5, abs(fract(fl / 10.0) - 0.5)) * vSide;
        totalEmissiveRadiance += vec3(0.3, 0.8, 1.0) * (fl10 * 0.35 * (0.4 + tall) + (1.0 - vSide) * 0.05); }`);
}; }
const rMat = new THREE.MeshLambertMaterial(''')

# 手機的方塊建物也套同一套風格
rep('const rMat = new THREE.MeshLambertMaterial(', '''{ const _bob = bMat.onBeforeCompile; bMat.onBeforeCompile = sh => { _bob(sh); sh.uniforms.uBS = { value: BSTYLE };
  sh.fragmentShader = sh.fragmentShader.replace("uniform float uNight;", "uniform float uNight; uniform float uBS;")
    .replace("diffuseColor.rgb *= mix(1.0, 0.035, uNight);", `
      float bh = vY * vH, bfl = bh / (3.3 / 1000.0 * 2.5), bband = step(0.35, fract(bfl)) * step(fract(bfl), 0.8) * vSide, btall = clamp(vH * 8.0, 0.0, 1.0);
      if (uBS > 0.5 && uBS < 1.5) {
        vec3 c1 = vRand < 0.3 ? vec3(0.62, 0.61, 0.6) : vRand < 0.55 ? vec3(0.84, 0.79, 0.69) : vRand < 0.75 ? vec3(0.7, 0.55, 0.46) : vRand < 0.9 ? vec3(0.76, 0.75, 0.72) : vec3(0.55, 0.58, 0.6);
        vec3 fac = mix(c1, vec3(0.3, 0.42, 0.54), btall * step(0.35, vRand)); fac = mix(fac, vec3(0.16, 0.2, 0.25), bband * 0.55);
        diffuseColor.rgb = mix(vec3(0.5, 0.5, 0.49), fac, vSide) * mix(0.45, 1.0, smoothstep(0.0, 0.45, bh * 40.0 + (1.0 - vSide)));
      } else if (uBS > 1.5) {
        diffuseColor.rgb = mix(vec3(0.07, 0.085, 0.11), vec3(0.11, 0.13, 0.16), vSide) * (1.0 + bband * 0.5);
      }
      diffuseColor.rgb *= mix(1.0, 0.035, uNight);`)
    .replace("totalEmissiveRadiance *= vSide * win * lit * (0.45 + 0.75 * vRand) * uNight * 1.25;", `totalEmissiveRadiance *= vSide * win * lit * (0.45 + 0.75 * vRand) * uNight * 1.25;
      if (uBS > 1.5) totalEmissiveRadiance += vec3(0.3, 0.8, 1.0) * (smoothstep(0.44, 0.5, abs(fract(fl / 10.0) - 0.5)) * vSide * 0.35 * (0.4 + clamp(vH * 8.0, 0.0, 1.0)) + (1.0 - vSide) * 0.05);`);
}; }
const rMat = new THREE.MeshLambertMaterial(''')
