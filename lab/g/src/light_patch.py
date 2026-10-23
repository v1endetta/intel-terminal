# ===== 遊戲感光影：太陽陰影（電腦版）、天空、遠處霧氣 =====
# 太陽方向記下來（陰影要跟著鏡頭移動，但方向不變）
rep('  sun.position.set(Math.sin(az) * Math.cos(e) * 1000, Math.sin(e) * 1000, -Math.cos(az) * Math.cos(e) * 1000);',
    '  sun.position.set(Math.sin(az) * Math.cos(e) * 1000, Math.sin(e) * 1000, -Math.cos(az) * Math.cos(e) * 1000); SUNDIR.copy(sun.position).normalize(); SUNEL = el;')
rep('  const t = new Date().toLocaleTimeString("zh-TW", { timeZone: "Asia/Taipei", hour: "2-digit", minute: "2-digit", hour12: false });\n  $("clock")',
    '  if (!day) SUNDIR.copy(sun.position).normalize();\n  const t = new Date().toLocaleTimeString("zh-TW", { timeZone: "Asia/Taipei", hour: "2-digit", minute: "2-digit", hour12: false });\n  $("clock")')
rep('function applySun() {', 'const SUNDIR = new THREE.Vector3(0.5, 0.7, -0.5).normalize(); let SUNEL = 0.9, AMB0 = 0.5, SUN0 = 2.3;\nfunction applySun() {')
rep('  if (!day) SUNDIR.copy(sun.position).normalize();', '  if (!day) SUNDIR.copy(sun.position).normalize();\n  AMB0 = amb.intensity; SUN0 = sun.intensity;')
rep('if (FORCE === "day") { el = 0.9; az = 2.4; }', 'if (FORCE === "day") { el = 0.6; az = 4.75; }   // 強制白天用下午偏西的太陽，影子比較長')
rep('scene.add(sun);', '''scene.add(sun); scene.add(sun.target);
const SHADOWS = !MOBILE && new URLSearchParams(location.search).get("sh") !== "0";
if (SHADOWS) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.00002; sun.shadow.normalBias = 0.0006; sun.shadow.radius = 2; }''')

