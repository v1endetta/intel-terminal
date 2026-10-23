
/* ---- 手機：順暢＋好操作 ----
   1. 張數：手機動的時候每秒 30 張、靜止 2 秒後降到每秒 12 張（不熱、不降頻）；分頁切到背景本來就停
   2. 卡片改成底部抽屜（像 Apple 地圖）：平常只露標題和大數字，點一下或往上滑展開，往下滑收起
   3. 地圖主體往上移，不被抽屜擋住 */
if (MOBILE) {
  const FR = { last: 0, still: 0, cam: "" };
  const _loopM = loop;
  loop = function () {
    const now = performance.now(), e = camera.matrixWorld.elements, k = `${e[12].toFixed(3)},${e[13].toFixed(3)},${e[14].toFixed(3)},${e[2].toFixed(4)}`;
    const moving = k !== FR.cam || fly || GD.ptrs.size || Math.abs(GD.vx) > 0.05 || ST.on && !ST.explore || INTRO.on;
    if (moving) FR.still = now; FR.cam = k;
    const gap = now - FR.still > 2000 ? 80 : 30;
    if (now - FR.last < gap) { requestAnimationFrame(loop); return; }
    FR.last = now; _loopM();
  };
  // 自己逛的時候，地圖的中心往上移一點（下方是抽屜和分類列）
  setInterval(() => { if (!ST.explore || ST.globeForce) return; const oy = Math.round(VH() * 0.09);
    if (!camera.view || camera.view.offsetY !== oy || camera.view.fullHeight !== VH()) camera.setViewOffset(innerWidth, VH(), 0, oy, innerWidth, VH()); }, 500);
  // 抽屜：往上滑展開、往下滑收起
  const SW = { y: 0, t: 0 };
  document.addEventListener("touchstart", e => { if (e.target.closest && e.target.closest("#side")) { if (typeof lpopClose === "function") lpopClose(); SW.y = e.touches[0].clientY; SW.t = performance.now(); SW.top = $("side").scrollTop; } }, { passive: true });
  document.addEventListener("touchend", e => { const sd = e.target.closest && e.target.closest("#side"); if (!sd || !SW.t) return; const dy = e.changedTouches[0].clientY - SW.y; SW.t = 0;
    if (dy < -30 && !sd.classList.contains("open")) { sd.classList.add("open"); SW.swiped = performance.now(); }
    else if (dy > 40 && sd.classList.contains("open") && (SW.top || 0) <= 2) { sd.classList.remove("open"); SW.swiped = performance.now(); } }, { passive: true });
  window.__swipedAt = () => SW.swiped || 0;
}
// 開場暖機：地球照片先傳到顯示卡、所有材質先編譯，開場動畫就不會在中途卡一下（手機最明顯）
async function warmUp() {
  if (typeof buildEarth === "function") buildEarth();
  const texs = [];
  if (EARTH.mat) texs.push(EARTH.mat.uniforms.uDay.value, EARTH.mat.uniforms.uNightT.value);
  if (GLOBE && GLOBE.mat) texs.push(GLOBE.mat.uniforms.uDay.value, GLOBE.mat.uniforms.uNight.value);
  const t0 = performance.now();
  while (texs.some(t => !t || !t.image || (t.image.complete === false)) && performance.now() - t0 < 6000) await new Promise(r => setTimeout(r, 80));
  for (const t of texs) if (t && t.image) renderer.initTexture(t);
  const show = [EARTH.g, GLOBE && GLOBE.g].filter(Boolean).map(g => [g, g.visible]); show.forEach(([g]) => { g.visible = true; });
  try { if (renderer.compileAsync) await Promise.race([renderer.compileAsync(scene, camera), new Promise(r => setTimeout(r, 4000))]); else renderer.compile(scene, camera); } catch (e) { }
  show.forEach(([g, v]) => { g.visible = v; });
}

// 底部項目列：只在還有東西可以滑的那一邊淡出（第一顆不會被切一半，最後面還有東西時看得出來）
function chipEdges() {
  const c = $("chips"); if (!c) return false;
  const f = () => { c.classList.toggle("at0", c.scrollLeft < 4); c.classList.toggle("at1", c.scrollLeft + c.clientWidth > c.scrollWidth - 4); };
  c.addEventListener("scroll", f, { passive: true }); addEventListener("resize", f);
  new MutationObserver(() => requestAnimationFrame(f)).observe(c, { childList: true });
  f(); return true;
}
{ const _ce = setInterval(() => { if (chipEdges()) clearInterval(_ce); }, 400); }
