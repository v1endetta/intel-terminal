
/* ---- 地球場景：在台灣沒有地點、但在世界上有地點的資訊 ----
   全球股市、匯率、原物料、精品、美元流動性、AI 快線、法人：從各地拉一條弧線到台灣。
   顏色＝漲跌（綠漲紅跌），粗細＝幅度，光點流動的方向＝錢或貨往哪裡走。 */
const GX = { g: null, flows: [], key: "", spec: null };
const TW_LL = [121.52, 25.04];
const GXP = { 紐約: [-74, 40.71], 東京: [139.69, 35.69], 香港: [114.17, 22.32], 上海: [121.47, 31.23], 首爾: [126.98, 37.57], 孟買: [72.88, 19.07], 法蘭克福: [8.68, 50.11], 巴黎: [2.35, 48.86],
  倫敦: [-0.13, 51.5], 華盛頓: [-77.04, 38.9], 米蘭: [9.19, 45.46], 西班牙: [-8.41, 43.36], 奧勒岡: [-122.8, 45.49], 美國德州: [-99, 31.5], 美國奧克拉荷馬: [-96.77, 35.98], 北海: [2, 57.5],
  智利: [-69.5, -23.6], 中國: [112, 33], 墨西哥: [-102, 23.5], 西澳: [118.5, -22.5], 舊金山: [-122.42, 37.77], 山景城: [-122.08, 37.39], 雷德蒙: [-122.12, 47.67], 西雅圖: [-122.33, 47.61],
  聖塔克拉拉: [-121.96, 37.35], 庫比蒂諾: [-122.03, 37.32], 門洛帕克: [-122.18, 37.45], 杭州: [120.15, 30.27], 北京: [116.4, 39.9] };
