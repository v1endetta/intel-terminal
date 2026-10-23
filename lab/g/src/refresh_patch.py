# 每 5 分鐘更新資料：原本把所有圖層刪掉只重建五個 → 航班、地球場景這兩個圖層 5 分鐘後就消失（點了沒反應、正在看的會被踢回台灣）
# 改成只重建那五個；舊的幾何／材質釋放掉（長時間開著手機不會越來越吃記憶體）；航班資料原地換新，不打斷正在看的人
rep('''        const was = cur; if (cur) { layers[cur].off && layers[cur].off(); }
        for (const k in layers) { scene.remove(layers[k].g); }
        for (const k in layers) delete layers[k];
        setupWx(); setupQuake(); setupHouse(); setupTraffic(); setupFlow();
        cur = null; if (was && document.body.classList.contains("exploring")) setLayer(was);
      } catch (e) { }''','''        const REB = ["wx", "quake", "house", "traffic", "flow"], was = cur, inReb = REB.includes(cur);
        if (inReb) { try { layers[cur].off && layers[cur].off(); } catch (e) { console.warn(e); } }
        for (const k of REB) if (layers[k]) { const g = layers[k].g; scene.remove(g); g.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose()); }); delete layers[k]; }
        setupWx(); setupQuake(); setupHouse(); setupTraffic(); setupFlow();
        if (inReb) { cur = null; if (document.body.classList.contains("exploring")) setLayer(was); }
        try { flRefresh(); } catch (e) { console.warn("flights refresh", e); }
        try { const sig = Object.values(P || {}).map(x => (x && x.updatedAt) || "").join("|"); if (ST._sig && sig !== ST._sig && ST.redrawCard) ST.redrawCard(); ST._sig = sig; } catch (e) { console.warn("card redraw", e); }   // 資料有變：開著的卡片跟著重畫
      } catch (e) { console.warn("refresh", e); }''')
# 雷達圖每次重抓一張新貼圖，舊的要釋放
rep('uni.uRadarTex.value = t; });','const o = uni.uRadarTex.value; uni.uRadarTex.value = t; if (o && o !== t && o.dispose) o.dispose(); });')
# 切換圖層時任何一步出錯，都不能讓畫面卡在半套狀態（例如地球模式關不掉）
rep('''  if (cur && layers[cur]) { layers[cur].g.visible = false; layers[cur].off && layers[cur].off(); }
  cur = name; const L = layers[name]; if (!L) return;
  L.g.visible = true; L.on && L.on();''','''  if (cur && layers[cur]) { try { layers[cur].g.visible = false; layers[cur].off && layers[cur].off(); } catch (e) { console.warn("layer off", cur, e); } }
  cur = name; const L = layers[name]; if (!L) return;
  try { L.g.visible = true; L.on && L.on(); } catch (e) { console.warn("layer on", name, e); }''')
