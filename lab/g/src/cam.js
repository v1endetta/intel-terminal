
/* ---- 公路攝影機觀看面板 ----
   電腦：左側一欄（右邊是資訊卡，地圖留在中間）；手機：下方一張小卡，平常收成一顆「攝影機」按鈕。
   一次只播一支（每支都是持續傳的串流，同時開很多支會吃流量）；可以上一支／下一支、鍵盤左右鍵切換。
   地圖上正在看的那支會亮起來，旁邊寫這一段的即時車速。 */
const CAM = { list: [], i: -1, open: false, where: "", user: false };
function camEl() {
  let el = $("camPanel"); if (el) return el;
  el = document.createElement("aside"); el.id = "camPanel"; el.setAttribute("aria-label", "公路即時影像"); document.body.appendChild(el);
  el.addEventListener("click", e => {
    const b = e.target.closest("[data-cp]"); if (!b) return; const a = b.dataset.cp;
    if (a === "x") camClose(); else if (a === "o") { CAM.user = true; camShow(Math.max(0, CAM.i)); } else if (a === "p") camShow(CAM.i - 1); else if (a === "n") camShow(CAM.i + 1);
    else if (a === "f") { const c = CAM.list[CAM.i]; if (c) { const g = gp(c[0], c[1], 0); flyTo(g.clone().add(V(0.6, 0.9, 1.1)), g, 1.4); } }
    else if (a === "r") camShow(CAM.i);
  });
  el.addEventListener("pointerdown", e => e.stopPropagation());
  addEventListener("keydown", e => { if (!CAM.open || /input|textarea/i.test((e.target || {}).tagName || "")) return;
    if (e.key === "ArrowRight") camShow(CAM.i + 1); else if (e.key === "ArrowLeft") camShow(CAM.i - 1); else if (e.key === "Escape") camClose(); });
  return el;
}
// 視角換到新地方時，把附近的攝影機交給面板；正在看的那支會保留在清單最前面
function camSetList(list, opt = {}) {
  const cur = CAM.open ? CAM.list[CAM.i] : null;
  CAM.list = list.slice(0, 20); CAM.where = opt.where || "";
  if (cur) { const k = CAM.list.findIndex(c => c[4] === cur[4]); if (k < 0) CAM.list.unshift(cur); CAM.i = k < 0 ? 0 : k; }
  else CAM.i = CAM.list.length ? 0 : -1;
  if (!CAM.list.length && !CAM.open) return camHide();
  if (!CAM.open && opt.auto && !CAM.closedByUser) camShow(0); else camRender();
}
function camShow(i) {
  if (!CAM.list.length) return;
  CAM.i = (i + CAM.list.length) % CAM.list.length; CAM.open = true; camRender(true);
}
function camClose() { CAM.open = false; CAM.closedByUser = true; clearLabels("camsel"); camRender(); }
function camHide() { CAM.open = false; clearLabels("camsel"); const el = $("camPanel"); if (el) el.className = ""; document.body.classList.remove("cam-on"); }
// 攝影機附近那一段的即時車速（國道、省道、台北市區）
function camSpeed(c) {
  let best = null, bd = 0.8;
  for (const x of trSegs()) if (x.s != null) { const d = kmBetween(x.ll, [c[0], c[1]]); if (d < bd) { bd = d; best = x.s; } }
  if (best == null && sameC((countyAt(c[0], c[1]) || {}).name || "", "臺北市")) for (const x of vdSegs()) { const d = kmBetween([(x[0] + x[2]) / 2, (x[1] + x[3]) / 2], [c[0], c[1]]); if (d < 0.4 && d < bd) { bd = d; best = x[4]; } }
  return best;
}
function camRender(fresh) {
  const el = camEl(), n = CAM.list.length;
  if (!n) { camHide(); return; }
  document.body.classList.toggle("cam-on", CAM.open);
  if (!CAM.open) {   // 收起來：一顆按鈕告訴你附近有幾支
    el.className = "pill"; el.innerHTML = `<button data-cp="o" class="cp-pill"><i></i>${CAM.where ? esc(CAM.where) + " · " : ""}${n} 支公路攝影機</button>`; clearLabels("camsel"); return;
  }
  const c = CAM.list[CAM.i], u = c[4], name = camName(c), sp = camSpeed(c), kind = CAMK[c[2]] || "攝影機";
  const spC = sp == null ? "#8e8e93" : sp >= 60 ? UPH : sp >= 30 ? "#ffd60a" : DNH;
  const hls = /\.m3u8|Showcctv|\.aspx|\.html?(\?|$)/i.test(u), insecure = location.protocol === "https:" && u.startsWith("http:");   // 網頁型的（台中市區）也改成新視窗開
  el.className = "open";
  if (fresh || !el.querySelector(".cp-v")) el.innerHTML = `
    <div class="cp-h"><span class="cp-live"><i></i>即時</span><span class="cp-k">${kind}</span><span class="cp-n">${CAM.i + 1} / ${n}</span><button data-cp="x" aria-label="關閉攝影機">×</button></div>
    <div class="cp-v">${hls || insecure ? `<p class="cp-msg">這支要在新視窗看<br><a href="${esc(u)}" target="_blank" rel="noopener">開啟即時影像 ›</a></p>`
      : `<div class="cp-load">連線中…</div><img class="on" src="${esc(u)}" alt="${esc(name)} 即時影像" referrerpolicy="no-referrer">`}</div>
    <div class="cp-t"><b>${esc(name)}</b><span>${sp != null ? `<em style="color:${spC}">● ${sp} km/h</em>這一段的即時車速` : "這一段沒有即時車速"}</span></div>
    <div class="cp-b"><button data-cp="p" aria-label="上一支">‹ 上一支</button><button data-cp="f">在地圖上找</button><button data-cp="n" aria-label="下一支">下一支 ›</button></div>
    <div class="cp-f">${esc(CAM.where)}附近・${c[2] === "fw" ? "高公局" : "公路局"}・點地圖上的藍點也能切換・← → 鍵</div>`;
  const img = el.querySelector(".cp-v img");
  if (img && fresh) { CAM.ok = false; img.onload = () => { CAM.ok = true; el.querySelector(".cp-load") && el.querySelector(".cp-load").remove(); };
    img.onerror = () => { if (CAM.ok) return;   /* 播過之後的斷線交給接力處理，不要跳錯誤 */ const v = el.querySelector(".cp-v"); if (v) v.innerHTML = `<p class="cp-msg">畫面載不到<br><small>攝影機離線，或人在海外被擋</small><br><button data-cp="r">重試</button>　<a href="${esc(u)}" target="_blank" rel="noopener">直接開啟 ›</a></p>`; }; }
  // 地圖上：正在看的那支亮起來
  clearLabels("camsel");
  addLabel(`<span class="nvcam sel"><i></i></span>`, gp(c[0], c[1], 0.1), "nv camsel", "camsel", 40);
}
// 地圖上的藍點、卡片裡的清單：點了就換到那一支（沒在清單裡的就加進去）
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-cam]"); if (!b) return;
  const u = b.dataset.cam; let k = CAM.list.findIndex(c => c[4] === u);
  if (k < 0) { const ll = (b.dataset.ll || "").split(",").map(Number); CAM.list.unshift([ll[0], ll[1], /thb/.test(u) ? "thb" : "fw", b.dataset.camn || "", u]); k = 0; }
  CAM.closedByUser = false; camShow(k);
});

