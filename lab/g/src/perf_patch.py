# ===== 手機滑動順暢度 =====
# 1) 畫布固定用「最大可視高度」（100lvh）：iPhone 網址列收合時不再觸發重新配置畫布
rep('const MOBILE = matchMedia("(max-width:760px)").matches || /Mobi|Android/i.test(navigator.userAgent);',
    '''const MOBILE = matchMedia("(max-width:760px)").matches || /Mobi|Android/i.test(navigator.userAgent);
const _lvhEl = document.createElement("div"); _lvhEl.style.cssText = "position:fixed;top:0;left:0;width:0;height:100lvh;visibility:hidden;pointer-events:none"; document.body.appendChild(_lvhEl);
let _VH = 0; const _measureVH = () => { _VH = MOBILE ? Math.max(innerHeight, _lvhEl.offsetHeight || 0) : innerHeight; }; _measureVH();
const VH = () => _VH;''')
_head, _sep, _mod = src.rpartition('<script type="module">')
_body, _end, _tail = _mod.partition('</script>')
_n = _body.count('innerHeight')
_body = _body.replace('innerHeight', 'VH()').replace('Math.max(VH(), _lvhEl.offsetHeight || 0) : VH()', 'Math.max(innerHeight, _lvhEl.offsetHeight || 0) : innerHeight')
src = _head + _sep + _body + _end + _tail
print('innerHeight → VH():', _n - 2)
# 尺寸真的變了（轉向、改視窗）才重新配置畫布和後製
rep('addEventListener("resize", () => { if (composer) { composer.setSize(innerWidth, VH()); bloom.resolution.set(innerWidth * (MOBILE ? 0.5 : 1), VH() * (MOBILE ? 0.5 : 1)); } });', '')
rep('addEventListener("resize", () => { camera.aspect = innerWidth / VH(); camera.updateProjectionMatrix(); renderer.setSize(innerWidth, VH()); });',
    '''let _rsW = innerWidth, _rsH = VH();
addEventListener("resize", () => { _measureVH(); const w = innerWidth, h = VH(); if (w === _rsW && h === _rsH) return; _rsW = w; _rsH = h;
  camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
  if (composer) { composer.setSize(w, h); bloom.resolution.set(w * (MOBILE ? 0.5 : 1), h * (MOBILE ? 0.5 : 1)); } });''')
rep('#stage{position:fixed;inset:0;', '@media (max-width:760px){#stage,#ihud,#leaderSvg{bottom:auto!important;height:100lvh!important}}\n#stage{position:fixed;inset:0;')

# 2) 鏡頭跟著捲動「平滑追上」，手指滑動的抖動不會直接變成畫面跳動
rep('const N = CH.length, y = scrollY / secH(),', '''const yRaw = scrollY / secH(); ST.ys = (ST.ys == null || Math.abs(yRaw - ST.ys) > 1.5) ? yRaw : ST.ys + (yRaw - ST.ys) * Math.min(1, dt * (MOBILE ? 7 : 10));
  const N = CH.length, y = ST.ys,''')

# 3) 手機白天不跑光暈後製（白天光暈強度只有 0.08，看不出差別，卻要多畫好幾張全螢幕圖）
rep('  if (FX.on && composer) {', '  if (FX.on && composer && !(MOBILE && !uni.uNight.value && !uni.uScanOn.value)) {')

# 4) 引線不必每格都量面板位置
rep('r = $("side").getBoundingClientRect();', 'r = (performance.now() - (leader._t || 0) < 300 && leader._r) || (leader._t = performance.now(), leader._r = $("side").getBoundingClientRect());')

