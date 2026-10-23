# 3D 首頁建置：python3 lab/g/src/build.py lab/g/src → 產生 lab/g/src/index.html（測試版）
# 正式上線：複製到 lab/g/index.html，再把標題換回正式版寫到根目錄 index.html（見 CLAUDE.md「3D 首頁」）
import sys,re,os
G=sys.argv[1] if len(sys.argv)>1 else os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..'))
src=open(os.path.join(ROOT,'lab','_src.html')).read()
css=open(G+'/story.css').read(); js=open(G+'/story_head.js').read()+open(G+'/story_body.js').read()+open(G+'/intro.js').read()+open(G+'/flights.js').read()+open(G+'/mkcal.js').read()+open(G+'/press.js').read()+open(G+'/wnews.js').read()+open(G+'/gx.js').read()+open(G+'/earth.js').read()+open(G+'/nav.js').read()+open(G+'/cam.js').read()+open(G+'/glass.js').read()+open(G+'/tb.js').read()+open(G+'/click.js').read()+open(G+'/mobile.js').read()+open(G+'/grants.js').read()+open(G+'/prices.js').read()+open(G+'/tourism.js').read()+open(G+'/gtop.js').read()+open(G+'/lens2.js').read()+open(G+'/insights.js').read()+open(G+'/seas.js').read()+open(G+'/area.js').read()+open(G+'/city.js').read()+open(G+'/money.js').read()+open(G+'/viz.js').read()+open(G+'/usage.js').read()+open(G+'/deeplink.js').read()
def rep(a,b,cnt=1):
    global src
    assert src.count(a)==cnt, (a[:70], src.count(a)); src=src.replace(a,b)
rep('<title>台灣此刻 · dalta 情報站</title>','<title>台灣此刻 · 劇本版（測試）</title>\n<meta name="robots" content="noindex">')
rep('</style>\n<script type="importmap">', css+'</style>\n<script type="importmap">')
rep('<div id="caption">','<main id="story" aria-label="今天的台灣"></main>\n<aside id="side" aria-live="polite"></aside>\n<svg id="leaderSvg" aria-hidden="true"><g id="leaderG" style="opacity:0"><line id="leader"/><circle id="leaderDot" r="3.5"/></g></svg>\n<div id="dock2" aria-label="情報站分類"></div>\n<div id="intro" aria-hidden="true"></div>\n<canvas id="ihud" aria-hidden="true"></canvas><div id="ihudTxt" aria-hidden="true"></div>\n\n<div id="caption">')
rep('$("go").onclick = start;','if ($("go")) $("go").onclick = start;')
rep('/* ---------- 啟動 ---------- */', js+'\n/* ---------- 啟動 ---------- */')
rep('  controls.update(); renderer.render(scene, camera); placeLabels();','  if (ST.on) storyTick(dt);\n  if (!ST.on || ST.explore) controls.update(); else camera.lookAt(controls.target);\n  renderer.render(scene, camera); placeLabels();')
rep('''    camera.position.set(-200, 1300, 1100); controls.target.set(0, 0, 0);
    if (MOBILE) flyTo(new THREE.Vector3(40, 560, 560), new THREE.Vector3(0, 0, -90), 3.2);
    else flyTo(new THREE.Vector3(200, 400, 470), new THREE.Vector3(0, 60, 0), 3.2);
    $("load").classList.add("done");
    loop();''','''    controls.enabled = false; controls.autoRotate = false; document.body.classList.add("storying");
    try { await buildStory(); } catch (e) { console.error('story', e); ST.on = false; controls.enabled = true; document.body.classList.remove("storying"); start(); }
    $("load").classList.add("done");
    loop();''')
# 夜間燈光強度可調
rep('* uNight * (1.0 - smoothstep(0.25, 0.85, uClose));','* uNight * (1.0 - smoothstep(0.25, 0.85, uClose)) * uLightK;')
rep('uniform sampler2D uLights; uniform float uHasLights; uniform float uClose;")','uniform sampler2D uLights; uniform float uHasLights; uniform float uClose; uniform float uLightK;")')
rep('uClose: { value: 0 } };','uClose: { value: 0 }, uLightK: { value: 1 } };')
# 氣象署缺值會回 -99，別印出來
rep('<span class="n"> ${esc(nm)} ${esc(it.weather || "")}</span>','<span class="n"> ${esc(nm)} ${esc(it.weather && it.weather !== "-99" ? it.weather : "")}</span>')
# 開場掃描：還沒掃到的地方是線框地形（經緯格＋等高線），掃描線經過才露出真實地表
rep('uClose: { value: 0 }, uLightK: { value: 1 } };','uClose: { value: 0 }, uLightK: { value: 1 }, uScan: { value: 99 }, uScanOn: { value: 0 } };')
rep('uniform float uClose; uniform float uLightK;")','uniform float uClose; uniform float uLightK; uniform float uScan; uniform float uScanOn;")')
rep("""          diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 0.55, rc.a * uRadar);
        }""","""          diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 0.55, rc.a * uRadar);
        }
        if (uScanOn > 0.001) {
          float sd = vLL.y - uScan, hid = smoothstep(-0.01, 0.06, sd) * uScanOn;
          diffuseColor.rgb *= 1.0 - hid * 0.94; totalEmissiveRadiance *= 1.0 - hid;
          vec2 gq = abs(fract(vLL * 12.0) - 0.5); float gline = smoothstep(0.035, 0.0, min(gq.x, gq.y));
          float cline = smoothstep(0.06, 0.0, abs(fract(vElev / 300.0) - 0.5)) * step(30.0, vElev);
          totalEmissiveRadiance += vec3(0.22, 0.7, 1.0) * (gline * 0.22 + cline * 0.55) * hid;
          totalEmissiveRadiance += vec3(0.45, 0.9, 1.0) * (exp(-pow(sd / 0.015, 2.0)) * 1.25 + exp(min(sd, 0.0) / 0.25) * step(sd, 0.0) * 0.12) * uScanOn;
        }""")
# 故事模式不放 12 種物件
rep('setupFlow(); setupObjects(); setupObjects2();','setupFlow();',2)
exec(open(G+'/fx_patch.py').read())
exec(open(G+'/ortho_patch.py').read())
exec(open(G+'/perf_patch.py').read())
exec(open(G+'/adapt_patch.py').read())
exec(open(G+'/facade_patch.py').read())
exec(open(G+'/light_patch.py').read())
exec(open(G+'/life_patch.py').read())
exec(open(G+'/mem_patch.py').read())
exec(open(G+'/landmark_patch.py').read())
exec(open(G+'/nav_patch.py').read())
exec(open(G+'/info_patch.py').read())
exec(open(G+'/mobile_patch.py').read())
exec(open(G+'/glass_patch.py').read())
exec(open(G+'/refresh_patch.py').read())
open(G+'/index.html','w').write(src)
print('ok', len(src))
