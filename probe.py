import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
r = S.get("https://today.line.me/tw/v2/tab/top", timeout=25)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
nd = json.loads(m.group(1))
def walk(o, path, out):
    if isinstance(o, dict):
        if "title" in o and isinstance(o.get("title"), str) and ("url" in o or "hash" in o):
            out.append((path, {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in list(o.items())[:12]}))
        for k, v in o.items(): walk(v, path + "." + k, out)
    elif isinstance(o, list):
        for i, v in enumerate(o[:60]): walk(v, path + "[]", out)
out = []; walk(nd, "", out)
from collections import Counter
rep["paths"] = Counter(p for p, _ in out).most_common(12)
rep["samples"] = [o for p, o in out if "ranking" in p.lower() or "rank" in json.dumps(o).lower()][:4] or [o for _, o in out[:4]]
# modules with names
mods = []
def walk2(o):
    if isinstance(o, dict):
        if "name" in o and "articles" in o: mods.append((o.get("name"), len(o["articles"]) if isinstance(o["articles"], list) else 0))
        for v in o.values(): walk2(v)
    elif isinstance(o, list):
        for v in o: walk2(v)
walk2(nd); rep["mods"] = mods[:20]
r = S.get("https://kworb.net/spotify/country/tw_daily.html", timeout=25); r.encoding = "utf-8"
rows = re.findall(r"<tr>(.*?)</tr>", r.text, re.S)[:4]; rep["kworb_rows"] = [re.sub(r"<[^>]+>", "|", x)[:200] for x in rows]
r = S.get("https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv", timeout=60)
lines = r.text.splitlines(); rep["nf_head"] = lines[0]; tw = [l for l in lines if "\tTW\t" in l]; rep["nf_tw"] = tw[:12]
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
