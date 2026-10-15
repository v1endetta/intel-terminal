import json, requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
for did in ("177859", "157689", "120044", "157547", "178083", "166201", "165619"):
    try:
        res = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{did}", timeout=30).json().get("result") or {}
        dist = [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), (d.get("resourceDescription") or "")[:40]) for d in res.get("distribution") or []]
        o = {"title": res.get("title"), "n": len(dist), "dist": dist[:4], "fields": (res.get("fieldDescription") or "")[:200]}
        for fmt, u, _ in dist:
            if fmt and fmt.upper() in ("CSV", "JSON") and u:
                try:
                    r = S.get(u, timeout=(8, 20), stream=True)
                    o["try"] = [u, r.status_code, r.headers.get("content-type"), r.headers.get("content-length"), r.raw.read(700, decode_content=True).decode("utf-8-sig", "replace")]
                except Exception as e:
                    o["try"] = [u, repr(e)[:120]]
                break
        out[did] = o
    except Exception as e:
        out[did] = repr(e)[:200]
    json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
