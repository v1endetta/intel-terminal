"""暫時探測：消費者「買」的商品層級來源（App Store 台灣、博客來、PChome、momo）。不用任何金鑰，用完刪掉。"""
import json
import re
import sys
import time
from pathlib import Path

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
rep = {}


def hit(name, url, keep=0, want=(), **kw):
    try:
        r = S.get(url, timeout=30, **kw)
        txt = r.text
        info = {"url": url, "status": r.status_code, "final": str(r.url), "len": len(txt), "ctype": r.headers.get("content-type", "")[:40],
                "server": r.headers.get("server", "")[:20], "cf": r.headers.get("cf-mitigated", ""),
                "challenge": bool(re.search(r"Just a moment|cf-chl|captcha|Attention Required|Access Denied|驗證", txt[:6000], re.I)),
                "has": {w: (w in txt) for w in want}}
        if keep:
            (OUT / f"{name}.txt").write_text(txt[:keep], encoding="utf-8")
        rep[name] = info
        print(name, json.dumps(info, ensure_ascii=False), flush=True)
        return r
    except Exception as e:  # noqa: BLE001
        rep[name] = {"url": url, "err": f"{type(e).__name__}: {str(e)[:160]}"}
        print(name, rep[name], flush=True)
        return None
    finally:
        time.sleep(2)


# ---- App Store 台灣（Apple 官方榜單）----
hit("as_free", "https://rss.marketingtools.apple.com/api/v2/tw/apps/top-free/25/apps.json", keep=30000, want=("results",))
hit("as_paid", "https://rss.marketingtools.apple.com/api/v2/tw/apps/top-paid/25/apps.json", keep=8000, want=("results",))
hit("as_gross", "https://itunes.apple.com/tw/rss/topgrossingapplications/limit=25/json", keep=30000, want=("entry", "category"))

# ---- 博客來 ----
hit("bk_robots", "https://www.books.com.tw/robots.txt", keep=6000)
hit("bk_top", "https://www.books.com.tw/web/sys_saletopb/books/", keep=250000, want=("TOP", "暢銷", "price"))
hit("bk_top7", "https://www.books.com.tw/web/sys_saletopb/books/?attribute=7", keep=0, want=("暢銷",))

# ---- PChome ----
hit("pc_robots", "https://24h.pchome.com.tw/robots.txt", keep=6000)
hit("pc_home", "https://24h.pchome.com.tw/", keep=0, want=("熱銷", "24h"))
hit("pc_search", "https://ecshweb.pchome.com.tw/search/v3.3/all/results", keep=20000, want=("prods",),
    params={"q": "保溫杯", "page": 1, "sort": "sale/dc"})

# ---- momo ----
hit("mo_robots", "https://www.momoshop.com.tw/robots.txt", keep=6000)
hit("mo_home", "https://www.momoshop.com.tw/main/Main.jsp", keep=0, want=("熱銷", "momo"))
hit("mo_rank", "https://m.momoshop.com.tw/rankingAll.momo", keep=60000, want=("排行", "熱銷"))

(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
