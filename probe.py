import os, json, re, requests
os.makedirs("out9", exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
U = {"robots": "https://www.zeczec.com/robots.txt",
     "cats": "https://www.zeczec.com/categories",
     "cats_hot": "https://www.zeczec.com/categories?sort_by=popular",
     "cats_new": "https://www.zeczec.com/categories?sort_by=newest",
     "cats_json": "https://www.zeczec.com/categories.json",
     "proj": "https://www.zeczec.com/projects/qianqiangreen",
     "proj_json": "https://www.zeczec.com/projects/qianqiangreen.json",
     "sitemap": "https://www.zeczec.com/sitemap.xml",
     "terms": "https://www.zeczec.com/terms"}
for k, u in U.items():
    try:
        r = S.get(u, timeout=30)
        t = r.text
        rep[k] = {"status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "head": t[:800],
                  "links": sorted(set(re.findall(r'href="(/projects/[^"?#]+)"', t)))[:30],
                  "nums": re.findall(r'NT\$\s?[\d,]+', t)[:20], "pct": re.findall(r'\d+%', t)[:20]}
        open(f"out9/{k}.html", "w").write(t[:500000])
    except Exception as e:
        rep[k] = {"err": repr(e)[:200]}
json.dump(rep, open("out9/report.json", "w"), ensure_ascii=False, indent=1)
