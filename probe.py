import os, json, requests, re, io, csv
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
def t(name, fn):
    try: rep[name] = fn()
    except Exception as e: rep[name] = f"ERR {type(e).__name__}: {str(e)[:200]}"
for sid in ("QTWN628BIS", "QTWR628BIS"):
    def f(sid=sid):
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", headers=H, timeout=40)
        lines = r.text.strip().splitlines()
        return {"st": r.status_code, "n": len(lines), "head": lines[:3], "tail": lines[-4:]}
    t(sid, f)
# data.gov.tw search
for q in ("消費者物價指數", "建物買賣移轉", "住宅價格指數", "建物所有權第一次登記"):
    def f(q=q):
        r = requests.get("https://data.gov.tw/api/v2/rest/dataset", params={"q": q, "limit": 8}, headers=H, timeout=40)
        js = r.json()
        res = js.get("result") or js
        out = []
        for d in (res.get("datasets") if isinstance(res, dict) else res) or []:
            out.append({k: d.get(k) for k in ("identifier", "title", "publisher", "updateFrequency")})
        return {"st": r.status_code, "keys": list(js.keys())[:5], "rows": out[:8], "raw": json.dumps(js, ensure_ascii=False)[:600] if not out else ""}
    t("search:" + q, f)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
