import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def get(name, url, n=3000, **kw):
    try:
        r = S.get(url, timeout=90, **kw)
        rep[name] = {"status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "cd": r.headers.get("content-disposition"), "head": r.text[:n] if "zip" not in (r.headers.get("content-type") or "") and r.content[:2] != b"PK" else "ZIP " + str(r.content[:4])}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:200]}
TK = "43b47d07-4795-45d9-819a-9c71c72e4105"
get("tm_top5", f"https://cloud.tipo.gov.tw/S220/opdataapi/api/TmarkAppl?tk={TK}&format=json&top=5", 5000)
get("tm_skip", f"https://cloud.tipo.gov.tw/S220/opdataapi/api/TmarkAppl?tk={TK}&format=json&top=3&skip=5000", 1500)
r = get("opdata_home", "https://cloud.tipo.gov.tw/S220/opdata/", 200)
if r is not None:
    rep["opdata_links"] = list(dict.fromkeys(re.findall(r'(?:href|src)="([^"]+)"', r.text)))[:80]
    rep["opdata_api_mentions"] = list(dict.fromkeys(re.findall(r'opdataapi/api/[A-Za-z]+', r.text)))
for p in ["PatentPub", "PatentAppl", "PatPub", "InventionPub", "PatentRights", "TmarkStat"]:
    get("try_" + p, f"https://cloud.tipo.gov.tw/S220/opdataapi/api/{p}?tk={TK}&format=json&top=2", 600)
get("gaz_I07", "https://cloud.tipo.gov.tw/S220/opdata/api/gazettes/I07", 800)
get("gaz_T02", "https://cloud.tipo.gov.tw/S220/opdata/api/gazettes/T02", 800)
get("tm_stat_csv", "https://tiponet.tipo.gov.tw/datagov/tm/163-108-001.csv", 2500)
get("join_policy", "https://join.gov.tw/toOpenData/ey/policy", 4000)
get("join_idea", "https://join.gov.tw/toOpenData/v2/ey/idea?year=2026", 4000)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
