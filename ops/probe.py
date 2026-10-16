# 一次性實測：新資料源從 GitHub Actions 抓不抓得到（結果寫 probe.json；不寫入任何金鑰）
import json, os, re, time, csv, io
import requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 dalta-intel/1.0 (personal non-commercial)"
FRED = os.environ.get("FRED_API_KEY", "").strip()
OUT = {}
def clean(t):
    t = str(t)
    if FRED: t = t.replace(FRED, "***")
    return re.sub(r"api_key=[^&\s]+", "api_key=***", t)
def hit(name, url, params=None, n=600, **kw):
    t0 = time.time()
    try:
        r = S.get(url, params=params, timeout=40, **kw)
        b = r.content
        OUT[name] = {"st": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(b), "ms": int((time.time()-t0)*1000), "head": clean(b[:n].decode("utf-8", "replace"))}
        return r
    except Exception as e:
        OUT[name] = {"err": clean(repr(e))[:300]}
        return None
def note(name, **kw): OUT.setdefault(name, {}).update({k: clean(v) if isinstance(v, str) else v for k, v in kw.items()})

# 1 FRED 信用利差
for sid in ("BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC"):
    r = hit("fred_" + sid, "https://api.stlouisfed.org/fred/series/observations", {"series_id": sid, "api_key": FRED, "file_type": "json", "sort_order": "desc", "limit": 5}, n=0)
    try:
        j = r.json(); note("fred_" + sid, last=[(o["date"], o["value"]) for o in j["observations"][:5]])
        r2 = S.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id": sid, "api_key": FRED, "file_type": "json", "sort_order": "asc", "limit": 1}, timeout=30).json()
        note("fred_" + sid, first=r2["observations"][0]["date"] if r2.get("observations") else None)
        m = S.get("https://api.stlouisfed.org/fred/series", params={"series_id": sid, "api_key": FRED, "file_type": "json"}, timeout=30).json()
        s = (m.get("seriess") or [{}])[0]; note("fred_" + sid, title=s.get("title"), freq=s.get("frequency"), notes=(s.get("notes") or "")[:500], updated=s.get("last_updated"))
    except Exception as e: note("fred_" + sid, perr=repr(e)[:200])

# 2 Federal Register / USTR / congress
FR = "https://www.federalregister.gov/api/v1/documents.json"
for ag in ("trade-representative-office-of-united-states", "industry-and-security-bureau", "international-trade-administration"):
    r = hit("fr_" + ag, FR, {"conditions[agencies][]": ag, "per_page": 5, "order": "newest", "fields[]": ["title", "publication_date", "type", "html_url", "abstract"]}, n=0)
    try: j = r.json(); note("fr_" + ag, count=j.get("count"), items=[(d["publication_date"], d["type"], d["title"][:120]) for d in j.get("results", [])])
    except Exception as e: note("fr_" + ag, perr=repr(e)[:200])
r = hit("fr_term", FR, {"conditions[term]": '"Taiwan" | semiconductor | "Section 232" | tariff | "export control"', "conditions[agencies][]": ["trade-representative-office-of-united-states", "industry-and-security-bureau", "international-trade-administration"], "per_page": 8, "order": "newest", "fields[]": ["title", "publication_date", "agencies"]}, n=0)
try: j = r.json(); note("fr_term", count=j.get("count"), items=[(d["publication_date"], d["title"][:120]) for d in j.get("results", [])])
except Exception as e: note("fr_term", perr=repr(e)[:200])
hit("fr_pi", "https://www.federalregister.gov/api/v1/public-inspection-documents/current.json", n=300)
for u in ("https://ustr.gov/about-us/policy-offices/press-office/press-releases", "https://ustr.gov/rss.xml", "https://ustr.gov/about-us/policy-offices/press-office/press-releases/feed", "https://ustr.gov/taxonomy/term/116/feed"):
    r = hit("ustr " + u.split("ustr.gov")[1], u, n=400)
    if r is not None and r.ok:
        t = r.text; note("ustr " + u.split("ustr.gov")[1], items=re.findall(r'<a href="(/about-us/policy-offices/press-office/press-releases/20\d\d/[^"]+)"[^>]*>([^<]{10,140})</a>', t)[:5], rss=re.findall(r"<title>([^<]{10,140})</title>", t)[:5])
hit("congress_nokey", "https://api.congress.gov/v3/bill", {"format": "json", "limit": 1}, n=300)

