import os, json, requests, time, re
os.makedirs("out21", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def tree(o, d=0):
    if d > 3: return "…"
    if isinstance(o, dict): return {k: tree(v, d + 1) for k, v in list(o.items())[:16]}
    if isinstance(o, list): return [len(o), tree(o[0], d + 1)] if o else [0]
    return str(o)[:50]
def hit(k, u, **kw):
    try:
        t0=time.time(); r = S.get(u, timeout=30, **kw); b = r.content[:300000]
        info = {"st": r.status_code, "len": len(r.content), "ct": r.headers.get("content-type","")[:30], "cors": r.headers.get("access-control-allow-origin"), "s": round(time.time()-t0,1)}
        try: info["tree"] = tree(json.loads(b))
        except Exception:
            for enc in ("utf-8-sig","big5"):
                try: info["head"] = b[:700].decode(enc); break
                except Exception: pass
        rep[k] = info; return r
    except Exception as e:
        rep[k] = repr(e)[:160]
# data.gov.tw datasets
for ds in (27505, 44062):
    r = hit(f"gov{ds}", f"https://data.gov.tw/api/v2/rest/dataset/{ds}")
    try:
        j = r.json(); dist = j["result"]["distribution"]
        rep[f"gov{ds}"]["title"] = j["result"].get("title"); rep[f"gov{ds}"]["dist"] = [(d.get("resourceDescription","")[:40], d.get("resourceFormat"), d.get("resourceDownloadUrl")) for d in dist][:6]
        u = dist[-1].get("resourceDownloadUrl"); hit(f"gov{ds}_file", u)
    except Exception as e:
        rep[f"gov{ds}_err"] = repr(e)[:150]
for q in ("減班休息", "停水", "停電", "違反勞動", "人口數"):
    hit("search_"+q, "https://data.gov.tw/api/v2/rest/dataset", params={"q": q, "limit": 5})
hit("twse_mopsnews", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L")
hit("twse_basic", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
hit("gcis_kw", "https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C", params={"$format": "json", "$filter": "Company_Name like 達而 and Company_Status eq 01", "$skip": 0, "$top": 5})
hit("gcis_swagger", "https://data.gcis.nat.gov.tw/resources/swagger/swagger.json")
hit("job104", "https://www.104.com.tw/jobs/search/api/jobs", params={"keyword": "設計", "page": 1, "pagesize": 20}, headers={"Referer": "https://www.104.com.tw/jobs/search/"})
hit("job104_old", "https://www.104.com.tw/jobs/search/list", params={"ro": 0, "kwop": 7, "keyword": "設計", "page": 1}, headers={"Referer": "https://www.104.com.tw/jobs/search/"})
hit("cake", "https://www.cake.me/jobs?q=design")
hit("yourator", "https://www.yourator.co/api/v4/jobs?page=1")
hit("ris_pop", "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP019/11508")
hit("moa_pork", "https://data.moa.gov.tw/Service/OpenData/FromM/PorkTransType.aspx")
hit("moa_egg", "https://data.moa.gov.tw/Service/OpenData/FromM/PoultryTransType.aspx")
hit("mol_layoff_page", "https://www.mol.gov.tw/1607/28162/28166/28218/28228/lpsimplelist")
hit("water_outage", "https://www.water.gov.tw/opendata/WaterStop.json")
hit("cec", "https://db.cec.gov.tw/")
open("out21/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
