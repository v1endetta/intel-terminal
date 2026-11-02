"""暫時探測：1111 API 的職類／地區參數、台灣就業通查詢介面能不能分頁。用完刪掉。"""
import json, sys, time
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
API = "https://www.1111.com.tw/api/v1/search/jobs/"
H = {"Referer": "https://www.1111.com.tw/search/job"}
def q(**p):
    j = S.get(API, params={"page": 1, **p}, headers=H, timeout=40).json()
    r = j.get("result") or {}
    return (r.get("pagination") or {}).get("totalCount"), r.get("hits") or []
base, hits = q()
rep["base_total"] = base
rep["hit_sample"] = {k: v for k, v in (hits[0] if hits else {}).items() if not isinstance(v, str) or len(v) < 80}
(OUT / "hits.json").write_text(json.dumps(hits[:5], ensure_ascii=False, indent=1), encoding="utf-8")
# 從第一筆職缺找出像代碼的欄位值，逐一試常見參數名，看總數有沒有變
cands = {}
def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items(): walk(v, p + k + ".")
    elif isinstance(o, list) and o and not isinstance(o[0], (dict, list)):
        cands[p.rstrip(".")] = o[0]
    elif isinstance(o, (int,)) or (isinstance(o, str) and o.isdigit() and 3 <= len(o) <= 12):
        cands[p.rstrip(".")] = o
for h in hits[:1]: walk(h)
rep["code_fields"] = cands
names = ["d0", "c0", "i0", "t0", "ca", "cr", "city", "area", "jobCategory", "category", "industry", "duty", "dutyCategory", "jobs", "occupation", "workCity", "areaId", "categoryId"]
tests = {}
for f, v in list(cands.items())[:10]:
    for nm in names:
        try:
            tot, _ = q(**{nm: v}); time.sleep(0.4)
            if tot is not None and tot != base:
                tests[f"{nm}={v} ({f})"] = tot
        except Exception as e:
            pass
rep["param_hits"] = tests
# 台灣就業通查詢介面
MOL = "https://apiservice.mol.gov.tw/OdService/rest/datastore/A17000000J-030144-VAL"
def mol(**p):
    r = S.get(MOL, params=p, timeout=90); j = r.json()
    res = j.get("result") if isinstance(j, dict) else None
    recs = (res or {}).get("records") if isinstance(res, dict) else (j if isinstance(j, list) else None)
    return {"status": r.status_code, "keys": list(j)[:10] if isinstance(j, dict) else type(j).__name__,
            "result_keys": list(res)[:12] if isinstance(res, dict) else None, "total": (res or {}).get("total") if isinstance(res, dict) else None,
            "n": len(recs) if recs is not None else None, "first_city": (recs[0].get("CITYNAME") if recs and isinstance(recs[0], dict) else None),
            "links": (res or {}).get("_links") if isinstance(res, dict) else None}
for nm, p in [("mol_plain", {}), ("mol_limit", {"limit": 1000}), ("mol_offset", {"limit": 1000, "offset": 5000}), ("mol_top", {"top": 1000, "skip": 5000})]:
    try: rep[nm] = mol(**p)
    except Exception as e: rep[nm] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(nm, rep[nm], flush=True)
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
