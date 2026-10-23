
/* ---- 使用紀錄：只存在這台瀏覽器（localStorage），不上傳；跑 6 週後用來決定哪些晶片可以砍 ----
   記：點了哪個晶片（分類/名稱）、總次數、點過幾天、最後一次。終端機網址加 #usage 可以看整理好的表。 */
(() => {
  const K = "intel:usage", day = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
  let U = null; try { U = JSON.parse(localStorage.getItem(K) || "null"); } catch (_) {}
  if (!U || !U.start) U = { start: day(), p: {}, m: {} }; U.m = U.m || {};
  let dirty = false, lastK = "", lastT = 0;
  const save = () => { if (!dirty) return; dirty = false; try { localStorage.setItem(K, JSON.stringify(U)); } catch (_) {} };
  const hit = k => { if (!k || (k === lastK && Date.now() - lastT < 1500)) return; lastK = k; lastT = Date.now();
    const r = U.m[k] || (U.m[k] = { c: 0, days: 0 }); r.c++; if (r.last !== day()) { r.days++; r.last = day(); } dirty = true; save(); };
  document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("#chips button"); if (b && ST.curCat) hit(ST.curCat() + "/" + b.textContent.trim()); }, true);
  const wrap = () => { if (!ST.openAt || ST.openAt.__u) return !!(ST.openAt && ST.openAt.__u); const f = ST.openAt; ST.openAt = (c, n) => { hit(c + "/" + n); return f(c, n); }; ST.openAt.__u = 1; return true; };
  const t = setInterval(() => { if (wrap() && ST.allChips) { U.all3d = ST.allChips; dirty = true; save(); clearInterval(t); } }, 1000);
  addEventListener("pagehide", save);
})();
