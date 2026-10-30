"""暫時探測：嘖嘖（能不能從 GitHub 讀、有哪些欄位）與 Lyst（為什麼一直找不到頁面）。不用任何金鑰，用完刪掉。"""
import gzip
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


def hit(name, url, cffi=False, keep=0, want=()):
    try:
        if cffi:
            from curl_cffi import requests as cr
            r = cr.get(url, impersonate="chrome", timeout=30, headers={"Accept-Language": "zh-TW,zh;q=0.9"})
        else:
            r = S.get(url, timeout=30)
        body = r.content
        try:
            txt = gzip.decompress(body).decode("utf-8", "replace") if url.endswith(".gz") else r.text
        except Exception:  # noqa: BLE001
            txt = r.text
        info = {"url": url, "via": "curl_cffi" if cffi else "requests", "status": r.status_code, "final": str(r.url), "len": len(txt),
                "server": r.headers.get("server", ""), "cf": r.headers.get("cf-mitigated", "") or r.headers.get("cf-ray", "")[:6],
                "challenge": bool(re.search(r"Just a moment|cf-chl|captcha|Attention Required", txt[:5000], re.I)),
                "has": {w: (w in txt) for w in want}}
        if keep:
            (OUT / f"{name}.txt").write_text(txt[:keep], encoding="utf-8")
        rep[name] = info
        print(name, json.dumps(info, ensure_ascii=False), flush=True)
        return txt
    except Exception as e:  # noqa: BLE001
        rep[name] = {"url": url, "err": f"{type(e).__name__}: {str(e)[:160]}"}
        print(name, rep[name], flush=True)
        return ""
    finally:
        time.sleep(3)


# ---- 嘖嘖 ----
home = hit("zz_home", "https://www.zeczec.com/", keep=200000, want=("NT$", "專案", "贊助"))
hit("zz_home_cffi", "https://www.zeczec.com/", cffi=True, want=("NT$",))
hit("zz_robots", "https://www.zeczec.com/robots.txt", keep=4000)
sm = hit("zz_sitemap", "https://sitemaps.zeczec.com/sitemap.xml.gz", keep=20000)
links = sorted(set(re.findall(r'href="(/projects/[A-Za-z0-9_\-]+)"', home)))
rep["zz_project_links"] = links[:40]
for i, p in enumerate(links[:2]):
    hit(f"zz_proj{i}", "https://www.zeczec.com" + p, keep=200000, want=("NT$", "贊助人", "%", "剩餘", "ld+json"))
for name, path in [("zz_cat", "/categories"), ("zz_cat_q", "/categories?type=0"), ("zz_api", "/api/projects")]:
    hit(name, "https://www.zeczec.com" + path, keep=60000, want=("NT$",))

# ---- Lyst ----
for name, path in [("ly_land", "/the-lyst-index/"), ("ly_q326", "/the-lyst-index/Q3-26"), ("ly_q326s", "/the-lyst-index/Q3-26/"),
                   ("ly_q226", "/the-lyst-index/Q2-26")]:
    hit(name, "https://www.lyst.com" + path, keep=120000 if name == "ly_q326s" else 0, want=("Hottest", "hottest", "HOTTEST", "Prada"))
hit("ly_q326_cffi", "https://www.lyst.com/the-lyst-index/Q3-26/", cffi=True, want=("Hottest", "hottest", "Prada"))

(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
