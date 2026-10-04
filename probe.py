import os, json, requests, time, collections
os.makedirs("out19", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}


def tree(o, d=0):
    if d > 5: return "…"
    if isinstance(o, dict): return {k: tree(v, d + 1) for k, v in list(o.items())[:25]}
    if isinstance(o, list): return [len(o), tree(o[0], d + 1)] if o else [0]
    return str(o)[:60]


for cat in ["6", "1", "2", "7", "17"]:
    try:
        t0 = time.time()
        r = S.get("https://cloud.culture.tw/frontsite/trans/SearchShowAction.do", params={"method": "doFindTypeJ", "category": cat}, timeout=60)
        j = r.json()
        geo = sum(1 for e in j if any(str(s.get("latitude") or "").strip() for s in e.get("showInfo", [])))
        ends = collections.Counter((e.get("endDate") or "")[:7] for e in j).most_common(6)
        rep["culture" + cat] = {"n": len(j), "bytes": len(r.content), "sec": round(time.time() - t0, 1), "geo": geo, "ends": ends,
                               "sample": tree(j[0]), "titles": [e.get("title") for e in j[:8]],
                               "hit": sorted([(int(e.get("hitRate") or 0), e.get("title")) for e in j], reverse=True)[:5]}
    except Exception as e:
        rep["culture" + cat] = repr(e)[:200]

for name, params in [("moa_default", {}), ("moa_top", {"$top": "2000"}), ("moa_date", {"StartDate": "115.10.02", "EndDate": "115.10.03", "$top": "2000"})]:
    try:
        r = S.get("https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx", params=params, timeout=60)
        j = r.json()
        rep[name] = {"n": len(j), "bytes": len(r.content), "dates": collections.Counter(x.get("交易日期") for x in j).most_common(5),
                     "markets": collections.Counter(x.get("市場名稱") for x in j).most_common(8),
                     "kinds": collections.Counter(x.get("種類代碼") for x in j).most_common(8),
                     "sample": j[:3],
                     "crops": collections.Counter(x.get("作物名稱") for x in j).most_common(40)}
    except Exception as e:
        rep[name] = repr(e)[:200]
open("out19/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
