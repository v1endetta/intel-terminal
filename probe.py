import os, gzip, json, requests, re
os.makedirs("out7", exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session(); S.headers["User-Agent"] = UA
rep = {}
def hit(k, u, t=40, **kw):
    try:
        r = S.get(u, timeout=t, **kw); raw = r.content
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        txt = raw.decode("utf-8-sig", errors="replace")
        rep[k] = {"url": u, "status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "head": txt[:1200]}
        open(f"out7/{k}.txt", "w").write(txt[:300000]); return txt
    except Exception as e:
        rep[k] = {"url": u, "err": repr(e)[:250]}
for ds in (136781, 173477, 146969, 67784):
    t = hit(f"gov_{ds}", f"https://data.gov.tw/api/v2/rest/dataset/{ds}")
    try:
        j = json.loads(t); 
        for i, d in enumerate((j.get("result") or {}).get("distribution", [])[:3]):
            u = d.get("resourceDownloadUrl") or d.get("resourceAccessUrl")
            if u: hit(f"gov_{ds}_{i}", u, 60)
    except Exception as e:
        rep[f"gov_{ds}_parse"] = {"err": repr(e)[:200]}
t = hit("tycg_page", "https://opendata.tycg.gov.tw/datalist/be75ea89-fe9c-4aa0-befa-82c8575d4d9b")
if t:
    links = sorted(set(re.findall(r'https?://[^"\'\s<>]+(?:json|download|api)[^"\'\s<>]*', t)))[:20]
    rep["tycg_links"] = links
for k, u in {"fw_http": "http://tisvcloud.freeway.gov.tw/history/motc20/ETagPairLive.xml",
             "fw_https90": "https://tisvcloud.freeway.gov.tw/history/motc20/SectionLive.xml",
             "fw_1968": "https://1968.freeway.gov.tw/",
             "tpe_vd_static": "https://tcgbusfs.blob.core.windows.net/blobtisv/GetVD.xml.gz",
             "ntpc_yb_all": "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json?page=0&size=3000",
             "tc_od": "https://opendata.taichung.gov.tw/search/6e38eb56-0e9a-4b9e-806d-23cd35d44d6b"}.items():
    hit(k, u, 90)
json.dump(rep, open("out7/report.json", "w"), ensure_ascii=False, indent=1)
