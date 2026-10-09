import os, json, re, time, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research)"}
rep = {}
def j(name, url, n=2500, headers=None, **kw):
    try:
        r = requests.get(url, headers=headers or H, timeout=90, **kw)
        rep[name] = {"status": r.status_code, "url": r.url, "len": len(r.content), "body": r.text[:n]}
        return r.json()
    except Exception as e:
        rep[name] = rep.get(name, {}); rep[name]["err"] = repr(e)[:300]
# SEC efts shape (single request)
js = j("efts", "https://efts.sec.gov/LATEST/search-index?q=%22GLP-1%22&dateRange=custom&startdt=2026-07-01&enddt=2026-09-30&forms=10-K,10-Q,8-K", n=600,
       headers={"User-Agent": "intel-terminal research admin@example.com"})
if js:
    rep["efts_total"] = js.get("hits", {}).get("total"); rep["efts_keys"] = list(js.keys()); rep["efts_aggs"] = {k: (v.get("buckets") or [])[:5] for k, v in (js.get("aggregations") or {}).items()}
    h = (js.get("hits", {}).get("hits") or [{}])[0]; rep["efts_hit"] = {k: h.get("_source", {}).get(k) for k in ("display_names", "file_date", "form", "root_forms", "sics", "biz_locations")}
# LY bills
js = j("ly_recent", "https://ly.govapi.tw/v2/bills?limit=50&議案類別=法律案", n=300)
if js:
    rep["ly_total"] = js.get("total"); b = js.get("bills") or []
    rep["ly_sample"] = [{k: x.get(k) for k in ("議案名稱", "提案單位/提案委員", "議案狀態", "提案來源", "最新進度日期", "提案日期", "會期")} for x in b[:12]]
    rep["ly_dates"] = [x.get("最新進度日期") for x in b]
js = j("ly_one", "https://ly.govapi.tw/v2/bills/201110233750000", n=3000)
js = j("ly_bydate", "https://ly.govapi.tw/v2/bills?limit=5&提案日期=2026-10-01", n=1500)
js = j("ly_srcfilter", "https://ly.govapi.tw/v2/bills?limit=5&提案來源=委員提案&議案類別=法律案", n=1500)
# PCC search shape
js = j("pcc_s", "https://pcc-api.openfun.app/api/searchbytitle?query=" + requests.utils.quote("人工智慧") + "&page=1", n=1500, headers={"User-Agent": "Mozilla/5.0"})
if js:
    rep["pcc_keys"] = list(js.keys()); rep["pcc_meta"] = {k: v for k, v in js.items() if k != "records"}
    rec = js.get("records") or []
    rep["pcc_n"] = len(rec); rep["pcc_dates"] = [r.get("date") for r in rec][:120]; rep["pcc_types"] = [((r.get("brief") or {}).get("type")) for r in rec][:40]
js = j("pcc_s3", "https://pcc-api.openfun.app/api/searchbytitle?query=" + requests.utils.quote("人工智慧") + "&page=3", n=300, headers={"User-Agent": "Mozilla/5.0"})
if js:
    rep["pcc_p3_dates"] = [r.get("date") for r in (js.get("records") or [])][:5]
# fish market
js = j("fish", "https://data.moa.gov.tw/Service/OpenData/FromM/AquaticTransData.aspx?IsTransData=1&UnitId=039", n=1500)
if isinstance(js, list):
    rep["fish_n"] = len(js); rep["fish_keys"] = list(js[0].keys()) if js else None
    from collections import Counter
    rep["fish_dates"] = Counter(x.get("交易日期") for x in js).most_common(10)
    rep["fish_markets"] = Counter(x.get("市場名稱") for x in js).most_common(12)
    rep["fish_sample"] = js[:4]
js = j("fish_range", "https://data.moa.gov.tw/Service/OpenData/FromM/AquaticTransData.aspx?IsTransData=1&UnitId=039&Start_time=115.09.01&End_time=115.09.03", n=400)
if isinstance(js, list):
    from collections import Counter
    rep["fish_range_dates"] = Counter(x.get("交易日期") for x in js).most_common(10); rep["fish_range_n"] = len(js)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
