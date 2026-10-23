# ===== 地圖上每個標籤都帶「點了要顯示什麼」：第 6 個參數（函式，點的時候才算） =====
rep('''"", "wx", /^(臺北|台北|高雄)/.test(nm) ? 1.5 : /^(新北|桃園|臺中|台中|臺南|台南)/.test(nm) ? 1 : 0);''',
    '''"", "wx", /^(臺北|台北|高雄)/.test(nm) ? 1.5 : /^(新北|桃園|臺中|台中|臺南|台南)/.test(nm) ? 1 : 0, () => wxInfo(it, c));''')
rep('''Q.slice(0, 4).forEach((q, i) => addLabel(`M${fmt(q.mag)}<span class="n"> ${ago(q.at)} · 深 ${fmt(q.depth, 0)} km</span>`, q._pos, i === 0 ? "big" : "", "quake"));''',
    '''Q.slice(0, 4).forEach((q, i) => addLabel(`M${fmt(q.mag)}<span class="n"> ${ago(q.at)} · 深 ${fmt(q.depth, 0)} km</span>`, q._pos, i === 0 ? "big" : "", "quake", 0, () => quakeInfo(q)));''')
rep('''new THREE.Vector3(b.x, b.y0 + b.h + 5, b.z), "pillv", "house"); }''',
    '''new THREE.Vector3(b.x, b.y0 + b.h + 5, b.z), "pillv", "house", 0, () => ({ html: `<b>${esc(b.name)}</b><p>實價登錄平均 ${fmt(b.v)} 萬／坪</p>`, go: () => navGoCounty(COUNTIES.find(c => c.name === b.name)), goTxt: "看各區房價" })); }''')
rep('''new THREE.Vector3(x, hAt(lon, lat) + 4, z), "", "traffic");''',
    '''new THREE.Vector3(x, hAt(lon, lat) + 4, z), "", "traffic", 0, () => ({ html: `<i class="lp-k" style="color:#ff453a">國道壅塞</i><b>${esc(nm)}</b><p>現在平均 ${s} km/h（低於 40 算壅塞）</p><p>高公局即時車速</p>`, go: () => flyNear(gp(lon, lat, 0), 6) }));''')
rep('''f.o.clone().add(new THREE.Vector3(0, 14, 0)), "flow", "flow");''',
    '''f.o.clone().add(new THREE.Vector3(0, 14, 0)), "flow", "flow", 0, () => ({ html: `<i class="lp-k">海外市場</i><b>${esc(f.s.label)}</b><p class="${f.s.chg >= 0 ? "up" : "dn"}">前一個交易日 ${sgn(f.s.chg)}${fmt(f.s.chg, 2)}%</p>${f.stuck ? "<p>⚠️ 這條線跟台股方向相反：海外漲、台股跌（或反過來），傳導卡住</p>" : ""}` }));''')
rep('''target.clone().add(new THREE.Vector3(0, 16, 0)), "flow", "flow");''',
    '''target.clone().add(new THREE.Vector3(0, 16, 0)), "flow", "flow", 0, () => ({ html: `<b>台股加權</b><p class="${tw >= 0 ? "up" : "dn"}">${sgn(tw)}${fmt(tw, 2)}%</p><p>外資 ${inst.net != null ? (inst.net > 0 ? "買超 " : "賣超 ") + fmt(Math.abs(inst.net), 0) + " 億" : "—"}</p><p>每條線是一個海外市場前一個交易日的漲跌，光點往台灣流；紅圈代表那個市場跟台股方向相反。</p>${(((P.tw_market || {}).institutions || {}).items || []).filter(x => x.name !== "合計").map(x => `<p>${esc(x.name)} ${x.net >= 0 ? "買超" : "賣超"} ${fmt(Math.abs(x.net), 0)} 億</p>`).join("")}` }));''')
