import os, json, re, requests
from collections import Counter
from urllib.parse import urlparse
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
U = {
 "美麗佳人": "https://www.marieclaire.com.tw/google-news.xml",
 "VOGUE": "https://www.vogue.com.tw/feed/rss",
 "ELLE": "https://www.elle.com/tw/rss/all.xml",
 "BAZAAR": "https://www.harpersbazaar.com/tw/rss/all.xml",
 "COSMO": "https://www.cosmopolitan.com/tw/rss/all.xml",
 "GQ": "https://www.gq.com.tw/feed/rss",
 "Esquire": "https://www.esquire.com/tw/rss/all.xml",
 "WomensHealth": "https://www.womenshealthmag.com/tw/rss/all.xml",
 "MensHealth": "https://www.menshealth.com/tw/rss/all.xml",
 "Bella": "https://www.bella.tw/rss",
 "Bella2": "https://www.bella.tw/feed",
 "LaVie": "https://www.wowlavie.com/rss",
 "LaVie2": "https://www.wowlavie.com/feed",
 "MensUno": "https://www.menu.com.tw/feed",
 "LOfficiel": "https://www.lofficiel.com.tw/feed",
 "Beauty321": "https://www.beauty321.com/rss",
 "VogueGN": "https://www.vogue.com.tw/sitemap/google-news.xml",
 "GQ_GN": "https://www.gq.com.tw/sitemap/google-news.xml",
 "Numero": "https://numero.tw/feed",
 "Popdaily": "https://www.popdaily.com.tw/rss",
}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=25); t = r.text
        links = re.findall(r"<link>\s*(?:<!\[CDATA\[)?\s*(https?://[^<\]\s]+)", t) or re.findall(r"<loc>\s*(https?://[^<\s]+)", t)
        paths = Counter("/".join(urlparse(l).path.strip("/").split("/")[:2]) for l in links)
        cats = Counter(re.findall(r"<category[^>]*>(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?</category>", t))
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?\s*([^<\]]+)", t)[:4] or re.findall(r"<news:title>(?:<!\[CDATA\[)?\s*([^<\]]+)", t)[:4]
        rep[k] = {"status": r.status_code, "bytes": len(t), "n": len(links), "paths": paths.most_common(15), "cats": cats.most_common(15), "titles": titles, "head": t[:150]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:160]}
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
