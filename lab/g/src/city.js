
/* ---- 住哪裡：各鄉鎮生活條件評分（網路、咖啡與共同工作空間、租金、空氣、交通、醫療、人口），每項是全台百分位 ---- */
LENS.city = { n: "住哪裡", c: "#bf5af2" };
const CYS = { scene: "遠端工作" };
const CYD = () => lazyJSON("city", "city_scores.json", 720);
const CY_M = [
  ["net", "固網速度", r => r.net_fixed != null ? `${r.net_fixed} Mbps` : null],
  ["mobile", "行動網路", r => r.net_mobile != null ? `${r.net_mobile} Mbps` : null],
  ["cafe", "咖啡廳與共同工作空間", r => r.cafe != null ? `咖啡 ${r.cafe}・共享空間 ${r.cowork}` : null],
  ["rent", "租金（住家）", r => r.rent != null ? `每坪 ${r.rent.toLocaleString("en-US")} 元／月` : null],
  ["air", "空氣（PM2.5）", r => r.pm25 != null ? `${r.pm25} μg/m³（${r.pm_site}站）` : null],
  ["transit", "車站", r => r.station != null ? `${r.station} 站` : null],
  ["clinic", "診所密度", r => r.clinic10k != null ? `每萬人 ${r.clinic10k} 家` : null],
  ["growth", "人口流入", r => r.net_mig != null ? `近一年 ${r.net_mig >= 0 ? "+" : "−"}${Math.abs(r.net_mig).toLocaleString("en-US")} 人` : null],
  ["young", "20～39 歲比例", r => `${r.young}%`],
];
const cyRows = () => ((CYD() || {}).rows) || [];
const cyScore = r => (r.score || {})[CYS.scene];
const cyTop = rows => rows.filter(r => cyScore(r) != null).sort((a, b) => cyScore(b) - cyScore(a));
const cySceneBtns = () => `<span class="arr">${Object.keys((CYD() || {}).scenes || { "遠端工作": 1, "年輕成家": 1, "生活機能": 1 }).map(s => `<button data-scn="${esc(s)}" class="${s === CYS.scene ? "on" : ""}">${esc(s)}</button>`).join("")}</span>`;
const cyWhy = () => { const D = CYD() || {}, w = (D.scenes || {})[CYS.scene] || []; const zh = Object.fromEntries(CY_M.map(m => [m[0], m[1]]));
  return `<p class="why">總分＝各項在全台的百分位平均，「${esc(CYS.scene)}」看的是：${esc(w.map(k => zh[k] || k).join("、"))}。安全和幸福感沒有鄉鎮級的公開資料，所以不算；人口不到 3 萬的鄉鎮不排。</p>`; };
const cyEmpty = () => ({ eyebrow: "住哪裡", title: "哪一區最適合住？", big: "", color: LENS.city.c, body: `<p class="empty">${CYD() === false ? "評分資料還在準備（每週算一次，第一次要等網路速度、咖啡廳這些資料抓完）。" : "資料載入中…"}</p>` });
const cyTownOf = r => (NAV.towns || []).find(t => sameC(t.county, r.c) && t.name === r.t);
TW_VIEW.city = () => {
  const rows = cyRows(); navCounties(() => ({ op: 0.15, dim: true }));
  if (!rows.length) return cyEmpty();
  const top = cyTop(rows), view = NAV.viewD || 400;
  top.slice(0, 10).forEach((r, i) => { const t = cyTownOf(r); if (t) navCol(t.c[0], t.c[1], cyScore(r) / 100, view, r.t, `${cyScore(r)} 分`, 8 - i * 0.3, LENS.city.c); });
  return { eyebrow: `住哪裡 · ${CYS.scene}`, title: "哪一區最適合住？", big: top[0] ? `${top[0].c}${top[0].t}` : "", color: LENS.city.c,
    body: cySceneBtns() + cyWhy() + `<ul class="lst nvl">${top.slice(0, 12).map((r, i) => `<li data-ar="${esc(cyTownOf(r) ? cyTownOf(r).county : r.c)}|${esc(r.t)}" style="cursor:pointer">${i + 1}. ${esc(r.c)} ${esc(r.t)}<span>${cyScore(r)} 分・${esc(CY_M.filter(m => (r.p || {})[m[0]] >= 80).map(m => m[1]).slice(0, 3).join("、") || "各項平均")}</span></li>`).join("")}</ul>` };
};
CITY_VIEW.city = C => {
  const ts = navOutline(C), rows = cyRows().filter(r => sameC(r.c, C.name)), view = NAV.viewD || 60;
  if (!cyRows().length) return cyEmpty();
  const top = cyTop(rows);
  top.forEach((r, i) => { const t = ts.find(x => x.name === r.t); if (t) navCol(t.c[0], t.c[1], cyScore(r) / 100, view, r.t, `${cyScore(r)} 分`, 6 - i * 0.2, LENS.city.c); });
  townPills(ts, new Set(top.map(r => r.t)));
  return { eyebrow: `${norm(C.name)} · 住哪裡 · ${CYS.scene}`, title: "這座城市哪一區最適合？", big: top[0] ? top[0].t : norm(C.name), color: LENS.city.c,
    body: cySceneBtns() + cyWhy() + `<ul class="lst nvl">${rankRows(top.map(r => [r.t, `${cyScore(r)} 分・全台第 ${cyTop(cyRows()).indexOf(r) + 1}`]), "nt")}</ul>` };
};
STREET_VIEW.city = (T, C) => {
  for (const r of T.rings) navLine(r, 0xffffff, 0.8, 0.15);
  const all = cyRows(), r = all.find(x => sameC(x.c, T.county) && x.t === T.name);
  if (!all.length) return cyEmpty();
  if (!r) return { eyebrow: `${norm(T.county)} › ${T.name} · 住哪裡`, title: "這一區適合住嗎？", big: T.name, color: LENS.city.c, body: `<p class="empty">這一區人口不到 3 萬或資料不足，沒有排名。</p>` };
  const rk = cyTop(all).indexOf(r) + 1;
  return { eyebrow: `${norm(T.county)} › ${T.name} · 住哪裡 · ${CYS.scene}`, title: "這一區適合住嗎？", big: cyScore(r) != null ? `${cyScore(r)} 分` : T.name, chg: rk ? `全台第 ${rk}` : "", color: LENS.city.c,
    body: cySceneBtns() + `<p class="why">人口 ${r.pop.toLocaleString("en-US")}，65 歲以上 ${r.old}%。下面每一項的長條是全台百分位（越長越好；租金、PM2.5 是越低越長）。</p>`
      + barsHTML(CY_M.map(([k, n, f]) => { const v = f(r), p = (r.p || {})[k]; return p == null ? { name: n, v: 0, txt: "沒有資料", color: "#8e8e93" } : { name: n, v: p, txt: `${v}`, color: p >= 66 ? UPH : p >= 33 ? "#ffd60a" : DNH }; }), { signed: false })
      + `<p class="why">資料：${esc(((CYD() || {}).src) || "")}。網路速度是 Ookla 測速使用者的平均，不是電信業者保證的速度。</p>` };
};
document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("#side [data-scn]"); if (!b) return; CYS.scene = b.dataset.scn; NAV.key = ""; });
