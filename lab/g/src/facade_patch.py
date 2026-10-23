# ===== 台灣街景立面（電腦版精細建物）=====
# 1) 背景執行緒多送一個「整棟幾層樓」給每個頂點（決定是公寓還是玻璃帷幕大樓）
rep('const BK = new Map(); let P, N, I, R, C;', 'const BK = new Map(); let P, N, I, R, C, B;')
rep('b = { P: [], N: [], I: [], R: [], C: [] };', 'b = { P: [], N: [], I: [], R: [], C: [], B: [] };')
rep('({ P, N, I, R, C } = bk(ci));', '({ P, N, I, R, C, B } = bk(ci));')
rep('R.push(0, 0); C.push(cuv[0], cuv[1]); }', 'R.push(0, 0); C.push(cuv[0], cuv[1]); B.push(h / 3.3); }')
rep('R.push(u[0], u[1]); C.push(cuv[0], cuv[1]); }', 'R.push(u[0], u[1]); C.push(cuv[0], cuv[1]); B.push(h / 3.3); }')
rep('CC = new Float32Array(nvAll * 2); let v0 = 0;', 'CC = new Float32Array(nvAll * 2), BB = new Float32Array(nvAll); let v0 = 0;')
rep('CC.set(b.C, v0 * 2); v0 += nv; }', 'CC.set(b.C, v0 * 2); BB.set(b.B, v0); v0 += nv; }')
rep('RU: RR, CU: CC,', 'RU: RR, CU: CC, BH: BB,')
rep('out.CU.buffer,', 'out.CU.buffer, out.BH.buffer,')
rep('bg.setAttribute("aCUV", new THREE.BufferAttribute(d.CU, 2));', 'bg.setAttribute("aCUV", new THREE.BufferAttribute(d.CU, 2)); if (d.BH) bg.setAttribute("aBH", new THREE.BufferAttribute(d.BH, 1));')

