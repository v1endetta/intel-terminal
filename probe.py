import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}

# 國發會 PMI/NMI：用瀏覽器抓 XHR，找各產業資料
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for page in ("data/PMI", "data/NMI"):
            pg = b.new_page(locale="zh-TW", user_agent=S.headers["User-Agent"])
            xhr = []
            def on_resp(resp, xhr=xhr):
                try:
                    if resp.request.resource_type in ("xhr", "fetch"):
                        body = resp.text()
                        xhr.append({"url": resp.url, "method": resp.request.method, "post": (resp.request.post_data or "")[:300],
                                    "len": len(body), "head": body[:1500]})
                except Exception as e:
                    xhr.append({"url": resp.url, "err": repr(e)[:100]})
            pg.on("response", on_resp)
            try:
                pg.goto(f"https://index.ndc.gov.tw/n/zh_tw/{page}", wait_until="networkidle", timeout=60000)
            except Exception:
                pass
            pg.wait_for_timeout(9000)
            txt = pg.inner_text("body")
            rep[f"ndc_{page.replace('/','_')}"] = {"xhr": xhr, "text": txt[:15000]}
            pg.close()
        b.close()
except Exception as e:
    rep["ndc_err"] = repr(e)[:300]

for cat in ("pmi-ch", "nmi-ch"):
    try:
        r = S.get(f"https://www.cier.edu.tw/eco_cat/{cat}/", timeout=40); r.encoding = "utf-8"
        links = [l for l in dict.fromkeys(re.findall(r'href="(https://www\.cier\.edu\.tw/[^"]+)"', r.text)) if "eco_cat" not in l and "/category/" not in l]
        rep[f"cier_{cat}"] = {"status": r.status_code, "links": links[:60]}
        art = [l for l in links if re.search(r"/eco/|pmi|nmi", l)]
        if art:
            a = S.get(art[0], timeout=40); a.encoding = "utf-8"
            t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", a.text, flags=re.S)
            t = re.sub(r"<[^>]+>", " ", t); t = re.sub(r"\s+", " ", t)
            i = t.find("產業")
            rep[f"cier_{cat}_art"] = {"url": art[0], "len": len(t), "txt": t[max(0, i-1500):i+6000]}
    except Exception as e:
        rep[f"cier_{cat}"] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
