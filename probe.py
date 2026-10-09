import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
sites = {
 "518": ["https://case.518.com.tw/robots.txt", "https://case.518.com.tw/case-index.html", "https://case.518.com.tw/"],
 "1111": ["https://case.1111.com.tw/robots.txt", "https://case.1111.com.tw/"],
 "pro360": ["https://www.pro360.com.tw/robots.txt", "https://www.pro360.com.tw/case"],
 "tasker": ["https://www.tasker.com.tw/robots.txt", "https://www.tasker.com.tw/cases"],
 "104case": ["https://case.104.com.tw/robots.txt", "https://case.104.com.tw/"],
 "chickpt": ["https://www.chickpt.com.tw/robots.txt"],
}
for k, urls in sites.items():
    for u in urls:
        try:
            r = S.get(u, timeout=40); r.encoding = r.apparent_encoding or "utf-8"
            t = r.text
            info = {"status": r.status_code, "len": len(t), "final": r.url}
            if u.endswith("robots.txt"):
                info["body"] = t[:1500]
            else:
                tt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
                tt = re.sub(r"<[^>]+>", "\n", tt); tt = re.sub(r"\n\s*\n+", "\n", tt)
                info["text"] = tt[:2500]
                info["links"] = list(dict.fromkeys(re.findall(r'href="([^"]*(?:case|job|task|detail)[^"]*)"', t)))[:40]
                info["json_api"] = list(dict.fromkeys(re.findall(r'["\'](/api/[^"\']+|https?://[^"\']*api[^"\']*)["\']', t)))[:20]
            rep[u] = info
        except Exception as e:
            rep[u] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
