"""暫時探測（2026-11-13，Vin 核准）：保險預測指標的資料來源讀不讀得到。只存回應、不動正式資料。用完刪掉。"""
import json, os, re, sys, time, urllib.parse
import requests

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"}
idx = []


def grab(tag, url, binary=False, keep=400000):
    rec = {"tag": tag, "url": url}
    try:
        r = requests.get(url, headers=UA, timeout=40)
        rec.update(status=r.status_code, len=len(r.content), ctype=r.headers.get("content-type", ""))
        ext = "bin" if binary else ("json" if "json" in rec["ctype"] else ("csv" if "csv" in rec["ctype"] else "html"))
        m = re.search(r"\.(xlsx?|pdf|csv|ods)(?:$|\?)", url)
        if m:
            ext = m.group(1)
        fn = f"{tag}.{ext}"
        open(os.path.join(OUT, fn), "wb").write(r.content[:keep] if ext in ("html", "json", "csv") else r.content[:6_000_000])
        rec["file"] = fn
        return r
    except Exception as e:  # noqa: BLE001
        rec["err"] = repr(e)[:200]
        return None
    finally:
        idx.append(rec)
        time.sleep(1.2)


# 1) 保發中心：開放資料目錄（找解約、保單貸款、產險月資料）、年報人身保險給付表、季指標
for u in ("https://openapi.tii.org.tw/", "https://openapi.tii.org.tw/TIIOPENDATA/", "https://openapi.tii.org.tw/TIIOPENDATA/swagger/v1/swagger.json",
          "https://openapi.tii.org.tw/swagger/v1/swagger.json", "https://openapi.tii.org.tw/TIIOPENDATA/swagger/index.html"):
    grab("tiiapi_%d" % len(idx), u)
for i in list(range(13505, 13530)) + list(range(14495, 14520)):
    r = grab(f"dg_{i}", f"https://data.gov.tw/api/v2/rest/dataset/{i}", keep=20000)
for n in range(1, 11):
    r = grab(f"tiiyb_{n:02d}", f"https://www.tii.org.tw/tii/information/information1/{n:06d}.html")
    if r is not None and r.ok:
        for m in re.finditer(r'href="([^"]*/files/(?:7-2|5-2|3-life)[^"]*\.xlsx?)"', r.text):
            u = urllib.parse.urljoin(r.url, m.group(1))
            grab("tiifile_" + re.sub(r"[^0-9A-Za-z.-]", "_", u.rsplit("/", 1)[1])[:40].rsplit(".", 1)[0], u, binary=True)
grab("tiipivot", "https://pivot.tii.org.tw/")
grab("tiistat", "https://www.tii.org.tw/tii/information/information2/")
# 2) 保險局新聞稿（每月保險業損益、淨值、外匯價格變動準備金）
for t, u in (("ib_news", "https://www.ib.gov.tw/ch/home.jsp?id=239&parentpath=0,2,238"), ("ib_stat", "https://www.ib.gov.tw/ch/home.jsp?id=48&parentpath=0,4"),
             ("fsc_rss", "https://www.fsc.gov.tw/RSS/Messages?serno=201202290009&language=chinese"), ("fsc_news", "https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2"),
             ("ib_rss", "https://www.ib.gov.tw/RSS/Messages?serno=201202290009&language=chinese")):
    r = grab(t, u)
    if t == "ib_news" and r is not None and r.ok:
        hits = [m for m in re.finditer(r'href="([^"]+)"[^>]*>([^<]*(?:損益|淨值|外匯價格|保費收入)[^<]*)<', r.text)][:3]
        for k, m in enumerate(hits):
            grab(f"ib_news_item{k}", urllib.parse.urljoin(r.url, m.group(1).replace("&amp;", "&")))
# 3) 債券 ETF 規模、國際債發行
for t, u in (("tpex_swagger", "https://www.tpex.org.tw/openapi/swagger.json"), ("twse_swagger", "https://openapi.twse.com.tw/v1/swagger.json"),
             ("sitca_etf", "https://www.sitca.org.tw/ROC/Industry/IN2629.aspx?pid=IN22601_04"), ("sitca_home", "https://www.sitca.org.tw/ROC/Industry/IN2000.aspx"),
             ("tpex_bondetf", "https://www.tpex.org.tw/zh-tw/bond/info/statistics-etf.html"), ("tpex_intl", "https://www.tpex.org.tw/zh-tw/bond/info/statistics/intl-bond.html")):
    grab(t, u, keep=3_000_000 if "swagger" in t else 400000)
json.dump(idx, open(os.path.join(OUT, "index.json"), "w"), ensure_ascii=False, indent=1)
print(len(idx), "requests")
