# ===== 防當機：控制顯示記憶體 =====
# 1) 電腦也一次只載一個城市（原本台北會連桃園、基隆的建物、航照一起載）
rep('  if (MOBILE && near.length > 1) {', '  if (near.length > 1) {')
# 2) 航照：電腦版全島底圖 9→6 塊、市區 9→6 塊；4096 高解析只給鏡頭正下方 1 塊
rep('.slice(0, MOBILE ? 4 : 9).forEach(o => want.add(o.k))', '.slice(0, MOBILE ? 4 : 6).forEach(o => want.add(o.k))')
rep('.slice(0, MOBILE ? 3 : 9)\n        .forEach((o, n) => { want.add(o.k); if (!MOBILE && n < 4 && cd < 40) hi.add(o.k); });',
    '.slice(0, MOBILE ? 3 : 6)\n        .forEach((o, n) => { want.add(o.k); if (!MOBILE && n < 1 && cd < 20) hi.add(o.k); });')
rep('const cap = want.size + (MOBILE ? 2 : 6),', 'const cap = want.size + (MOBILE ? 2 : 3),')
# 3) 離開超過 40 秒的城市整個釋放（原本逛過的城市都留在記憶體裡，逛久了就爆）
rep('  for (const [k, v] of Object.entries(CITY)) if (v.mesh) v.mesh.visible = near.includes(k);', '''  for (const [k, v] of Object.entries(CITY)) if (v.mesh) { const on = near.includes(k); v.mesh.visible = on; v.away = on ? 0 : (v.away || performance.now());
    if (!on && performance.now() - v.away > 40000) { scene.remove(v.mesh); v.mesh.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.isInstancedMesh) o.dispose(); }); if (LIFE.city === v) { LIFE.city = null; LIFE.cars = []; } delete CITY[k]; } }''')
# 4) 顯示晶片撐不住時（WebGL context lost）不要整頁黑掉，改成提示可以重新載入
rep('$("stage").appendChild(renderer.domElement);', '''$("stage").appendChild(renderer.domElement);
renderer.domElement.addEventListener("webglcontextlost", e => { e.preventDefault(); const d = document.createElement("div");
  d.style.cssText = "position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.82);color:#fff;font:15px/1.6 -apple-system,sans-serif;text-align:center;padding:24px";
  d.innerHTML = "顯示記憶體不夠，3D 畫面先暫停了<br><button style='margin-top:14px;padding:8px 18px;border-radius:999px;border:0;background:#0a84ff;color:#fff;font-size:15px' onclick='location.reload()'>重新載入</button><br><small style='opacity:.6'>網址加上 ?lite=1 可以用輕量版</small>"; document.body.appendChild(d); });''')
# 5) ?lite=1 輕量版：不開陰影、車流與頂樓、高解析航照、光暈
rep('const VH = () => _VH;', 'const VH = () => _VH;\nconst LITE = new URLSearchParams(location.search).has("lite");')
rep('const SHADOWS = !MOBILE && ', 'const SHADOWS = !MOBILE && !LITE && ')
rep('function cityLife(grp, d) {\n  if (MOBILE) return;', 'function cityLife(grp, d) {\n  if (MOBILE || LITE) return;')
rep('if (!MOBILE && n < 1 && cd < 20) hi.add(o.k);', 'if (!MOBILE && !LITE && n < 1 && cd < 20) hi.add(o.k);')
rep('const FX = { on: new URLSearchParams(location.search).get("fx") !== "0" };', 'const FX = { on: new URLSearchParams(location.search).get("fx") !== "0" && !LITE };')
# 6) 電腦版也自動降畫質：掉到每秒 28 格以下，依序關影子 → 收起車流與頂樓 → 降解析度 → 關光暈；左下角提示一下
rep('const PERF = {', 'const QUAL = { sh: true, life: true };\nconst PERF = {')
rep('  if (P.auto && MOBILE && !document.hidden) {', '''  if (P.auto && !MOBILE && !document.hidden) {
    if (fps < 28) { P.good = 0; let msg = "";
      if (QUAL.sh && SHADOWS) { QUAL.sh = false; msg = "關掉影子"; } else if (QUAL.life) { QUAL.life = false; msg = "收起車流與頂樓"; }
      else if (P.dpr > 1) { perfSetDpr(P.dpr - 0.25); msg = "降低解析度"; } else if (FX.on) { FX.on = false; msg = "關掉光暈"; }
      if (msg) { P.log.unshift(msg); qualToast("畫面有點吃力，已自動" + msg); } }
  }
  if (P.auto && MOBILE && !document.hidden) {''')
rep('function perfHud(fps) {', '''function qualToast(t) { let el = document.getElementById("qualToast"); if (!el) { el = document.createElement("div"); el.id = "qualToast";
  el.style.cssText = "position:fixed;left:16px;bottom:16px;z-index:60;font:12px/1.4 -apple-system,sans-serif;color:#e5e5ea;background:rgba(28,28,30,.86);padding:7px 12px;border-radius:10px;transition:opacity .5s;pointer-events:none"; document.body.appendChild(el); }
  el.textContent = t; el.style.opacity = 1; clearTimeout(qualToast.t); qualToast.t = setTimeout(() => el.style.opacity = 0, 4000); }
function perfHud(fps) {''')
# 影子：鏡頭在動的時候不重算，停下來 0.4 秒後才更新一次；頂樓物件不投影子
rep('  const on = close > 0.35 && !uni.uNight.value && !globe;', '  const on = QUAL.sh && close > 0.35 && !uni.uNight.value && !globe;')
rep('    _shT += dt; if (_shLast.distanceTo(t) > S * 0.02 || _shT > 2) { _shLast.copy(t); _shT = 0; renderer.shadowMap.needsUpdate = true; }',
    '''    const mv = _shLast.distanceTo(t) + (lightTick.cp ? lightTick.cp.distanceTo(camera.position) : 1); lightTick.cp = (lightTick.cp || camera.position.clone()).copy(camera.position); _shLast.copy(t);
    _shT = mv > 1e-4 ? 0 : _shT + dt; if (_shT > 0.4 && !lightTick.done) { renderer.shadowMap.needsUpdate = true; lightTick.done = true; } if (mv > 1e-4) lightTick.done = false;''')
rep('    m.castShadow = m.receiveShadow = true; grp.add(m); LIFE_MATS.push(m.material);', '    m.receiveShadow = true; grp.add(m); LIFE_MATS.push(m.material);')
rep('    m.castShadow = true; grp.add(m); LIFE_MATS.push(m.material);', '    grp.add(m); LIFE_MATS.push(m.material); m.userData.life = 1;')
# 測試用：?noauto 關掉自動降畫質
rep('maxDpr: renderer.getPixelRatio(), auto: true,', 'maxDpr: renderer.getPixelRatio(), auto: !new URLSearchParams(location.search).has("noauto"),')