# 每一格：陰影相機跟著鏡頭（只有拉近、白天才開）；天空與霧氣依遠近、晝夜調整
rep('  lodTick(dt); orthoTick(dt);', '  lodTick(dt); orthoTick(dt); lightTick(dt);')
rep('/* ---------- 啟動 ---------- */', r'''/* ---- 光影 ---- */
// 天空：一顆跟著鏡頭的大球，白天藍天到地平線泛白、太陽周圍一圈暖光；晚上深藍，地平線帶一點城市的暖光
const SKY = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, depthTest: true, fog: false, transparent: true,
  uniforms: { uSun: { value: SUNDIR }, uNight: uni.uNight, uVis: { value: 0 } },
  vertexShader: "varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader: `uniform vec3 uSun; uniform float uNight; uniform float uVis; varying vec3 vD;
    void main(){ vec3 d = normalize(vD); float h = clamp(d.y, -0.2, 1.0);
      vec3 dayC = mix(vec3(0.78, 0.84, 0.9), vec3(0.32, 0.5, 0.76), pow(max(h, 0.0), 0.55));
      float s = max(dot(d, normalize(uSun)), 0.0); dayC += vec3(1.0, 0.86, 0.62) * (pow(s, 48.0) * 0.5 + pow(s, 6.0) * 0.12);
      vec3 nightC = mix(vec3(0.2, 0.12, 0.07), vec3(0.012, 0.018, 0.045), pow(max(h, 0.0), 0.32));   // 地平線上一圈城市光害的橘光，往上漸漸變深藍
      vec3 c = mix(dayC, nightC, uNight); if (h < 0.0) c = mix(c, c * 0.7, -h * 5.0);
      gl_FragColor = vec4(c, uVis); }` }));
SKY.renderOrder = -100; SKY.frustumCulled = false; scene.add(SKY); window.__SKY = SKY;
const HAZE_DAY = new THREE.Color(0.74, 0.8, 0.87), HAZE_NIGHT = new THREE.Color(0.13, 0.085, 0.06), _hz = new THREE.Color(), _blk = new THREE.Color(0, 0, 0);
window.__sun = sun; window.__rend = renderer; let _shT = 0; const _shLast = new THREE.Vector3(1e9, 0, 0);
function lightTick(dt) {
  const close = uni.uClose.value, t = controls.target, cd = camera.position.distanceTo(t), globe = !!ST.globeForce;
  // 天空與霧：拉近才出現（遠景維持原本的黑色宇宙感）
  // 捲動劇本換章時鏡頭會穿過地底、飛向地球，這段不能開天空和霧（不然整個畫面會被霧色蓋成一片咖啡色）；只有停在城市章節或自己逛時才開
  const stable = ST.explore ? 1 : (ST.on ? Math.max(0, 1 - Math.abs(ST.c - Math.round(ST.c)) / 0.12) : 1);
  const k = (globe || ST.earthOn || (scene.fog !== FOG)) ? 0 : Math.min(1, Math.max(0, (close - 0.25) / 0.45)) * stable;
  SKY.visible = k > 0.01; SKY.material.uniforms.uVis.value = k; SKY.position.copy(camera.position); SKY.scale.setScalar(camera.far * 0.9);
  if (scene.fog === FOG) { _hz.copy(HAZE_DAY).lerp(HAZE_NIGHT, uni.uNight.value);
    FOG.color.copy(_blk).lerp(_hz, k); FOG.near = 1100 + (cd * 1.6 + 1.5 - 1100) * k; FOG.far = 2800 + (cd * 7 + 14 - 2800) * k; }
  // 太陽陰影：白天、拉近時開；陰影範圍跟著鏡頭，鏡頭移動才重算
  if (!SHADOWS) return;
  const on = close > 0.35 && !uni.uNight.value && !globe;
  if (sun.castShadow !== on) { sun.castShadow = on; renderer.shadowMap.needsUpdate = true; }
  amb.intensity = AMB0 * (on ? 0.45 : 1); sun.intensity = SUN0 * (on ? 1.3 : 1);   // 陰影開著時，直射光比環境光強，影子才看得出來
  if (on) {
    const S = Math.min(7, Math.max(0.7, cd * 0.85)), R = 30;
    sun.position.copy(t).addScaledVector(SUNDIR, R); sun.target.position.copy(t); sun.target.updateMatrixWorld();
    const sc = sun.shadow.camera; if (Math.abs(sc.right - S) > S * 0.15) { sc.left = -S; sc.right = S; sc.top = S; sc.bottom = -S; sc.near = 1; sc.far = R * 2; sc.updateProjectionMatrix(); renderer.shadowMap.needsUpdate = true; }
    _shT += dt; if (_shLast.distanceTo(t) > S * 0.02 || _shT > 2) { _shLast.copy(t); _shT = 0; renderer.shadowMap.needsUpdate = true; }
    for (const v of Object.values(CITY)) if (v.mesh && !v.mesh.userData.sh) { v.mesh.userData.sh = 1; v.mesh.traverse(o => { if (o.isMesh) { o.receiveShadow = true; o.castShadow = o === v.mesh.children[0]; } }); renderer.shadowMap.needsUpdate = true; }
    for (const m of ORTHO.patches.values()) if (!m.receiveShadow) { m.receiveShadow = true; m.material.needsUpdate = true; }
    if (terrain && !terrain.receiveShadow) { terrain.receiveShadow = true; terrain.material.needsUpdate = true; }
  } else { sun.position.copy(SUNDIR).multiplyScalar(1000); sun.target.position.set(0, 0, 0); sun.target.updateMatrixWorld(); }
}
/* ---------- 啟動 ---------- */''')

# 晚上的路：路燈一盞一盞打在路面上的光圈（約 35 公尺一盞），快速道路偏白、一般道路偏暖黃
rep('sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\\nuniform float uNight; varying float vCls;")',
    'sh.vertexShader = sh.vertexShader.replace("vCls = aCls;", "vCls = aCls; vWP2 = (modelMatrix * vec4(transformed, 1.0)).xyz;").replace("varying float vCls;", "varying float vCls; varying vec3 vWP2;");\n  sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\\nuniform float uNight; varying float vCls; varying vec3 vWP2;")')
rep('totalEmissiveRadiance *= uNight * mix(0.95, 0.12, clamp((vCls - 1.0) / 5.0, 0.0, 1.0));',
    'vec2 lc = vWP2.xz / 0.03; float pd = length(fract(lc) - 0.5); float pool = pow(smoothstep(0.42, 0.0, pd), 3.0); float hw = 1.0 - clamp((vCls - 1.0) / 2.0, 0.0, 1.0); vec3 lampC = mix(vec3(1.0, 0.62, 0.3), vec3(0.95, 0.92, 0.85), hw); float farK = smoothstep(0.004, 0.02, fwidth(vWP2.x) + fwidth(vWP2.z)); totalEmissiveRadiance = lampC * mix(0.05 + 0.75 * pool * mix(1.0, 0.6, hw), 0.35, farK) * uNight * mix(0.9, 0.16, clamp((vCls - 1.0) / 5.0, 0.0, 1.0));')
