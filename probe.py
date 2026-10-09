import os, json, re, requests, collections
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (intel-terminal research)"}
rep = {}
def text(html):
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
def get(name, url, n=4000, raw=False, **kw):
    try:
        r = requests.get(url, headers=H, timeout=90, **kw)
        ct = r.headers.get("content-type") or ""
        body = r.text if (raw or "json" in ct or "plain" in ct or "xml" in ct or "csv" in ct) else text(r.text)
        rep[name] = {"status": r.status_code, "ct": ct, "url": r.url, "len": len(r.content), "body": body[:n]}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:300]}
for ds in ("6951", "41430", "7299", "17327"):
    try:
        js = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=40).json()["result"]
        rep["dgt_" + ds] = {k: js.get(k) for k in ("title", "updateFrequency", "license", "modifiedDate", "description")}
        rep["dgt_" + ds]["dist"] = [(x.get("resourceFormat"), x.get("resourceDownloadUrl")) for x in (js.get("distribution") or [])][:4]
    except Exception as e:
        rep["dgt_" + ds] = {"err": repr(e)[:200]}
# health food sample
for k, v in list(rep.items()):
    if k == "dgt_6951" and "dist" in v:
        for fmt, u in v["dist"]:
            if fmt == "JSON" or "json" in (u or "").lower():
                r = requests.get(u, headers=H, timeout=120)
                try:
                    js = r.json(); rows = js if isinstance(js, list) else js.get("data") or js
                    rep["hf_n"] = len(rows); rep["hf_keys"] = list(rows[0].keys()); rep["hf_first"] = rows[:2]; rep["hf_last"] = rows[-2:]
                    dk = [c for c in rows[0] if "日期" in c]
                    rep["hf_datecols"] = dk
                    for c in dk:
                        vals = sorted(str(x.get(c)) for x in rows if x.get(c))
                        rep["hf_" + c] = vals[-8:]
                        rep["hf_" + c + "_byyear"] = collections.Counter(v[:3] if v[:3].isdigit() and len(v) < 10 else v[:4] for v in vals).most_common(40)
                except Exception as e:
                    rep["hf_err"] = repr(e)[:300] + r.text[:300]
                break
# fish market sample
get("fish_api", "https://data.moa.gov.tw/api/v1/FisheryProductsTransType/?Start_time=115.10.01&End_time=115.10.08", n=1500)
get("moa_terms", "https://data.moa.gov.tw/", n=200)
# LYAPI disclaimer
r = get("ly_v2", "https://ly.govapi.tw/v2", n=200, raw=True)
if r is not None and r.ok:
    links = re.findall(r'href="([^"]+)"[^>]*>([\s\S]{0,60}?)</a>', r.text)
    rep["ly_links"] = [(h, re.sub(r"<[^>]+>|\s+", " ", t).strip()) for h, t in links][:60]
    for h, t in rep["ly_links"]:
        if re.search(r"免責|Disclaimer|CC-BY|License|授權", t + h, re.I):
            u = h if h.startswith("http") else "https://ly.govapi.tw" + h
            get("ly_doc_" + t[:10], u, n=4000)
# PCC copyright: search homepage html for 著作權
r = requests.get("https://web.pcc.gov.tw/pis/", headers=H, timeout=60)
rep["pcc_cr_ctx"] = [r.text[max(0, m.start()-300):m.start()+100] for m in re.finditer("著作權|版權|資料開放宣告|隱私", r.text)][:6]
for u in ("https://web.pcc.gov.tw/pis/prac/declarationClient/copyright", "https://web.pcc.gov.tw/pis/prac/declarationClient/readCopyright", "https://web.pcc.gov.tw/tps/tp/copyright"):
    get("pcc_try_" + u.rsplit("/", 1)[-1], u, n=3000)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
