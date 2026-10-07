import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
for qq in ("Q3-26", "Q2-26"):
    url = f"https://www.lyst.com/the-lyst-index/{qq}"
    try:
        r = S.get(url, timeout=60)
        h = r.text
        info = {"status": r.status_code, "len": len(h), "hottest": h.count("Hottest"), "next": "__NEXT_DATA__" in h}
        t = re.sub(r"<script.*?</script>|<style.*?</style>", "\n", h, flags=re.S)
        t = re.sub(r"<[^>]+>", "\n", t); t = re.sub(r"\n\s*\n+", "\n", t)
        lines = [l.strip() for l in t.split("\n") if l.strip()]
        idx = [i for i, l in enumerate(lines) if "hottest" in l.lower()]
        info["ctx"] = [lines[max(0, i - 2):i + 30] for i in idx[:3]]
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
        if m:
            info["next_head"] = m.group(1)[:3000]
        imgs = re.findall(r'alt="([^"]{2,60})"', h)
        info["alts"] = imgs[:60]
        rep[qq] = info
    except Exception as e:
        rep[qq] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
