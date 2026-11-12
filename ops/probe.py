"""暫時探測（2026-11-13，Vin 核准）：保險預測指標的資料來源讀不讀得到。只存回應、不動正式資料。用完刪掉。"""
import json, os, re, sys, time, urllib.parse
import requests

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"}
idx = []


def grab(tag, url, binary=False, keep=400000):
    rec = {"tag": tag, "url": url}
    try:
        r = requests.get(url, headers=UA, timeout=40)
        rec.update(status=r.status_code, len=len(r.content), ctype=r.headers.get("content-type", ""))
        ext = "bin" if binary else ("json" if "json" in rec["ctype"] else ("csv" if "csv" in rec["ctype"] else "html"))
        m = re.search(r"\.(xlsx?|pdf|csv|ods)(?:$|\?)", url)
        if m:
            ext = m.group(1)
        fn = f"{tag}.{ext}"
        open(os.path.join(OUT, fn), "wb").write(r.content[:keep] if ext in ("html", "json", "csv") else r.content[:6_000_000])
        rec["file"] = fn
        return r
    except Exception as e:  # noqa: BLE001
        rec["err"] = repr(e)[:200]
        return None
    finally:
        idx.append(rec)
        time.sleep(1.2)


# 第二輪：保發中心開放資料各表（找月資料：資產負債、損益、給付／解約、產險保費）
API = "https://openapi.tii.org.tw/TIIOPENDATA/API/CSV_EXPORT?TableID="
ids = ["I%02d" % n for n in range(1, 46)] + ["I13", "I14", "I15_1", "I15_2", "I15_3", "I16", "I161", "I162", "I17", "I171", "I172", "I31", "A01", "A02", "K01", "K02", "K03"]
for t in dict.fromkeys(ids):
    grab("tii_" + t, API + t, keep=60000)
for t, u in (("tpex_iss10", "https://www.tpex.org.tw/openapi/v1/bond_ISSBD10_data"), ("tpex_iss11", "https://www.tpex.org.tw/openapi/v1/bond_ISSBD11_data"),
             ("tpex_intl_org", "https://www.tpex.org.tw/openapi/v1/tpex_international_bond_issue_org"),
             ("sitca_2105", "https://www.sitca.org.tw/ROC/Industry/IN2105.aspx"), ("sitca_2106", "https://www.sitca.org.tw/ROC/Industry/IN2106.aspx"),
             ("sitca_2201", "https://www.sitca.org.tw/ROC/Industry/IN2201.aspx"), ("sitca_2213", "https://www.sitca.org.tw/ROC/Industry/IN2213.aspx"),
             ("sitca_menu", "https://www.sitca.org.tw/ROC/Industry/IN2001.aspx"),
             ("fsc_kw", "https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_list.jsp&keyword=" + urllib.parse.quote("保險業損益")),
             ("ib_kw", "https://www.ib.gov.tw/ch/home.jsp?id=239&parentpath=0,2,238&mcustomize=news_list.jsp&keyword=" + urllib.parse.quote("損益")),
             ("ib_p2", "https://www.ib.gov.tw/ch/home.jsp?id=239&parentpath=0,2,238&page=2&pagesize=50"), ("ib_p50", "https://www.ib.gov.tw/ch/home.jsp?id=239&parentpath=0,2,238&pagesize=100")):
    grab(t, u, keep=300000)
json.dump(idx, open(os.path.join(OUT, "index.json"), "w"), ensure_ascii=False, indent=1)
print(len(idx), "requests")
