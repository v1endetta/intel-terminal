
/* ---- 全台建物（依行政區分檔，ops/bake_towns.py）----
   台灣層：不放建物，只看地形和資料。
   縣市層：鏡頭附近一整片的簡化方塊，拉遠看得到城市的輪廓和密度。
   行政區／街道層：所在行政區＋相鄰幾區的真實外形、道路、河川公園（電腦版；手機一律用方塊，比較省）。
   有 tb/index.json 就用這套；還沒烤好的時候沿用原本的六都＋市中心。 */
const TB = { meta: null, keys: [], geo: null };
fetch(`tb/index.json?v=${ASSET_V}`).then(r => r.ok ? r.json() : null).then(j => {
  if (!j || !j.towns) return;
  for (const c of Object.values(j.towns)) { const [a, b] = toXZ(c.rect[0], c.rect[3]), [d, e] = toXZ(c.rect[2], c.rect[1]); c.box = [Math.min(a, d), Math.min(b, e), Math.max(a, d), Math.max(b, e)]; }
  TB.meta = j; TB.keys = Object.keys(j.towns);
}).catch(() => {});
const tbDist = (c, t) => Math.hypot(Math.max(c.box[0] - t.x, 0, t.x - c.box[2]), Math.max(c.box[1] - t.z, 0, t.z - c.box[3]));
const TB_SKIP = [[121.5262, 25.0787, 140], [120.6406, 24.1627, 100], [120.2025, 22.9975, 70]];   // 手做地標的位置，方塊版不重複畫
async function tbBoxes(k) {
  const id = "b:" + k, c = TB.meta.towns[k]; CITY[id] = { state: "loading" };
  try {
    const buf = await (await fetch(`tb/b_${k}.bin?v=${ASSET_V}`)).arrayBuffer();
    const dv = new DataView(buf), n = Math.floor(buf.byteLength / 11);
    if (!TB.geo) { TB.geo = new THREE.BoxGeometry(1, 1, 1); TB.geo.translate(0, 0.5, 0); }
    const mesh = new THREE.InstancedMesh(TB.geo, bMat, Math.max(1, n));
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), sc = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), Z = new THREE.Matrix4().makeScale(0, 0, 0);
    if (!n) mesh.setMatrixAt(0, Z);
    for (let i = 0; i < n; i++) {
      const o = i * 11, x = dv.getUint16(o, true) / 2, z = dv.getUint16(o + 2, true) / 2, w = dv.getUint16(o + 4, true) / 10, d = dv.getUint16(o + 6, true) / 10;
      const a = dv.getUint8(o + 8) / 255 * Math.PI, h = dv.getUint16(o + 9, true) / 10, lon = c.bbox[0] + x / c.kx, lat = c.bbox[1] + z / c.ky;
      if (TB_SKIP.some(s => Math.hypot((lon - s[0]) * c.kx, (lat - s[1]) * c.ky) < s[2])) { mesh.setMatrixAt(i, Z); continue; }
      const [sx, sz] = toXZ(lon, lat);
      p.set(sx, hAt(lon, lat) * 0.42 - 0.01, sz); q.setFromAxisAngle(up, a); sc.set(Math.max(w, 4) / 1000, h / 1000 * BEX, Math.max(d, 4) / 1000);
      m.compose(p, q, sc); mesh.setMatrixAt(i, m);
    }
    mesh.instanceMatrix.needsUpdate = true; mesh.computeBoundingSphere(); mesh.visible = false;
    scene.add(mesh); CITY[id] = { state: "ready", mesh };
  } catch (e) { CITY[id] = { state: "error" }; }
}
function tbDetail(k) {
  const c = TB.meta.towns[k]; CITY[k] = { state: "detail" };
  const T = { ox: (c.bbox[0] - LONC) * KX, oz: -(c.bbox[1] - LATC) * KY, kxs: KX, ky: KY, v: ASSET_V };
  cityWorker().postMessage({ key: k, c, base: document.baseURI + "tb/", T, BEX, chunks: [] });
}
function tbDrop(id, v) {
  scene.remove(v.mesh); v.mesh.traverse(o => { if (o.geometry && o.geometry !== TB.geo) o.geometry.dispose(); if (o.isInstancedMesh) o.dispose(); });
  if (LIFE.city === v) { LIFE.city = null; LIFE.cars = []; }
  delete CITY[id];
}
const _lodCity = lodTick;
lodTick = function (dt) {
  if (!TB.meta) return _lodCity(dt);
  lodT += dt; if (lodT < 0.5) return; lodT = 0;
  const t = controls.target, dist = camera.position.distanceTo(t), now = performance.now(), want = new Map();
  if (dist <= 170 && !ST.globeForce && !ST.earthOn) {
    const det = dist <= 45 && !MOBILE && typeof Worker !== "undefined" && !LITE;
    const R = det ? Math.max(3, dist * 0.7) : Math.max(12, dist * 0.9);
    let budget = det ? 200000 : (MOBILE ? 80000 : 360000), cnt = 0;
    for (const [k, d] of TB.keys.map(k => [k, tbDist(TB.meta.towns[k], t)]).filter(x => x[1] <= R).sort((a, b) => a[1] - b[1])) {
      const c = TB.meta.towns[k], n = det ? c.pn : c.n;
      if (cnt && budget < n) break;
      budget -= n; cnt++; want.set(k, det && !CITY_NODETAIL.has(k) ? "d" : "b");
    }
  }
  const ready = k => CITY[k] && CITY[k].state === "ready";
  for (const [k, m] of want) {
    if (m === "d" && !CITY[k]) tbDetail(k);
    if (!CITY["b:" + k] && (m === "b" || !ready(k))) tbBoxes(k);   // 真實外形還在組的時候，先用方塊頂著
  }
  for (const [id, v] of Object.entries(CITY)) {
    if (!v.mesh) continue;
    const isB = id.startsWith("b:"), k = isB ? id.slice(2) : id, m = want.get(k);
    const on = isB ? (m === "b" || (m === "d" && !ready(k))) : m === "d";
    v.mesh.visible = on; v.away = on ? 0 : (v.away || now);
    if (!on && now - v.away > 30000) tbDrop(id, v);
  }
};
