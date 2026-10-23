
/* ---- 開場：從太空看真實地球，一路縮到台灣，再接原本的掃描動畫 ----
   地球照片：NASA Blue Marble（白天）＋ Black Marble（夜間燈光），晝夜分界照「現在」太陽直射的位置。 */
const EARTH_T = 4.2;   // 地球段落的秒數
const EARTH = { g: null, mat: null, stars: null };
function earthSunDir() {
  const now = new Date(), doy = Math.floor((now - new Date(Date.UTC(now.getUTCFullYear(), 0, 0))) / 864e5);
  let lat = -23.44 * Math.cos(2 * Math.PI / 365 * (doy + 10)), lon = -15 * (now.getUTCHours() + now.getUTCMinutes() / 60 - 12);
  if (FORCE === "day") { lon = 125; lat = 15; } else if (FORCE === "night") { lon = -55; lat = -10; }
  return GLOBE.G(lon, lat, 0).sub(V(0, -6371, 0)).normalize();
}
function buildEarth() {
  if (EARTH.g) return EARTH.g;
  const g = new THREE.Group(), NX = MOBILE ? 128 : 256, NY = MOBILE ? 64 : 128, pos = [], uv = [], idx = [];
  for (let j = 0; j <= NY; j++) for (let i = 0; i <= NX; i++) { const lon = -180 + 360 * i / NX, lat = 90 - 180 * j / NY, p = GLOBE.G(lon, lat, -3); pos.push(p.x, p.y, p.z); uv.push(i / NX, 1 - j / NY); }
  for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) { const a = j * (NX + 1) + i, b = a + 1, c = a + NX + 1, d = c + 1; idx.push(a, c, b, b, c, d); }
  const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2)); geo.setIndex(idx);
  const L = new THREE.TextureLoader(), sfx = MOBILE ? "_m" : "", tex = n => { const t = L.load(`earth_${n}${sfx}.jpg?v=${ASSET_V}`); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
  EARTH.mat = new THREE.ShaderMaterial({ transparent: true, uniforms: { uDay: { value: tex("day") }, uNightT: { value: tex("night") }, uSun: { value: earthSunDir() }, uC: { value: V(0, -6371, 0) }, uOp: { value: 1 }, uGlass: { value: GLASS ? 1 : 0 } },
    vertexShader: "varying vec2 vUv; varying vec3 vN; varying vec3 vW; uniform vec3 uC; void main(){ vUv = uv; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vN = normalize(w.xyz - uC); gl_Position = projectionMatrix * viewMatrix * w; }",
    fragmentShader: `uniform sampler2D uDay; uniform sampler2D uNightT; uniform vec3 uSun; uniform float uOp; uniform float uGlass; varying vec2 vUv; varying vec3 vN; varying vec3 vW;
      void main(){ float d = dot(vN, uSun), dayK = smoothstep(-0.12, 0.18, d);
        vec3 day = texture2D(uDay, vUv).rgb, nt = texture2D(uNightT, vUv).rgb;
        vec3 v = normalize(cameraPosition - vW); float rim = pow(1.0 - max(dot(v, vN), 0.0), 3.0);
        vec3 c = day * (0.25 + 0.95 * max(d, 0.0)) * dayK + pow(nt, vec3(1.6)) * vec3(1.0, 0.78, 0.5) * 1.6 * (1.0 - dayK);
        if (uGlass > 0.5) {   // 玻璃風：跟資料用的地球同一套顏色（陸地霧面灰藍、海深藍），晨昏線讓夜晚那一半暗一點
          float l = dot(day, vec3(0.299, 0.587, 0.114)), ocean = 0.0; { vec3 dm = texture2D(uDay, vUv, 1.5).rgb; float lm = dot(dm, vec3(0.299, 0.587, 0.114)); ocean = smoothstep(0.85, 1.0, (dm.b + 0.003) / (max(dm.r, dm.g) + 0.003)) * (1.0 - smoothstep(0.30, 0.45, lm));   /* 深海在照片裡幾乎是全黑，要算成海（之前被當成陸地，台灣看起來跟大陸連在一起） */ }   // 用稍微模糊的那層判斷海陸，海岸線不會一格一格
          vec3 land = mix(vec3(0.38, 0.43, 0.52), vec3(0.62, 0.67, 0.76), smoothstep(0.04, 0.45, l)), sea = vec3(0.025, 0.05, 0.11);
          // 台灣本島、澎湖由立體地形來畫：拉近時把照片裡的台灣換成海，不然照片的陸地比真正的海岸線胖一圈，看起來陸地伸到海裡
          { float lon = vUv.x * 360.0 - 180.0, lat = vUv.y * 180.0 - 90.0, alt = length(cameraPosition - vec3(0.0, -6371.0, 0.0)) - 6371.0;
            float tw = step(119.3, lon) * step(lon, 122.15) * step(21.85, lat) * step(lat, 25.35) * (1.0 - step(24.75, lat) * step(lon, 120.6));
            ocean = max(ocean, tw); }
          c = mix(land, sea, ocean) * (0.45 + 0.55 * dayK); }
        c += vec3(0.3, 0.55, 1.0) * rim * (0.25 + 0.6 * dayK);                       // 邊緣的大氣
        float spec = pow(max(dot(reflect(-uSun, vN), v), 0.0), 220.0) * dayK * step(day.g * 1.05, day.b) * step(day.r * 1.2, day.b); c += vec3(1.0, 0.95, 0.85) * spec * 0.22;   // 海面反光
        gl_FragColor = vec4(c, uOp); }` });
  g.add(new THREE.Mesh(geo, EARTH.mat));
  // 外圈大氣光暈
  const atm = new THREE.Mesh(new THREE.SphereGeometry(6371 * 1.025, 64, 32), new THREE.ShaderMaterial({ side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, uniforms: { uOp: EARTH.mat.uniforms.uOp, uSun: EARTH.mat.uniforms.uSun },
    vertexShader: "varying vec3 vN; varying vec3 vP; varying vec3 vWN; void main(){ vN = normalize(normalMatrix * normal); vWN = normalize(position); vec4 mv = modelViewMatrix * vec4(position, 1.0); vP = mv.xyz; gl_Position = projectionMatrix * mv; }",
    fragmentShader: "uniform float uOp; uniform vec3 uSun; varying vec3 vN; varying vec3 vP; varying vec3 vWN; void main(){ float f = pow(1.0 - abs(dot(normalize(-vP), vN)), 2.5); float lit = smoothstep(-0.3, 0.4, dot(vWN, uSun)); gl_FragColor = vec4(vec3(0.3, 0.6, 1.0) * f * (0.25 + 0.9 * lit) * uOp, 1.0); }" }));
  atm.position.set(0, -6371, 0); g.add(atm);
  // 星空
  const sp = []; for (let i = 0; i < 2500; i++) { const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, r = 80000; sp.push(Math.sqrt(1 - u * u) * Math.cos(a) * r, u * r, Math.sqrt(1 - u * u) * Math.sin(a) * r); }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.Float32BufferAttribute(sp, 3));
  EARTH.stars = new THREE.Points(sg, new THREE.PointsMaterial({ size: 1.4, sizeAttenuation: false, color: 0xcfd8ff, transparent: true, opacity: 0.8, depthWrite: false })); EARTH.stars.frustumCulled = false; g.add(EARTH.stars);
  g.visible = false; scene.add(g); EARTH.g = g; return g;
}
// 起點：地球中心為目標、從亞洲太平洋上空 3 萬公里看過來
function earthCam() { const C = V(0, -6371, 0), d = GLOBE.G(MOBILE ? 128 : 136, MOBILE ? 14 : 12, 0).sub(C).normalize(); return { tgt: C, pos: C.clone().addScaledVector(d, 6371 + (MOBILE ? 26000 : 17000)) }; }
function earthTick() {
  const on = INTRO.on && INTRO.ek != null && INTRO.ek < 1;
  ST.earthOn = on;
  if (!EARTH.g) { if (!on) return; buildEarth(); }
  EARTH.g.visible = on;
  if (!on) { const box = $("intro"); if (box && box.style.opacity === "0") box.style.opacity = ""; return; }
  const k = INTRO.ek; EARTH.mat.uniforms.uOp.value = 1 - Math.min(1, Math.max(0, (k - 0.72) / 0.28));
  EARTH.stars.material.opacity = 0.8 * (1 - Math.min(1, k * 1.6)); EARTH.stars.position.copy(camera.position);
  $("intro").style.opacity = "0";
}
window.__scene = scene;
