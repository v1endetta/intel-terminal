import requests, json, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
try:
    m = S.get("https://data.gov.tw/api/v2/rest/dataset/15393", timeout=60).json().get("result") or {}
    out["meta"] = {k: m.get(k) for k in ("title", "updateFrequency", "modifiedDate", "fieldDescription")}
    out["dist"] = [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceModifiedDate")) for d in m.get("distribution") or []]
except Exception as e:
    out["meta_err"] = str(e)
u = "https://www.mohw.gov.tw/dl-96581-66dbb751-f83a-416a-a998-893222e20fef.html"
try:
    r = S.get(u, timeout=120)
    out["dl"] = [r.status_code, r.headers.get("content-type"), r.headers.get("content-disposition"), len(r.content)]
    import pandas as pd
    xs = pd.read_excel(io.BytesIO(r.content), engine="odf", sheet_name=None)
    out["sheets"] = {}
    for name, df in xs.items():
        info = {"rows": len(df), "cols": [str(c) for c in df.columns][:40], "head": df.head(3).astype(str).values.tolist()}
        kc = [c for c in df.columns if "科別" in str(c)]
        if kc:
            s = df[kc[0]].astype(str)
            info["n_plastic"] = int(s.str.contains("整形").sum()); info["n_derm"] = int(s.str.contains("皮膚").sum())
            info["kebie_sample"] = s[s.str.contains("整形")].head(10).tolist()
        nc = [c for c in df.columns if "名稱" in str(c)]
        if nc:
            n = df[nc[0]].astype(str)
            info["n_beauty_name"] = int(n.str.contains("醫美|美學|美容|整形|皮膚").sum())
            info["beauty_names"] = n[n.str.contains("醫美|美學|整形")].head(15).tolist()
        out["sheets"][str(name)] = info
except Exception as e:
    out["dl_err"] = repr(e)[:400]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1, default=str)
