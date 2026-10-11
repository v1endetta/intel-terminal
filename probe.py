import os, json, requests, re
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
for ds in (121969, 121381, 132984, 132593, 23854, 89668, 134490, 168540, 13897, 13898, 134492):
    try:
        m = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=40).json()["result"]
        out = {"title": m.get("title"), "pub": m.get("publisher"), "freq": m.get("updateFrequency"), "dist": []}
        for d in (m.get("distribution") or [])[:3]:
            u = d.get("resourceDownloadUrl"); fmt = d.get("resourceFormat")
            rec = {"fmt": fmt, "url": u, "desc": (d.get("resourceDescription") or "")[:60]}
            try:
                r = requests.get(u, headers=H, timeout=40)
                txt = r.content.decode("utf-8-sig", "replace")
                lines = txt.strip().splitlines()
                rec.update(st=r.status_code, n=len(lines), head=[l[:220] for l in lines[:3]], tail=[l[:220] for l in lines[-2:]])
            except Exception as e:
                rec["err"] = str(e)[:120]
            out["dist"].append(rec)
        rep[ds] = out
    except Exception as e:
        rep[ds] = f"ERR {e}"[:200]
try:
    raw = requests.get("https://www.sinyinews.com.tw/quarterly", headers=H, timeout=40).text
    qs = re.findall(r"(20\d\d)年第([一二三四])季", raw)
    rep["sinyi"] = {"len": len(raw), "quarters": len(set(qs)), "sample": sorted(set(qs))[:5], "area_n": raw.count('"area"'), "snip": raw[raw.find('"area"')-300: raw.find('"area"')+400] if '"area"' in raw else ""}
except Exception as e:
    rep["sinyi"] = str(e)[:200]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
