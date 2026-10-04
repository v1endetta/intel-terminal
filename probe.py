import os, json, requests
os.makedirs("out23", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def hit(k, u, **kw):
    try:
        r = S.get(u, timeout=40, **kw)
        try:
            j = r.json(); rep[k] = {"st": r.status_code, "n": len(j) if isinstance(j, list) else None, "first": (j[:2] if isinstance(j, list) else str(j)[:400])}
        except Exception: rep[k] = {"st": r.status_code, "head": r.text[:300]}
        return r
    except Exception as e: rep[k] = repr(e)[:200]
r = hit("taifex_swagger", "https://openapi.taifex.com.tw/swagger.json")
try:
    j = r.json(); rep["taifex_paths"] = [(p, v.get("get", {}).get("summary", "")[:40]) for p, v in j["paths"].items()][:80]; rep.pop("taifex_swagger", None)
except Exception as e: rep["taifex_err"] = repr(e)[:150]
hit("taifex_inst", "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")
hit("taifex_pcr", "https://openapi.taifex.com.tw/v1/PutCallRatio")
hit("twse_all_etf", "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
try:
    rows = S.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=40).json()
    by = {x["Code"]: x for x in rows}
    rep["etf_check"] = {c: (by.get(c) or {}).get("Name") for c in ["0050", "006208", "0056", "00878", "00919", "00929", "00631L", "00675L", "00632R", "00940", "2330", "2317", "2454", "2382", "2308", "3711", "2881", "2882", "2412", "2603", "00679B", "00687B", "00937B"]}
except Exception as e: rep["etf_err"] = repr(e)[:150]
hit("tpex_daily", "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
try:
    rows = S.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", timeout=40).json()
    by = {x.get("SecuritiesCompanyCode"): x for x in rows}
    rep["tpex_check"] = {c: (by.get(c) or {}).get("CompanyName") for c in ["00679B", "00687B", "00937B", "5347", "6488", "8299", "3105", "6274"]}
    rep["tpex_keys"] = list(rows[0].keys())
except Exception as e: rep["tpex_err"] = repr(e)[:150]
hit("sitca", "https://www.sitca.org.tw/ROC/Industry/IN2629.aspx?pid=IN22601_04")
hit("fundclear", "https://www.fundclear.com.tw/")
open("out23/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
