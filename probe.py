import os, json, re, requests, traceback
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research; contact via github)"}
rep = {}
def get(name, url, n=6000, **kw):
    try:
        r = requests.get(url, headers=H, timeout=40, **kw)
        rep[name] = {"status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "url": r.url, "head": r.text[:n]}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:300]}
get("pcc_robots", "https://web.pcc.gov.tw/robots.txt")
r = get("pcc_opendata", "https://web.pcc.gov.tw/tps/tp/OpenData/showList", n=20000)
if r is not None and r.ok:
    rep["pcc_links"] = sorted(set(re.findall(r'href="([^"]+)"', r.text)))[:200]
    txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
    rep["pcc_text"] = txt[:8000]
get("dgt_robots", "https://data.gov.tw/robots.txt")
for ds in ("6576", "6155", "165150", "23838", "56284", "90711"):
    get("dgt_" + ds, f"https://data.gov.tw/api/v2/rest/dataset/{ds}", n=4000)
get("hub_robots", "https://hub.twinkleai.tw/robots.txt")
get("hub_docs", "https://hub.twinkleai.tw/docs", n=12000)
get("ronny_robots", "https://pcc.g0v.ronny.tw/robots.txt")
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
