import os, json, re, requests
os.makedirs("out11", exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36", "Accept": "application/json, text/html;q=0.9"})
U = {"ks_robots": "https://www.kickstarter.com/robots.txt",
     "ks_disc_json": "https://www.kickstarter.com/discover/advanced.json?sort=magic&page=1",
     "ks_disc_json2": "https://www.kickstarter.com/discover/advanced?format=json&sort=popularity&woe_id=23424971",
     "ks_disc_html": "https://www.kickstarter.com/discover/advanced?sort=popularity",
     "ks_atom": "https://www.kickstarter.com/projects/feed.atom",
     "ks_blog_rss": "https://www.kickstarter.com/blog.atom",
     "kicktraq_hot": "https://www.kicktraq.com/hot/",
     "kicktraq_robots": "https://www.kicktraq.com/robots.txt",
     "kicktraq_rss": "https://www.kicktraq.com/feeds/hot/"}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=30)
        rep[k] = {"status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "server": r.headers.get("server"), "head": r.text[:1500]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:200]}
json.dump(rep, open("out11/report.json", "w"), ensure_ascii=False, indent=1)
