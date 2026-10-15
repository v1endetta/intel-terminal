import requests, json, re
import xml.etree.ElementTree as ET
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (compatible; intel-terminal/1.0)"
C = {
 "bbg_markets": ["https://feeds.bloomberg.com/markets/news.rss", "https://www.bloomberg.com/feeds/markets/news.rss"],
 "bbg_econ": ["https://feeds.bloomberg.com/economics/news.rss"],
 "bbg_tech": ["https://feeds.bloomberg.com/technology/news.rss"],
 "bbg_gurman": ["https://www.bloomberg.com/authors/AS7Hj1mBMGM/mark-gurman.rss"],
 "prtimes": ["https://prtimes.jp/index.rdf", "https://prtimes.jp/main/html/index/rss"],
 "fashionsnap": ["https://www.fashionsnap.com/rss.xml", "https://www.fashionsnap.com/feed/", "https://www.fashionsnap.com/rss/"],
 "wwdjapan": ["https://www.wwdjapan.com/feed", "https://www.wwdjapan.com/rss"],
 "glossy": ["https://www.glossy.co/feed/"],
 "voguebiz": ["https://www.voguebusiness.com/feed/rss", "https://www.voguebusiness.com/rss"],
 "dwell": ["https://www.dwell.com/feed", "https://www.dwell.com/rss"],
 "wallpaper": ["https://www.wallpaper.com/feeds/all", "https://www.wallpaper.com/rss"],
 "modernretail": ["https://www.modernretail.co/feed/"],
 "retaildive": ["https://www.retaildive.com/feeds/news/"],
 "springwise": ["https://www.springwise.com/feed/"],
 "restofworld": ["https://restofworld.org/feed/latest/", "https://restofworld.org/feed/"],
 "36kr": ["https://36kr.com/feed", "https://36kr.com/feed-newsflash"],
 "skift": ["https://skift.com/feed/"],
}
out = {}
for k, urls in C.items():
    res = []
    for u in urls:
        try:
            r = S.get(u, timeout=25, allow_redirects=True)
            t = r.content
            n, titles, dates = 0, [], []
            try:
                root = ET.fromstring(t)
                its = [e for e in root.iter() if e.tag.split('}')[-1] in ("item", "entry")]
                n = len(its)
                for e in its[:4]:
                    ti = next((c.text for c in e if c.tag.split('}')[-1] == "title"), "")
                    da = next((c.text for c in e if c.tag.split('}')[-1] in ("pubDate", "date", "published", "updated")), "")
                    titles.append((ti or "")[:90]); dates.append(da)
            except Exception as e:
                titles = [repr(e)[:80], t[:150].decode("utf-8", "replace")]
            res.append({"u": u, "st": r.status_code, "final": r.url[:90], "n": n, "titles": titles, "dates": dates[:2]})
            if n:
                break
        except Exception as e:
            res.append({"u": u, "err": repr(e)[:120]})
    out[k] = res
# 台灣中文新聞查詢（Google News）測試
for q in ["退貨險", "外泌體", "Labubu"]:
    try:
        r = S.get("https://news.google.com/rss/search", params={"q": f"{q} when:30d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}, timeout=25)
        out["gn_" + q] = len(re.findall(r"<item>", r.text))
    except Exception as e:
        out["gn_" + q] = repr(e)[:100]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
