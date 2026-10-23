
/* ---- 新視角：診所（健保名冊）、人口遷徙（內政部遷入遷出） ---- */
LENS.clinic = { n: "診所", c: "#ff7ab6" };
LENS.move = { n: "人口遷徙", c: "#34c759" };
const CL = () => P.clinics || {};
const clTowns = C => ((CL().towns) || []).filter(r => sameC(r[0], C.name || C));
const clRecent = (cty, town) => ((CL().recent) || []).filter(r => sameC(r[3], cty) && (!town || r[4] === town));
const clDate = d => d ? `${+String(d).slice(4, 6)}/${+String(d).slice(6, 8)}` : "";
const clGs = gs => (gs || []).map(g => `${g[0]} ${g[1]}`).join("、");
const yoyTxt = v => v == null ? "" : `${v >= 0 ? "+" : "−"}${Math.abs(v)}%`;
const clEmpty = () => ({ eyebrow: "台灣 · 診所", title: "哪一科新開最多？", big: "載入中", color: LENS.clinic.c, body: '<p class="empty">診所資料下一輪更新後出現（每天一次）。</p>' });
TW_VIEW.clinic = () => {
  const D = CL(), Cs = D.counties || {}, ks = Object.keys(Cs);
  if (!ks.length) { navCounties(() => ({ op: 0.2 })); return clEmpty(); }
  const mx = Math.max(1, ...ks.map(k => Cs[k].new)), col = new THREE.Color(LENS.clinic.c);
  navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true, op: 0.12 }; const v = Cs[k];
    return { col, op: 0.25 + 0.7 * Math.sqrt(v.new / mx), sub: `新開 ${v.new}・歇業 ${v.close}`, dot: v.new >= v.close ? UPH : DNH, prio: 2 + v.new / mx * 4 }; });
  const G = (D.groups || []).filter(g => g.g !== "其他西醫"), up = G.filter(g => g.yoy != null && g.new >= 20).sort((a, b) => b.yoy - a.yoy), top = up[0];
  const tot = ks.reduce((a, k) => a + Cs[k].new, 0), cl = ks.reduce((a, k) => a + Cs[k].close, 0);
  return { eyebrow: `台灣 · 診所 · 近 12 個月`, title: "哪一科新開最多？", big: top ? `${top.g} ${yoyTxt(top.yoy)}` : `新開 ${tot.toLocaleString("en-US")} 家`, color: LENS.clinic.c,
    body: `<p class="why">健保特約診所近 12 個月新開 ${tot.toLocaleString("en-US")} 家、歇業 ${cl.toLocaleString("en-US")} 家；百分比是新開家數跟前 12 個月比。某一科突然開很多，代表那類需求在長。</p>`
      + barsHTML(G.map(g => ({ name: g.g, v: g.new, txt: `${g.new} 家　${yoyTxt(g.yoy)}`, color: g.yoy == null ? LENS.clinic.c : tone(g.yoy) })), { signed: false })
      + `<div class="nvh">各縣市（點進去看哪一區）</div><ul class="lst nvl">${rankRows(ks.sort((a, b) => Cs[b].new - Cs[a].new).slice(0, 10).map(k => [k, `新開 ${Cs[k].new}・歇業 ${Cs[k].close}・現有 ${Cs[k].active.toLocaleString("en-US")}`, Cs[k].new >= Cs[k].close ? UPH : DNH]), "nc")}</ul>` };
};
CITY_VIEW.clinic = C => {
  const ts = navOutline(C), R = clTowns(C), view = NAV.viewD || 60, mx = Math.max(1, ...R.map(r => r[2]));
  if (!CL().towns) return clEmpty();
  R.forEach((r, i) => { const t = ts.find(t => t.name === r[1]); if (t && r[2]) navCol(t.c[0], t.c[1], r[2] / mx, view, r[1], `新開 ${r[2]}`, 6 - i * 0.2, r[2] >= r[3] ? UPH : DNH); });
  townPills(ts, new Set(R.map(r => r[1])));
  const v = (CL().counties || {})[Object.keys(CL().counties || {}).find(k => sameC(k, C.name))] || { new: 0, close: 0, active: 0 }, rec = clRecent(C.name);
  return { eyebrow: `${norm(C.name)} · 診所 · 近 12 個月`, title: "新診所開在哪一區？", big: `新開 ${v.new} 家`, color: LENS.clinic.c,
    body: `<p class="why">光柱越高開越多；綠＝新開比歇業多、紅＝歇業比較多。現有 ${v.active.toLocaleString("en-US")} 家、歇業 ${v.close} 家。</p><ul class="lst nvl">${rankRows(R.slice(0, 8).map(r => [r[1], `新開 ${r[2]}・歇業 ${r[3]}${r[5].length ? "・" + clGs(r[5]) : ""}`]), "nt")}</ul>`
      + (rec.length ? `<div class="nvh">最近兩個月新開</div>` + listHTML(rec.slice(0, 8).map(r => ({ t: r[0], s: `${r[1]}・${r[4]}・${clDate(r[5])} 特約`, url: `https://www.google.com/search?q=${encodeURIComponent(r[0] + " " + r[4])}` }))) : "") };
};
STREET_VIEW.clinic = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
  const R = clTowns(T.county), me = R.find(r => r[1] === T.name), rec = clRecent(T.county, T.name);
  if (!me) return { eyebrow: `${norm(T.county)} › ${T.name} · 診所`, title: "這一區開了什麼診所？", big: T.name, color: LENS.clinic.c, body: `<p class="empty">${CL().towns ? "這一區近 12 個月沒有新開或歇業的診所。" : "資料載入中。"}</p>` };
  return { eyebrow: `${norm(T.county)} › ${T.name} · 診所 · 近 12 個月`, title: "這一區開了什麼診所？", big: `新開 ${me[2]} 家`, color: LENS.clinic.c,
    body: `<p class="why">在${esc(norm(T.county))}排第 ${R.indexOf(me) + 1}／${R.length}。現有 ${me[4]} 家、歇業 ${me[3]} 家。${me[5].length ? "新開的以" + esc(clGs(me[5])) + "為主。" : ""}</p>`
      + (rec.length ? `<div class="nvh">最近兩個月新開</div>` + listHTML(rec.slice(0, 10).map(r => ({ t: r[0], s: `${r[1]}${r[2] ? "（" + r[2] + "）" : ""}・${clDate(r[5])} 特約`, url: `https://www.google.com/search?q=${encodeURIComponent(r[0] + " " + T.name)}` }))) : "") };
};

