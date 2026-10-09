import os, json, re, requests, io, zipfile, collections
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research)"}
B = "https://web.pcc.gov.tw"
rep = {}
def get(name, url, n=3000, keep=False, **kw):
    try:
        r = requests.get(url, headers=H, timeout=90, **kw)
        rep[name] = {"status": r.status_code, "ct": r.headers.get("content-type"), "cd": r.headers.get("content-disposition"), "len": len(r.content), "url": r.url, "head": r.text[:n] if "xml" in (r.headers.get("content-type") or "") or "json" in (r.headers.get("content-type") or "") or "html" in (r.headers.get("content-type") or "") or "text" in (r.headers.get("content-type") or "") else None}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:300]}
r = requests.get(B + "/tps/tp/OpenData/showList", headers=H, timeout=60)
links = re.findall(r'href="([^"]+)"', r.text)
dl = [l for l in links if "downloadFile" in l]
rep["dl_count"] = len(dl)
rep["dl_prefixes"] = collections.Counter(re.sub(r"_?\d{6,8}.*", "", l.split("fileName=")[-1]) for l in dl).most_common()
rep["dl_last"] = sorted(dl)[-12:]
rep["dl_sample_tender"] = [l for l in dl if "award" not in l][-6:]
# footer / terms links
rep["policy_links"] = [l for l in links if re.search(r"privacy|open|copyright|policy|宣告|secur", l, re.I)][:40]
txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
i = txt.find("決標資料"); rep["award_text"] = txt[i:i+600] if i >= 0 else None
rep["tail"] = txt[-2500:]
# latest files
def fetch_file(name, rel):
    url = rel if rel.startswith("http") else B + "/tps/tp/OpenData/" + rel
    rr = get(name, url, n=4000)
    if rr is not None and rr.ok:
        c = rr.content
        if c[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(c)); rep[name]["zip"] = [(f.filename, f.file_size) for f in z.infolist()][:10]
            c = z.read(z.infolist()[0])
        s = c.decode("utf-8", "ignore")
        rep[name]["text_head"] = s[:5000]
        rep[name]["tags"] = collections.Counter(re.findall(r"<([A-Za-z_][\w\-]*)[ >]", s)).most_common(60)
        rep[name]["n_bytes"] = len(c)
aw = sorted([l for l in dl if "award" in l])
tn = sorted([l for l in dl if "award" not in l])
if aw: fetch_file("award_latest", aw[-1])
if tn: fetch_file("tender_latest", tn[-1])
for k, u in {"top5": "/tps/openDataApi/atmTop5", "ly1": "/tps/openDataApi/lyOpenData?runType=1", "ly2": "/tps/openDataApi/lyOpenData?runType=2", "cpc": "/osm/public/proctrg/download/CpcOpenData.xml"}.items():
    get(k, B + u, n=3000)
for p in ("/pis/prac/declarationClient/privacy", "/pis/prac/declarationClient/openData", "/pis/prac/declarationClient/security", "/pis/srch/pisSearchClient/searchSiteMap"):
    get("pg" + p.replace("/", "_"), B + p, n=200)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