# 2) 立面著色：一樓騎樓與店面招牌、住宅磁磚＋鐵窗＋冷氣、老公寓水漬、14 樓以上玻璃帷幕；晚上窗戶、招牌、店面各自發光
FACADE = r'''{ vec3 roofC = texture2D(uOrtho, vec2(vRUV.x, 1.0 - vRUV.y)).rgb;
  vec3 bodyC = texture2D(uOrtho, vec2(vCUV.x, 1.0 - vCUV.y), 3.0).rgb;
  float FH = 3.3 / 1000.0 * 2.5;
  float hh2 = max(vY - vInfo.x, 0.0), fl = hh2 / FH, flI = floor(fl), ff = fract(fl);
  float H = max(vBH, 1.0), rnd = vInfo.y;
  float tower = clamp(step(16.0, H) * step(0.45, rnd) + step(28.0, H), 0.0, 1.0), low = 1.0 - tower,   // 16 樓以上一半是玻璃帷幕，28 樓以上都是；其他高樓仍是磁磚住宅
  old = step(H, 4.5) * step(rnd, 0.5);
  float bay = vH * 1000.0 / mix(3.4, 1.7, tower), bi = floor(bay), bf = fract(bay);
  float hb = fract(sin(bi * 12.9898 + flI * 78.233 + rnd * 437.0) * 43758.5453);
  float hb2 = fract(sin(bi * 39.346 + rnd * 11.135) * 43758.5453);
  vec3 tile = rnd < 0.22 ? vec3(0.80, 0.76, 0.68) : rnd < 0.42 ? vec3(0.72, 0.72, 0.70) : rnd < 0.58 ? vec3(0.82, 0.72, 0.66) : rnd < 0.74 ? vec3(0.88, 0.87, 0.84) : rnd < 0.88 ? vec3(0.62, 0.64, 0.64) : vec3(0.74, 0.66, 0.56);
  float lumB = dot(bodyC, vec3(0.3, 0.59, 0.11));
  tile = mix(tile, mix(vec3(lumB), bodyC, 0.5) * 1.15 + 0.06, 0.22);
  float grain = fract(sin(dot(floor(vec2(vH * 1000.0 / 0.3, hh2 * 1000.0 / 2.5 / 0.15)), vec2(12.9898, 78.233))) * 43758.5453);
  vec3 wall = tile * (0.94 + 0.06 * grain) * 0.86;
  float streak = fract(sin(floor(vH * 1000.0 / 1.1) * 3.17 + rnd * 91.0) * 43758.5453);
  wall *= 1.0 - old * (smoothstep(0.55, 1.0, streak) * (0.25 + 0.2 * (1.0 - ff)) + 0.16);
  float winX = step(0.16, bf) * step(bf, 0.84), winY = step(0.30, ff) * step(ff, 0.86);
  float isWin = winX * winY * step(1.0, flI) * step(0.12, hb);
  vec3 glass = vec3(0.09, 0.115, 0.15) + 0.06 * hb;
  float gx = fract((bf - 0.16) / 0.68 * 5.0), gy = fract((ff - 0.30) / 0.56 * 4.0);
  float bars = max(step(0.82, gx), step(0.85, gy)) * step(0.4, hb2) * low;
  vec3 res = mix(wall, glass, isWin);
  res = mix(res, vec3(0.58, 0.59, 0.58), bars * isWin * 0.85);
  float ac = step(0.68, hb) * step(0.22, bf) * step(bf, 0.46) * step(0.08, ff) * step(ff, 0.27) * step(1.0, flI) * low;
  res = mix(res, vec3(0.83, 0.83, 0.80), ac);
  res = mix(res, wall * 1.14, step(ff, 0.07) * step(1.0, flI) * low);
  vec3 vdir = normalize(vViewPosition);
  float fres = pow(1.0 - clamp(abs(dot(vdir, normalize(vNormal))), 0.0, 1.0), 2.0);
  vec3 gt = rnd < 0.6 ? vec3(0.13, 0.19, 0.25) : rnd < 0.78 ? vec3(0.16, 0.22, 0.2) : rnd < 0.9 ? vec3(0.24, 0.2, 0.16) : vec3(0.32, 0.36, 0.4);   // 藍、綠、茶、銀灰玻璃
  vec3 cw = mix(gt, vec3(0.55, 0.64, 0.74), fres * 0.6 + 0.08 * hb2);
  cw = mix(cw, cw * 0.55, step(0.93, bf));
  cw = mix(cw, vec3(0.22, 0.24, 0.27), step(ff, 0.14));
  float g0 = (1.0 - step(1.0, fl)) * low;
  vec3 shopIn = mix(vec3(0.05, 0.05, 0.06), vec3(0.42, 0.36, 0.26), step(0.45, hb) * 0.6);
  float sgn = g0 * step(0.72, ff) * step(ff, 0.96) * step(0.2, hb);
  vec3 sc = hb < 0.42 ? vec3(0.86, 0.16, 0.13) : hb < 0.58 ? vec3(0.96, 0.78, 0.18) : hb < 0.72 ? vec3(0.13, 0.42, 0.86) : hb < 0.86 ? vec3(0.95, 0.95, 0.92) : vec3(0.12, 0.62, 0.34);
  float vsg = step(1.0, flI) * step(fl, 5.0) * step(0.86, bf) * step(0.62, hb2) * low * step(H, 13.0);
  vec3 vsc = hb2 < 0.75 ? vec3(0.9, 0.2, 0.15) : hb2 < 0.88 ? vec3(0.98, 0.85, 0.2) : vec3(0.95, 0.95, 0.95);
  vec3 fac = mix(res, cw, tower);
  fac = mix(fac, shopIn, g0 * step(ff, 0.72));
  fac = mix(fac, sc, sgn); fac = mix(fac, vsc, vsg);
  float detail = 1.0 - smoothstep(0.18, 0.55, fwidth(fl));   // 遠到一層樓不到幾個像素就改用平均色，不會閃成雜訊
  vec3 avgC = mix(mix(wall, glass, 0.32) * 0.95, cw, tower);
  fac = mix(avgC, fac, detail);
  fac *= mix(0.62, 1.0, clamp(hh2 * 60.0, 0.0, 1.0));
  _fw = mix(isWin, step(0.14, ff) * step(bf, 0.93), tower) * step(1.0, flI);
  float lh = fract(sin(bi * 7.13 + flI * 3.7 + rnd * 91.7) * 43758.5453); _flit = step(0.82, fract(lh * 13.7));   // _flit 拿來當冷白／暖黃的選擇
  _fw = mix(0.09, _fw * step(0.68, lh), detail);   // 約三成的窗亮著；遠處用平均亮度
  _fsign = sc * sgn + vsc * vsg;
  _fshop = vec3(1.0, 0.72, 0.42) * g0 * step(ff, 0.72) * step(0.45, hb) * 0.9;
  diffuseColor.rgb = mix(roofC * 1.08, fac, vSide); }'''
EMIT = 'totalEmissiveRadiance = (mix(vec3(1.0, 0.76, 0.5), vec3(0.85, 0.9, 1.0), _flit) * _fw * (0.45 + 0.5 * vInfo.y) * 0.95 + _fsign * 2.0 + _fshop) * uNight * vSide;'
rep('  m.customProgramCacheKey = () => "orthoB";', '''  { const ob = m.onBeforeCompile; m.onBeforeCompile = sh => { ob(sh);
    sh.vertexShader = sh.vertexShader.replace("varying vec2 vRUV;", "varying vec2 vRUV; attribute float aBH; varying float vBH;").replace("vRUV = aRUV;", "vRUV = aRUV; vBH = aBH;");
    sh.fragmentShader = sh.fragmentShader.replace("varying vec2 vRUV;", "varying vec2 vRUV; varying float vBH; float _fw = 0.0; float _flit = 0.0; vec3 _fsign = vec3(0.0); vec3 _fshop = vec3(0.0);")
      .replace(/\\{ vec3 roofC[\\s\\S]*?diffuseColor\\.rgb = mix\\(roofC \\* 1\\.08, fac, vSide\\); \\}/, () => `''' + FACADE + '''`)
      .replace("totalEmissiveRadiance *= vSide * win * lit * (0.45 + 0.75 * vInfo.y) * uNight * 1.25;", "''' + EMIT + '''"); }; }
  m.customProgramCacheKey = () => "orthoB2";''')