const MV = () => P.migration || {};
const mvTowns = C => ((MV().towns) || []).filter(r => sameC(r[0], C.name || C));
const mvSgn = v => `${v >= 0 ? "+" : "−"}${Math.abs(v).toLocaleString("en-US")}`;
const mvEmpty = () => ({ eyebrow: "台灣 · 人口遷徙", title: "大家搬去哪裡？", big: "載入中", color: LENS.move.c, body: '<p class="empty">人口遷徙資料下一輪更新後出現。</p>' });
TW_VIEW.move = () => {
  const D = MV(), Cs = D.counties || {}, ks = Object.keys(Cs);
  if (!ks.length) { navCounties(() => ({ op: 0.2 })); return mvEmpty(); }
  const mx = Math.max(1, ...ks.map(k => Math.abs(Cs[k].net12)));
  navCounties(c => { const k = ks.find(x => sameC(x, c.name)); if (!k) return { dim: true, op: 0.12 }; const v = Cs[k].net12;
    return { col: new THREE.Color(v >= 0 ? UPH : DNH), op: 0.2 + 0.7 * Math.sqrt(Math.abs(v) / mx), sub: `${mvSgn(v)} 人`, dot: v >= 0 ? UPH : DNH, prio: 2 + Math.abs(v) / mx * 4 }; });
  const rows = ks.map(k => [k, Cs[k].net12]).sort((a, b) => b[1] - a[1]), tops = (D.towns || []).slice(0, 5);
  return { eyebrow: `台灣 · 人口遷徙 · ${D.n_months >= 12 ? "近 12 個月" : `近 ${D.n_months} 個月`}（到 ${String(D.month || "").replace("-", "/")}）`, title: "大家搬去哪裡？", big: `${norm(rows[0][0])} ${mvSgn(rows[0][1])}`, color: LENS.move.c,
    body: `<p class="why">遷入減遷出（不含出生死亡），綠＝人搬進來、紅＝人搬走。人往哪裡移，商圈、學校、診所、房價通常會跟著走。</p>`
      + `<div class="nvh">淨流入最多的鄉鎮</div><ul class="lst nvl">${tops.map(t => `<li data-nc="${esc(t[0])}" style="cursor:pointer"><span class="sdot" style="background:${UPH}"></span>${esc(norm(t[0]))} ${esc(t[1])}<span>${mvSgn(t[5])} 人・外縣市搬來 ${t[6].toLocaleString("en-US")}</span></li>`).join("")}</ul>`
      + `<div class="nvh">各縣市</div><ul class="lst nvl">${rankRows(rows.map(([k, v]) => [k, `${mvSgn(v)} 人`, v >= 0 ? UPH : DNH]), "nc")}</ul>` };
};
CITY_VIEW.move = C => {
  const ts = navOutline(C), R = mvTowns(C), view = NAV.viewD || 60;
  if (!MV().towns) return mvEmpty();
  const mx = Math.max(1, ...R.map(r => Math.abs(r[5])));
  R.slice().sort((a, b) => Math.abs(b[5]) - Math.abs(a[5])).forEach((r, i) => { const t = ts.find(x => x.name === r[1]); if (t && r[5]) navCol(t.c[0], t.c[1], Math.abs(r[5]) / mx, view, r[1], `${mvSgn(r[5])} 人`, 6 - i * 0.2, r[5] >= 0 ? UPH : DNH); });
  townPills(ts, new Set(R.map(r => r[1])));
  const v = (MV().counties || {})[Object.keys(MV().counties || {}).find(k => sameC(k, C.name))] || { net12: 0 }, inn = R.filter(r => r[5] > 0), out = R.filter(r => r[5] < 0).reverse();
  return { eyebrow: `${norm(C.name)} · 人口遷徙 · 近 ${MV().n_months || 12} 個月`, title: "這裡的人往哪一區搬？", big: `${mvSgn(v.net12)} 人`, color: v.net12 >= 0 ? UPH : DNH,
    body: `<p class="why">光柱高度＝淨流入或流出的人數，綠進紅出。</p>`
      + (inn.length ? `<div class="nvh">搬進來最多</div><ul class="lst nvl">${rankRows(inn.slice(0, 6).map(r => [r[1], `${mvSgn(r[5])} 人・外縣市 ${r[6].toLocaleString("en-US")}・本縣他區 ${r[7].toLocaleString("en-US")}`, UPH]), "nt")}</ul>` : "")
      + (out.length ? `<div class="nvh">搬走最多</div><ul class="lst nvl">${rankRows(out.slice(0, 5).map(r => [r[1], `${mvSgn(r[5])} 人`, DNH]), "nt")}</ul>` : "") };
};
STREET_VIEW.move = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.7, 0.15);
  const R = mvTowns(T.county), me = R.find(r => r[1] === T.name);
  if (!me) return { eyebrow: `${norm(T.county)} › ${T.name} · 人口遷徙`, title: "人搬進來還是搬走？", big: T.name, color: LENS.move.c, body: `<p class="empty">${MV().towns ? "這一區沒有遷徙資料。" : "資料載入中。"}</p>` };
  const ext = me[6], loc = me[7], abr = me[8], tot = Math.max(1, ext + loc + abr);
  return { eyebrow: `${norm(T.county)} › ${T.name} · 人口遷徙 · 近 ${MV().n_months || 12} 個月`, title: "人搬進來還是搬走？", big: `${mvSgn(me[5])} 人`, color: me[5] >= 0 ? UPH : DNH,
    body: `<p class="why">在${esc(norm(T.county))}排第 ${R.indexOf(me) + 1}／${R.length}。最近一個月 ${mvSgn(me[2])} 人（遷入 ${me[3].toLocaleString("en-US")}、遷出 ${me[4].toLocaleString("en-US")}）。</p>`
      + `<div class="nvh">搬進來的人從哪裡來</div>` + barsHTML([{ name: "外縣市", v: ext, txt: `${Math.round(ext / tot * 100)}%` }, { name: "同縣市其他區", v: loc, txt: `${Math.round(loc / tot * 100)}%` }, { name: "國外", v: abr, txt: `${Math.round(abr / tot * 100)}%` }], { signed: false }) };
};

