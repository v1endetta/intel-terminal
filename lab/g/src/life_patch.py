# ===== 讓城市動起來：車流（照即時車速）、夜間車燈、頂樓水塔與鐵皮加蓋（電腦版精細城市）=====
# 1) 背景執行緒：主要道路的中心線（給車子走）＋ 每棟公寓頂樓的水塔、鐵皮加蓋
rep('  const RP = [], RC = [];', '  const RP = [], RC = [], RD = [], RV = [];')
rep('    const w = W[cls] / 2000;', '    const w = W[cls] / 2000; let dd = Math.random();')
rep('      for (let q = 0; q < 6; q++) RC.push(cls);', '      for (let q = 0; q < 6; q++) RC.push(cls);\n      RD.push(dd, dd + L, dd + L, dd, dd + L, dd); RV.push(1, 1, -1, 1, -1, -1); dd += L;')
rep('    nb++;', '''    { const fl = h / 3.3;   // 3～15 樓的建物：頂樓常見的水塔、鐵皮加蓋
      if (fl >= 3 && fl <= 15) {
        let A = 0, ang = 0, best = 0;
        for (let k = 0; k < pts.length; k++) { const a = pts[k], b = pts[(k + 1) % pts.length]; A += a[0] * b[1] - b[0] * a[1]; const L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2; if (L2 > best) { best = L2; ang = Math.atan2(b[1] - a[1], b[0] - a[0]); } }
        A = Math.abs(A) / 2 * 1e6;
        if (A > 60 && A < 2500) {
          const ca = Math.cos(ang), sa = Math.sin(ang); let u0 = 1e9, u1 = -1e9, v0 = 1e9, v1 = -1e9;
          for (const p of pts) { const dx = p[0] - mx, dz = p[1] - mz, u = dx * ca + dz * sa, v = -dx * sa + dz * ca; u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
          const W2 = u1 - u0, D2 = v1 - v0, uc = (u0 + u1) / 2, vc = (v0 + v1) / 2, cxr = mx + uc * ca - vc * sa, czr = mz + uc * sa + vc * ca;
          if (Math.random() < 0.35 && W2 > 0.006) { const sw = W2 * (0.45 + Math.random() * 0.25), sd = D2 * (0.5 + Math.random() * 0.3), off = (W2 - sw) / 2 * (Math.random() < 0.5 ? -1 : 1);
            SH.push(cxr + off * ca, y1, czr + off * sa, sw, sd, ang, Math.floor(Math.random() * 4)); }
          if (Math.random() < 0.75) { const tu = uc + (Math.random() - 0.5) * W2 * 0.6, tv = vc + (Math.random() - 0.5) * D2 * 0.6;
            TK.push(mx + tu * ca - tv * sa, y1, mz + tu * sa + tv * ca, Math.random() < 0.6 ? 0 : 1); }
        }
      } }
    nb++;''')
rep('  const BK = new Map(); let P, N, I, R, C, B;', '  const BK = new Map(); let P, N, I, R, C, B; const TK = [], SH = [];')
rep('RU: RR, CU: CC, BH: BB,', 'RU: RR, CU: CC, BH: BB, RD: f(RD), RV: f(RV), TK: f(TK), SH: f(SH),')
rep('  scene.add(grp);\n  CITY[d.key] = { state: "ready", mesh: grp, nb: d.nb };', '  try { cityLife(grp, d); } catch (e) { console.warn("cityLife", e); }\n  scene.add(grp);\n  CITY[d.key] = { state: "ready", mesh: grp, nb: d.nb, life: grp.userData.life };')
rep('  lodTick(dt); orthoTick(dt); lightTick(dt);', '  lodTick(dt); orthoTick(dt); lightTick(dt); lifeTick(dt);')
rep('out.RP.buffer, out.RC.buffer,', 'out.RP.buffer, out.RC.buffer, out.RD.buffer, out.RV.buffer,')
rep('/* ---- 光影 ---- */', open(G + '/life.js').read() + '\n/* ---- 光影 ---- */')

# 自己逛可以拉到街道高度
rep('controls.minDistance = 3; controls.maxDistance = 1600;', 'controls.minDistance = 0.25; controls.maxDistance = 1600;')
rep('  lodTick(dt); orthoTick(dt); lightTick(dt); lifeTick(dt);', '  lodTick(dt); orthoTick(dt); lightTick(dt); lifeTick(dt); earthTick();')
