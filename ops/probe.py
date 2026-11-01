"""暫時探測：104 總數欄位、台北房價 CSV 格式、經濟部統計處是否擋 GitHub。用完刪掉。"""
import json, sys, re
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
def t(name, fn):
    try: rep[name] = fn()
    except Exception as e: rep[name] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:600], flush=True)
H104 = {"Referer": "https://www.104.com.tw/jobs/search/", "Accept": "application/json"}
def j104(**p):
    r = S.get("https://www.104.com.tw/jobs/search/api/jobs", params={"page": 1, "pagesize": 30, **p}, headers=H104, timeout=30)
    j = r.json(); md = j.get("metadata") or {}
    return {"status": r.status_code, "metadata": md, "n_data": len(j.get("data") or []), "top_keys": list(j)[:10]}
t("104_all", j104)
t("104_cat", lambda: j104(jobcat="2007000000"))
t("104_page34", lambda: j104(page=34))
def taipei():
    r = S.get("https://data.taipei/api/dataset/ce4ea2c6-6334-44f8-945a-5705492b187d/resource/02c7bb70-2113-4daf-81d3-5c14b9ae26df/download", timeout=60)
    txt = r.content.decode("utf-8-sig", "replace")
    lines = txt.splitlines()
    (OUT / "taipei.csv").write_text("\n".join(lines[:40]), encoding="utf-8")
    return {"status": r.status_code, "ctype": r.headers.get("content-type"), "len": len(txt), "n": len(lines), "head": lines[:6], "has_全市": sum(1 for l in lines if "全市" in l)}
t("taipei", taipei)
for nm, u in [("moea_orders", "https://service.moea.gov.tw/EE520/opendata/b.csv"),
              ("moea_retail", "https://service.moea.gov.tw/EE520/opendata/%E7%B6%93%E6%BF%9F%E9%83%A8%E7%B5%B1%E8%A8%88%E8%99%95_%E6%89%B9%E7%99%BC%E3%80%81%E9%9B%B6%E5%94%AE%E5%8F%8A%E9%A4%90%E9%A3%B2%E6%A5%AD%E7%87%9F%E6%A5%AD%E9%A1%8D%E6%8C%87%E6%95%B8.csv")]:
    t(nm, lambda u=u: (lambda r: {"status": r.status_code, "len": len(r.content), "server": r.headers.get("server")})(S.get(u, timeout=60)))
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
