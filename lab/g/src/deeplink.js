
/* ---- 網址記住畫面：?看=醫美&地=台中市北屯區 → 打開就是同一個項目、同一個地方；逛的時候網址跟著變，複製就能分享 ---- */
const DL = { applied: false, last: "" };
const dlFind = n => { const E = EXPLORE(); for (const c of E) { const it = c.items.find(x => x.n === n); if (it) return [c.cat, it.n]; } return null; };
const dlPlace = s => {
  s = norm(String(s || "")); if (!s) return {};
  const C = COUNTIES.find(c => s.startsWith(norm(c.name))); if (!C) return {};
  const rest = s.slice(norm(C.name).length);
  const T = rest ? (NAV.towns || []).find(t => sameC(t.county, C.name) && t.name === rest) : null;
  return { C, T };
};
function dlApply() {
  const q = new URLSearchParams(location.search), item = q.get("看"), place = q.get("地");
  if (!item && !place) { DL.applied = true; return; }
  if (place && !NAV.towns && !DL.tw) { DL.tw = 1; navTowns(); }   // 行政區外框平常是進到地圖才載，這裡先載
  if (!ST.openAt || !ST.chapters || !ST.chapters.length || !COUNTIES.length || (place && !NAV.towns)) return setTimeout(dlApply, 300);
  DL.applied = true;
  if (typeof INTRO !== "undefined" && INTRO.on) endIntro(true);
  const hit = dlFind(item) || ["現場", "此刻"];
  scrollTo({ top: (ST.chapters.length - 1) * secH(), behavior: "auto" });
  setTimeout(() => { ST.openAt(hit[0], hit[1]);
    const { C, T } = dlPlace(place);
    const pc = (q.get("圈") || "").split(",").map(Number);
    if (pc.length === 3 && pc.every(isFinite)) ARP.pin = { ll: [pc[0], pc[1]], r: pc[2] };
    if (C) setTimeout(() => { if (T) navGoTown(T); else navGoCounty(C); }, 1500);   // 先等鏡頭回到全台灣，再飛過去
  }, 400);
}
function dlState() {
  if (!DL.applied) return;
  let s = "";
  if (ST.explore && EXCAT >= 0) {
    const E = EXPLORE(), it = E[EXCAT] && E[EXCAT].items[EXITEM], q = new URLSearchParams();
    if (it) q.set("看", it.n);
    if (NAV.level >= 1 && NAV.county) q.set("地", norm(NAV.county.name) + (NAV.level === 2 && NAV.town ? NAV.town.name : ""));
    if (NAV.lens === "area" && NAV.level === 2 && ARP.pin) q.set("圈", `${ARP.pin.ll[0].toFixed(5)},${ARP.pin.ll[1].toFixed(5)},${ARP.pin.r}`);
    s = q.toString() ? "?" + q.toString() : "";
  }
  if (s !== DL.last) { DL.last = s; try { history.replaceState(null, "", location.pathname + s); } catch (e) { } }
}
setTimeout(dlApply, 600);
setInterval(dlState, 800);
// 麵包屑的「分享」：複製這個畫面的連結
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-go=share]"); if (!b) return;
  dlState();
  const done = () => { b.classList.add("ok"); b.textContent = "已複製"; setTimeout(() => { b.classList.remove("ok"); b.textContent = "分享"; }, 1600); };
  if (navigator.share && MOBILE) navigator.share({ title: document.title, url: location.href }).catch(() => { });
  else if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(done, () => { b.textContent = "請從網址列複製"; });
});
