
/* ---- 本月洞見：程式算訊號、Gemini 寫句子（數字都對過原始資料）；有地點的可以直接飛過去看 ---- */
function insightsCard() {
  const D = P.insights || {}, xs = D.items || [];
  if (!xs.length) return { html: sideHTML({ eyebrow: "走向 · 本月洞見", title: "資料告訴我們什麼？", body: '<p class="empty">洞見每天整理一次，下一輪更新後出現。</p>' }) };
  return { html: sideHTML({ eyebrow: `走向 · 本月洞見 · 交叉比對 ${D.n_sources || ""} 份資料`, title: "資料告訴我們什麼？", big: xs[0].title, color: "#ffd60a",
    body: `<p class="why">人口遷徙、診所、新公司、新興生意、物價、消費放在一起看。訊號由程式算，句子由 AI 寫，每個數字都對過原始資料，對不上的就不放。</p>`
      + xs.map((x, i) => `<div class="ins"><div class="ins-tags">${(x.tags || []).map(t => `<i>${esc(t)}</i>`).join("")}</div><b>${esc(x.title)}</b><p>${esc(x.body)}</p>`
        + (x.why ? `<p class="ins-so">${esc(x.why)}</p>` : x.so ? `<p class="ins-so">${esc(x.so)}</p>` : "") + (x.place ? `<button type="button" class="ins-go" data-insgo="${i}">在地圖上看 ${esc(x.place)} ›</button>` : "") + `</div>`).join("") }) };
}
document.addEventListener("click", e => {
  const g = e.target.closest && e.target.closest("[data-insgo]");
  if (g) {
    const x = ((P.insights || {}).items || [])[+g.dataset.insgo]; if (!x) return;
    const t = (NAV.towns || []).find(t => norm(t.county) + t.name === norm(x.place)) || (NAV.towns || []).find(t => norm(x.place).endsWith(t.name) && norm(x.place).startsWith(norm(t.county).slice(0, 2)));
    navSetLens(x.lens || "now"); if (t) navGoTown(t);
    return;
  }
  if (e.target.closest && e.target.closest("[data-ins]") && ST.openAt) ST.openAt("走向", "本月洞見");
  if (e.target.closest && e.target.closest("[data-thz]") && ST.openAt) ST.openAt("走向", "論點追蹤");
});

/* ---- 各分類洞見：只用這一類的資料寫 2～3 條 ---- */
const INS_SRC_ZH = { taiex: "台股", tw_market: "法人", world: "全球股市", fx: "匯率", fear: "恐慌", commodities: "原物料", luxury: "精品", sectors: "類股", revenue: "營收",
  macro: "景氣", prices: "物價", veg: "菜價", oil: "油價", tourism: "觀光", liquidity: "美元流動性", consume: "消費", gmacro: "全球總經", house: "房價", cards: "刷卡", cars: "新車", permits: "建照", gap: "台灣還沒報", demo: "人口", bizlife: "公司生滅",
  weekly: "本週走向", voice: "趨勢雷達", chain: "主題鏈", wiki: "主題熱度", migration: "人口遷徙", attention: "注意力",
  jobs: "職缺", taxreg: "新興生意", grants: "補助", tenders: "標案", radar: "公司雷達", clinics: "診所", brands: "新公司", aiwire: "AI 快線",
  mood: "情緒", ptt: "PTT", trends: "熱搜", cofacts: "謠言", gtop: "焦點新聞", worldnews: "全球新聞",
  weather: "天氣", quake: "地震", power: "電力", alerts: "示警", plaact: "台海", cables: "海纜", airport: "機場", typhoon: "颱風" };
function insCatCard(cat) {
  const D = (((P.insights_cat || {}).cats) || {})[cat], xs = (D && D.items) || [];
  if (!xs.length) return { html: sideHTML({ eyebrow: `${cat} · 洞見`, title: "這一類最值得注意的", body: '<p class="empty">每個分類輪流整理，約 6 小時內會出現。</p>' }) };
  return { html: sideHTML({ eyebrow: `${cat} · 洞見 · ${navAgo(D.at)}更新`, title: "這一類最值得注意的", big: xs[0].title, color: "#ffd60a",
    body: `<p class="why">只看「${esc(cat)}」這一類的資料。句子由 AI 寫，每個數字都對過原始資料，對不上的就不放；約 6 小時重寫一次。</p>`
      + xs.map(x => `<div class="ins"><div class="ins-tags">${(x.src || []).map(t => `<i>${esc(INS_SRC_ZH[t] || t)}</i>`).join("")}</div><b>${esc(x.title)}</b>${vzInsRow(x)}<p>${esc(x.body)}</p></div>`).join("") }) };
}
