# ===== 標籤排版省力：用 transform 移動（不觸發重排）、鏡頭沒動就不重算、手機同時最多顯示 22 個 =====
rep('''function placeLabels() {
  const vis = [];''', '''const _lbKey = { k: "", n: 0 };
function placeLabels() {
  // 鏡頭、畫面大小、標籤數量都沒變：不用重算（每 12 格還是算一次，接住內容變寬之類的變化）
  { const e = camera.matrixWorld.elements, p = camera.projectionMatrix.elements, k = `${e[12].toFixed(4)},${e[13].toFixed(4)},${e[14].toFixed(4)},${e[0].toFixed(5)},${e[2].toFixed(5)},${e[9].toFixed(5)},${p[0].toFixed(5)},${p[9].toFixed(5)},${LBL.length},${innerWidth},${VH()}`;
    if (k === _lbKey.k && ++_lbKey.n % 12) return; _lbKey.k = k; }
  const vis = [];''')
rep('''    L.el.style.left = L.sx + "px"; L.el.style.top = L.sy + "px";''', '''    { const tx = Math.round(L.sx), ty = Math.round(L.sy); if (tx !== L.tx || ty !== L.ty) { L.tx = tx; L.ty = ty; L.el.style.transform = `translate3d(${tx}px,${ty}px,0) translate(-50%,-100%)`; } }''')
rep('''  vis.sort((a, b) => b.prio - a.prio);
  _shown.length = 0;''', '''  vis.sort((a, b) => b.prio - a.prio);
  _shown.length = 0; let _cnt = 0; const _cap = MOBILE ? 22 : 999;''')
rep('''    for (const S of _shown) if (x0 < S[2] && x1 > S[0] && y0 < S[3] && y1 > S[1]) { hit = true; break; }''', '''    for (const S of _shown) if (x0 < S[2] && x1 > S[0] && y0 < S[3] && y1 > S[1]) { hit = true; break; }
    if (!hit && ++_cnt > _cap) hit = true;''')

# ===== 開場順暢：載入畫面結束前，先把地球照片傳上顯示卡、把所有著色器編譯好（不然開場前幾秒會一頓一頓） =====
rep('''    try { await buildStory(); } catch (e) { console.error('story', e); ST.on = false; controls.enabled = true; document.body.classList.remove("storying"); start(); }''',
    '''    try { await buildStory(); } catch (e) { console.error('story', e); ST.on = false; controls.enabled = true; document.body.classList.remove("storying"); start(); }
    try { await warmUp(); } catch (e) { console.warn("warmUp", e); }''')
rep('''.filter(t => (perCity[t[2]] = (perCity[t[2]] || 0) + 1) <= 2).slice(0, 18);''', '''.filter(t => (perCity[t[2]] = (perCity[t[2]] || 0) + 1) <= 2).slice(0, MOBILE ? 6 : 18);''')

# ===== 飛行照實際時間走：手機一忙（每秒不到 20 張）飛行也不會被拖慢 =====
rep('''  const dt = Math.min(clock.getDelta(), 0.05); T += dt; uni.uTime.value = T;''', '''  const rawDt = clock.getDelta(), dt = Math.min(rawDt, 0.05); T += dt; uni.uTime.value = T;''')
rep('''    fly.k = Math.min(1, fly.k + dt / fly.dur); const e = ease(fly.k);''', '''    fly.k = Math.min(1, fly.k + Math.min(rawDt, 0.25) / fly.dur); const e = ease(fly.k);''')

# ===== 天氣標籤：圖示＋溫度＋縣市（＋降雨機率），取代「25° 臺中 晴」的純文字 =====
rep('''addLabel(`${fmt(it.temp, 0)}°<span class="n"> ${esc(nm)} ${esc(it.weather && it.weather !== "-99" ? it.weather : "")}</span>`, new THREE.Vector3(x, hAt(c.c[0], c.c[1]) + 6, z), "", "wx",''',
    '''addLabel(`${wxIcon(it)}<b class="wt">${fmt(it.temp, 0)}°</b><span class="n">${esc(nm)}</span>${wxRain(it)}`, new THREE.Vector3(x, hAt(c.c[0], c.c[1]) + 6, z), "wxl", "wx",''')
