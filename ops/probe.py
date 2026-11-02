"""暫時探測：勞動部月報 6-1 有沒有 xls、主計總處薪資調查的檔案清單。用完刪掉。"""
import json, sys, re
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0", "Accept-Language": "zh-TW,zh;q=0.9"})
rep = {}
def hit(name, url):
    try:
        r = S.get(url, timeout=60)
        rep[name] = {"status": r.status_code, "ctype": r.headers.get("content-type", "")[:50], "len": len(r.content), "server": r.headers.get("server", "")[:20]}
        if "html" in rep[name]["ctype"]:
            t = r.text
            rep[name]["title"] = (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:80]
            rep[name]["links"] = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|ods|csv|pdf))"', t, re.I)))[:40]
            rep[name]["links2"] = sorted(set(re.findall(r'href="([^"]*(?:Download|download|dl\.asp|File)[^"]*)"', t)))[:30]
            (OUT / f"{name}.html").write_text(t[:200000], encoding="utf-8")
        else:
            (OUT / f"{name}.bin").write_bytes(r.content[:3_000_000])
    except Exception as e:
        rep[name] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
    print(name, json.dumps(rep[name], ensure_ascii=False)[:600], flush=True)
for ext in ("xls", "xlsx", "ods", "csv"):
    hit(f"mol26010_{ext}", f"https://statdb.mol.gov.tw/html/mon/26010.{ext}")
hit("mol26010_pdf", "https://statdb.mol.gov.tw/html/mon/26010.pdf")
hit("mol_mon_index", "https://statdb.mol.gov.tw/statis/jspProxy.aspx?sys=100&kind=10&type=1&funid=q13011")
hit("dgbas_2712", "https://www.stat.gov.tw/cl.aspx?n=2712")
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
