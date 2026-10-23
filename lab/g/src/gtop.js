
/* ---- Google 焦點新聞：Google 判斷台灣此刻最重要的新聞（非個人化），附幾家在報、上榜多久 ---- */
function gtopCard() {
  const G = P.gtop || {}, xs = G.items || [];
  if (!xs.length) return { html: sideHTML({ eyebrow: "輿情 · Google 焦點新聞", title: "大家現在在看什麼？", body: '<p class="empty">焦點新聞下一輪更新後出現（每半小時一次）。</p>' }) };
  const hrs = x => x.first ? (Date.now() - new Date(x.first)) / 36e5 : 0;
  const onFor = x => { const h = hrs(x); return h < 1 ? "剛上榜" : h < 24 ? `上榜 ${Math.round(h)} 小時` : `上榜 ${Math.round(h / 24)} 天`; };
  const top = xs[0], long = xs.filter(x => hrs(x) >= 12).length;
  const row = x => `<li class="${x.img ? "gti" : ""}">${x.img ? `<img src="${esc(x.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.remove('gti');this.remove()">` : ""}<div><a href="${esc(x.url)}" target="_blank" rel="noopener"><i class="gtr">${x.rank}</i>${esc(x.t)}</a>`
    + `<span>${esc([x.src, x.n > 1 ? `${x.n} 家報導` : "", onFor(x), x.at ? navAgo(x.at) : ""].filter(Boolean).join("・"))}</span></div></li>`;
  return { html: sideHTML({ eyebrow: `輿情 · Google 焦點新聞${long ? ` · ${long} 則上榜超過半天` : ""}`, title: "大家現在在看什麼？", big: top.t.length > 22 ? top.t.slice(0, 21) + "…" : top.t, color: "#64d2ff",
    body: `<p class="why">Google 新聞判斷台灣此刻最重要的新聞，不是個人化推薦，大多數人在 Google 新聞首頁看到的就是這些。排序照 Google；上榜越久、越多家在報，代表話題越持久。</p>`
      + `<ul class="lst gtl">${xs.slice(0, 15).map(row).join("")}</ul>` }) };
}
