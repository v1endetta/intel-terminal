"""暫時探測：台灣保險統計來源（壽險公會、產險公會、保發中心、保險局、保險業公開資訊觀測站、中再保、證交所月營收）。用完刪掉。
只讀公開頁面，低量（每頁間隔 1 秒），不登入、不繞過驗證；被擋就記下狀態。"""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
KW = re.compile(r"統計|業績|保費|簽單|新契約|再保|資訊公開|公開資訊|業務|險種|年報|財務|Fact|月報")
DOC = re.compile(r"\.(pdf|xlsx?|csv|ods|zip)(\?|$)", re.I)
SEEDS = {
    "liaroc": ["https://www.lia-roc.org.tw/", "https://www.lia-roc.org.tw/?catg_id=10", "https://www.lia-roc.org.tw/?catg_id=11", "https://www.lia-roc.org.tw/?catg_id=13"],
    "nlia": ["https://www.nlia.org.tw/", "https://www.nlia.org.tw/category/information_area/factbook_line/"],
    "tii": ["https://www.tii.org.tw/"],
    "ib": ["https://www.ib.gov.tw/"],
    "insinfo": ["https://ins-info.ib.gov.tw/"],
    "centralre": ["https://www.centralre.com/"],
    "datagov": ["https://data.gov.tw/dataset/14507", "https://data.gov.tw/dataset/14501", "https://data.gov.tw/dataset/172653"],
}
log = {}


def fetch(url):
    for how in ("req", "cffi"):
        try:
            if how == "req":
                r = S.get(url, timeout=30)
            else:
                from curl_cffi import requests as cr
                r = cr.get(url, timeout=30, impersonate="chrome")
            return r.status_code, r.headers.get("content-type", ""), r.content, how
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:120]}"
    return None, "", b"", err


def links(html, base):
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        txt = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()[:80]
        out.append((txt, urljoin(base, m.group(1).strip())))
    return out


for site, seeds in SEEDS.items():
    host = {urlparse(u).netloc for u in seeds}
    seen, queue, pages, docs = set(), [(u, 0) for u in seeds], [], []
    while queue and len(pages) < 45:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        st, ct, body, how = fetch(url); time.sleep(1)
        rec = {"url": url, "status": st, "ct": ct[:40], "len": len(body), "via": how}
        if DOC.search(url) or "pdf" in ct or "spreadsheet" in ct or "excel" in ct:
            if st == 200 and len(docs) < 25 and len(body) < 15e6:
                fn = f"{site}_{len(docs):02d}_" + re.sub(r"[^\w.]+", "_", urlparse(url).path.split("/")[-1])[-60:]
                (OUT / fn).write_bytes(body); rec["saved"] = fn; docs.append(url)
            pages.append(rec); continue
        html = body.decode("utf-8", "replace")
        t = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        rec["title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:100] if t else ""
        rec["challenge"] = bool(re.search(r"Just a moment|cf-challenge|Attention Required|請稍候", html[:5000]))
        hits = [(x, h) for x, h in links(html, url) if KW.search(x) or KW.search(h)]
        rec["hits"] = hits[:120]
        if depth == 0:
            (OUT / f"{site}_{len(pages):02d}.html").write_text(html[:400000], encoding="utf-8")
        pages.append(rec)
        for x, h in hits:
            if urlparse(h).netloc in host and h not in seen and depth < 2:
                if DOC.search(h):
                    if KW.search(x) and len(docs) < 25:
                        queue.insert(0, (h, depth + 1))
                else:
                    queue.append((h, depth + 1))
    log[site] = pages

# 證交所月營收（上市公司），取中再保 2851
try:
    rows = S.get("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", timeout=30).json()
    log["twse_2851"] = [r for r in rows if str(r.get("公司代號")) == "2851"]
except Exception as e:  # noqa: BLE001
    log["twse_2851"] = f"ERR {e}"

(OUT / "index.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (len(v) if isinstance(v, list) else v) for k, v in log.items()})
