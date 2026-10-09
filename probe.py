import os, json, re, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research)"}
rep = {}
def text(html):
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
def get(name, url, n=4000, raw=False, headers=None, **kw):
    try:
        r = requests.get(url, headers=headers or H, timeout=60, **kw)
        ct = r.headers.get("content-type") or ""
        body = r.text if (raw or "json" in ct or "plain" in ct or "xml" in ct) else text(r.text)
        rep[name] = {"status": r.status_code, "ct": ct, "url": r.url, "len": len(r.content), "body": body[:n]}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:300]}
# PCC copyright
r = get("pcc_home", "https://web.pcc.gov.tw/pis/", n=500, raw=True)
if r is not None and r.ok:
    links = re.findall(r'href="([^"]*)"[^>]*>([^<]{0,40})<', r.text)
    rep["pcc_policy_links"] = [(h, t.strip()) for h, t in links if re.search(r"著作|版權|隱私|資料開放|安全|宣告|政策", t)]
    for h, t in rep["pcc_policy_links"][:6]:
        u = h if h.startswith("http") else "https://web.pcc.gov.tw" + (h if h.startswith("/") else "/" + h)
        get("pcc_pol_" + t, u, n=5000)
# openfun
get("openfun_home", "https://pcc-api.openfun.app/", n=4000, headers={"User-Agent": "Mozilla/5.0"})
get("openfun_robots", "https://pcc-api.openfun.app/robots.txt", n=800)
# LY
get("lygov_v2", "https://ly.govapi.tw/v2", n=3000)
get("lygov_home", "https://ly.govapi.tw/", n=3000)
get("lygov_bills", "https://ly.govapi.tw/v2/bills?limit=2", n=3000)
get("dataly_robots", "https://data.ly.gov.tw/robots.txt", n=800)
r = get("dataly_home", "https://data.ly.gov.tw/", n=3000, raw=True)
if r is not None and r.ok:
    rep["dataly_links"] = [(h, t.strip()) for h, t in re.findall(r'href="([^"]*)"[^>]*>([^<]{0,40})<', r.text) if re.search(r"授權|規範|條款|著作|API|議案|說明", t)][:30]
# data.gov.tw metadata
for ds in ("20561", "20560", "16859", "175926", "135731", "135723", "135724", "25848", "56696", "54606"):
    try:
        js = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=40).json()["result"]
        rep["dgt_" + ds] = {k: js.get(k) for k in ("title", "agency", "updateFrequency", "license", "modifiedDate", "description")}
        rep["dgt_" + ds]["dist"] = [(x.get("resourceFormat"), x.get("resourceDownloadUrl")) for x in (js.get("distribution") or [])][:4]
    except Exception as e:
        rep["dgt_" + ds] = {"err": repr(e)[:200]}
# FDA
get("fda_robots", "https://data.fda.gov.tw/robots.txt", n=800)
# SEC
SH = {"User-Agent": "intel-terminal research contact@example.com"}
get("sec_robots", "https://www.sec.gov/robots.txt", n=1500, headers=SH)
get("sec_sub", "https://data.sec.gov/submissions/CIK0000320193.json", n=600, headers=SH)
get("sec_frames", "https://data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2025Q2I.json", n=600, headers=SH)
get("sec_fts", "https://efts.sec.gov/LATEST/search-index?q=%22tariff%22&forms=10-Q", n=600, headers=SH)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
