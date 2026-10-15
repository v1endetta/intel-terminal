import json, requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
for k, u in {"17219": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/9C370B2D-D336-4F48-B061-58E07AE4E0DA/resource/0F2DC0B5-51E9-4863-921F-90832F000F1E/download",
             "176214": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/10D30B57-DD57-40FA-8931-F2948CB6EB49/resource/4D61821E-5081-4F77-945D-DF0F2E4B6D7A/download"}.items():
    try:
        r = S.get(u, timeout=(10, 60)); out[k] = [r.status_code, r.headers.get("content-type"), r.text[:1500]]
    except Exception as e:
        out[k] = repr(e)[:200]
for did in ("7438", "25128", "17219"):
    try:
        res = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{did}", timeout=30).json().get("result") or {}
        out["meta" + did] = [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceDescription", "")[:80]) for d in res.get("distribution") or []][:30]
    except Exception as e:
        out["meta" + did] = repr(e)[:200]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
