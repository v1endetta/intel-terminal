import requests, json, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
out = {}
for u in ["https://www.submarinecablemap.com/api/v3/cable/cable-geo.json", "https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json",
          "https://www.submarinecablemap.com/api/v3/country/taiwan.json", "https://www.submarinecablemap.com/api/v3/cable/apricot.json",
          "https://www.mnd.gov.tw/news/plaactlist", "https://www.mnd.gov.tw/", "https://www.mnd.gov.tw/PublishTable.aspx?Types=%E5%8D%B3%E6%99%82%E8%BB%8D%E4%BA%8B%E5%8B%95%E6%85%8B&title=%E5%9C%8B%E9%98%B2%E6%B6%88%E6%81%AF",
          "https://www.mnd.gov.tw/english/news/plaactlist", "https://news.google.com/rss/search?q=%E5%85%B1%E6%A9%9F+%E6%9E%B6%E6%AC%A1+%E5%85%B1%E8%89%A6&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"]:
    try:
        r = S.get(u, timeout=40)
        t = r.text
        x = {"st": r.status_code, "ct": r.headers.get("content-type"), "len": len(t), "head": t[:600]}
        if "mnd" in u:
            x["links"] = list(dict.fromkeys(re.findall(r'href="([^"]*(?:plaact|PLAact|Plaact)[^"]*)"', t)))[:15]
            x["kw"] = [m for m in re.findall(r"[^<>]{0,60}(?:架次|共艦|共機)[^<>]{0,60}", t)][:10]
        if "taiwan.json" in u or "apricot" in u:
            x["head"] = t[:2500]
        if "google" in u:
            x["titles"] = re.findall(r"<title>(.*?)</title>", t)[:15]
        out[u] = x
    except Exception as e:
        out[u] = repr(e)[:200]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
