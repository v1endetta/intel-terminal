"""暫時探測：台電行業別售電量 ZIP 內容、勞保資料集的所有資源（有沒有往年）。用完刪掉。"""
import json, sys, csv, io, zipfile
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0", "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
def dec(b):
    for enc in ("utf-8-sig", "cp950"):
        try: return b.decode(enc)
        except UnicodeDecodeError: pass
    return b.decode("utf-8", "replace")
for ds in ["31966", "33369", "33357"]:
    try:
        r = (S.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40).json().get("result") or {})
        rep[ds] = {"title": r.get("title"), "modified": r.get("modifiedDate") or r.get("updated"), "n_dist": len(r.get("distribution") or []),
                   "dist": [{"desc": d.get("resourceDescription"), "fmt": d.get("resourceFormat"), "url": d.get("resourceDownloadUrl")} for d in (r.get("distribution") or [])][:12]}
    except Exception as e:
        rep[ds] = {"err": str(e)[:200]}
# 台電 ZIP
try:
    zu = next(d["url"] for d in rep["31966"]["dist"] if d["fmt"] == "ZIP")
    b = S.get(zu, timeout=180).content
    z = zipfile.ZipFile(io.BytesIO(b)); info = {"bytes": len(b), "files": [(f.filename, f.file_size) for f in z.infolist()][:20]}
    f0 = next(f for f in z.infolist() if f.filename.lower().endswith((".csv", ".txt")))
    rows = list(csv.reader(io.StringIO(dec(z.read(f0)))))
    info["sample_file"] = f0.filename; info["n"] = len(rows); info["head"] = rows[:3]; info["tail"] = rows[-3:]
    info["col0_vals"] = sorted({r[0] for r in rows[1:] if r})[:40]
    info["col1_vals"] = sorted({r[1] for r in rows[1:] if len(r) > 1})[:60]
    rep["taipower_zip"] = info
except Exception as e:
    rep["taipower_zip"] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
