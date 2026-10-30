import { execSync } from 'child_process';
import fs from 'fs'; import path from 'path';
const { chromium } = await import(path.join(execSync('npm root -g').toString().trim(), 'playwright/index.mjs'));
const L = path.join(path.dirname(new URL(import.meta.url).pathname), '..', '.work');
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await b.newContext({ viewport: { width: +process.argv[2], height: 900 } });
const mime = f => f.endsWith('.json') ? 'application/json' : 'text/html';
await ctx.route('**/*', async r => { const u = new URL(r.request().url()); let f = null;
  if (u.host === 'raw.githubusercontent.com') f = path.join(L, 'raw', path.basename(u.pathname));
  else if (u.host === 'lab.local') { let p = u.pathname; if (p.endsWith('/')) p += 'index.html'; f = path.join(L, 'site', p); }
  if (f && fs.existsSync(f)) return r.fulfill({ body: fs.readFileSync(f), contentType: mime(f) });
  return r.abort(); });
const p = await ctx.newPage();
p.on('pageerror', e => console.log('pageerror:', e.message.slice(0,200)));
await p.goto('http://lab.local/terminal/'); await p.waitForTimeout(7000);
const TAB = { 'p-twsectors':'macro', 'p-sectors':'macro', 'p-champions':'macro', 'p-polls':'social','p-appstore':'social','p-pop':'social','p-forums':'social','p-mood':'social', 'p-aicycle':'macro','p-dlead':'macro','p-credit':'macro','p-exports':'macro','p-stress':'macro','p-logistics':'market','p-uspolicy':'intel','p-ossuse':'intel','p-insights':'overview','p-theses':'overview','p-cars':'macro','p-permits':'macro','p-renewal':'macro','p-prices':'macro','p-tourism':'macro','p-cards':'macro','p-gap':'trend','p-migration':'trend','p-births':'trend','p-maptools':'trend','p-clinics':'intel','p-aesthetic':'intel','p-grants':'intel','p-gtop':'social','p-worldnews':'social','p-townnews':'social','p-plaact':'live','p-cables':'live','p-pressure':'live' };
for (const id of process.argv.slice(3)) { await p.evaluate(k => document.querySelector('#tab-' + k).click(), TAB[id]); await p.waitForTimeout(1500);
  await p.evaluate(k => { const e = document.getElementById(k); if (e && !e.offsetParent) { const b = document.querySelector('[data-ibp="' + k + '"]'); b && b.click(); } }, id); await p.waitForTimeout(800);
  const el = await p.$('#' + id); if (!el) { console.log('missing', id); continue; }
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(400); await el.screenshot({ path: `${L}/el_${id}.png` }); console.log('shot', id); }
await b.close();
