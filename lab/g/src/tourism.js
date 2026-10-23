
/* ---- 觀光：誰來台灣、台灣人去哪裡（觀光署年資料）＋台北旅館每月住用率 ---- */
function tourismCard() {
  const T = P.tourism || {}, I = T.inbound, O = T.outbound, H = T.tpe_hotel;
  if (!I && !O && !H) return { html: sideHTML({ eyebrow: "總經 · 觀光", title: "誰來台灣、台灣人去哪裡？", body: '<p class="empty">觀光資料下一輪更新後出現（每天一次）。</p>' }) };
  const wan = v => v >= 1e4 ? `${(v / 1e4).toFixed(v >= 1e6 ? 0 : 1)} 萬` : nf(v);
  const bars = rows => barsHTML(rows.map(r => ({ name: r.name, v: r.n, txt: `${wan(r.n)}${r.yoy != null ? `　${pct(r.yoy, 0)}` : ""}`, color: r.yoy == null ? "#64d2ff" : tone(r.yoy) })), { signed: false });
  let body = "";
  if (I) body += `<div class="nvh">來台旅客 ${I.year} 年：${wan(I.total)} 人次${I.yoy != null ? `（${pct(I.yoy, 1)}）` : ""}${I.vs2019 ? `，恢復到疫情前的 ${I.vs2019}%` : ""}</div>` + bars(I.top.slice(0, 8))
    + (I.rise && I.rise.length ? `<p class="why">成長最快：${I.rise.slice(0, 4).map(r => `${esc(r.name)} ${pct(r.yoy, 0)}`).join("、")}</p>` : "");
  if (O) body += `<div class="nvh">國人出國 ${O.year} 年：${wan(O.total)} 人次${O.yoy != null ? `（${pct(O.yoy, 1)}）` : ""}</div>` + bars(O.top.slice(0, 8));
  if (H && H.last) body += `<div class="nvh">台北一般旅館 ${H.last.m.slice(0, 4)} 年 ${+H.last.m.slice(5)} 月${(Date.now() - new Date(H.last.m + "-15")) / 864e5 > 120 ? "（台北市開放資料只更新到這個月）" : ""}</div><p class="why">住用率 <b>${H.last.occ.toFixed(1)}%</b>${H.occ_yoy_pp != null ? `（比去年同月 ${H.occ_yoy_pp >= 0 ? "+" : "−"}${Math.abs(H.occ_yoy_pp)} 個百分點）` : ""}，平均房價 <b>${nf(H.last.price)} 元</b>${H.price_yoy != null ? `（${pct(H.price_yoy, 1)}）` : ""}</p>`
    + lineSVG(H.rows.map(r => r.occ), "#64d2ff");
  const big = I ? `來台 ${wan(I.total)}` : H ? `住用率 ${H.last.occ.toFixed(0)}%` : "";
  return { html: sideHTML({ eyebrow: "總經 · 觀光", title: "誰來台灣、台灣人去哪裡？", big, color: I && I.yoy != null ? tone(I.yoy) : "#64d2ff",
    body: `<p class="why">來台和出國是觀光署的年資料（每年更新一次）；台北旅館是每月資料，看得出旺季和淡季。</p>` + body }) };
}