const GX_UNIT = { "USD/bbl": "美元／桶", "USc/lb": "美分／磅", "USD/lb": "美元／磅", "USD/t": "美元／噸", "USD/oz": "美元／盎司" };
const gxPct = v => v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`;
const gxCol = v => v == null ? 0x64d2ff : v >= 0 ? 0x30d158 : 0xff453a;
// 每個分類：節點（地點、漲跌、粗細）＋ 鏡頭看哪裡 ＋ 卡片
const GX_SPEC = {
  world() {
    const AT = { "^GSPC": "紐約", "^IXIC": "紐約", "^DJI": "紐約", "^N225": "東京", "^HSI": "香港", "000001.SS": "上海", "^KS11": "首爾", "^NSEI": "孟買", "^GDAXI": "法蘭克福", "^STOXX50E": "巴黎", "^FTSE": "倫敦" }, by = {};
    for (const x of items("world")) { const c = AT[x.sym]; if (c && x.chg_pct != null) (by[c] = by[c] || []).push(x); }
    return { look: [150, 30], alt: 15000, dir: "in", title: "全球股市", eyebrow: "市場 · 各地最近收盤",
      nodes: Object.entries(by).map(([c, xs]) => ({ name: c, ll: GXP[c], chg: xs.reduce((a, x) => a + x.chg_pct, 0) / xs.length, sub: xs.map(x => `${x.name} ${gxPct(x.chg_pct)}`).join("　") })),
      why: "每條線是一個市場前一個交易日的漲跌，光點往台灣流。歐美在地球另一面，拖曳地球就看得到。" };
  },
  fx() {
    const AT = { 美元: "華盛頓", 歐元: "法蘭克福", 日圓: "東京", 人民幣: "上海" };
    return { look: [140, 32], alt: 14000, dir: "in", title: "台幣匯率", eyebrow: "市場 · 綠＝外幣變貴（台幣變弱）",
      nodes: items("fx").filter(x => AT[x.name]).map(x => ({ name: x.name, ll: GXP[AT[x.name]], chg: x.chg_pct, sub: `${nf(x.mid)}　${gxPct(x.chg_pct)}` })),
      why: "線越粗，那個貨幣今天對台幣動得越多。" };
  },
  cmdty() {
    const AT = { 棉花: "美國德州", "WTI 原油": "美國奧克拉荷馬", "Brent 原油": "北海", 銅: "智利", 鋁: "中國", 黃金: "倫敦", 白銀: "墨西哥", "鐵礦砂 62%": "西澳", 熱軋鋼捲: "中國" }, seen = {};
    return { look: [150, 0], alt: 17000, dir: "in", title: "原物料期貨", eyebrow: "市場 · 主要產地或定價地 → 台灣",
      nodes: items("commodities").filter(x => AT[x.name]).map(x => { const ll = GXP[AT[x.name]].slice(), k = seen[AT[x.name]] = (seen[AT[x.name]] || 0) + 1; if (k > 1) { ll[0] += 4 * (k - 1); ll[1] -= 3 * (k - 1); } const u = GX_UNIT[x.unit] || x.unit || "";
        return { name: x.name, ll, chg: x.chg_pct, price: x.price != null ? nf(x.price) : null, sub: `${u ? u + "・" : ""}${gxPct(x.chg_pct)}・${AT[x.name]}` }; }),
      why: "線從主要產地或定價地拉到台灣：台灣的原料大多靠進口，這些價格最後會進到成本。" };
  },
  lux() {
    const AT = { LVMH: "巴黎", Kering: "巴黎", "Hermès": "巴黎", Inditex: "西班牙", "Fast Retailing": "東京", Nike: "奧勒岡", Prada: "米蘭", Burberry: "倫敦" }, seen = {};
    return { look: [60, 40], alt: 17000, dir: "in", title: "精品與快時尚", eyebrow: "市場 · 品牌總部 → 台灣",
      nodes: items("luxury").filter(x => AT[x.name]).map(x => { const ll = GXP[AT[x.name]].slice(), k = seen[AT[x.name]] = (seen[AT[x.name]] || 0) + 1; if (k > 1) { ll[0] += 3 * (k - 1); ll[1] += 2 * (k - 1); } return { name: x.name, ll, chg: x.chg_pct, sub: `${AT[x.name]}　${gxPct(x.chg_pct)}` }; }),
      why: "品牌總部所在地的股價漲跌，看消費情緒從哪裡先轉。" };
  },
  exports() {   // 台灣出口：線從台灣拉到各市場，粗細＝近 3 個月年增
    const E = P.exports || {}, AT = { 美國: [-98, 38.5], 中國大陸及香港: GXP["上海"], 東協: [104, 4], 日本: GXP["東京"], 南韓: GXP["首爾"], 德國: GXP["法蘭克福"], 墨西哥: GXP["墨西哥"], 越南: [106, 16], 印度: GXP["孟買"] };
    const rows = (E.markets || []).concat((E.extra || []).filter(x => x.name === "墨西哥" || x.name === "越南" || x.name === "印度"));
    return { look: [175, 22], alt: 18000, dir: "out", scale: 60, title: "台灣出口賣到哪裡", eyebrow: `總經 · 財政部 · ${(E.month || "").replace("-", "/")} · 近 3 個月比去年同期`,
      nodes: rows.filter(x => AT[x.name] && x.yoy3 != null).map(x => ({ name: x.name === "中國大陸及香港" ? "中港" : x.name, ll: AT[x.name], chg: x.yoy3,
        sub: `${(x.month || "").replace("-", "/")} 單月 ${x.v != null ? nf(x.v) : "—"} 億美元（${x.yoy != null ? gxPct(x.yoy) : "—"}）${x.ee_share != null ? `・機械及電機設備占 ${Math.round(x.ee_share)}%` : ""}${x.name === "墨西哥" || x.name === "越南" || x.name === "印度" ? "・國別總表，較晚更新" : ""}` })),
      why: `線越粗，對那個市場的出口近 3 個月成長越多。${E.note ? E.note + "。" : ""}墨西哥、越南、印度用財政部國別總表，比主要市場晚 2～3 個月。`,
      extra: (E.goods || []).length ? `<div class="nvh">賣什麼（近 3 個月比去年同期）</div>` + barsHTML(E.goods.map(g => ({ name: g.name, v: g.yoy3, txt: `${pct(g.yoy3, 1)}・占 ${Math.round(g.share || 0)}%` }))) + `<p class="why">電子零組件含半導體；資通與視聽含伺服器、電腦。</p>` : "" };
  },
  liq() {
    const L = P.liquidity || {}, n = L.net || {}, k = n.chg4w;
    return { look: [-160, 35], alt: 16000, dir: "out", title: "美元流動性", eyebrow: "總經 · 聯準會",
      nodes: [{ name: "聯準會", ll: GXP["華盛頓"], chg: k == null ? null : k / 10, sub: `淨流動性 ${nf(n.value || 0)} 十億美元　四週 ${k == null ? "—" : (k >= 0 ? "+" : "−") + nf(Math.abs(k))}` }],
      why: "淨流動性＝聯準會資產 − 財政部帳戶 − 逆回購。變多（綠）代表市場上的美元變多，通常對台股、科技股有利。",
      extra: listHTML([{ t: `逆回購 ${nf((L.rrp || {}).value || 0)} 十億`, s: (L.rrp || {}).date }, { t: `準備金 ${nf((L.reserves || {}).value || 0)} 十億`, s: (L.reserves || {}).date }, { t: `聯準會資產 ${nf((L.walcl || {}).value || 0)} 十億`, s: (L.walcl || {}).date }]) };
  },
  ai() {
    const CO = [["OpenAI", /openai/i, "舊金山"], ["Anthropic", /anthropic|claude/i, "舊金山"], ["Google", /google|deepmind|gemini/i, "山景城"], ["Meta", /\bmeta\b|llama/i, "門洛帕克"],
      ["Microsoft", /microsoft/i, "雷德蒙"], ["Nvidia", /nvidia/i, "聖塔克拉拉"], ["Amazon", /amazon|aws/i, "西雅圖"], ["Apple", /apple/i, "庫比蒂諾"], ["DeepSeek", /deepseek/i, "杭州"],
      ["阿里巴巴", /alibaba|qwen/i, "杭州"], ["Mistral", /mistral/i, "巴黎"], ["百度", /baidu|ernie/i, "北京"]];
    const by = {};
    for (const x of items("aiwire")) { const txt = `${x.title} ${x.source}`, c = CO.find(c => c[1].test(txt)); if (c) (by[c[0]] = by[c[0]] || { c, xs: [] }).xs.push(x); }
    const seen = {};
    return { look: [-170, 38], alt: 15000, dir: "in", title: "AI 公司最新動作", eyebrow: "訊號 · 總部位置 · 線越粗動作越多",
      nodes: Object.values(by).map(({ c, xs }) => { const ll = GXP[c[2]].slice(), k = seen[c[2]] = (seen[c[2]] || 0) + 1; if (k > 1) { ll[0] += 1.6 * (k - 1); ll[1] += 1.2 * (k - 1); } return { name: c[0], ll, chg: null, w: xs.length, sub: xs[0].title.slice(0, 40) }; }),
      why: "近期有動作的 AI 公司總部；線連回台灣，因為它們的晶片和伺服器大多在台灣做。",
      extra: listHTML(Object.values(by).flatMap(({ c, xs }) => xs.slice(0, 2).map(x => ({ t: x.title, s: `${c[0]}・${x.source}`, url: x.url }))).slice(0, 8)) };
  },
  wnews() { return { mode: "news", lookLL: [60, 25], alt: 17000, title: "全球新聞", eyebrow: "輿情 · 全球", nodes: [], why: "" }; },
  press() { return { mode: "press", lookLL: [124, 24], alt: 8500, title: "地面氣壓圖", eyebrow: "現場 · 氣壓", nodes: [], why: "" }; },
  clock() {
    const now = Date.now();
    return { mode: "clock", lookLL: [112, 26], alt: 21000, title: "市場時鐘", eyebrow: "市場 · 各交易所",
      nodes: MKX.map(x => { const s = mkStatus(x, now); return { name: x.c, ll: x.ll, x, s }; }), why: "" };
  },
  inst() {
    const I = ((((P.tw_market || {}).institutions) || {}).items || []), f = I.find(x => /外資/.test(x.name)) || {};
    return { look: [170, 35], alt: 15000, dir: (f.net || 0) >= 0 ? "in" : "out", title: "三大法人買賣超", eyebrow: "市場 · 外資的錢流進還是流出",
      nodes: f.net != null ? [{ name: "外資", ll: GXP["紐約"], chg: Math.max(-3, Math.min(3, f.net / 150)), sub: `${f.net >= 0 ? "買超" : "賣超"} ${nf(Math.abs(f.net))} 億` }, { name: "（香港、新加坡帳戶）", ll: GXP["香港"], chg: Math.max(-3, Math.min(3, f.net / 300)), sub: "" }] : [],
      why: `外資${(f.net || 0) >= 0 ? "買超，光點流進台灣" : "賣超，光點從台灣流出"}；線越粗金額越大。`,
      extra: barsHTML(I.filter(x => x.name !== "合計").map(x => ({ name: x.name, v: x.net, txt: (x.net > 0 ? "+" : "−") + nf(Math.abs(x.net)) + " 億" }))) };
  },
};
function gxCard(key) {
  if (key === "clock") return mkCard();
  if (key === "press") return prsCard();
  if (key === "wnews") return wnCard();
  let s = null; try { s = GX_SPEC[key](); } catch (e) { console.warn(e); }
  if (!s) return { html: sideHTML({ title: "地球", body: '<p class="empty">資料暫時讀不到</p>' }) };
  const rows = s.nodes.slice().sort((a, b) => Math.abs(b.chg ?? 0) - Math.abs(a.chg ?? 0));
  return { layer: "gx", gx: key, html: sideHTML({ eyebrow: s.eyebrow, title: s.title, body: (key === "world" ? worldViz() : "") + `<p class="why">${s.why}</p>` + (key === "ai" || key === "liq" || key === "inst" || key === "world" ? "" : listHTML(rows.map(n => ({ t: n.price != null ? `${n.name}　${n.price}` : n.name, s: n.sub })))) + (s.extra || "") }) };
}
function gxBuild() {
  if (GX.g) { SG.remove(GX.g); GX.g.traverse(o => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }); }
  GX.g = new THREE.Group(); GX.flows = []; GX.lbls = []; SG.add(GX.g);
  const s = GX.spec; if (!s || !GLOBE) return;
  if (s.mode === "clock") { gxClock(); return; }
  if (s.mode === "press") { gxPress(); return; }
  if (s.mode === "news") { gxNews(); return; }
  s.nodes.forEach((n, i) => {
    if (!n.ll) return;
    const pts = s.dir === "out" ? GLOBE.arc(TW_LL, n.ll, 0.05, 90) : GLOBE.arc(n.ll, TW_LL, 0.05, 90), col = gxCol(n.chg);
    const mag = n.chg == null ? Math.min(1, (n.w || 1) / 4) : Math.min(1, Math.abs(n.chg) / (s.scale || 2.5)), r = 7 + 26 * mag;
    const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 90, r, 6, false), fm(new THREE.MeshBasicMaterial({ color: col, blending: THREE.AdditiveBlending, depthTest: true, depthWrite: false }), 0.32 + 0.4 * mag));
    const dot = new THREE.Mesh(new THREE.SphereGeometry(30 + 40 * mag, 16, 12), fm(new THREE.MeshBasicMaterial({ color: col, depthTest: true }), 0.95));
    dot.position.copy(GLOBE.G(n.ll[0], n.ll[1], 30));
    const P0 = dotsObj(14, MOBILE ? 7 : 6, 1);
    P0.material.color = new THREE.Color(col);
    GX.g.add(tube, dot, P0);
    GX.flows.push({ pts, P: P0, sp: 0.06 + 0.12 * mag, off: i * 0.13 });
    GX.lbls.push([addLabel(`<span class="gxl" data-gx="${i}"><b>${esc(n.name)}</b>${n.price != null ? `<em>${esc(n.price)}</em>` : ""}${n.chg != null ? `<em style="color:#${new THREE.Color(col).getHexString()}">${s.key === "liq" || s.key === "inst" ? "" : gxPct(n.chg)}</em>` : n.w ? `<em>${n.w} 則</em>` : ""}</span>`, GLOBE.G(n.ll[0], n.ll[1], 260), "gx", "gx", 2 + mag * 3), GLOBE.G(n.ll[0], n.ll[1], 0)]);
  });
  const tw = new THREE.Mesh(new THREE.SphereGeometry(55, 16, 12), fm(new THREE.MeshBasicMaterial({ color: 0xffffff }), 1)); tw.position.copy(GLOBE.G(TW_LL[0], TW_LL[1], 40)); GX.g.add(tw);
  addLabel(`<span class="gxl tw"><b>台灣</b></span>`, GLOBE.G(TW_LL[0], TW_LL[1], 300), "gx", "gx", 9, () => ({ html: `<b>${esc(s.title || "台灣")}</b><p>${esc(s.why || "")}</p>${s.nodes.length ? `<p>${s.nodes.slice(0, 6).map(n => `${esc(n.name)} ${n.chg != null ? gxPct(n.chg) : ""}`).join("　")}</p>` : ""}` }));
}
function gxClock() {
  clearLabels("gx"); GX.lbls = []; GX.rings = [];
  const now = Date.now();
  for (const x of MKX) {
    const st = mkStatus(x, now), col = new THREE.Color(MK_ST[st.st][0]), on = st.st === "open";
    const dot = new THREE.Mesh(new THREE.SphereGeometry(on ? 70 : 48, 16, 12), fm(new THREE.MeshBasicMaterial({ color: col, depthTest: true }), 1));
    dot.position.copy(GLOBE.G(x.ll[0], x.ll[1], 30)); GX.g.add(dot);
    if (on || st.st === "lunch" || st.st === "pre" || st.st === "post") {   // 開著的市場：一圈一圈往外擴散的光環
      const n = GLOBE.G(x.ll[0], x.ll[1], 0).sub(_gxC).normalize();
      for (let i = 0; i < 2; i++) { const r = new THREE.Mesh(new THREE.RingGeometry(0.82, 1, 48), fm(new THREE.MeshBasicMaterial({ color: col, transparent: true, depthTest: true, depthWrite: false, side: THREE.DoubleSide }), 0.6));
        r.position.copy(GLOBE.G(x.ll[0], x.ll[1], 35)); r.lookAt(r.position.clone().add(n)); GX.g.add(r); GX.rings.push({ r, ph: i * 0.5, sp: on ? 0.5 : 0.25 }); }
    }
    const lt = `${String(Math.floor(st.loc.m / 60)).padStart(2, "0")}:${String(st.loc.m % 60).padStart(2, "0")}`;
    const sub = st.st === "open" ? `剩 ${inTxt(st.until - now)}` : st.until ? `${whenTxt(st.until).replace(/^今天 /, "")} 開` : "";
    GX.lbls.push([addLabel(`<span class="gxl mkg ${st.st}" data-mx="${x.k}"><b>${esc(x.n)}</b><em style="color:${MK_ST[st.st][0]}">${MK_ST[st.st][1]}${st.why ? "・" + esc(st.why).slice(0, 8) : ""}</em><small>${esc(x.c)} ${lt}${sub ? "・台北 " + sub : ""}</small></span>`, GLOBE.G(x.ll[0], x.ll[1], 300), "gx", "gx", on ? 6 : 3), GLOBE.G(x.ll[0], x.ll[1], 0)]);
  }
  GX.clockAt = now;
}
const _gxC = V(0, -6371, 0), _gxA = V(0, 0, 0), _gxB = V(0, 0, 0);
function gxTick(T) {
  if (GX.spec && GX.spec.mode === "clock") {
    for (const o of GX.rings || []) { const u = (T * o.sp + o.ph) % 1; o.r.scale.setScalar(90 + 520 * u); o.r.material.opacity = 0.55 * (1 - u); }
    if (GLOBE.mat) { const [lo, la] = sunLL(); GLOBE.mat.uniforms.uSunN.value.copy(GLOBE.G(lo, la, 0).sub(_gxC).normalize()); }
    if (Date.now() - (GX.clockAt || 0) > 30000) { GX.g.traverse(o => { o.geometry && o.geometry.dispose(); }); GX.g.clear(); gxClock(); }   // 每 30 秒重新判斷開收盤
  }
  for (const [L, p] of GX.lbls || []) { _gxA.copy(p).sub(_gxC); _gxB.copy(camera.position).sub(p); L.hide = _gxA.dot(_gxB) < 0; }   // 在地球背面的標籤先藏起來
  for (const f of GX.flows) { const a = f.P.geometry.attributes.position, N = a.count;
    for (let i = 0; i < N; i++) { const u = (i / N + T * f.sp + f.off) % 1, v = arcAt(f.pts, u); a.setXYZ(i, v.x, v.y, v.z); }
    a.needsUpdate = true; }
}
layers.gx = {
  get g() { return GX.g || new THREE.Group(); },
  on() {
    try { GX.spec = GX_SPEC[GX.key](); GX.spec.key = GX.key; } catch (e) { GX.spec = null; }
    ST.globeForce = true; document.body.classList.add("fl-on");
    // 鏡頭對準「台灣＋各節點」的中間，讓弧線大多在畫面裡
    const C = V(0, -6371, 0), look = GLOBE.G(TW_LL[0], TW_LL[1], 0).sub(C).normalize().multiplyScalar(2.5);
    if (GX.spec && GX.spec.lookLL) look.copy(GLOBE.G(GX.spec.lookLL[0], GX.spec.lookLL[1], 0).sub(C));
    else for (const n of (GX.spec && GX.spec.nodes) || []) if (n.ll) look.add(GLOBE.G(n.ll[0], n.ll[1], 0).sub(C).normalize());
    look.normalize();
    if (GLOBE.mat) GLOBE.mat.uniforms.uTerm.value = GX.spec && GX.spec.mode === "clock" ? 1 : 0;
    controls.enabled = false; controls.autoRotate = false; GD.on = true; GD.vx = GD.vy = 0;
    controls.minDistance = 0; controls.maxDistance = Infinity; controls.minPolarAngle = 0; controls.maxPolarAngle = Math.PI;
    camera.up.copy(gdAxis()); camera.near = 20; camera.far = 300000; camera.updateProjectionMatrix();
    flyTo(C.clone().addScaledVector(look, 6371 + ((GX.spec && GX.spec.alt) || 12000) * (MOBILE ? 1.5 : 1.15)), C, 2.2);
    gxBuild(); GX.g.visible = true;
  },
  off() {
    clearLabels("gx"); if (GX.g) GX.g.visible = false; if (GLOBE && GLOBE.mat) GLOBE.mat.uniforms.uTerm.value = 0;
    ST.globeForce = false; document.body.classList.remove("fl-on");
    GD.on = false; GD.ptrs.clear(); camera.up.set(0, 1, 0); controls.enabled = ST.explore; controls.minDistance = 0.25; controls.maxPolarAngle = Math.PI * 0.46;
    if (ST.explore) { controls.maxDistance = 1600; camera.near = 1; camera.updateProjectionMatrix(); flyTo(ISLAND.pos, ISLAND.tgt, 1.8); }
  },
  tick(T, dt) { gdTick(dt); gxTick(T); },
};
