import json, requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
u = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/03C1D0A5-1F39-4C1F-AA2E-BB37A0405369/resource/94882A33-8B06-43FA-8CEC-016F4EB67D19/download"
try:
    r = S.get(u, timeout=(10, 120), stream=True); out["h"] = [r.status_code, r.headers.get("content-type"), r.headers.get("content-length"), r.headers.get("content-disposition")]
    out["head"] = r.raw.read(3000, decode_content=True).decode("utf-8-sig", "replace")
except Exception as e:
    out["err"] = repr(e)[:200]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
