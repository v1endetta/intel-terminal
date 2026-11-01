"""暫時探測：104 有沒有回真實總數的端點。用完刪掉。"""
import json, sys, re
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
H = {"Referer": "https://www.104.com.tw/jobs/search/", "Accept": "application/json"}
rep = {}
def t(name, url, params=None, kind="json"):
    try:
        r = S.get(url, params=params, headers=H, timeout=30)
        txt = r.text
        info = {"status": r.status_code, "len": len(txt), "ctype": r.headers.get("content-type", "")[:40]}
        try:
            j = r.json()
            def walk(o, p=""):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if re.search(r"total|count|num", k, re.I) and not isinstance(v, (dict, list)):
                            info.setdefault("nums", {})[p + k] = v
                        if isinstance(v, (dict,)):
                            walk(v, p + k + ".")
            walk(j); info["keys"] = list(j)[:10] if isinstance(j, dict) else type(j).__name__
        except Exception:
            info["nums_html"] = re.findall(r"(?:共|總共|totalCount\W+|jobCount\W+)\s*([\d,]{4,})", txt)[:8]
            (OUT / f"{name}.txt").write_text(txt[:30000], encoding="utf-8")
        rep[name] = info
    except Exception as e:
        rep[name] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:500], flush=True)
t("list_all", "https://www.104.com.tw/jobs/search/list", {"ro": 0, "page": 1, "mode": "s", "jobsource": "index_s"})
t("list_cat", "https://www.104.com.tw/jobs/search/list", {"ro": 0, "page": 1, "mode": "s", "jobcat": "2007000000"})
t("api_count", "https://www.104.com.tw/jobs/search/api/jobs/count", {"jobcat": "2007000000"})
t("api_jobs_area", "https://www.104.com.tw/jobs/search/api/jobs", {"page": 1, "pagesize": 30, "area": "6001001000"})
t("main_page", "https://www.104.com.tw/jobs/main/", None)
t("search_html", "https://www.104.com.tw/jobs/search/", {"jobcat": "2007000000"})
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
