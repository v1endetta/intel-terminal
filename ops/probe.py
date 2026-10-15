import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
KW = re.compile(r"美容醫學|醫美|醫療機構|醫事機構|診所|整形|美容")
def tryget(u, **k):
    try:
        r = S.get(u, timeout=60, **k); return r
    except Exception as e:
        out.setdefault("errs", []).append(f"{u}: {e}"); return None
hits = []
for u in ["https://data.gov.tw/datasets/export/csv", "https://data.gov.tw/datasets/export/csv?type=dataset"]:
    r = tryget(u)
    out[u] = None if r is None else [r.status_code, r.headers.get("content-type"), len(r.content)]
    if r is not None and r.ok and len(r.content) > 100000:
        txt = r.content.decode("utf-8-sig", "replace")
        rows = list(csv.reader(io.StringIO(txt)))
        out["catalog_header"] = rows[0]
        for row in rows[1:]:
            line = " | ".join(row[:4])
            if KW.search(row[1] if len(row) > 1 else line):
                hits.append([c[:120] for c in row[:12]])
        break
out["hits"] = hits[:200]
# 看前幾個看起來像醫療機構名冊的資料集
cand = [h for h in hits if re.search(r"美容醫學|醫美|醫療機構|醫事機構", h[1] if len(h) > 1 else "")][:25]
out["samples"] = {}
for h in cand:
    did = h[0]
    r = tryget(f"https://data.gov.tw/api/v2/rest/dataset/{did}")
    try:
        res = r.json().get("result") or {}
    except Exception:
        continue
    info = {"title": res.get("title"), "org": res.get("organization"), "freq": res.get("updateFrequency"), "mod": res.get("modifiedDate"), "fields": res.get("fieldDescription", "")[:400], "dist": []}
    for d in (res.get("distribution") or [])[:2]:
        u = d.get("resourceDownloadUrl"); fmt = d.get("resourceFormat")
        x = {"fmt": fmt, "url": u}
        if u and (fmt or "").upper() in ("CSV", "JSON", "XML"):
            rr = tryget(u, stream=True)
            if rr is not None:
                x["status"] = rr.status_code
                try: x["head"] = rr.raw.read(1500, decode_content=True).decode("utf-8-sig", "replace")
                except Exception as e: x["head"] = str(e)
        info["dist"].append(x)
    out["samples"][did] = info
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
