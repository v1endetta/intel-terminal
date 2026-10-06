import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def tryget(name, url, n=1200, **kw):
    try:
        r = S.get(url, timeout=40, **kw)
        rep[name] = {"status": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(r.content), "head": r.text[:n]}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:200]}

# 1. IPO / new listings
tryget("twse_publicForm", "https://www.twse.com.tw/rwd/zh/announcement/publicForm?response=json", 2500)
tryget("twse_t187ap03_L", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", 800)
tryget("tpex_t187ap03_O", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", 800)
tryget("tpex_t187ap03_R", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R", 800)
tryget("twse_newlisting", "https://www.twse.com.tw/rwd/zh/company/newlisting?response=json", 2500)
try:
    r = S.get("https://openapi.twse.com.tw/v1/swagger.json", timeout=40)
    rep["twse_paths"] = [(p, (v.get("get") or {}).get("summary", "")) for p, v in r.json().get("paths", {}).items()]
except Exception as e:
    rep["twse_paths_err"] = repr(e)[:200]
try:
    r = S.get("https://www.tpex.org.tw/openapi/swagger.json", timeout=40)
    rep["tpex_paths"] = [(p, (v.get("get") or {}).get("summary", "")) for p, v in r.json().get("paths", {}).items()]
except Exception as e:
    rep["tpex_paths_err"] = repr(e)[:200]
# 2. PMI / NMI by industry
tryget("cier_pmi", "https://www.cier.edu.tw/pmi/", 1500)
tryget("cier_nmi", "https://www.cier.edu.tw/nmi/", 1500)
tryget("ndc_pmi", "https://index.ndc.gov.tw/n/zh_tw/data/PMI", 800)
# 3. 法說會 via MOPS
tryget("mops_conf", "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1", 1500, params={"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": "sii", "year": "115", "month": "10"})
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
