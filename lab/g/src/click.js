
/* ---- 地圖上看得到的東西都能點 ----
   資料點（路況、新聞、藝文、重大訊息…）：跳出小卡（標題、來源、距離、原文連結），鏡頭拉近到那裡。
   縣市、行政區的名稱：直接進到那一層。地球上的節點、交易所：跳出那一個的數字。
   其他（天氣、地震、航班…）：拉近到那裡，並把標籤上的字放大顯示。 */
function lpopEl() {
  let el = $("lpop"); if (el) return el;
  el = document.createElement("div"); el.id = "lpop"; el.setAttribute("role", "dialog"); document.body.appendChild(el);
  el.addEventListener("click", e => { if (e.target.closest("[data-lp=x]")) lpopClose(); else if (e.target.closest("[data-lp=go]") && LPGO.fn) { const f = LPGO.fn; lpopClose(); f(); } });
  el.addEventListener("pointerdown", e => e.stopPropagation());
  return el;
}
const LPGO = { fn: null };
function lpop(html, r, go, goTxt) {
  LPGO.fn = go || null;
  const el = lpopEl(); el.innerHTML = `<button data-lp="x" aria-label="關閉">×</button>${html}${go ? `<button data-lp="go" class="lp-go">${esc(goTxt || "拉近看")} ›</button>` : ""}`; el.classList.add("on");
  const w = el.offsetWidth, h = el.offsetHeight, x = Math.min(innerWidth - w - 12, Math.max(12, r.left + r.width / 2 - w / 2)), top0 = 104, y = r.top - h - 10 > top0 ? r.top - h - 10 : Math.max(top0, Math.min(innerHeight - h - 12, r.bottom + 10));   // 不蓋住上方的「地球／台灣」切換
  el.style.left = x + "px"; el.style.top = y + "px";
}
function lpopClose() { const el = $("lpop"); if (el) el.classList.remove("on"); }
renderer.domElement.addEventListener("pointerdown", lpopClose);
addEventListener("keydown", e => { if (e.key === "Escape") lpopClose(); });
document.addEventListener("click", e => { if (e.target.closest && e.target.closest("#chips, #dock2 .seg, #crumb, #gcrumb, #side")) lpopClose(); });
function flyNear(pos, d) {   // 拉近到那個位置（已經夠近就不動距離，只把它移到中間）
  if (GD.on || !ST.explore) return;
  const cur = camera.position.distanceTo(controls.target), D = Math.min(cur, d), tgt = pos.clone(); tgt.y = 0;
  flyTo(tgt.clone().add(V(0, D * 0.78, D * 0.62)), tgt, 1.3);
}
const lpLink = u => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">看原文 ›</a>` : "";
// 每個標籤可以帶第 6 個參數：點的時候要顯示什麼（函式，點了才算，資料永遠是最新的）
const _addLabel0 = addLabel;
addLabel = function (html, pos, cls, group, prio, info) { const L = _addLabel0(html, pos, cls, group, prio); if (info) L.info = info; return L; };
// 天氣：氣象署測站＋縣市預報＋警特報
function wxInfo(it, c) {
  const f = (it.forecast || []).slice(0, 2), warn = (((P.weather || {}).warnings) || []).filter(w => norm(w.where) === norm(c.name));
  return { html: `<i class="lp-k" style="color:#64d2ff">天氣・氣象署 ${esc(it.station || "")}站</i><b>${esc(norm(c.name))} ${(+it.temp).toFixed(1)}°C ${esc(it.weather && it.weather !== "-99" ? it.weather : "")}</b>`
    + `<p>濕度 ${it.rh ?? "—"}%・風 ${it.wind ?? "—"} m/s・今天雨量 ${it.rain24h ?? 0} mm${it.uv != null ? "・紫外線 " + it.uv : ""}</p>`
    + f.map(x => `<p>${esc(x.start)} 起：${esc(x.wx)}，${esc(x.minT)}–${esc(x.maxT)}°C，降雨機率 ${esc(x.pop)}%</p>`).join("")
    + (warn.length ? `<p style="color:#ff9f0a">${warn.map(w => esc(w.what + (w.level || ""))).join("、")}</p>` : "")
    + (it.obsTime ? `<p>觀測時間 ${esc(String(it.obsTime).slice(11, 16))}</p>` : "") + lpLink("https://www.cwa.gov.tw/V8/C/W/County/index.html").replace("看原文", "氣象署縣市預報"), go: () => navGoCounty(c), goTxt: "看這個縣市" };
}
// 地震：氣象署地震報告
function quakeInfo(q) {
  return { html: `<i class="lp-k" style="color:#ff9f0a">地震・氣象署第 ${esc(String(q.no || ""))} 號</i><b>規模 ${q.mag}・深度 ${q.depth} 公里</b><p>${esc(q.loc || "")}</p><p>${new Date(q.at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}（${ago(q.at)}）・最大震度 ${esc(q.intensity || "—")}</p>${lpLink(q.url)}`,
    go: () => flyNear(gp(q.lon, q.lat, 0), 30), goTxt: "看震央" };
}
// 縣市、行政區的小標籤：數字＋右邊清單裡同一列的細節，按鈕進到那一層
function pillInfo(nm, sub, el) {
  const T = NAV.county && (NAV.towns || []).find(t => t.name === nm && sameC(t.county, NAV.county.name)), C = !T && COUNTIES.find(c => norm(c.name) === norm(nm));
  const li = [...document.querySelectorAll("#side [data-nt], #side [data-nc]")].find(b => norm(b.dataset.nt || b.dataset.nc) === norm(nm));
  const det = li ? [...li.querySelectorAll("span")].filter(x => !x.classList.contains("sdot")).map(x => x.textContent).join("・") : "";
  const LZ = LENS[NAV.lens] || LENS.now, here = (T && NAV.town && NAV.town.name === T.name && NAV.level === 2) || (C && NAV.county && sameC(NAV.county.name, C.name) && NAV.level === 1);
  const big = el.querySelector(".nvp.big");
  return { html: `<i class="lp-k" style="color:${LZ.c}">${esc(LZ.n)}${T ? "・" + esc(norm(T.county)) : ""}</i><b>${esc(nm)}</b>${sub ? `<p>${esc(sub)}</p>` : ""}${det && det !== sub ? `<p>${esc(det)}</p>` : ""}${big ? "<p>完整數字在右邊的卡片。</p>" : ""}`,
    go: here || big ? null : T ? () => navGoTown(T) : C ? () => navGoCounty(C) : null, goTxt: T ? "進入這一區" : "進入這個縣市" };
}
document.addEventListener("click", e => {
  const el = e.target.closest && e.target.closest("#labels .lbl"); if (!el || el.classList.contains("lhid")) return;
  if (e.target.closest("[data-cam]")) return;   // 攝影機：由攝影機面板處理
  const L = LBL.find(l => l.el === el); if (!L) return;
  const r = el.getBoundingClientRect(), txt = el.textContent.replace(/\s+/g, " ").trim();
  if (L.info) { let o = null; try { o = L.info(); } catch (err) { console.warn(err); } if (o) { lpop(o.html, r, o.go, o.goTxt); return; } }
  // 資料點
  const pe = el.querySelector("[data-pin]"), it = pe && (NAV.pins || [])[+pe.dataset.pin];
  if (it) {
    const cams = it.cam && camsNear(it.ll, 2);
    lpop(`${it.k ? `<i class="lp-k" style="color:${it.c}">${esc(it.k)}</i>` : ""}<b>${esc(it.t)}</b>${it.s ? `<p>${esc(it.s)}</p>` : ""}${it.d2 ? `<p>${esc(it.d2)}</p>` : ""}${it.desc ? `<p class="lp-desc">${esc(String(it.desc).slice(0, 220))}…</p>` : ""}${it.d != null ? `<p>距離鏡頭中心 ${dist(it.d)}</p>` : ""}${lpLink(it.url)}`, r,
      cams && cams.length ? () => { camSetList(cams.map(x => x.c), { where: "這裡" }); CAM.closedByUser = false; camShow(0); } : () => flyNear(gp(it.ll[0], it.ll[1], 0), 3), cams && cams.length ? `看附近的攝影機（${cams.length}）` : "拉近到這裡");
    return;
  }
  // 交易所（市場時鐘）
  const mx = el.querySelector("[data-mx]");
  if (mx) { const x = MKX.find(m => m.k === mx.dataset.mx), s = x && mkStatus(x), now = Date.now();
    if (x) { const H = Object.entries(mkHol()[x.k] || {}).filter(([d]) => d >= tpeDay(now)).slice(0, 3);
      lpop(`<b>${esc(x.n)}・${esc(x.c)}</b><p style="color:${MK_ST[s.st][0]}">${MK_ST[s.st][1]}${s.why ? "・" + esc(s.why) : ""}</p><p>交易時間（當地）${x.s.map(a => a.join("–")).join("、")}</p>${s.until ? `<p>${s.st === "open" ? "收盤" : "下次開盤"}：台北 ${whenTxt(s.until)}（${inTxt(s.until - now)}後）</p>` : ""}${H.length ? `<p>接下來休市：${H.map(([d, n]) => `${mdW(d)} ${esc(n)}`).join("、")}</p>` : ""}`, r); }
    return; }
  // 地球上的節點
  const gx = el.querySelector("[data-gx]"), n = gx && GX.spec && GX.spec.nodes[+gx.dataset.gx];
  if (n) { lpop(`<i class="lp-k">${esc(GX.spec.title || "")}</i><b>${esc(n.name)}</b>${n.chg != null ? `<p style="color:${n.chg >= 0 ? UPH : DNH}">${gxPct(n.chg)}</p>` : n.w ? `<p>最近 ${n.w} 則動態</p>` : ""}${n.sub ? `<p>${esc(n.sub)}</p>` : ""}`, r); return; }
  // 縣市、行政區名稱
  const nm = ((el.querySelector(".nvp b") || {}).textContent || "").trim();
  if (nm && ST.explore && !GD.on) { const o = pillInfo(nm, ((el.querySelector(".nvp em") || {}).textContent || "").trim(), el); lpop(o.html, r, o.go, o.goTxt); return; }
  // 其他：放大顯示＋拉近
  lpop(`<b>${esc(txt)}</b>`, r, GD.on ? null : () => flyNear(L.pos, Math.max(4, camera.position.distanceTo(controls.target) * 0.45)), "拉近看");
});
// ---- 天氣狀態圖示：晴／晴時多雲／多雲／陰／雨／雷雨／霧，晚上的晴換成月亮 ----
const WXI = {
  sun: '<circle cx="12" cy="12" r="4.6" fill="#ffd60a"/><g stroke="#ffd60a" stroke-width="2" stroke-linecap="round"><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></g>',
  moon: '<path d="M15.5 3.5a8.5 8.5 0 1 0 5 13.6A7 7 0 0 1 15.5 3.5z" fill="#f2e3a0"/>',
  cloud: '<path d="M7 18.5h10.2a4.3 4.3 0 0 0 .5-8.6A6 6 0 0 0 6.2 11a3.8 3.8 0 0 0 .8 7.5z" fill="#d1d1d6"/>',
  part: '<circle cx="8.5" cy="8.5" r="3.6" fill="#ffd60a"/><g stroke="#ffd60a" stroke-width="1.7" stroke-linecap="round"><path d="M8.5 1.8v1.6M1.8 8.5h1.6M3.8 3.8l1.1 1.1M13.2 3.8l-1.1 1.1"/></g><path d="M8.6 20h9.2a3.8 3.8 0 0 0 .4-7.6 5.3 5.3 0 0 0-10.1 1.2 3.3 3.3 0 0 0 .5 6.4z" fill="#d1d1d6"/>',
  partn: '<path d="M10 2.5a6 6 0 1 0 3.6 9.7A5 5 0 0 1 10 2.5z" fill="#f2e3a0"/><path d="M8.6 20h9.2a3.8 3.8 0 0 0 .4-7.6 5.3 5.3 0 0 0-10.1 1.2 3.3 3.3 0 0 0 .5 6.4z" fill="#d1d1d6"/>',
  rain: '<path d="M7 14.5h10.2a4.1 4.1 0 0 0 .5-8.2A5.8 5.8 0 0 0 6.3 7.3 3.6 3.6 0 0 0 7 14.5z" fill="#aeb4bf"/><g stroke="#64d2ff" stroke-width="2" stroke-linecap="round"><path d="M8.5 17l-1 3M12.5 17l-1 3M16.5 17l-1 3"/></g>',
  storm: '<path d="M7 14h10.2a4.1 4.1 0 0 0 .5-8.2A5.8 5.8 0 0 0 6.3 6.8 3.6 3.6 0 0 0 7 14z" fill="#8e94a0"/><path d="M12.8 13.5l-3 5h2.6l-1.4 4.3 4.2-6h-2.7l1.6-3.3z" fill="#ffd60a"/>',
  fog: '<g stroke="#c7c7cc" stroke-width="2" stroke-linecap="round"><path d="M4 8h16M6 12h12M4 16h16"/></g>',
};
function wxKind(txt, night) {
  const s = String(txt || "");
  if (/雷/.test(s)) return "storm";
  if (/雨/.test(s)) return "rain";
  if (/霧/.test(s)) return "fog";
  if (/陰/.test(s) || /多雲/.test(s) && !/晴/.test(s)) return "cloud";
  if (/多雲|雲/.test(s)) return night ? "partn" : "part";
  return night ? "moon" : "sun";
}
function wxIcon(it) {
  const txt = it.weather && it.weather !== "-99" ? it.weather : ((it.forecast || [])[0] || {}).wx, h = +String(it.obsTime || "").slice(11, 13);
  const night = isFinite(h) ? h >= 18 || h < 6 : false, k = wxKind(txt, night);
  return `<svg class="wxi" viewBox="0 0 24 24" aria-label="${esc(txt || "")}">${WXI[k]}</svg>`;
}
function wxRain(it) {   // 接下來 12 小時的降雨機率，30% 以上才標
  const pop = Math.max(0, ...(it.forecast || []).slice(0, 2).map(f => +f.pop || 0));
  return pop >= 30 ? `<i class="wxp">雨 ${pop}%</i>` : "";
}
