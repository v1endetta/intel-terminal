import requests, json, csv, io, re, base64
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
out = {}
def save(): json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
GT = [["徐巧芯「留時間給沈伯洋來質詢」 王義川不滿罵「爛召委」", "https://news.google.com/rss/articles/CBMiUEFVX3lxTE9yREJTS0JOalhURU1rVjl5SXY3RjBfNnpQMU13M1BoeVhLVEdSQUNaM3lpd1pYX3ZYTlZlWFBTZEtNSVE1eWJfbDJKYXlNaUkx0gFWQVVfeXFMUDZVZzRlakJiNXM4WUY3bGlsSXhLMGcyakR1WFJIbW45d1phaHRhUVoyRGNhRU5FR1lqN19fdnlGUVI2T1BWTWpQVF9mMFBPdjVvYWM4OHc?oc=5"], ["胡塞：飛彈擊中沙國戰機 襲擊沙國聯軍軍事目標", "https://news.google.com/rss/articles/CBMiT0FVX3lxTE9pMVEyY0pseTlTLXd1Y1FWZFdqMDFfUXlhbTVkSzY1dmJjR05qT0twUzF4S3BvemdMZTF4V0J6bzREZUlabGNTODZHYWlGTWc?oc=5"], ["買了長達20年！川普爆台灣包下阿拉斯加30％天然氣　外媒曝一背後隱憂", "https://news.google.com/rss/articles/CBMiSEFVX3lxTE16WGJyOGFhTUUtRDY0X1ZhUG1STHJMb1pRck5ic3dXNVBCS3ZCLTVGZkNXZlZ5QlNXNVBsblc0VEpuMHkxUmwxNNIBTEFVX3lxTE44RjFGaS1xR0c2V1hJbWVZS01VYjdubHo1MkJ4Wm91RmMtU0pZRklwTWlhbTliRmE1TDZ5alJzcnFvVzJxWEpadUpGLXo?oc=5"]]
# 1. Google 新聞連結能不能解出原文、拿 og:image
res = []
for t, u in GT:
    o = {"t": t}
    try:
        r = S.get(u, timeout=20, allow_redirects=True); o["final"] = r.url[:120]; o["st"] = r.status_code
        m = re.search(r'data-n-a-sg="([^"]+)".*?data-n-a-ts="([^"]+)"', r.text, re.S); o["sg"] = bool(m)
        o["og"] = (re.findall(r'property="og:image" content="([^"]+)"', r.text) or [""])[0][:150]
    except Exception as e:
        o["err"] = repr(e)[:120]
    # Bing 新聞 RSS 用標題查
    try:
        b = S.get("https://www.bing.com/news/search", params={"q": t[:40], "format": "rss", "mkt": "zh-TW"}, timeout=20).text
        o["bing_img"] = re.findall(r"<News:Image>(.*?)</News:Image>", b)[:2]
        o["bing_titles"] = re.findall(r"<title>(.*?)</title>", b)[1:3]
    except Exception as e:
        o["bing_err"] = repr(e)[:120]
    res.append(o)
out["news"] = res; save()
# 2. OSM Overpass：北屯區咖啡店數
try:
    q = '[out:json][timeout:25];area["name"="北屯區"]["admin_level"="7"]->.a;(node["amenity"="cafe"](area.a);node["amenity"="coworking_space"](area.a);node["office"="coworking"](area.a););out count;'
    r = S.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=60); out["overpass"] = [r.status_code, r.text[:400]]
except Exception as e:
    out["overpass"] = repr(e)[:150]
save()
# 3. 開放資料目錄搜尋
try:
    r = S.get("https://data.gov.tw/datasets/export/csv", timeout=120)
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
    pats = {"crime": r"刑案|竊盜|犯罪|治安", "rent": r"租賃.*實價|實價.*租賃|租金", "aqi": r"空氣品質.*(年|月)|細懸浮微粒.*(年|月)|PM2\.?5.*(年|月)", "age": r"人口.*年齡|年齡.*人口|扶老比|人口結構", "foreign": r"外籍|外僑|居留", "noise": r"噪音", "green": r"公園|綠地"}
    for k, p in pats.items():
        out["cat_" + k] = [[x[0], x[1][:50], x[5][:20], x[11][:16], x[12][:10], x[10][:120]] for x in rows[1:] if re.search(p, x[1]) and re.search(r"內政部|警政署|環境部|移民署|主計|國土|營建|統計", x[11])][:25]
except Exception as e:
    out["cat_err"] = repr(e)[:150]
save()
