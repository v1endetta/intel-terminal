import os, json, re, requests
os.makedirs("out13", exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"})
sites = {"mc": "https://www.marieclaire.com.tw", "vogue": "https://www.vogue.com.tw", "elle": "https://www.elle.com/tw", "bazaar": "https://www.harpersbazaar.com/tw", "gq": "https://www.gq.com.tw", "cosmo": "https://www.cosmopolitan.com/tw", "wwd": "https://www.wwd.com"}
paths = ["/robots.txt", "/rss", "/feed", "/rss.xml", "/feed/rss", "/sitemap.xml", "/"]
rep = {}
for k, base in sites.items():
    for p in paths:
        u = base + p
        try:
            r = S.get(u, timeout=25, allow_redirects=True)
            t = r.text
            rep[f"{k}{p}"] = {"url": r.url, "status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "server": r.headers.get("server"),
                              "head": t[:500], "feeds": sorted(set(re.findall(r'(?:href|<loc>)\s*=?\s*"?([^"<>\s]*(?:rss|feed|sitemap)[^"<>\s]*)', t)))[:15]}
            if p == "/robots.txt": rep[f"{k}{p}"]["head"] = t[:1500]
        except Exception as e:
            rep[f"{k}{p}"] = {"err": repr(e)[:160]}
json.dump(rep, open("out13/report.json", "w"), ensure_ascii=False, indent=1)
