import os, json, re, io, csv, requests, time
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; github.com/v1endetta/intel-terminal)"}
rep = {}
def t(name, url, n=800, **kw):
    try:
        r = requests.get(url, headers=H, timeout=60, **kw)
        rep[name] = {"status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "head": r.text[:n]}
        return r
    except Exception as e:
        rep[name] = {"err": repr(e)[:200]}
# 1) data.gov.tw catalog export
cat = None
for u in ("https://data.gov.tw/datasets/export/csv", "https://data.gov.tw/api/front/dataset/export?format=csv", "https://data.gov.tw/datasets/export/json"):
    r = t("cat_" + u.rsplit("/", 2)[-2] + u.rsplit("/", 1)[-1][:12], u, n=300)
    if r is not None and r.ok and len(r.content) > 100000:
        cat = r; rep["cat_url"] = u; break
KW = {
 "寵物登記": r"寵物登記|犬貓.*登記|登記.*犬貓",
 "結婚出生": r"結婚(對數|登記)|出生(數|登記|人數)|嬰兒出生",
 "捷運進出": r"捷運.*(進出|運量|旅運)",
 "1999陳情": r"1999|市民熱線|陳情案件",
 "消費申訴": r"消費(爭議|申訴)|申訴案件",
 "ISBN新書": r"ISBN|新書|出版品",
 "補習班": r"補習班|短期補習",
 "遊客旅宿": r"遊客人數|觀光遊樂|旅館.*住用|住房率|旅宿",
 "行業用電": r"(行業|業別).*用電|用電量.*(行業|業別)",
 "類流感": r"類流感|流感.*門急診",
 "出入境": r"出國人數|來臺旅客|來台旅客|入境旅客",
 "進口統計": r"進口(貿易|統計|值)|海關進出口|進出口貿易",
 "信用卡": r"信用卡",
 "減班休息": r"減班休息|無薪假",
 "外銷訂單": r"外銷訂單",
 "毛豬雞蛋": r"毛豬|雞蛋|蛋價|畜產.*行情",
 "建物移轉": r"建物.*(移轉|買賣)|買賣移轉",
 "建照使照": r"建造執照|使用執照|建照|使照",
 "房貸": r"購屋貸款|房貸|新承做",
 "營業額": r"銷售額|營業額.*行業|營利事業.*銷售",
 "領先指標": r"領先指標|景氣指標",
 "食品業者登錄": r"食品業者登錄|非登不可",
 "化粧品登錄": r"化粧品.*(登錄|產品)",
}
if cat is not None:
    txt = cat.content.decode("utf-8-sig", "ignore")
    rows = list(csv.reader(io.StringIO(txt)))
    hdr = rows[0]; rep["cat_hdr"] = hdr; rep["cat_n"] = len(rows)
    idx = {h: i for i, h in enumerate(hdr)}
    def col(r, *names):
        for nm in names:
            if nm in idx and idx[nm] < len(r): return r[idx[nm]]
        return ""
    for k, pat in KW.items():
        hits = []
        for r in rows[1:]:
            title = col(r, "資料集名稱")
            if re.search(pat, title):
                hits.append({"id": col(r, "資料集識別碼"), "title": title[:60], "org": col(r, "提供機關")[:20], "freq": col(r, "更新頻率")[:16],
                             "fmt": col(r, "檔案格式")[:30], "lic": col(r, "授權方式")[:20], "url": col(r, "資料下載網址")[:200], "upd": col(r, "詮釋資料更新時間")[:10]})
        hits.sort(key=lambda h: h["upd"], reverse=True)
        rep["kw_" + k] = hits[:12]
# 2) non-gov APIs
t("wiki_pv", "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/zh.wikipedia/all-access/user/%E5%AF%B5%E7%89%A9/monthly/20230101/20260930", n=300)
t("wiki_ll", "https://zh.wikipedia.org/w/api.php?action=query&titles=%E5%AF%B5%E7%89%A9&prop=langlinks&lllang=en&format=json&redirects=1", n=300)
t("arxiv", "http://export.arxiv.org/api/query?search_query=all:%22agentic%22&max_results=1", n=300)
t("openalex", "https://api.openalex.org/works?filter=title_and_abstract.search:agentic,from_publication_date:2026-01-01&group_by=publication_year", n=300)
t("pypistats", "https://pypistats.org/api/packages/langchain/recent", n=300)
t("npm", "https://api.npmjs.org/downloads/point/last-month/react", n=300)
t("steam", "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=730", n=300)
t("cdc", "https://od.cdc.gov.tw/eic/NHI_Influenza_like_illness.csv", n=400)
t("fao", "https://www.fao.org/worldfoodsituation/foodpricesindex/en/", n=200)
t("estat", "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList?searchWord=家計調査", n=300)
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
