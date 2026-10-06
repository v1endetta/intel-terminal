import os, json, re, requests
os.makedirs("out25", exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
JS = """async (u) => { const t=(document.querySelector('meta[name=csrf-token]')||{}).content||'';
  const r=await fetch(u,{method:'POST',headers:{'X-CSRF-TOKEN':t,'X-Requested-With':'XMLHttpRequest'}}); return r.status+'|'+(await r.text()); }"""
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for page in ("PMI", "NMI"):
            pg = b.new_page(locale="zh-TW", user_agent=UA)
            try:
                pg.goto(f"https://index.ndc.gov.tw/n/zh_tw/{page}", wait_until="networkidle", timeout=60000)
            except Exception:
                pass
            pg.wait_for_timeout(3000)
            for kind in ("industry", "index"):
                try:
                    t = pg.evaluate(JS, f"/n/json/data/{page}/{kind}")
                    st, body = t.split("|", 1)
                    info = {"status": st, "len": len(body)}
                    try:
                        j = json.loads(body)
                        info["lines"] = [(k, v.get("name"), v.get("code"), (v.get("data") or [])[-3:]) for k, v in (j.get("line") or {}).items()]
                        info["keys"] = list(j.keys())
                    except Exception:
                        info["head"] = body[:800]
                    rep[f"{page}_{kind}"] = info
                except Exception as e:
                    rep[f"{page}_{kind}"] = {"err": repr(e)[:300]}
            pg.close()
        b.close()
except Exception as e:
    rep["err"] = repr(e)[:300]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
