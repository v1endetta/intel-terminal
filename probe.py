import os, json, re, requests, time, urllib.parse
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def g(k, u, **kw):
    try:
        r = S.get(u, timeout=25, **kw); rep[k] = {"status": r.status_code, "bytes": len(r.text), "head": re.sub(r"\s+", " ", r.text[:300])}; return r
    except Exception as e:
        rep[k] = {"err": repr(e)[:150]}
r = g("kworb_tw", "https://kworb.net/spotify/country/tw_daily.html")
if r is not None and r.ok: rep["kworb_rows"] = re.findall(r'<td class="text mp"><div>(.*?)</div>', r.text)[:5]
r = g("kworb_tw_weekly", "https://kworb.net/spotify/country/tw_weekly.html")
g("spotify_charts", "https://charts-spotify-com-service.spotify.com/public/v0/charts")
r = g("nf_top10_tw", "https://www.netflix.com/tudum/top10/taiwan")
if r is not None and r.ok:
    rep["nf_titles"] = re.findall(r'"name":"([^"]{2,60})"', r.text)[:12]
    rep["nf_len_json"] = len(re.findall(r"__NEXT_DATA__|window\.netflix", r.text))
g("nf_tsv", "https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv")
g("flixpatrol", "https://flixpatrol.com/top10/netflix/taiwan/")
r = g("line_today", "https://today.line.me/tw/v2/tab/top")
if r is not None and r.ok:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    rep["lt_next"] = bool(m); rep["lt_titles"] = re.findall(r'"title":"([^"]{6,60})"', r.text)[:10]
g("line_today_api", "https://today.line.me/webapi/portal/page/setting?country=tw&path=top")
r = g("apple_pod", "https://rss.applemarketingtools.com/api/v2/tw/podcasts/top/25/podcasts.json")
if r is not None and r.ok: rep["pod"] = [x["name"] for x in r.json()["feed"]["results"][:5]]
# google trends interest over time
try:
    req = {"comparisonItem": [{"keyword": k, "geo": "TW", "time": "today 3-m"} for k in ["塗料", "外泌體", "設計家具"]], "category": 0, "property": ""}
    r = S.get("https://trends.google.com/trends/api/explore", params={"hl": "zh-TW", "tz": "-480", "req": json.dumps(req, ensure_ascii=False)}, timeout=25)
    rep["gt_explore"] = r.status_code
    w = json.loads(r.text[4:])["widgets"]; ts = [x for x in w if x["id"] == "TIMESERIES"][0]
    time.sleep(2)
    r2 = S.get("https://trends.google.com/trends/api/widgetdata/multiline", params={"hl": "zh-TW", "tz": "-480", "req": json.dumps(ts["request"], ensure_ascii=False), "token": ts["token"]}, timeout=25)
    rep["gt_multi"] = r2.status_code
    tl = json.loads(r2.text[5:])["default"]["timelineData"]; rep["gt_points"] = len(tl); rep["gt_last"] = tl[-3:]
except Exception as e:
    rep["gt_err"] = repr(e)[:200]
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
