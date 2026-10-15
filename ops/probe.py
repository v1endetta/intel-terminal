import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
r = S.get("https://data.gov.tw/datasets/export/csv", timeout=120)
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
pats = {"retail": r"(批發|零售|餐飲).*(營業額|銷售額)|營業額.*(零售|餐飲)",
        "card": r"信用卡.*(消費|簽帳|類別)|簽帳.*金額",
        "permit": r"(使用執照|建造執照|建照|使照)",
        "dissolve": r"(解散|廢止|歇業).*(登記|公司|商業)|(公司|商業).*(解散|歇業|廢止)",
        "car": r"(新領牌|領牌|新車).*(數|照)|汽車.*新領",
        "birth": r"(出生|結婚).*(按|區域|縣市|鄉鎮)",
        "app": r"App|應用程式"}
for k, p in pats.items():
    hits = [x for x in rows[1:] if re.search(p, x[1])]
    out[k] = [[x[0], x[1][:44], x[5][:12], x[11][:12], x[12][:8], x[18][:10] if len(x) > 18 else "", x[19][:10] if len(x) > 19 else "", x[6][:110], x[10][:120]] for x in hits][:18]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
