"""暫時探測：104 的替代來源（政府職缺開放資料、其他求職網）能不能從 GitHub 讀、有沒有總數。用完刪掉。"""
import json, sys, re
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
NUM = re.compile(r"(?:共|總共|找到|有)\s*([\d,]{3,})\s*(?:筆|個|份|則)|\"(?:total|totalCount|total_count|count|jobCount)\"\s*:\s*(\d{3,})")
def t(name, url, params=None, headers=None):
    try:
        r = S.get(url, params=params, headers=headers or {}, timeout=40)
        txt = r.text
        info = {"status": r.status_code, "len": len(txt), "ctype": r.headers.get("content-type", "")[:40], "server": r.headers.get("server", "")[:20],
                "challenge": bool(re.search(r"Just a moment|cf-chl|captcha|Access Denied", txt[:6000], re.I)),
                "nums": [a or b for a, b in NUM.findall(txt)][:8], "title": (re.search(r"<title>(.*?)</title>", txt, re.S) or [None, ""])[1].strip()[:80]}
        (OUT / f"{name}.txt").write_text(txt[:40000], encoding="utf-8")
        rep[name] = info
    except Exception as e:
        rep[name] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:400], flush=True)
for ds in ("44062", "146545", "146546"):
    t("gov_" + ds, f"https://data.gov.tw/api/v2/rest/dataset/{ds}")
t("p1111", "https://www.1111.com.tw/search/job")
t("p1111_api", "https://www.1111.com.tw/api/v1/search/jobs/", {"page": 1})
t("p518", "https://www.518.com.tw/job-index.html")
t("yes123", "https://www.yes123.com.tw/wk_index/joblist.asp")
t("cake", "https://www.cake.me/jobs", {"location_list[0]": "Taiwan"})
t("yourator", "https://www.yourator.co/api/v4/jobs", {"page": 1})
t("taiwanjobs", "https://job.taiwanjobs.gov.tw/Internet/Index/job_search_list.aspx")
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
