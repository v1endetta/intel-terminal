"""臨時探測：在 GitHub Actions 上測幾個資料源抓不抓得到（沙盒連不到台灣政府網站）。跑完就刪。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {"ds": {}, "rss": {}, "gnews": {}, "misc": {}}
def get(u, n=900, **kw):
    try:
        r = requests.get(u, headers=H, timeout=30, **kw)
        return {"code": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(r.content), "head": r.content[:n].decode("utf-8", "replace")}
    except Exception as e:
        return {"err": str(e)[:200]}
for ds in ["9158", "131035", "44211", "168052", "73280", "73281", "146977", "94183", "40531", "7780"]:
    meta = get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", 6000)
    rec = {"meta": meta}
    try:
        js = json.loads(meta["head"] if meta.get("len", 0) <= 6000 else requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=30).text)
        res = js.get("result") or js
        rec["title"] = res.get("title")
        dists = res.get("distribution") or []
        rec["dist"] = [{"fmt": d.get("resourceFormat"), "url": d.get("resourceDownloadUrl"), "desc": d.get("resourceDescription")} for d in dists][:6]
        rec["samples"] = [get(d["url"], 1500) for d in rec["dist"][:3] if d.get("url")]
        meta["head"] = meta["head"][:300]
    except Exception as e:
        rec["perr"] = str(e)[:200]
    out["ds"][ds] = rec
for name, u in [("nikkei", "https://asia.nikkei.com/rss/feed/nar"), ("scmp_biz", "https://www.scmp.com/rss/92/feed"), ("scmp_china", "https://www.scmp.com/rss/4/feed"),
                ("straits_asia", "https://www.straitstimes.com/news/asia/rss.xml"), ("straits_biz", "https://www.straitstimes.com/news/business/rss.xml"),
                ("nhk", "https://www3.nhk.or.jp/rss/news/cat0.xml"), ("cna_biz", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936"),
                ("kedglobal", "https://www.kedglobal.com/newsRss"), ("thestar_biz", "https://www.thestar.com.my/rss/Business/Business-News"),
                ("japantoday", "https://japantoday.com/feed"), ("asiatimes", "https://asiatimes.com/feed/"), ("nikkei_biz", "https://asia.nikkei.com/rss/feed/Business")]:
    r = get(u, 400)
    r["items"] = len(re.findall(r"<item[\s>]", requests.get(u, headers=H, timeout=30).text)) if r.get("code") == 200 else 0
    out["rss"][name] = r
for q in ["補助 徵件 when:7d", "補助計畫 受理申請 截止 when:7d", "徵件 獎勵 新創 when:7d", "site:gov.tw 補助 徵件"]:
    u = "https://news.google.com/rss/search?q=" + requests.utils.quote(q) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        t = requests.get(u, headers=H, timeout=30).text
        out["gnews"][q] = re.findall(r"<title>(.*?)</title>", t)[1:12]
    except Exception as e:
        out["gnews"][q] = str(e)[:100]
for name, u in [("dgbas_cpi_page", "https://www.dgbas.gov.tw/cp.aspx?n=2834"), ("nstat_sdmx", "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sdmx/A030101015/1..M.json&startTime=2026-M1"),
                ("stat_tourism", "https://stat.taiwan.net.tw/"), ("moc_grants", "https://grants.moc.gov.tw/Web/"), ("startup_gov", "https://www.startupterrace.tw/"),
                ("sbir", "https://www.sbir.org.tw/"), ("ndc_grants", "https://www.ndc.gov.tw/"), ("sme_rss", "https://www.sme.gov.tw/rss.php")]:
    out["misc"][name] = get(u, 300)
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
