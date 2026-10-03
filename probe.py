import os, json, re, requests
os.makedirs("out14", exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"})
U = {"mc_gnews": "https://www.marieclaire.com.tw/google-news.xml", "mc_fashion": "https://www.marieclaire.com.tw/rss/sitemap/fashion",
     "vogue": "https://www.vogue.com.tw/feed/rss", "elle": "https://www.elle.com/tw/rss/all.xml", "bazaar": "https://www.harpersbazaar.com/tw/rss/all.xml",
     "cosmo": "https://www.cosmopolitan.com/tw/rss/all.xml"}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=30); t = r.text
        titles = re.findall(r"<(?:title|news:title)>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</(?:title|news:title)>", t)
        dates = re.findall(r"<(?:pubDate|news:publication_date|lastmod)>(.*?)<", t)
        rep[k] = {"status": r.status_code, "bytes": len(r.content), "n": len(titles), "titles": titles[:8], "dates": dates[:4], "head": t[:400]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:200]}
json.dump(rep, open("out14/report.json", "w"), ensure_ascii=False, indent=1)
