import os, json, re, requests
from collections import Counter
from urllib.parse import urlparse
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
U = {
 "VOGUE_US": "https://www.vogue.com/feed/rss",
 "ELLE_US": "https://www.elle.com/rss/all.xml",
 "BAZAAR_US": "https://www.harpersbazaar.com/rss/all.xml",
 "COSMO_US": "https://www.cosmopolitan.com/rss/all.xml",
 "MC_US": "https://www.marieclaire.com/feeds/all",
 "MC_US2": "https://www.marieclaire.com/rss/all.xml",
 "MC_UK": "https://www.marieclaire.co.uk/feeds/all",
 "GQ_US": "https://www.gq.com/feed/rss",
 "WH_US": "https://www.womenshealthmag.com/rss/all.xml",
 "VOGUE_UK": "https://www.vogue.co.uk/feed/rss",
 "GQ_TW_GNEWS": "https://news.google.com/rss/search?q=site:gq.com.tw&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=25); t = r.text
        links = re.findall(r"<link>\s*(?:<!\[CDATA\[)?\s*(https?://[^<\]\s]+)", t)
        paths = Counter("/".join(urlparse(l).path.strip("/").split("/")[:1]) for l in links)
        cats = Counter(re.findall(r"<category[^>]*>(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?</category>", t))
        dates = re.findall(r"<pubDate>([^<]+)", t)
        rep[k] = {"status": r.status_code, "bytes": len(t), "n": len(links), "paths": paths.most_common(12), "cats": cats.most_common(12),
                  "titles": re.findall(r"<title>(?:<!\[CDATA\[)?\s*([^<\]]+)", t)[1:4], "d0": dates[:1], "d1": dates[-1:]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:160]}
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