/* ---- 新興生意：財政部稅籍登記，細分行業近半年新設家數（已校正全體） ---- */
function nicheCard() {
  const T = P.taxreg || {}, up = T.up || [], nw = T.new || [], dn = T.down || [];
  if (!up.length && !nw.length) return { html: sideHTML({ eyebrow: "訊號 · 新興生意", title: "哪些生意正在冒出來？", body: '<p class="empty">資料載入中。</p>' }) };
  const w = T.win ? `${String(T.win[0]).replace("-", "/")}～${String(T.win[1]).replace("-", "/")}` : "近 6 個月", top = nw[0] || up[0];
  const row = x => ({ name: x.name, v: x.yoy != null ? x.yoy : 100, txt: x.new ? `新冒出 ${x.n6} 家` : `${x.n6} 家　${x.yoy >= 0 ? "+" : "−"}${Math.abs(x.yoy)}%` });
  return { html: sideHTML({ eyebrow: `訊號 · 新興生意 · ${w}`, title: "哪些生意正在冒出來？", big: top ? `${top.name}${top.new ? "" : ` +${top.yoy}%`}` : "", color: UPH,
    body: `<p class="why">財政部全國營業登記，細分行業近半年新設家數跟去年同期比（已扣掉整體景氣的影響）。冷門行業突然變多，常常比新聞早看到新生意。</p>`
      + (nw.length ? `<div class="nvh">新冒出來的</div>` + barsHTML(nw.slice(0, 5).map(row)) : "")
      + `<div class="nvh">成長最快</div>` + barsHTML(up.slice(0, 8).map(row))
      + (dn.length ? `<div class="nvh">正在退的</div>` + barsHTML(dn.slice(0, 5).map(row)) : "") }) };
}
