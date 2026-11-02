"""暫時探測：克強式勞動溫度計候選資料集（勞保投保、台電用電等）的說明與內容。用完刪掉。"""
import json, sys, re, csv, io
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0", "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
def peek(url):
    r = S.get(url, timeout=120); b = r.content
    for enc in ("utf-8-sig", "cp950"):
        try: txt = b.decode(enc); break
        except UnicodeDecodeError: txt = b.decode("utf-8", "replace")
    if txt.lstrip()[:1] in "[{":
        try:
            j = json.loads(txt); recs = j if isinstance(j, list) else (j.get("result") or {}).get("records") or j.get("data") or j
            if isinstance(recs, list) and recs:
                return {"status": r.status_code, "n": len(recs), "keys": list(recs[0].keys())[:20] if isinstance(recs[0], dict) else None, "first": recs[0], "last": recs[-1]}
        except Exception: pass
    rows = list(csv.reader(io.StringIO(txt)))
    return {"status": r.status_code, "bytes": len(b), "n": len(rows), "head": rows[:2], "tail": rows[-2:]}
for ds in ["33369", "33360", "33357", "31966", "112650", "161209"]:
    try:
        j = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json(); r = j.get("result") or j
        info = {"title": r.get("title"), "freq": r.get("updateFrequency"), "desc": str(r.get("description"))[:160], "dist": []}
        for d in (r.get("distribution") or [])[:3]:
            u = d.get("resourceDownloadUrl"); fmt = d.get("resourceFormat")
            item = {"fmt": fmt, "url": u}
            if u and fmt in ("CSV", "JSON") and not item.get("peek"):
                try: item["peek"] = peek(u)
                except Exception as e: item["peek"] = {"err": f"{type(e).__name__}: {str(e)[:120]}"}
            info["dist"].append(item)
            if item.get("peek") and "err" not in item["peek"]: break
        rep[ds] = info
    except Exception as e:
        rep[ds] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(ds, json.dumps(rep[ds], ensure_ascii=False)[:900], flush=True)
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
