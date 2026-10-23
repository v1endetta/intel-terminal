
/* ---- 政府補助與徵件：近兩週新聞裡「現在還能申請」的補助、獎勵、徵件；依適不適合小型創意公司／個人工作室排序，再看截止日 ---- */
function grantsCard() {
  const G = P.grants || {}, xs = G.items || [];
  if (!xs.length) return { html: sideHTML({ eyebrow: "訊號 · 補助與徵件", title: "現在可以申請什麼？", body: '<p class="empty">補助與徵件下一輪更新後出現（每 6 小時一次）。</p>' }) };
  const now = Date.now(), left = x => x.due ? Math.ceil((new Date(x.due + "T23:59:59+08:00") - now) / 864e5) : null;
  const row = x => { const d = left(x), due = x.due ? `截止 ${+x.due.slice(5, 7)}/${+x.due.slice(8, 10)}${d != null ? `（${d <= 0 ? "今天" : `還有 ${d} 天`}）` : ""}` : "";
    return `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${x.cat ? `<i class="gtag">${esc(x.cat)}</i>` : ""}${esc(x.name || x.t)}</a>`
      + `<span>${esc([x.org, x.who, x.amt ? "最高 " + x.amt.replace(/^最高/, "") : ""].filter(Boolean).join("・"))}${due ? `　<b class="gdue${d != null && d <= 7 ? " hot" : ""}">${esc(due)}</b>` : ""}</span></li>`; };
  const fit = xs.filter(x => (x.fit || 0) >= 2), rest = xs.filter(x => (x.fit || 0) < 2), soon = xs.filter(x => { const d = left(x); return d != null && d <= 7; }).length;
  return { html: sideHTML({ eyebrow: `訊號 · 補助與徵件${soon ? ` · ${soon} 個一週內截止` : ""}`, title: "現在可以申請什麼？", big: fit.length ? `${fit.length} 個適合你` : `${xs.length} 個徵件中`, color: "#30d158",
    body: grantsViz(xs) + `<p class="why">近兩週新聞裡還能申請的補助、獎勵、徵件與計畫徵求。先排小型創意設計公司或個人工作室有機會申請的，再看截止日。內容是從新聞標題判讀的，申請前請看原公告。</p>`
      + (fit.length ? `<div class="nvh">適合你（${fit.length}）</div><ul class="lst gl">${fit.slice(0, 10).map(row).join("")}</ul>` : "")
      + (rest.length ? `<div class="nvh">其他徵件（${rest.length}）</div><ul class="lst gl">${rest.slice(0, 8).map(row).join("")}</ul>` : "") }) };
}
