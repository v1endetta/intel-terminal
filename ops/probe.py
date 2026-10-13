"""臨時探測（第二輪）：CPI 細項 SDMX、觀光統計、日經日期格式。跑完就刪。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {}
def get(u, n=1500, **kw):
    try:
        r = requests.get(u, headers=H, timeout=40, **kw)
        return {"code": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(r.content), "head": r.content[:n].decode("utf-8", "replace")}
    except Exception as e:
        return {"err": str(e)[:200]}
B = "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/"
for name, u in [("cpi15_1", B + "A030101015/1..M&startTime=2025-M1&endTime=2026-M12"), ("cpi15_meta", B + "A030101015/"),
                ("cpi25_1", B + "A030101025/1..M&startTime=2026-M1&endTime=2026-M12"), ("cpi_dash", B + "A030101015/1.1.M&startTime=2026-01&endTime=2026-12")]:
    r = get(u, 200)
    try:
        js = requests.get(u, headers={**H, "Accept": "application/json"}, timeout=60).json()
        st = js.get("structure") or (js.get("data") or {}).get("structure") or {}
        dims = (st.get("dimensions") or {})
        r["dims"] = {k: [[x.get("id"), x.get("name")] for x in (d.get("values") or [])][:80] for k in ("series", "observation") for d in (dims.get(k) or [])[:4] for _ in [0]} if dims else None
        r["dims_raw"] = json.dumps(dims, ensure_ascii=False)[:6000]
        ds = ((js.get("data") or js).get("dataSets") or [{}])[0].get("series") or {}
        r["n_series"] = len(ds); r["sample"] = json.dumps(dict(list(ds.items())[:2]), ensure_ascii=False)[:800]
    except Exception as e:
        r["perr"] = str(e)[:200]
    out[name] = r
for ds in ["15453", "15450", "45512", "15432", "41898"]:
    m = get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", 8000)
    try:
        res = json.loads(requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=30).text).get("result") or {}
        out["ds" + ds] = {"title": res.get("title"), "freq": res.get("updateFrequency") or res.get("accrualPeriodicity"), "dist": [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceDescription")) for d in (res.get("distribution") or [])][:4]}
        out["ds" + ds]["sample"] = [get(d[1], 900) for d in out["ds" + ds]["dist"][:2] if d[1]]
    except Exception as e:
        out["ds" + ds] = {"err": str(e)[:200], "m": m}
st = get("https://stat.taiwan.net.tw/", 200000)
out["stat_links"] = sorted(set(re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', st.get("head", ""))))[:20]
out["stat_api_guess"] = {u: get(u, 600) for u in ["https://stat.taiwan.net.tw/api/inbound", "https://stat.taiwan.net.tw/inboundSearch", "https://stat.taiwan.net.tw/data/api/inbound/residence?year=2026"]}
js_urls = [l if l.startswith("http") else "https://stat.taiwan.net.tw" + l for l in out["stat_links"] if "js" in l][:6]
apis = set()
for u in js_urls:
    try:
        t = requests.get(u, headers=H, timeout=30).text
        apis.update(re.findall(r'["\'](/(?:api|data|stat)[^"\']{3,80})["\']', t))
    except Exception:
        pass
out["stat_js_apis"] = sorted(apis)[:60]
t = requests.get("https://asia.nikkei.com/rss/feed/nar", headers=H, timeout=30).text
out["nikkei_item"] = (re.search(r"<item>.*?</item>", t, re.S) or [""])[0][:1200]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
