import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}

# 法說會：MOPS 舊站 GET 有回表格；存整頁 + 試 CSV 下載
for typek in ("sii", "otc"):
    try:
        r = S.get("https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1", timeout=40,
                  params={"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": typek, "year": "115", "month": "10"})
        r.encoding = "utf-8"
        open(f"out25/mops_{typek}.html", "w").write(r.text)
        fn = re.search(r"name='filename' value='([^']+)'", r.text)
        rep[f"mops_{typek}"] = {"status": r.status_code, "len": len(r.text), "fn": fn.group(1) if fn else None,
                                "rows": len(re.findall(r"<tr", r.text))}
        if fn:
            c = S.post("https://mopsov.twse.com.tw/server-java/t105sb02", timeout=40,
                       data={"firstin": "true", "step": "10", "filename": fn.group(1)})
            raw = c.content
            try:
                t = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                t = raw.decode("big5", errors="ignore")
            rep[f"mops_{typek}_csv"] = {"status": c.status_code, "ct": c.headers.get("content-type", ""), "head": t[:2500]}
    except Exception as e:
        rep[f"mops_{typek}_err"] = repr(e)[:200]

# 國發會 PMI/NMI：用瀏覽器抓 XHR，找各產業資料
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for page in ("PMI", "NMI"):
            pg = b.new_page(locale="zh-TW")
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
            pg.wait_for_timeout(6000)
            txt = pg.inner_text("body")
            rep[f"ndc_{page}"] = {"xhr": xhr, "text": txt[:6000]}
            pg.close()
        b.close()
except Exception as e:
    rep["ndc_err"] = repr(e)[:300]

# IPO 公告完整一次
for name, url in (("publicForm", "https://www.twse.com.tw/rwd/zh/announcement/publicForm?response=json"),
                  ("tpex_esb", "https://www.tpex.org.tw/openapi/v1/tpex_esb_applicant_companies"),
                  ("applyLocal", "https://openapi.twse.com.tw/v1/company/applylistingLocal"),
                  ("ap24L", "https://openapi.twse.com.tw/v1/opendata/t187ap24_L"),
                  ("ap25L", "https://openapi.twse.com.tw/v1/opendata/t187ap25_L"),
                  ("ap24O", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap24_O"),
                  ("ap25O", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap25_O"),
                  ("tpex_apply", "https://www.tpex.org.tw/openapi/v1/tpex_apply_listing")):
    try:
        r = S.get(url, timeout=40)
        rep[name] = {"status": r.status_code, "len": len(r.content), "head": r.text[:3000]}
    except Exception as e:
        rep[name] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
