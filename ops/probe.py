"""暫時探測：1111 用關鍵字或中文地名篩選。用完刪掉。"""
import json, sys, time
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0", "Accept-Language": "zh-TW,zh;q=0.9"})
API = "https://www.1111.com.tw/api/v1/search/jobs/"
H = {"Referer": "https://www.1111.com.tw/search/job"}
def tot(**p):
    try:
        rr = S.get(API, params={"page": 1, **p}, headers=H, timeout=40); j = rr.json()
    except Exception as e:
        return f"ERR {rr.status_code if 'rr' in dir() else ''} {type(e).__name__}"
    r = j.get("result") or {}
    hs = r.get("hits") or []
    return (r.get("pagination") or {}).get("totalCount"), [h.get("title", "")[:20] for h in hs[:3]], [((h.get("workCity") or {}).get("name") if isinstance(h.get("workCity"), dict) else h.get("workCity")) for h in hs[:3]]
rep = {"base": tot()}
for nm in ["ks", "keyword", "kw", "q", "key", "keyWord", "searchKeyword", "query", "word", "k", "kws"]:
    rep["kw:" + nm] = tot(**{nm: "護理師"}); time.sleep(1.2)
for nm in ["city", "area", "c0", "workCity", "cityName", "location", "region", "addr"]:
    rep["city:" + nm] = tot(**{nm: "台北市"}); time.sleep(1.2)
for nm in ["workCity", "c0", "city", "area", "cityId", "workCityId", "w0"]:
    rep["cid:" + nm] = tot(**{nm: "100100"}); time.sleep(1.2)
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
