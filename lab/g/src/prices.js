
/* ---- 物價細項：CPI 基本分類年增率。哪一類東西漲最兇，就是大家最痛、最可能有替代方案的地方 ---- */
function pricesCard() {
  const D = P.prices || {}, xs = (D.items || []).filter(x => x.yoy != null);
  if (!xs.length) return { html: sideHTML({ eyebrow: "總經 · 物價細項", title: "哪些東西變貴了？", body: '<p class="empty">物價細項下一輪更新後出現（每天一次）。</p>' }) };
  const leaf = xs.filter(x => x.lvl === 2), big = xs.filter(x => x.lvl === 1), tot = xs.find(x => x.lvl === 0);
  const up = leaf.slice().sort((a, b) => b.yoy - a.yoy), top = up[0], m = String(D.month || "");
  const row = x => ({ name: x.name, v: x.yoy, txt: pct(x.yoy, 1) });
  return { html: sideHTML({ eyebrow: `總經 · 物價細項 · ${m.slice(0, 4)} 年 ${+m.slice(5, 7)} 月${D.area ? " · " + D.area : ""}`, title: "哪些東西變貴了？", big: top ? `${top.name} ${pct(top.yoy, 1)}` : "", color: top ? tone(top.yoy) : NEU,
    body: `<p class="why">跟去年同月比的價格變化${tot ? `（整體 ${pct(tot.yoy, 1)}）` : ""}。漲最兇的類別，是大家最有感、也最可能出現替代方案的地方。</p>`
      + `<div class="nvh">漲最多</div>` + barsHTML(up.slice(0, 8).map(row))
      + `<div class="nvh">跌最多</div>` + barsHTML(up.slice(-4).reverse().map(row))
      + (big.length ? `<div class="nvh">七大類</div>` + barsHTML(big.map(row)) : "") }) };
}
