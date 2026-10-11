import os, json, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
for ds in (9347, 29237):
    m = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=40).json()["result"]
    rep[ds] = [{k: x.get(k) for k in ("resourceDescription", "resourceModified", "resourceDownloadUrl", "resourceFormat")} for x in m.get("distribution") or []]
u = rep[9347][0]["resourceDownloadUrl"]
t = requests.get(u, headers=H, timeout=40).content.decode("utf-8-sig", "replace").splitlines()
rep["9347rows"] = t[:25]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
