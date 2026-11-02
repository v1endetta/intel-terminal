"""暫時探測（第二輪）：台灣就業通職缺清單內容、1111 API 總數、518/yes123 是否有總數。用完刪掉。"""
import json, sys, re, csv, io
from pathlib import Path
from collections import Counter
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
def t(name, fn):
    try: rep[name] = fn()
    except Exception as e: rep[name] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:700], flush=True)
def mol():
    r = S.get("https://apiservice.mol.gov.tw/OdService/download/A17000000J-030144-MKw", timeout=180)
    b = r.content
    for enc in ("utf-8-sig", "cp950"):
        try: txt = b.decode(enc); break
        except UnicodeDecodeError: continue
    rows = list(csv.reader(io.StringIO(txt)))
    hdr = rows[0] if rows else []
    info = {"status": r.status_code, "bytes": len(b), "rows": len(rows) - 1, "header": hdr[:40], "sample": rows[1][:40] if len(rows) > 1 else None}
    for col in hdr:
        if re.search(r"日期|時間|刊登|更新", col):
            i = hdr.index(col); vals = sorted(x[i] for x in rows[1:] if len(x) > i and x[i])
            info.setdefault("dates", {})[col] = [vals[0] if vals else None, vals[-1] if vals else None]
        if re.search(r"縣市|地區|工作地|行業|職類|產業", col):
            i = hdr.index(col); info.setdefault("top", {})[col] = Counter(x[i][:6] for x in rows[1:] if len(x) > i).most_common(6)
    return info
t("mol_44062", mol)
def j1111(**p):
    r = S.get("https://www.1111.com.tw/api/v1/search/jobs/", params={"page": 1, **p}, timeout=40, headers={"Referer": "https://www.1111.com.tw/search/job"})
    j = r.json(); pg = ((j.get("result") or {}).get("pagination") or {})
    return {"status": r.status_code, "pagination": pg, "n": len((j.get("result") or {}).get("hits") or [])}
t("1111_kw", lambda: j1111(ks="工程師"))
t("1111_all", lambda: j1111(ks=""))
t("1111_area", lambda: j1111(c0="100100"))
t("1111_cat", lambda: j1111(d0="140000"))
def html_tot(url):
    r = S.get(url, timeout=40); t_ = re.sub(r"<[^>]+>", " ", r.text)
    return {"status": r.status_code, "hits": re.findall(r"([\d,]{3,})\s*(?:筆|個職缺|份工作|個工作機會|筆職缺)", t_)[:6], "around": [re.sub(r"\s+", " ", t_[max(0, m.start() - 30):m.end() + 30]) for m in re.finditer(r"[共計]\s*[\d,]{3,}", t_)][:4]}
t("518_list", lambda: html_tot("https://www.518.com.tw/job-index-P-1.html"))
t("yes123_list", lambda: html_tot("https://www.yes123.com.tw/wk_index/joblist.asp?search_type=job"))
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
