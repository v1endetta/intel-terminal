# 一次性實測（第二輪）：Congress.gov 用更新日期區間抓最近的法案，看涉台法案抓不抓得到
import json, os, re, time, traceback
import requests
CK = os.environ.get("CONGRESS_API_KEY", "").strip()
OUT = {}
S = requests.Session()
def C(path, **p):
    r = S.get("https://api.congress.gov/v3/" + path, params={"api_key": CK, "format": "json", **p}, timeout=40); return r
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
KW = re.compile(r"Taiwan|semiconductor|chip|CHIPS|export control|tariff|Mexico|USMCA|China|PRC", re.I)
for days in (7, 30, 90):
    k = f"d{days}"
    try:
        bills, off = [], 0
        while off < 3000:
            r = C("bill", limit=250, offset=off, sort="updateDate desc", fromDateTime=(now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z"), toDateTime=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            j = r.json(); bs = j.get("bills") or []; bills += bs
            if len(bs) < 250: break
            off += 250
        OUT[k] = {"st": r.status_code, "n": len(bills), "total": (j.get("pagination") or {}).get("count"), "span": [bills[-1].get("updateDate"), bills[0].get("updateDate")] if bills else None,
                  "taiwan": [(b.get("congress"), b.get("type"), b.get("number"), b.get("title")[:140], (b.get("latestAction") or {}).get("actionDate"), (b.get("latestAction") or {}).get("text", "")[:100]) for b in bills if re.search("Taiwan", b.get("title") or "", re.I)],
                  "other_kw": [(b.get("type"), b.get("number"), b.get("title")[:120]) for b in bills if KW.search(b.get("title") or "") and not re.search("Taiwan", b.get("title") or "", re.I)][:15]}
    except Exception:
        OUT[k] = {"FAIL": traceback.format_exc()[-600:]}
# 主題標籤：涉台但標題沒寫 Taiwan 的（例如國防授權法）
try:
    r = C("bill/119/s/3018/subjects"); OUT["subjects_s3018"] = (r.json().get("subjects") or {}).get("legislativeSubjects", [])[:15]
except Exception:
    OUT["subjects_s3018"] = traceback.format_exc()[-300:]
s = json.dumps(OUT, ensure_ascii=False, indent=1)
if CK: s = s.replace(CK, "***")
open("probe.json", "w").write(s); print("done")
