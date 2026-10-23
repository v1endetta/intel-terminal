# ===== 手機：自動降畫質 ＋ 效能面板（?perf=1） =====
# 1) 手機白模最多 2 萬棟（資料已按體積排序，留下的是最大的那些）
rep('if (MOBILE) n = Math.min(n, 60000);', 'if (MOBILE) n = Math.min(n, 20000);')
# 2) 手機的航照地面用便宜的光照模型（兩層透明照片疊在地形上，每個像素算三次）
rep('  const m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.96, metalness: 0, emissive: 0xffffff, transparent: true,',
    '  const m = new (MOBILE ? THREE.MeshLambertMaterial : THREE.MeshStandardMaterial)({ map: tex, ...(MOBILE ? {} : { roughness: 0.96, metalness: 0 }), emissive: 0xffffff, transparent: true,')
# 3) 每一格的時間記下來；手機掉格就自動降解析度，再不行就關光暈；變順了再慢慢升回來
rep('function loop() {\n  const dt = Math.min(clock.getDelta(), 0.05);', '''const PERF = { on: new URLSearchParams(location.search).has("perf"), fr: [], js: [], dpr: renderer.getPixelRatio(), maxDpr: renderer.getPixelRatio(), auto: true, noOrtho: false, noCity: false, last: 0, good: 0, log: [] };
function perfSetDpr(d) { d = Math.max(1, Math.min(PERF.maxDpr, Math.round(d * 4) / 4)); if (d === PERF.dpr) return; PERF.dpr = d; renderer.setPixelRatio(d); renderer.setSize(innerWidth, VH()); if (composer) { composer.setPixelRatio(d); composer.setSize(innerWidth, VH()); } PERF.log.unshift("解析度 → " + d); }
function perfTick(now, jsMs) {
  const P = PERF; if (P._t0) P.fr.push(now - P._t0); P._t0 = now; P.js.push(jsMs);
  if (P.fr.length > 90) { P.fr.shift(); P.js.shift(); }
  if (now - P.last < 1500 || P.fr.length < 8) return; P.last = now;
  const avg = P.fr.reduce((a, b) => a + b, 0) / P.fr.length, fps = 1000 / avg;
  if (P.auto && MOBILE && !document.hidden) {
    if (fps < 42) { P.good = 0; if (P.dpr > 1) perfSetDpr(P.dpr - 0.25); else if (FX.on) { FX.on = false; P.log.unshift("關光暈"); } }
    else if (fps > 57) { if (++P.good >= 4 && P.dpr < P.maxDpr) { P.good = 0; perfSetDpr(P.dpr + 0.25); } }
  }
  if (P.on) perfHud(fps);
}
function perfHud(fps) {
  const P = PERF; let el = document.getElementById("perfHud");
  if (!el) { el = document.createElement("div"); el.id = "perfHud";
    el.style.cssText = "position:fixed;left:8px;top:104px;z-index:99;font:11px/1.45 ui-monospace,Menlo,monospace;color:#d8f6ff;background:rgba(0,0,0,.78);padding:8px 10px;border-radius:10px;pointer-events:auto;max-width:62vw";
    document.body.appendChild(el);
    el.addEventListener("click", e => { const b = e.target.dataset.k; if (!b) return;
      if (b === "fx") FX.on = !FX.on; if (b === "ortho") P.noOrtho = !P.noOrtho; if (b === "city") P.noCity = !P.noCity;
      if (b === "auto") P.auto = !P.auto; if (b === "dpr") { P.auto = false; perfSetDpr(P.dpr > 1 ? 1 : P.maxDpr); } perfHud(fps); }); }
  const s = [...P.fr].sort((a, b) => a - b), worst = s[s.length - 1] || 0, p90 = s[Math.floor(s.length * 0.9)] || 0, js = P.js.reduce((a, b) => a + b, 0) / (P.js.length || 1);
  const I = renderer.info, cities = Object.entries(CITY).filter(([k, v]) => v.mesh && v.mesh.visible).map(([k]) => k).join(",") || "—";
  const btn = (k, t, on) => `<span data-k="${k}" style="display:inline-block;margin:4px 4px 0 0;padding:3px 7px;border-radius:6px;background:${on ? "#1f6f4a" : "#5a2328"}">${t}</span>`;
  el.innerHTML = `<b>${fps.toFixed(0)} fps</b>　最慢 ${worst.toFixed(0)}ms　p90 ${p90.toFixed(0)}ms<br>JS ${js.toFixed(1)}ms／格　解析度 ${P.dpr}<br>繪製 ${I.render.calls} 次　三角形 ${(I.render.triangles / 1000).toFixed(0)}k<br>貼圖 ${I.memory.textures}　網格 ${I.memory.geometries}　航照 ${ORTHO.patches.size}<br>章節 ${ST.active}　城市 ${cities}<br>`
    + btn("auto", "自動", P.auto) + btn("dpr", "解析度", P.dpr > 1) + btn("fx", "光暈", FX.on) + btn("ortho", "航照", !P.noOrtho) + btn("city", "城市", !P.noCity)
    + (P.log.length ? `<div style="opacity:.7;margin-top:4px">${P.log.slice(0, 3).join("<br>")}</div>` : "");
}
function loop() {
  const _t0 = performance.now();
  const dt = Math.min(clock.getDelta(), 0.05);''')
rep('  present(); placeLabels();\n  requestAnimationFrame(loop);', '''  if (PERF.noOrtho) for (const m of ORTHO.patches.values()) m.visible = false;
  if (PERF.noCity) for (const v of Object.values(CITY)) if (v.mesh) v.mesh.visible = false;
  present(); placeLabels();
  perfTick(_t0, performance.now() - _t0);
  requestAnimationFrame(loop);''')
# 光暈開關要真的有效（原本的 FX.on 只在網址參數決定）
# 4) 手機一次只載鏡頭最近的一個城市（原本台北鏡頭會連桃園、基隆一起載）
rep('  const near = cityAtTarget(); if (near === null) return;', '''  let near = cityAtTarget(); if (near === null) return;
  if (MOBILE && near.length > 1) { const t = controls.target, dc = k => { const b = BMETA.cities[k].bbox, [x, z] = toXZ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2); return Math.hypot(x - t.x, z - t.z); }; near = [near.sort((a, b) => dc(a) - dc(b))[0]]; }''')