# 5) 航照：解碼移到背景執行緒（ImageBitmap）、離開不馬上丟（留快取），避免來回捲動一直重載
rep('function _otex(url) { const t = OTEX_LOADER.load(url); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy()); return t; }',
    '''const OBMP = typeof createImageBitmap !== "undefined" ? new THREE.ImageBitmapLoader().setOptions({ imageOrientation: "none", premultiplyAlpha: "none" }) : null;
const OBMP_S = OBMP && new THREE.ImageBitmapLoader().setOptions({ imageOrientation: "none", premultiplyAlpha: "none", resizeWidth: 1024, resizeHeight: 1024, resizeQuality: "high" });   // 手機的全島底圖縮成 1024，顯示記憶體少 3/4
function _otex(url, small) {   // 一律不翻轉影像，改在貼圖座標翻；兩種載入方式結果一致
  let t; const done = () => { t.userData.ready = true; (t.userData.cbs || []).forEach(f => f(t)); };
  if (OBMP) { t = new THREE.Texture(); (small ? OBMP_S : OBMP).load(url, bmp => { t.image = bmp; t.needsUpdate = true; done(); }); }
  else t = OTEX_LOADER.load(url, done);
  t.flipY = false; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = Math.min(MOBILE ? 2 : 8, renderer.capabilities.getMaxAnisotropy());
  t.repeat.set(1, -1); t.offset.set(0, 1); return t;
}''')
rep('{ vec3 roofC = texture2D(uOrtho, vRUV).rgb;', '{ vec3 roofC = texture2D(uOrtho, vec2(vRUV.x, 1.0 - vRUV.y)).rgb;')
rep('vec3 bodyC = texture2D(uOrtho, vCUV, 3.0).rgb;', 'vec3 bodyC = texture2D(uOrtho, vec2(vCUV.x, 1.0 - vCUV.y), 3.0).rgb;')
rep('''    for (const k of want) if (!ORTHO.patches.has(k)) ORTHO.patches.set(k, orthoPatch(k));
    for (const k of [...ORTHO.patches.keys()]) if (!want.has(k)) orthoDrop(k);''',
    '''    for (const k of want) if (!ORTHO.patches.has(k)) ORTHO.patches.set(k, orthoPatch(k));   // 照片在背景解碼，抵達時間自然錯開
    const cap = want.size + (MOBILE ? 2 : 6), old = [...ORTHO.patches.keys()].filter(k => !want.has(k));
    old.sort((a, b) => dist(orthoQ(b)) - dist(orthoQ(a)));   // 超過上限才丟，先丟最遠的
    while (ORTHO.patches.size > cap && old.length) orthoDrop(old.shift());''')
# 快取裡、這次用不到的塊先藏起來
rep('for (const m of ORTHO.patches.values()) { const o = m.userData.city ? op : _baseOp; m.material.opacity = o; m.visible = o > 0.01; }',
    'for (const [k, m] of ORTHO.patches) { const o = m.userData.city ? op : _baseOp; m.material.opacity = o; m.visible = o > 0.01 && (!ORTHO.want || ORTHO.want.has(k)); }')
rep('    const want = new Set(), hi = new Set();', '    const want = new Set(), hi = new Set(); ORTHO.want = want;')

# 高解析版載好才換上去（不然換的瞬間會黑一塊）；還沒載好的塊先不顯示
rep('  if (on && !ORTHO.hi.has(key)) { const t = _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}.jpg?v=${ASSET_V}`); ORTHO.hi.set(key, t); orthoUni(key).value = t; const p = ORTHO.patches.get(key); if (p) p.material.map = t; }',
    '  if (on && !ORTHO.hi.has(key)) { const t = _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}.jpg?v=${ASSET_V}`); ORTHO.hi.set(key, t); (t.userData.cbs = t.userData.cbs || []).push(() => { if (ORTHO.hi.get(key) !== t) return; orthoUni(key).value = t; const p = ORTHO.patches.get(key); if (p) p.material.map = t; }); }')
rep('m.visible = o > 0.01 && (!ORTHO.want || ORTHO.want.has(k)); }', 'm.visible = o > 0.01 && (!ORTHO.want || ORTHO.want.has(k)) && !!(m.material.map && m.material.map.userData.ready); }')
rep('has = [...ORTHO.patches.values()].some(m => m.userData.city) && op > 0.5;', 'has = [...ORTHO.patches].some(([k, m]) => m.userData.city && m.visible) && op > 0.5;')
rep('let _otT = 0, _baseOp = 0;', 'let _otT = 0, _baseOp = 0; window.__ortho = ORTHO;')

rep('function orthoLo(key) { if (!ORTHO.lo.has(key)) ORTHO.lo.set(key, _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}_m.jpg?v=${ASSET_V}`)); return ORTHO.lo.get(key); }',
    'function orthoLo(key) { if (!ORTHO.lo.has(key)) ORTHO.lo.set(key, _otex(`ortho/${orthoDir(key)}/${orthoQ(key).id}_m.jpg?v=${ASSET_V}`, MOBILE && key.startsWith("base:"))); return ORTHO.lo.get(key); }')
# 手機：市區照片 3 塊就夠蓋住畫面
rep('.filter(o => o.d < 14).sort((a, b) => a.d - b.d).slice(0, MOBILE ? 4 : 9)', '.filter(o => o.d < 14).sort((a, b) => a.d - b.d).slice(0, MOBILE ? 3 : 9)')
# 航班標籤：被地球擋住時藏起來
rep('if (!L.on) { L.el.style.opacity = 0; continue; }', 'if (!L.on || L.hide) { L.el.style.opacity = 0; continue; }')
# 航班地球：夜間光暈減弱（八十條航線疊加會整片過曝）
rep('bloom.strength = (nt ? 0.85 : 0.08)', 'bloom.strength = (nt ? (ST.globeForce ? 0.32 : 0.85) : 0.08)')
