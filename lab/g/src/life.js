/* ---- 活的城市：頂樓（水塔、鐵皮加蓋）＋ 路上的車（快速道路照高公局即時車速，其他道路依時段推估）---- */
const LIFE_MATS = [];
const LIFE = window.__life = { cars: [], body: null, lights: null, at: new THREE.Vector3(1e9, 0, 0), city: null, live: null, t: 0 };
function cityLife(grp, d) {
  if (MOBILE) return;
  const K = BEX / 1000, up = new THREE.Vector3(0, 1, 0), M = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), s = new THREE.Vector3(), C = new THREE.Color();
  // 鐵皮加蓋：藍、灰、白、鏽色
  const sh = d.SH; if (sh && sh.length) {
    const n = Math.min(20000, sh.length / 7), geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);
    const m = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.35 }), n), PAL = [0x5f7486, 0x8e9396, 0xbfc1bd, 0x7a5646];   // 藍灰、灰、米白、鏽色（壓低彩度）
    for (let i = 0; i < n; i++) { const o = i * 7; p.set(sh[o], sh[o + 1], sh[o + 2]); q.setFromAxisAngle(up, -sh[o + 5]); s.set(sh[o + 3], 3.0 * K, sh[o + 4]); M.compose(p, q, s); m.setMatrixAt(i, M); m.setColorAt(i, C.setHex(PAL[sh[o + 6] | 0])); }
    m.castShadow = m.receiveShadow = true; grp.add(m); LIFE_MATS.push(m.material);
  }
  // 水塔：不鏽鋼或藍色塑膠桶
  const tk = d.TK; if (tk && tk.length) {
    const n = Math.min(25000, tk.length / 4), geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);   // 方桶就好，省三角形
    const m = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.6 }), n);
    for (let i = 0; i < n; i++) { const o = i * 4; p.set(tk[o], tk[o + 1], tk[o + 2]); s.set(0.0019, 1.7 * K, 0.0019); M.compose(p, q.identity(), s); m.setMatrixAt(i, M); m.setColorAt(i, C.setHex(tk[o + 3] ? 0x3f6ea6 : 0xc8ccd0)); }
    m.castShadow = true; grp.add(m); LIFE_MATS.push(m.material);
  }
  // 車流：直接畫在路面上的移動圖案（顯示晶片算，不用每一格在程式裡移動每一台車）
  if (d.RD && d.RD.length && d.RP.length) {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(d.RP, 3)); g.setAttribute("aCls", new THREE.BufferAttribute(d.RC, 1));
    g.setAttribute("aD", new THREE.BufferAttribute(d.RD, 1)); g.setAttribute("aV", new THREE.BufferAttribute(d.RV, 1));
    // 國道、快速道路：載入城市時查一次高公局即時車速，寫進每一段路（之後每格不用再算）
    const RP = d.RP, RC = d.RC, SP = new Float32Array(RC.length);
    for (let i = 0; i < RC.length; i += 6) if (RC[i] <= 2) { const v = liveSpeed(RP[i * 3], RP[i * 3 + 2]); if (v != null) SP.fill(v, i, i + 6); }
    g.setAttribute("aSp", new THREE.BufferAttribute(SP, 1));
    const m = new THREE.Mesh(g, carMat()); m.renderOrder = 3; m.frustumCulled = false; m.userData.cars = 1; grp.add(m);
  }
}
let _carMat = null;
const CARU = { uTime: uni.uTime, uNight: uni.uNight, uVis: { value: 0 }, uDens: { value: 1 }, uSlow: { value: 1 } };
function carMat() {
  if (_carMat) return _carMat;
  _carMat = new THREE.ShaderMaterial({ uniforms: CARU, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -8,
    vertexShader: `attribute float aCls; attribute float aD; attribute float aV; attribute float aSp; varying float vC; varying float vD; varying float vV; varying float vSp;
      void main(){ vC = aCls; vD = aD; vV = aV; vSp = aSp; vec3 p = position; p.y += 0.0006; gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }`,
    fragmentShader: `uniform float uTime; uniform float uNight; uniform float uVis; uniform float uDens; uniform float uSlow; varying float vC; varying float vD; varying float vV; varying float vSp;
      float h1(float x){ return fract(sin(x * 127.1) * 43758.5453); }
      void main(){
        if (vC > 5.5 || uVis < 0.01) discard;
        float lane = step(0.0, vV), dir = lane * 2.0 - 1.0, av = abs(vV);
        if (av < 0.18 || av > 0.82) discard;                                  // 車道中間才有車
        float kmh = vC < 1.5 ? 85.0 : vC < 2.5 ? 60.0 : vC < 3.5 ? 40.0 : 32.0;
        float live = step(1.0, vSp); kmh = mix(kmh, vSp, live);
        float spd = kmh / 3600.0 * mix(uSlow, 1.0, live);                       // 公里／秒；有即時車速就照實際
        float jam = live * (1.0 - smoothstep(30.0, 70.0, vSp));                 // 塞車：車距縮短、車變多
        float spacing = (0.016 + vC * 0.004) * mix(1.0, 0.45, jam);            // 一格放一台的長度
        float s = vD - dir * uTime * spd, cell = floor(s / spacing), f = fract(s / spacing);
        float hh = h1(cell * 1.31 + lane * 17.0 + floor(vD * 0.05) * 3.7);
        float dens = clamp((vC < 2.5 ? 0.75 : 0.5) * mix(uDens, 1.3, live), 0.0, 0.95);
        if (hh > dens) discard;
        float L = 0.0045 / spacing; float f0 = 0.5 - L * 0.5, fc = (f - f0) / L;
        if (fc < 0.0 || fc > 1.0) discard;
        float far = smoothstep(0.35, 0.8, fwidth(f) / L); if (far > 0.98) discard;   // 太遠一台車不到一個像素就不畫，免得閃
        float hc = h1(cell * 3.17 + lane * 5.0);
        vec3 body = hc < 0.35 ? vec3(0.92) : hc < 0.53 ? vec3(0.08) : hc < 0.78 ? vec3(0.62, 0.64, 0.66) : hc < 0.84 ? vec3(0.65, 0.12, 0.1) : hc < 0.9 ? vec3(0.13, 0.25, 0.48) : vec3(0.95, 0.75, 0.1);
        float front = dir > 0.0 ? fc : 1.0 - fc;                               // 1 = 車頭
        float ac = (av - 0.18) / 0.64, pair = max(step(0.08, ac) * step(ac, 0.32), step(0.68, ac) * step(ac, 0.92));   // 左右兩顆燈
        vec3 lights = mix(vec3(1.0, 0.1, 0.04) * 1.6 * step(front, 0.14), vec3(1.0, 0.95, 0.82) * 2.4 * step(0.88, front), step(0.5, front)) * pair;
        vec3 c = mix(body * 0.85 + vec3(0.05) * (1.0 - abs(fc - 0.5) * 2.0), body * 0.05 + lights, uNight);
        gl_FragColor = vec4(c, uVis * (1.0 - far));
      }` });
  return _carMat;
}
// 每一格只更新幾個數字：拉近才顯示、白天晚上、尖峰車多又慢、深夜變少
function lifeTick(dt) {
  const t = controls.target, close = uni.uClose.value, cd = camera.position.distanceTo(t);
  if (ST.explore && !ST.globeForce) { const nr = Math.min(1, Math.max(0.002, cd * 0.004)), fr = Math.min(90000, Math.max(400, cd * 150));
    if (Math.abs(nr - camera.near) > camera.near * 0.05 || Math.abs(fr - camera.far) > camera.far * 0.05) { camera.near = nr; camera.far = fr; camera.updateProjectionMatrix(); } }
  for (const m of LIFE_MATS) m.color.setScalar(1 - 0.93 * uni.uNight.value);
  const on = !MOBILE && QUAL.life && !ST.globeForce;
  CARU.uVis.value = on ? Math.min(1, Math.max(0, (close - 0.45) / 0.3)) : 0;
  for (const v of Object.values(CITY)) if (v.mesh) for (const o of v.mesh.children) if (o.isInstancedMesh || o.userData.cars) o.visible = on;
  LIFE.t -= dt; if (LIFE.t > 0) return; LIFE.t = 30;
  const hr = +new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei", hour: "numeric", hour12: false }) % 24, rush = (hr >= 7 && hr < 10) || (hr >= 17 && hr < 20);
  CARU.uDens.value = rush ? 1.25 : hr < 6 ? 0.3 : hr >= 22 ? 0.65 : 1; CARU.uSlow.value = rush ? 0.55 : 1;
}
// 高公局即時車速：國道路段的點放進格子，查最近的那一段（每座城市載入時用一次）
function lifeLive() {
  if (LIFE.live || !ROADS_GEO || !ROADS_LIVE) return LIFE.live;
  const H = new Map(), fw = ROADS_GEO.fw, sp = ROADS_LIVE.fw || [];
  (fw.c || []).forEach((flat, i) => { const v = sp[i]; if (v == null || v < 0) return;
    for (let k = 0; k + 1 < flat.length; k += 2) { const [x, z] = toXZ(flat[k] / 1e4, flat[k + 1] / 1e4), key = Math.floor(x / 0.3) + "," + Math.floor(z / 0.3); if (!H.has(key)) H.set(key, []); H.get(key).push([x, z, v]); } });
  return (LIFE.live = H);
}
function liveSpeed(x, z) {
  const H = lifeLive(); if (!H) return null; let best = null, bd = 0.12;
  for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const q of H.get((Math.floor(x / 0.3) + i) + "," + (Math.floor(z / 0.3) + j)) || []) { const d = Math.hypot(q[0] - x, q[1] - z); if (d < bd) { bd = d; best = q[2]; } }
  return best;
}
