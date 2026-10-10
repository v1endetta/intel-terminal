import os, json, re, io, csv, requests, collections, time
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research; github.com/v1endetta/intel-terminal)"}
rep = {}
# 捷運 OD 檔大小與格式
u = "http://tcgmetro.blob.core.windows.net/stationod/%E8%87%BA%E5%8C%97%E6%8D%B7%E9%81%8B%E6%AF%8F%E6%97%A5%E5%88%86%E6%99%82%E5%90%84%E7%AB%99OD%E6%B5%81%E9%87%8F%E7%B5%B1%E8%A8%88%E8%B3%87%E6%96%99_202608.csv"
try:
    h = requests.head(u, headers=H, timeout=60); rep["od_head"] = {"status": h.status_code, "len": h.headers.get("content-length"), "type": h.headers.get("content-type")}
    r = requests.get(u, headers=H, timeout=60, stream=True); chunk = next(r.iter_content(4000)); r.close()
    rep["od_head_bytes"] = chunk.decode("utf-8-sig", "ignore")[:1500]
    rep["od_head_big5"] = chunk.decode("big5", "ignore")[:600]
except Exception as e:
    rep["od_err"] = repr(e)[:300]
# 果菜：種類代碼
try:
    js = requests.get("https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx", params={"StartDate": "115.10.07", "EndDate": "115.10.08", "Market": "台北一", "$top": "3000"}, headers=H, timeout=90).json()
    rep["farm_keys"] = list(js[0].keys()) if js else None
    rep["farm_kinds"] = collections.Counter(x.get("種類代碼") for x in js).most_common()
    fr = [x for x in js if x.get("種類代碼") not in ("N04",)]
    vol = collections.Counter()
    for x in fr: vol[(x.get("種類代碼"), (x.get("作物名稱") or "").split("-")[0])] += float(x.get("交易量") or 0)
    rep["farm_top_nonveg"] = vol.most_common(40)
except Exception as e:
    rep["farm_err"] = repr(e)[:300]
# 1999 派工
try:
    r = requests.get("https://data.gov.tw/api/v2/rest/dataset/121414", headers=H, timeout=60).json()["result"]
    rep["d1999"] = {"title": r.get("title"), "dist": [(d.get("resourceFormat"), d.get("resourceDownloadUrl")) for d in r.get("distribution", [])][:3], "fields": r.get("fieldDescription") or r.get("columnDescription")}
    u = rep["d1999"]["dist"][0][1]
    x = requests.get(u, headers=H, timeout=90); rep["d1999_sample"] = x.content[:1500].decode("utf-8-sig", "ignore"); rep["d1999_len"] = len(x.content)
except Exception as e:
    rep["d1999_err"] = repr(e)[:300]
# 維基：一個主題多語瀏覽量
def pv(lang, title):
    t = requests.utils.quote(title.replace(" ", "_"), safe="")
    r = requests.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{t}/monthly/20200101/20260930", headers=H, timeout=40)
    return [(i["timestamp"][:6], i["views"]) for i in r.json().get("items", [])] if r.ok else r.status_code
try:
    j = requests.get("https://zh.wikipedia.org/w/api.php", params={"action": "query", "titles": "匹克球", "prop": "langlinks", "lllimit": 50, "format": "json", "redirects": 1}, headers=H, timeout=40).json()
    pg = list(j["query"]["pages"].values())[0]; ll = {x["lang"]: x["*"] for x in pg.get("langlinks", [])}
    rep["wk_title"] = pg.get("title"); rep["wk_ll"] = {k: ll.get(k) for k in ("en", "ja", "ko")}
    rep["wk_zh"] = pv("zh", pg["title"])[-14:]
    if ll.get("en"): rep["wk_en"] = pv("en", ll["en"])[-14:]
    if ll.get("ja"): rep["wk_ja"] = pv("ja", ll["ja"])[-14:]
except Exception as e:
    rep["wk_err"] = repr(e)[:300]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
