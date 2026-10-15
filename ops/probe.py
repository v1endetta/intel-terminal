import requests, json, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
for did in ("6842", "175018", "62945", "21293", "29266", "6049", "30202", "157994", "131136", "29256"):
    try:
        res = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{did}", timeout=30).json().get("result") or {}
        dist = [(d.get("resourceFormat"), (d.get("resourceDownloadUrl") or "").strip(), (d.get("resourceDescription") or "")[:30]) for d in res.get("distribution") or []]
        o = {"t": res.get("title"), "n": len(dist), "dist": dist[:3] + dist[-2:]}
        for fmt, u, _ in (dist[-1:] + dist[:1]):
            if (fmt or "").upper() == "CSV" and u:
                try:
                    r = S.get(u, timeout=(8, 40), stream=True)
                    raw = r.raw.read(2500, decode_content=True)
                    try: txt = raw.decode("utf-8-sig")
                    except UnicodeDecodeError: txt = raw.decode("cp950", "replace")
                    o.setdefault("heads", []).append([u[-60:], r.status_code, txt[:1400]])
                except Exception as e:
                    o.setdefault("heads", []).append([u[-60:], repr(e)[:100]])
        out[did] = o
    except Exception as e:
        out[did] = repr(e)[:200]
    json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