// 實測（2026-10-13，用你的 Chrome）：高公局、公路局的串流每秒約 5 格，連上約 9 秒（45 格）就被對方切斷，畫面會停住或變黑。
// 對方允許同時開兩條，所以用兩層畫面輪流接力：每 6 秒在下面那層開一條新的，收到第一格就淡入蓋上，再關掉舊的那條。
// 分頁切到背景、面板收起來時就暫停，不浪費流量。
const camURL = u => u + (u.includes("?") ? "&" : "?") + "_=" + Date.now();
CAM.timer = setInterval(() => {
  if (!CAM.open || document.hidden) return;
  const v = document.querySelector("#camPanel .cp-v"), c = CAM.list[CAM.i]; if (!v || !c) return;
  const imgs = [...v.querySelectorAll("img")]; if (!imgs.length) return;
  const front = imgs.find(i => i.classList.contains("on")) || imgs[0];
  let back = imgs.find(i => i !== front);
  if (!back) { back = document.createElement("img"); back.referrerPolicy = "no-referrer"; back.alt = front.alt; v.appendChild(back); }
  back.onerror = null;
  back.onload = () => { if (CAM.list[CAM.i] !== c) return; back.classList.add("on"); front.classList.remove("on"); setTimeout(() => { if (!front.classList.contains("on")) front.removeAttribute("src"); }, 450); };
  back.src = camURL(c[4]);
}, 6000);
