import os, json, requests, time
os.makedirs("out22", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
H104 = {"Referer": "https://www.104.com.tw/jobs/search/"}
def g(u, **kw):
    try:
        r = S.get(u, timeout=40, **kw); return r
    except Exception as e:
        return e
r = g("https://www.104.com.tw/jobs/search/api/jobs", params={"page": 1, "pagesize": 20, "order": 16}, headers=H104)
try:
    j = r.json(); rep["104_all_keys"] = list(j.keys()); rep["104_meta"] = j.get("metadata"); d = j["data"]
    rep["104_first"] = {k: (str(v)[:80]) for k, v in d[0].items()}; rep["104_n"] = len(d)
except Exception as e: rep["104_all_err"] = repr(r)[:200] + repr(e)[:200]
r = g("https://www.104.com.tw/jobs/search/api/jobs", params={"page": 1, "pagesize": 20, "jobcat": "2013000000"}, headers=H104)
try: rep["104_cat_meta"] = r.json().get("metadata")
except Exception as e: rep["104_cat_err"] = repr(e)[:200]
r = g("https://www.104.com.tw/jobs/search/api/jobs", params={"page": 1, "pagesize": 20, "area": "6001001000"}, headers=H104)
try: rep["104_area_meta"] = r.json().get("metadata")
except Exception as e: rep["104_area_err"] = repr(e)[:200]
for k, u in [("jobcat", "https://static.104.com.tw/category-tool/json/JobCat.json"), ("area", "https://static.104.com.tw/category-tool/json/Area.json"), ("indust", "https://static.104.com.tw/category-tool/json/Indust.json")]:
    r = g(u)
    try:
        j = r.json(); rep[k] = [(x.get("no"), x.get("des"), len(x.get("n") or [])) for x in j][:40]
        if k == "area": rep["area_tw"] = [(x.get("no"), x.get("des")) for x in (j[0].get("n") or [])][:30]
    except Exception as e: rep[k + "_err"] = repr(r)[:120] + repr(e)[:120]
r = g("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
try: j = r.json(); rep["twse_basic_keys"] = list(j[0].keys()); rep["twse_basic_0"] = j[0]
except Exception as e: rep["twse_basic_err"] = repr(e)[:200]
for k, u in [("tpex_list", "https://www.tpex.org.tw/openapi/swagger.json"), ("tpex_major", "https://www.tpex.org.tw/openapi/v1/mopsfe_major_message"), ("tpex_basic", "https://www.tpex.org.tw/openapi/v1/mopsfe_company_basic"), ("twse_swagger", "https://openapi.twse.com.tw/v1/swagger.json")]:
    r = g(u)
    try:
        j = r.json()
        if "paths" in j: rep[k] = [p for p in j["paths"] if any(w in (p + json.dumps(j["paths"][p], ensure_ascii=False)) for w in ("重大", "major", "basic", "基本資料", "t187ap04", "t187ap03"))][:30]
        else: rep[k] = {"n": len(j), "first": j[0] if isinstance(j, list) and j else str(j)[:300]}
    except Exception as e: rep[k + "_err"] = (repr(r)[:120], repr(e)[:120])
open("out22/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
