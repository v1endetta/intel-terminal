# ===== 分層地圖：點擊改成「往下一層」，每格判斷層級 =====
rep('  if (c) openCard(c);\n});', '  if (c && ST.explore && typeof navClickAt === "function") navClickAt(lon, lat, c);   // 舊的縣市小卡會蓋住右邊的資訊卡，改成點了就飛過去，資訊交給分層地圖\n});')
rep('  lodTick(dt); orthoTick(dt); lightTick(dt); lifeTick(dt); earthTick();', '  lodTick(dt); orthoTick(dt); lightTick(dt); lifeTick(dt); earthTick(); navTick(dt);')
