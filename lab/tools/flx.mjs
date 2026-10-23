import { execSync } from 'child_process';
import fs from 'fs'; import path from 'path';
const { chromium } = await import(path.join(execSync('npm root -g').toString().trim(), 'playwright/index.mjs'));
const L = path.join(path.dirname(new URL(import.meta.url).pathname), '..', '.work');   // setup.sh 建的測試環境；截圖也存這裡
const [,, prefix='flx', w='1440', h='900'] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'] });
const mob = +w < 600;
const ctx = await b.newContext({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1, isMobile: mob, hasTouch: mob, userAgent: mob ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile' : undefined });
const mime = f => f.endsWith('.js') ? 'application/javascript' : f.endsWith('.json') ? 'application/json' : f.endsWith('.png') ? 'image/png' : f.endsWith('.bin') ? 'application/octet-stream' : 'text/html';
await ctx.route('**/*', async r => { const u = new URL(r.request().url()); let f = null;
  if (u.host === 'cdn.jsdelivr.net') f = path.join(L, 'npm/node_modules/three', u.pathname.replace('/npm/three@0.160.0/', ''));
  else if (u.host === 'raw.githubusercontent.com') f = path.join(L, 'raw', path.basename(u.pathname));
  else if (u.host === 'lab.local') { let p = u.pathname; if (p.endsWith('/')) p += 'index.html'; f = path.join(L, 'site', p); }
  if (f && fs.existsSync(f) && fs.statSync(f).isFile()) return r.fulfill({ body: f.endsWith('lab/g/index.html') ? fs.readFileSync(f,'utf8').replace('}, 300000);', '}, ' + (process.env.RI||300000) + ');').replace('window.__story = ST', 'window.__story = ST; window.__dbgS = () => ({ cur, gd: GD.on, ce: controls.enabled, fly: !!fly, fov: camera.fov, near: camera.near, cam: camera.position.toArray().map(Math.round), tgt: controls.target.toArray().map(Math.round) })') : fs.readFileSync(f), contentType: mime(f), headers: { 'access-control-allow-origin': '*' } });
  if (f) return r.fulfill({ status: 404, body: 'nf' }); return r.abort(); });
const p = await ctx.newPage();
p.on('console', m => { if (m.type() === 'warning' || m.type() === 'error') console.log('console:', m.text().slice(0, 300)); }); p.on('pageerror', e => console.log('pageerror:', e.message.slice(0, 400), (e.stack||'').slice(0,600)));
await p.goto('http://lab.local/lab/g/' + (process.env.Q || ''));
await p.waitForFunction(() => document.getElementById('load').classList.contains('done'), null, { timeout: 180000 });
const st = async tag => console.log(tag, JSON.stringify(await p.evaluate(() => ({ ...window.__dbgS(), gf: __story.globeForce, ex: __story.explore, built: __FL.built, gvis: __FL.g && __FL.g.visible, nR: Object.keys(__FL.R).length, fl: document.body.classList.contains('fl-on'), chip: (document.querySelector('#chips [aria-selected=true]')||{}).textContent, side: (document.querySelector('#side h2, #side .t')||{}).textContent }))));
const chip = async t => { const loc = p.locator('#chips button', { hasText: t }).first(); await loc.click({ timeout: 5000 }).catch(e => console.log('clickfail', t, e.message.slice(0,200))); };
const seg = async t => { await p.locator('#dock2 .seg button', { hasText: t }).first().click({ timeout: 5000 }).catch(e => console.log('segfail', t, e.message.slice(0,200))); };
const steps = (process.env.STEPS || '').split(';').filter(Boolean);
for (const s of steps) { const [a, v] = s.split('|');
  if (a === 'wait') await p.waitForTimeout(+v);
  else if (a === 'st') await st(v);
  else if (a === 'shot') await p.screenshot({ path: `${L}/${prefix}_${v}.png`, timeout: 180000 });
  else if (a === 'chip') { await chip(v); console.log('chip', v); }
  else if (a === 'seg') { await seg(v); console.log('seg', v); }
  else if (a === 'gc') { await p.locator('#gcrumb [data-g=tw]').click({ timeout: 5000 }).catch(e => console.log('gcfail', e.message.slice(0,200))); console.log('gcrumb tw'); }
  else if (a === 'drag') { const [x,y,dx,dy] = v.split(',').map(Number); await p.mouse.move(x,y); await p.mouse.down(); for (let i=1;i<=10;i++) await p.mouse.move(x+dx*i/10, y+dy*i/10); await p.mouse.up(); console.log('drag'); }
  else if (a === 'tap') { const [x,y] = v.split(',').map(Number); await p.mouse.click(x,y); console.log('tap', x, y); }
  else if (a === 'wheel') { const [x,y,d,n] = v.split(',').map(Number); await p.mouse.move(x,y); for (let i=0;i<(n||1);i++){ await p.mouse.wheel(0,d); await p.waitForTimeout(60);} console.log('wheel'); }
  else if (a === 'key') { await p.keyboard.press(v); console.log('key', v); }
  else if (a === 'el') { const e = await p.$('#side'); if (e) await e.screenshot({ path: `${L}/${prefix}_${v}.png`, timeout: 120000 }); else console.log('noside'); }
  else if (a === 'js') { console.log('js', JSON.stringify(await p.evaluate(v)).slice(0,1500)); }
}
await b.close();
