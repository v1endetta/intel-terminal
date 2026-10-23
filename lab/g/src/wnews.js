
/* ---- 全球新聞：國際媒體標題翻成台灣用語中文，依發生地點放到地球上 ----
   點的大小＝那個地方的新聞則數，顏色＝類別；點標籤看那裡的每一則（中文＋原文＋連結）。 */
const WN_C = { 戰爭衝突: "#ff453a", 政治: "#bf5af2", 經濟: "#30d158", 科技: "#64d2ff", 災害: "#ff9f0a", 社會: "#aeaeb2", 其他: "#aeaeb2" };
const WN = () => (((P.worldnews || {}).items) || []);
function wnGroups() {
  const g = new Map();
  for (const x of WN()) { if (!x.ll) continue; const k = x.place || `${x.ll[1]},${x.ll[0]}`; if (!g.has(k)) g.set(k, { place: x.place, ll: x.ll, xs: [] }); g.get(k).xs.push(x); }
  for (const G of g.values()) { G.tw = Math.max(...G.xs.map(x => x.tw || 0)); G.ns = Math.max(...G.xs.map(x => x.n_src || 1)); }
  return [...g.values()].sort((a, b) => (b.tw + 0.8 * (b.ns - 1)) - (a.tw + 0.8 * (a.ns - 1)) || b.xs.length - a.xs.length);
}
const WN_HAS_TW = () => WN().some(x => x.tw != null);   // 新版資料才有「對台灣的影響」分數
const twTag = x => (x.tw || 0) >= 4 ? "重大影響" : (x.tw || 0) >= 3 ? "影響台灣" : (x.tw || 0) >= 2 ? "值得留意" : "";
const wnRow = x => ({ t: x.t || x.en, s: [x.src, x.place, x.at ? navAgo(x.at) : ""].filter(Boolean).join("・"), url: x.url });
function gxNews() {
  clearLabels("gx"); GX.lbls = []; GX.rings = [];
  for (const G of wnGroups()) {
    const cat = (G.xs.find(x => x.cat === "戰爭衝突") || G.xs[0]).cat, col = WN_C[cat] || "#aeaeb2", n = G.xs.length;
    const dot = new THREE.Mesh(new THREE.SphereGeometry(WN_HAS_TW() ? 34 + 26 * Math.min(5, Math.max(G.tw, (G.ns - 1) * 0.8)) + 8 * Math.min(3, n - 1) : 40 + 22 * Math.min(4, n), 16, 12), fm(new THREE.MeshBasicMaterial({ color: col, depthTest: true }), 0.95));
    dot.position.copy(GLOBE.G(G.ll[0], G.ll[1], 30)); GX.g.add(dot);
    GX.lbls.push([addLabel(`<span class="gxl"><b>${esc(G.place || "")}</b><em>${n > 1 ? n + " 則" : esc((G.xs[0].t || "").slice(0, 14))}</em></span>`, GLOBE.G(G.ll[0], G.ll[1], 200), "gx", "gx", 2 + n + 3 * (G.tw || 0) + 2 * (G.ns - 1), () => ({
      html: `<i class="lp-k" style="color:${col}">全球新聞・${esc(G.place || "")}</i>${G.xs.slice(0, 5).map(x => `<p style="margin-top:8px"><b style="font-size:13px">${esc(x.t || x.en)}</b>${(x.n_src || 1) > 1 ? `<span style="display:block;font-size:11.5px;color:#64d2ff;margin-top:2px">${x.n_src} 家報導：${esc((x.srcs || []).join("、"))}</span>` : ""}${x.why ? `<span style="display:block;font-size:12px;color:#ffd60a;margin-top:2px">跟台灣：${esc(x.why)}</span>` : ""}${x.t ? `<span style="display:block;font-size:11px;color:#8e8e93">${esc(x.en)}</span>` : ""}<span style="display:block;font-size:11px;color:#aeaeb2">${esc(x.src)}・${x.at ? navAgo(x.at) : ""}　<a href="${esc(x.url)}" target="_blank" rel="noopener" style="margin:0">原文 ›</a></span></p>`).join("")}` })), GLOBE.G(G.ll[0], G.ll[1], 0)]);
  }
}
function wnCard() {
  const xs = WN(), W = P.worldnews || {}, gs = wnGroups();
  if (!xs.length) return { layer: "gx", gx: "wnews", html: sideHTML({ eyebrow: "輿情 · 全球新聞", title: "世界正在發生什麼？", body: '<p class="empty">全球新聞下一輪更新後出現（每小時一次）。</p>' }) };
  if (WN_HAS_TW()) {   // 依「對台灣的影響」排：標題直接放影響最大的那一則
    const top = xs[0], hi = xs.filter(x => (x.tw || 0) >= 3).length, big = xs.filter(x => (x.n_src || 1) >= 3).length, head = (top.t || top.en || "");
    return { layer: "gx", gx: "wnews", html: sideHTML({ eyebrow: `輿情 · 全球新聞 · ${[hi ? `${hi} 則影響台灣` : "", big ? `${big} 件多家同報` : ""].filter(Boolean).join("・") || "今天沒有直接影響台灣的大事"}`, title: "今天國外哪件事會影響台灣？", big: head.length > 22 ? head.slice(0, 21) + "…" : head, color: (top.tw || 0) >= 3 ? "#ffd60a" : "#bf5af2",
      body: (top.why ? `<p class="why" style="color:#ffd60a">跟台灣：${esc(top.why)}</p>` : "") + ((top.n_src || 1) > 1 ? `<p class="why" style="color:#64d2ff">${top.n_src} 家報導：${esc((top.srcs || []).join("、"))}</p>` : "")
        + vzFig(vzBubbles(xs.slice(0, 18), x => WN_C[x.cat] || "#aeaeb2"), [...new Set(xs.slice(0, 18).map(x => x.cat))].map(c => `<i class="vzk" style="background:${WN_C[c] || "#aeaeb2"}"></i>${esc(c)}`).join("　") + "・泡泡越大越多家報，數字對應下面的排名")
        + `<p class="why">九家英美、亞洲媒體，依跟台灣的關係和幾家同時在報排序，越舊越後面。點越大越重要，紅色是戰爭衝突。</p>`
        + `<ul class="lst wnl">${xs.slice(0, 18).map((x, i) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${i < 8 ? `<i class="rk">${i + 1}</i>` : ""}${(x.n_src || 1) >= 2 ? `<i class="srcn${x.n_src >= 3 ? " big" : ""}">${x.n_src} 家報導</i>` : ""}${twTag(x) ? `<i class="twt t${Math.min(4, x.tw)}">${twTag(x)}</i>` : ""}${esc(x.t || x.en)}</a>${x.why ? `<em class="tww">${esc(x.why)}</em>` : ""}<span>${esc([(x.srcs && x.srcs.length > 1 ? x.srcs.join("、") : x.src), x.place, x.at ? navAgo(x.at) : ""].filter(Boolean).join("・"))}</span></li>`).join("")}</ul>`
        + (W.n_zh < xs.length ? `<p class="why">有 ${xs.length - W.n_zh} 則還沒翻譯，先顯示原文。</p>` : "") }) };
  }
  return { layer: "gx", gx: "wnews", html: sideHTML({ eyebrow: "輿情 · 全球新聞 · 翻成中文", title: "世界正在發生什麼？", big: gs[0] && gs[0].xs.length > 1 ? `${gs[0].place} ${gs[0].xs.length} 則` : `${xs.length} 則國際新聞`, color: "#bf5af2",
    body: `<p class="why">BBC、半島電視台、NPR、衛報最新的國際新聞，翻成台灣用語；地球上的點是發生地點，越大則數越多，紅色是戰爭衝突。</p>` + listHTML(xs.slice(0, 18).map(wnRow))
      + (W.n_zh < xs.length ? `<p class="why">有 ${xs.length - W.n_zh} 則還沒翻譯，先顯示原文。</p>` : "") }) };
}