# 3 台灣出口 / 4 企業壓力：data.gov.tw 候選資料集與搜尋
def gov(ds):
    k = f"gov_{ds}"
    r = hit(k, f"https://data.gov.tw/api/v2/rest/dataset/{ds}", n=0)
    try:
        j = r.json()["result"]; d = j.get("distribution") or []
        note(k, title=j.get("title"), org=j.get("organization") or j.get("publisher"), freq=j.get("updateFrequency") or j.get("accrualPeriodicity"), modified=j.get("modifiedDate") or j.get("modified"),
             license=j.get("license"), dists=[(x.get("resourceDescription", "")[:40], x.get("resourceFormat"), (x.get("resourceDownloadUrl") or "")[:160]) for x in d[:4]], nd=len(d))
        u = next((x.get("resourceDownloadUrl") for x in d if x.get("resourceDownloadUrl")), None)
        if u:
            b = S.get(u, timeout=60).content
            for enc in ("utf-8-sig", "cp950"):
                try: t = b.decode(enc); break
                except Exception: t = None
            t = t or b.decode("utf-8", "replace")
            note(k, sample=t[:700], nlines=t.count("\n"))
    except Exception as e: note(k, perr=repr(e)[:200])
for ds in (13673, 10831, 15392, 8418, 23828, 10508, 32064, 8387, 67175):
    gov(ds)
for q in ("減班休息", "退票", "進出口 國家別", "出口 貨品 國家", "海關進出口"):
    for name, u, p in (("ckan", "https://scidm.nchc.org.tw/api/3/action/package_search", {"q": q, "rows": 12}),):
        r = hit(f"search_{name}_{q}", u, p, n=0)
        try:
            j = r.json(); note(f"search_{name}_{q}", res=[(x.get("name"), x.get("title"), (x.get("organization") or {}).get("title"), x.get("metadata_modified", "")[:10]) for x in j["result"]["results"]])
        except Exception as e: note(f"search_{name}_{q}", perr=repr(e)[:200])
hit("mof_stat_db", "https://web02.mof.gov.tw/njswww/WebMain.aspx?sys=100&funid=defjsptgl", n=400)
hit("customs_portal", "https://portal.sw.nat.gov.tw/APGA/GA30", n=400)
hit("mol_odservice", "https://apiservice.mol.gov.tw/OdService/rest/datastore/A17000000J-030169-Ub3", n=400)
hit("mol_site", "https://www.mol.gov.tw/1607/1632/1640/", n=300)
hit("cbc_site", "https://www.cbc.gov.tw/tw/lp-370-1.html", n=300)
hit("tch_site", "https://www.twnch.org.tw/", n=300)

# 5 物流
r = hit("drewry", "https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry", n=0)
if r is not None and r.ok: note("drewry", lanes=re.findall(r"(Shanghai[^<]{0,40}?(?:Rotterdam|Genoa|Los Angeles|New York)[^<]{0,80})", re.sub(r"<[^>]+>", " ", r.text))[:8])
for u in ("https://fbx.freightos.com/api/lane/FBX?isDaily=true", "https://fbx.freightos.com/", "https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/"):
    hit("fbx " + u[8:60], u, n=400)
r = hit("nhc", "https://www.nhc.noaa.gov/CurrentStorms.json", n=800)
hit("gdacs_rss", "https://www.gdacs.org/xml/rss.xml", n=800)
r = hit("gdacs_api", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH", {"eventlist": "TC", "alertlevel": "Green;Orange;Red"}, n=0)
try: j = r.json(); note("gdacs_api", n=len(j.get("features", [])), ev=[(f["properties"].get("name"), f["properties"].get("alertlevel"), f["properties"].get("fromdate"), f["geometry"]["coordinates"]) for f in j.get("features", [])[:6]])
except Exception as e: note("gdacs_api", perr=repr(e)[:200])
hit("jtwc_rss", "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss", n=600)
for u in ("https://www.freightwaves.com/news/feed", "https://www.freightwaves.com/feed", "https://www.supplychaindive.com/feeds/news/", "https://theloadstar.com/feed/"):
    r = hit("rss " + u[8:50], u, n=0)
    if r is not None and r.ok: note("rss " + u[8:50], titles=re.findall(r"<title>(?:<!\[CDATA\[)?([^<\]]{10,140})", r.text)[:6], dates=re.findall(r"<pubDate>([^<]+)</pubDate>", r.text)[:2])
json.dump(OUT, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("done", len(OUT))
