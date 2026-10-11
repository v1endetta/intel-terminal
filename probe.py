import os, json, requests, time
os.makedirs("out25", exist_ok=True)
rep = {}
for u in ("https://rss.marketingtools.apple.com/api/v2/tw/podcasts/top/25/podcasts.json", "https://rss.applemarketingtools.com/api/v2/tw/podcasts/top/25/podcasts.json", "https://itunes.apple.com/tw/rss/toppodcasts/limit=25/json"):
    t = time.time()
    try:
        r = requests.get(u, timeout=60, headers={"User-Agent": "intel-terminal/1.0"})
        rep[u] = {"st": r.status_code, "sec": round(time.time() - t, 1), "len": len(r.content), "head": r.text[:200]}
    except Exception as e:
        rep[u] = {"err": str(e)[:150], "sec": round(time.time() - t, 1)}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
