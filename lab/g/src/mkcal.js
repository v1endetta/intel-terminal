
/* ---- 市場行事曆＋市場時鐘（像彭博的 ECO 和 WEI 開收盤）----
   卡片：下一個重要數據倒數、各交易所現在開還是關、今天／本週／下週的公布時間（台北時間、前值、預測）、休市、台股法說會與新股。
   地球：各交易所一個點（綠＝開盤、黃＝午休或盤前盤後、灰＝收盤、橘＝休市），晨昏線＋夜裡的城市燈光，看得出世界哪裡醒著。 */
const MKX = [
  { k: "TWSE", n: "台股", c: "台北", ll: [121.52, 25.04], tz: "Asia/Taipei", s: [["09:00", "13:30"]] },
  { k: "XJPX", n: "日股", c: "東京", ll: [139.77, 35.68], tz: "Asia/Tokyo", s: [["09:00", "11:30"], ["12:30", "15:30"]] },
  { k: "XKRX", n: "韓股", c: "首爾", ll: [126.98, 37.57], tz: "Asia/Seoul", s: [["09:00", "15:30"]] },
  { k: "XSHG", n: "陸股", c: "上海", ll: [121.47, 31.23], tz: "Asia/Shanghai", s: [["09:30", "11:30"], ["13:00", "15:00"]] },
  { k: "XHKG", n: "港股", c: "香港", ll: [114.17, 22.28], tz: "Asia/Hong_Kong", s: [["09:30", "12:00"], ["13:00", "16:00"]] },
  { k: "XSES", n: "新加坡", c: "新加坡", ll: [103.85, 1.29], tz: "Asia/Singapore", s: [["09:00", "12:00"], ["13:00", "17:00"]] },
  { k: "XNSE", n: "印度", c: "孟買", ll: [72.88, 19.07], tz: "Asia/Kolkata", s: [["09:15", "15:30"]] },
  { k: "XETR", n: "德股", c: "法蘭克福", ll: [8.68, 50.11], tz: "Europe/Berlin", s: [["09:00", "17:30"]] },
  { k: "XLON", n: "英股", c: "倫敦", ll: [-0.09, 51.51], tz: "Europe/London", s: [["08:00", "16:30"]] },
  { k: "XNYS", n: "美股", c: "紐約", ll: [-74.01, 40.71], tz: "America/New_York", s: [["09:30", "16:00"]], pre: "04:00", post: "20:00" },
];
const MK_ST = { open: ["#30d158", "開盤中"], lunch: ["#ffd60a", "午休"], pre: ["#ffd60a", "盤前"], post: ["#ffd60a", "盤後"], closed: ["#8e8e93", "收盤"], hol: ["#ff9f0a", "休市"], wknd: ["#8e8e93", "週末"] };
const MK_R = { 台: "#64d2ff", 美: "#0a84ff", 歐: "#bf5af2", 英: "#5e5ce6", 日: "#ff375f", 中: "#ff453a", 港: "#ff9f0a", 韓: "#30b0c7", 德: "#ac8e68", 澳: "#32d74b", 加: "#ff6961", 紐: "#66d4cf", 瑞士: "#a2845e", 星: "#ff9f0a", 印: "#ffb340" };
const _mkF = {};
function tzParts(tz, t) {
  const f = _mkF[tz] || (_mkF[tz] = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", weekday: "short" }));
  const o = {}; for (const p of f.formatToParts(new Date(t))) o[p.type] = p.value;
  return { d: `${o.year}-${o.month}-${o.day}`, wd: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(o.weekday), m: (+o.hour % 24) * 60 + +o.minute };
}
function wallTs(tz, d, min) {   // 某時區的「某天幾點」→ 時間戳
  const [y, mo, dd] = d.split("-").map(Number), g = Date.UTC(y, mo - 1, dd, Math.floor(min / 60), min % 60), p = tzParts(tz, g), [y2, m2, d2] = p.d.split("-").map(Number);
  return g - (Date.UTC(y2, m2 - 1, d2, Math.floor(p.m / 60), p.m % 60) - g);
}
const hm = s => +s.slice(0, 2) * 60 + +s.slice(3, 5);
const MK = () => P.mktcal || null;
function mkHol() { const M = MK(); if (!M) return {}; if (M._h) return M._h; const h = {}; for (const x of M.hol || []) (h[x.ex] = h[x.ex] || {})[x.d] = x.n; return (M._h = h); }
function mkStatus(x, now = Date.now()) {
  const H = mkHol()[x.k] || {}, p = tzParts(x.tz, now), S = x.s.map(([a, b]) => [hm(a), hm(b)]), hol = H[p.d], wk = p.wd >= 1 && p.wd <= 5;
  let nextOpen = null;
  for (let i = 0; i < 12 && !nextOpen; i++) { const q = tzParts(x.tz, now + i * 864e5); if (q.wd < 1 || q.wd > 5 || H[q.d]) continue; const o = wallTs(x.tz, q.d, S[0][0]); if (o > now) nextOpen = o; }
  if (wk && !hol) {
    for (const [a, b] of S) if (p.m >= a && p.m < b) return { st: "open", until: wallTs(x.tz, p.d, b), nx: "收盤", loc: p };
    if (p.m >= S[0][0] && p.m < S[S.length - 1][1]) { const n = S.find(([a]) => a > p.m); return { st: "lunch", until: wallTs(x.tz, p.d, n[0]), nx: "下午開盤", loc: p }; }
    if (x.pre && p.m >= hm(x.pre) && p.m < S[0][0]) return { st: "pre", until: nextOpen, nx: "開盤", loc: p };
    if (x.post && p.m >= S[S.length - 1][1] && p.m < hm(x.post)) return { st: "post", until: nextOpen, nx: "開盤", loc: p };
  }
  return { st: hol ? "hol" : wk ? "closed" : "wknd", why: hol || "", until: nextOpen, nx: "開盤", loc: p };
}
const tpeHM = ts => new Date(ts).toLocaleTimeString("zh-TW", { timeZone: "Asia/Taipei", hour: "2-digit", minute: "2-digit", hour12: false });
const tpeDay = ts => tzParts("Asia/Taipei", ts).d;
function inTxt(ms) { if (ms == null) return ""; const m = Math.max(0, Math.round(ms / 6e4)); return m < 60 ? `${m} 分` : m < 1440 ? `${Math.floor(m / 60)} 小時 ${m % 60} 分` : `${Math.floor(m / 1440)} 天 ${Math.floor((m % 1440) / 60)} 小時`; }
function whenTxt(ts) {   // 「今晚 20:30」「明天 09:00」「週五 04:00」
  const d = tpeDay(ts), today = tpeDay(Date.now()), tm = tpeDay(Date.now() + 864e5), h = tpeHM(ts), hh = +h.slice(0, 2);
  if (d === today) return (hh >= 18 ? "今晚 " : hh < 6 ? "今天凌晨 " : "今天 ") + h;
  if (d === tm) return (hh < 6 ? "明天凌晨 " : hh >= 18 ? "明晚 " : "明天 ") + h;
  return `${WD[new Date(d + "T12:00:00+08:00").getDay()]} ${h}`;
}
const WD = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];
const mdW = d => { const x = new Date(d + "T12:00:00+08:00"); return `${WD[x.getDay()]} ${x.getMonth() + 1}/${x.getDate()}`; };
function mkItems() {
  const M = MK();
  if (M && M.items) return M.items;
  return (((P.calendar || {}).items) || []).map(x => ({ d: x.date, t: null, r: x.region, n: x.label.replace(/^美國 /, ""), k: x.kind === "holiday" ? "holiday" : x.kind || "data", imp: x.kind === "holiday" ? 2 : 2, ap: x.approx }));
}
const mkPast = (x, now) => x.ts ? x.ts < now - 6e4 : x.d < tpeDay(now);
function mkStrip(now) {
  const rank = { open: 0, lunch: 1, pre: 1, post: 2, hol: 3, closed: 4, wknd: 4 };
  const L = MKX.map(x => ({ x, s: mkStatus(x, now) })).sort((a, b) => rank[a.s.st] - rank[b.s.st] || (a.s.until || 0) - (b.s.until || 0));
  return `<div class="mkx">${L.map(({ x, s }) => { const [c, l] = MK_ST[s.st];
    const sub = s.st === "open" ? `剩 ${inTxt(s.until - now)}` : s.st === "lunch" ? `${tpeHM(s.until)} 開` : s.until ? (tpeDay(s.until) === tpeDay(now) ? `${tpeHM(s.until)} 開` : `${whenTxt(s.until).replace(/ \d\d:\d\d$/, "")} ${tpeHM(s.until)} 開`) : "";
    return `<div class="mkx1 ${s.st}" title="${esc(x.c)}當地 ${String(Math.floor(s.loc.m / 60)).padStart(2, "0")}:${String(s.loc.m % 60).padStart(2, "0")}${s.why ? "・" + esc(s.why) : ""}"><i style="background:${c}"></i><b>${x.n}</b><span>${l}</span><em>${sub}</em></div>`; }).join("")}</div>`;
}
function mkRow(x, now) {
  const past = mkPast(x, now), soon = x.ts && !past && x.ts - now < 6 * 36e5;
  const meta = [];
  if (x.k === "holiday") meta.push("交易所休市"); else if (x.k === "bank") meta.push("外匯市場清淡");
  if (x.pv || x.fc) meta.push(`前值 ${esc(String(x.pv || "—").split("|")[0])}`, `預測 ${esc(x.fc || "—")}`);
  if (x.k === "conf" && x.ind) meta.push(esc(x.ind));
  if (x.k === "ipo" && x.px) meta.push(`承銷價 ${x.px}`);
  if (x.k === "expiry") meta.push("結算日：留意尾盤波動");
  if (soon) meta.push(`<em data-ts="${x.ts}">${inTxt(x.ts - now)}後</em>`);
  const tag = x.k === "holiday" ? "休市" : x.k === "cb" ? "央行" : x.k === "expiry" ? "結算" : x.k === "conf" ? "法說" : x.k === "ipo" ? "新股" : x.k === "speech" ? "談話" : x.k === "auction" ? "標售" : "";
  return `<li class="mk${past ? " past" : ""}${soon ? " soon" : ""} i${x.imp}"><span class="mt">${x.t || "全天"}</span><span class="mr" style="--c:${MK_R[x.r] || "#8e8e93"}">${esc(x.r)}</span><span class="mn"><b>${esc(x.n)}</b>${x.ap ? `<i class="ap">約</i>` : ""}${tag ? `<i class="tg t-${x.k}">${tag}</i>` : ""}${meta.length ? `<small>${meta.join("　")}</small>` : ""}</span><span class="mi" aria-label="重要性 ${x.imp}">${"<b></b>".repeat(x.imp)}${"<s></s>".repeat(3 - x.imp)}</span></li>`;
}
const MKS = { tab: null, all: false };
function mkList(now = Date.now()) {
  const today = tpeDay(now), wd = new Date(today + "T12:00:00+08:00").getDay(), toSun = (7 - wd) % 7;
  const addD = (d, n) => tpeDay(new Date(d + "T12:00:00+08:00").getTime() + n * 864e5);
  const wkEnd = addD(today, toSun), nwS = addD(wkEnd, 1), nwE = addD(wkEnd, 7);
  let xs = mkItems();
  const T = MKS.tab;
  if (T === "today") xs = xs.filter(x => x.d === today);
  else if (T === "week") xs = xs.filter(x => x.d >= today && x.d <= wkEnd);
  else if (T === "next") xs = xs.filter(x => x.d >= nwS && x.d <= nwE);
  else if (T === "hol") xs = xs.filter(x => x.k === "holiday" || x.k === "bank");
  else if (T === "tw") xs = xs.filter(x => x.r === "台");
  if (!MKS.all && T !== "hol" && T !== "tw") xs = xs.filter(x => x.imp >= 2 || x.k === "holiday");
  if (T === "hol") { const H = (MK() || {}).hol || []; xs = H.map(h => ({ d: h.d, t: null, r: h.r, n: `${h.m}休市：${h.n}`, k: "holiday", imp: h.ex === "TWSE" || h.ex === "XNYS" ? 2 : 1 })); }
  if (!xs.length) return `<p class="empty">${T === "today" ? "今天沒有重要的公布，看看「本週」。" : "這段時間沒有排定的項目。"}</p>`;
  let out = "", last = "";
  for (const x of xs.slice(0, 80)) { if (x.d !== last) { last = x.d; out += `<li class="mkd${x.d === today ? " now" : ""}">${x.d === today ? "今天　" : ""}${mdW(x.d)}</li>`; } out += mkRow(x, now); }
  return `<ul class="mkl">${out}</ul>`;
}
function mkCardBody(now = Date.now()) {
  const tabs = [["today", "今天"], ["week", "本週"], ["next", "下週"], ["hol", "休市"], ["tw", "台股"]];
  return `${mkStrip(now)}<div class="mkt" role="tablist">${tabs.map(([k, l]) => `<button data-mkt="${k}" class="${MKS.tab === k ? "on" : ""}">${l}</button>`).join("")}</div>
    <label class="mka"><input type="checkbox" data-mka ${MKS.all ? "checked" : ""}> 顯示次要項目</label><div id="mkList">${mkList(now)}</div>
    <p class="why">時間都是台北時間。●●● 是對市場的影響程度（高／中／低）；「約」是依往例推估的日期，以官方公告為準。</p>`;
}
function mkNext(now) {
  const xs = mkItems().filter(x => x.ts && x.ts > now && x.k !== "holiday");
  return xs.find(x => x.imp >= 3) || xs.find(x => x.imp >= 2) || null;
}
function mkCard() {
  const now = Date.now(), M = MK(), nx = mkNext(now);
  if (!MKS.tab) { const t = tpeDay(now); MKS.tab = mkItems().filter(x => x.d === t && x.imp >= 2 && !mkPast(x, now)).length >= 2 ? "today" : "week"; }
  return { layer: "gx", gx: "clock", html: sideHTML({ eyebrow: `市場 · 行事曆 · 台北 ${tpeHM(now)}`, title: "接下來市場要等什麼？",
    big: nx ? `${nx.r === "台" ? "" : nx.r + " "}${nx.n}` : "這週沒有排定的重點", color: "#64d2ff",
    body: (nx ? `<p class="mkn">${whenTxt(nx.ts)}<em data-ts="${nx.ts}">還有 ${inTxt(nx.ts - now)}</em>${nx.fc ? `<span>預測 ${esc(nx.fc)}・前值 ${esc(String(nx.pv || "—").split("|")[0])}</span>` : ""}</p>` : "") +
      `<div id="mkBody">${mkCardBody(now)}</div>` + (M ? "" : `<p class="empty">完整行事曆（時間、前值、預測、各國休市）下一輪資料更新後出現；目前先列主要日期。</p>`) }) };
}
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-mkt]"); if (!b) return;
  MKS.tab = b.dataset.mkt; const box = $("mkBody"); if (box) box.innerHTML = mkCardBody();
});
document.addEventListener("change", e => { if (!e.target.matches || !e.target.matches("[data-mka]")) return; MKS.all = e.target.checked; const l = $("mkList"); if (l) l.innerHTML = mkList(); });
// 倒數每 20 秒更新一次；交易所狀態每分鐘重畫
setInterval(() => {
  const now = Date.now();
  document.querySelectorAll("#side [data-ts]").forEach(el => { const ts = +el.dataset.ts, pre = /^還有/.test(el.textContent) ? "還有 " : "", suf = /後$/.test(el.textContent) ? "後" : ""; el.textContent = ts > now ? pre + inTxt(ts - now) + suf : "已公布"; });
  const sx = document.querySelector("#side .mkx"); if (sx && (!mkCard.t || now - mkCard.t > 6e4)) { mkCard.t = now; sx.outerHTML = mkStrip(now); }
}, 20000);
// 地球：太陽直射點（晨昏線）
function sunLL(t = Date.now()) {
  const d = new Date(t), N = (Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5;
  const dec = -23.44 * Math.cos(2 * Math.PI / 365 * (N + 10)), h = d.getUTCHours() + d.getUTCMinutes() / 60;
  return [((12 - h) * 15 + 540) % 360 - 180, dec];
}
// 上方列：主要市場開收盤一眼看（點了打開行事曆）
function mkBar() {
  let el = $("mkbar"); const ck = $("clock"); if (!ck) return;
  if (!el) { el = document.createElement("button"); el.id = "mkbar"; el.type = "button"; el.setAttribute("aria-label", "主要市場開收盤，點開市場行事曆"); ck.parentNode.insertBefore(el, ck);
    el.addEventListener("click", () => { const seg = [...document.querySelectorAll("#dock2 .seg button")].find(b => b.textContent === "市場"); if (seg) seg.click();
      setTimeout(() => { const c = [...document.querySelectorAll("#chips button")].find(b => b.textContent.trim() === "行事曆"); if (c) c.click(); }, 80); }); }
  const now = Date.now();
  el.innerHTML = ["TWSE", "XJPX", "XHKG", "XLON", "XNYS"].map(k => { const x = MKX.find(m => m.k === k), s = mkStatus(x, now);
    return `<span class="${s.st}" title="${x.n} ${MK_ST[s.st][1]}${s.why ? "・" + esc(s.why) : ""}"><i style="background:${MK_ST[s.st][0]}"></i>${x.n.slice(0, 1)}</span>`; }).join("");
}
setTimeout(mkBar, 1500); setInterval(mkBar, 60000);
