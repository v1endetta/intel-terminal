import os, json, re, io, csv, requests
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; github.com/v1endetta/intel-terminal)"}
rep = {}
r = requests.get("https://data.gov.tw/datasets/export/csv", headers=H, timeout=180)
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "ignore"))))
hdr = rows[0]; idx = {h: i for i, h in enumerate(hdr)}
def col(r, nm): return r[idx[nm]] if idx[nm] < len(r) else ""
KW = {
 "捷運": r"捷運.*(OD|分時|各站|進出站|運量)",
 "1999": r"1999.*(案件|陳情|統計)|市民當家熱線",
 "結婚": r"結婚|離婚|出生數|出生人數|出生登記",
 "寵物": r"寵物.*(統計|數量|登記數)|犬貓.*(統計|數)",
 "用電": r"用電量|售電量",
 "減班": r"減班|無薪假|減少工時",
 "簽帳": r"簽帳|刷卡金額|信用卡.*(消費|業務統計)",
 "消保": r"消費者保護|消費爭議|消費糾紛|申訴.*統計",
 "建物": r"建物.*移轉|買賣移轉|建築物.*(執照|核發)|建造執照.*統計|使用執照.*統計",
 "出國": r"出國.*(目的地|人次|統計)|國人出國",
 "人口": r"人口.*(遷入|遷出|移動)",
 "營業登記": r"營業(登記|項目).*(新設|統計)|新設立.*(公司|商業)",
 "電子發票": r"電子發票.*(行業|消費|統計)",
 "旅宿": r"旅館業.*(營運|住用)|民宿.*(營運|住用)",
 "景氣": r"景氣(指標|對策)|領先指標|同時指標",
}
for k, pat in KW.items():
    hits = []
    for r in rows[1:]:
        title = col(r, "資料集名稱")
        if re.search(pat, title):
            hits.append({"id": col(r, "資料集識別碼"), "title": title[:60], "org": col(r, "提供機關")[:20], "freq": col(r, "更新頻率")[:10],
                         "fmt": col(r, "檔案格式")[:20], "lic": col(r, "授權方式")[:10], "url": col(r, "資料下載網址")[:220], "upd": col(r, "詮釋資料更新時間")[:10],
                         "desc": col(r, "資料集描述")[:120], "fields": col(r, "主要欄位說明")[:200]})
    hits.sort(key=lambda h: h["upd"], reverse=True)
    rep["kw_" + k] = hits[:15]
# fetch sample of key datasets found earlier
want = {"6053": None, "161861": None, "40331": None, "8938": None, "16461": None, "7296": None, "7536": None, "14584": None, "14593": None, "6845": None, "6099": None}
for r in rows[1:]:
    i = col(r, "資料集識別碼")
    if i in want:
        want[i] = {"title": col(r, "資料集名稱"), "url": col(r, "資料下載網址"), "fields": col(r, "主要欄位說明")[:400], "desc": col(r, "資料集描述")[:200], "freq": col(r, "更新頻率"), "lic": col(r, "授權方式")}
rep["want"] = want
for i, w in want.items():
    if not w: continue
    u = w["url"].split(";")[0]
    try:
        x = requests.get(u, headers=H, timeout=90)
        w["sample_status"] = x.status_code; w["sample_len"] = len(x.content)
        w["sample"] = x.content[:900].decode("utf-8-sig", "ignore") if x.ok else None
    except Exception as e:
        w["sample_err"] = repr(e)[:200]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
