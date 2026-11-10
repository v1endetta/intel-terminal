"""暫時探測（第二輪）：保發中心業務統計頁、政府開放資料 API、保險局 PDF、產險公會站內搜尋。用完刪掉。"""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin
import requests

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"})
log = {}
DOC = re.compile(r"\.(pdf|xlsx?|csv|ods|zip|json|xml)(\?|$)", re.I)


def get(url, name=None, **kw):
    try:
        r = S.get(url, timeout=40, **kw)
        rec = {"status": r.status_code, "ct": r.headers.get("content-type", "")[:50], "len": len(r.content)}
        if name and r.status_code == 200 and len(r.content) < 15e6:
            (OUT / name).write_bytes(r.content); rec["saved"] = name
        return r, rec
    except Exception as e:  # noqa: BLE001
        return None, {"err": f"{type(e).__name__}: {str(e)[:150]}"}
    finally:
        time.sleep(1)


# 1. 保發中心：保險財務業務統計各頁，與兩個報表索引（各類別）
tii = ["https://www.tii.org.tw/tii/information/information1/0000%02d.html" % i for i in range(2, 9)]
tii += [f"https://www.tii.org.tw/tii/actuarial/actuarial1/report/index.html?category={c:02d}" for c in (0, 1, 2, 4, 9, 10, 11)]
tii += [f"https://www.tii.org.tw/tii/actuarial/actuarial3/report/index.html?category={c}" for c in (51, 53, 54)]
for i, u in enumerate(tii):
    r, rec = get(u, f"tii_{i:02d}.html")
    if r is not None and r.status_code == 200:
        h = r.content.decode("utf-8", "replace")
        rec["docs"] = [(re.sub(r"<[^>]+>|\s+", " ", t).strip()[:70], urljoin(u, l)) for l, t in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', h, re.S) if DOC.search(l)][:60]
    log[u] = rec
# 每頁第一個文件下載下來看格式（最多 12 個）
n = 0
for u, rec in list(log.items()):
    for t, l in (rec.get("docs") or [])[:1]:
        if n < 12:
            _, log[l] = get(l, f"tiidoc_{n:02d}" + Path(l.split("?")[0]).suffix); n += 1

# 2. 政府資料開放平台 API：保險相關資料集的下載網址與更新頻率
for ds in (14508, 14509, 13517, 14506, 14501, 13519):
    r, rec = get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", f"datagov_{ds}.json")
    log[f"datagov_{ds}"] = rec
    try:
        res = r.json().get("result", {})
        dist = res.get("distribution") or []
        rec["title"] = res.get("title"); rec["freq"] = res.get("updateFrequency") or res.get("accrualPeriodicity")
        rec["dist"] = [(d.get("resourceFormat"), d.get("resourceDownloadUrl") or d.get("downloadURL")) for d in dist][:6]
        for j, (fmt, url) in enumerate(rec["dist"][:2]):
            if url:
                _, log[f"datagov_{ds}_file{j}"] = get(url, f"datagov_{ds}_{j}.{(fmt or 'bin').lower()}")
    except Exception as e:  # noqa: BLE001
        rec["parse_err"] = str(e)[:120]

# 3. 保險局統計 PDF（財產、人身保費收入）
for nm, f in (("ib_prop.pdf", "202506241903060.pdf"), ("ib_life.pdf", "202506241855110.pdf")):
    _, log[nm] = get(f"https://www.ib.gov.tw/uploaddowndoc?file=chdownload/{f}&flag=doc", nm)

# 4. 產險公會：站內搜尋簽單保費
r, rec = get("https://www.nlia.org.tw/?s=%E7%B0%BD%E5%96%AE%E4%BF%9D%E8%B2%BB", "nlia_search.html")
if r is not None:
    h = r.content.decode("utf-8", "replace")
    rec["hits"] = [(re.sub(r"<[^>]+>|\s+", " ", t).strip()[:80], l) for l, t in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', h, re.S) if re.search("保費|業績|統計", t)][:40]
log["nlia_search"] = rec

# 5. 保險業公開資訊觀測站、中再保官網：換 http 再試一次（只看連不連得到）
for u in ("http://ins-info.ib.gov.tw/", "http://www.centralre.com/"):
    _, log[u] = get(u)

(OUT / "index.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(log))
