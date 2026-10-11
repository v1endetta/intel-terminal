import os, json, requests, re
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; https://github.com/v1endetta/intel-terminal)"}
rep = {}
def head(u, n=4, timeout=60):
    try:
        r = requests.get(u, headers=H, timeout=timeout)
        t = r.content.decode("utf-8-sig", "replace")
        L = [l[:230] for l in t.strip().splitlines()]
        return {"st": r.status_code, "ct": r.headers.get("content-type", "")[:40], "n": len(L), "head": L[:n], "tail": L[-2:]}
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:150]}"
base = "https://statis.moi.gov.tw/micst/webMain.aspx?sys=220&kind=21&type=1&funid={f}&cycle=41&outmode=12&utf=1&compmode=0&outkind=1&ym=11301&ymt=11509"
for f in ("c0120103", "c0120201", "c0110201", "c0110101"):
    rep["moi:" + f] = head(base.format(f=f))
    rep["moi3:" + f] = head(base.format(f=f) + "&fldspc=0,30,&codspc0=0,2,")
for ds in (6551, 6549, 29262, 29237, 9347, 9663, 15432):
    try:
        m = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=40).json()["result"]
        d = [{"fmt": x.get("resourceFormat"), "url": x.get("resourceDownloadUrl"), "desc": (x.get("resourceDescription") or "")[:40]} for x in (m.get("distribution") or [])[:4]]
        rec = {"title": m.get("title"), "freq": m.get("updateFrequency"), "mod": m.get("modifiedDate") or m.get("modified"), "dist": d}
        for x in d[:2]:
            if x["url"]:
                x["probe"] = head(x["url"], 3)
        rep[f"ds{ds}"] = rec
    except Exception as e:
        rep[f"ds{ds}"] = f"ERR {e}"[:200]
for u in ("https://cpx.cbc.gov.tw/api/OpenData/OAS?set_id=6551", "https://cpx.cbc.gov.tw/API/OpenData/API?set_id=6551", "https://data.gcis.nat.gov.tw/resources/swagger/index.html"):
    rep[u] = head(u, 6)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
