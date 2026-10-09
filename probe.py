import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
for ds in [174681, 10895, 43381, 163765, 58036, 58297, 41664, 167826, 6436, 101673, 30117, 30119, 15975, 15992]:
    try:
        j = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json()["result"]
        rep[ds] = {"title": j.get("title"), "provider": j.get("publisher") or j.get("dataProvider"), "desc": (j.get("description") or "")[:200],
                   "freq": j.get("updateFrequency"), "modified": j.get("modifiedDate"),
                   "dist": [(d.get("resourceDescription", "")[:40], d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceModifiedDate")) for d in (j.get("distribution") or [])][:6]}
    except Exception as e:
        rep[ds] = {"err": repr(e)[:200]}
for u in ["https://cloud.tipo.gov.tw/S220/opdata/api/file/api/patent", "https://cloud.tipo.gov.tw/S220/opdata/api/file/api/trademark", "https://join.gov.tw/idea/index", "https://join.gov.tw/policies/"]:
    try:
        r = S.get(u, timeout=40); rep[u] = {"status": r.status_code, "ct": r.headers.get("content-type"), "head": r.text[:1500]}
    except Exception as e:
        rep[u] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
