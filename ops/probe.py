"""臨時探測：三份資料的完整欄位、檔案大小、營業項目資料集的下載方式。跑完就刪。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {}
def meta(ds):
    res = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=30).json().get("result") or {}
    return res, [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceDescription")) for d in (res.get("distribution") or [])]
for ds in ["77144", "168209", "168341", "39283", "41448"]:
    try:
        res, dist = meta(ds)
        rec = {"title": res.get("title"), "dist": dist[:4]}
        u = next((d[1] for d in dist if d[0] and "CSV" in d[0].upper()), dist[0][1] if dist else None)
        if u:
            r = requests.get(u, headers=H, timeout=120)
            t = r.content.decode("utf-8-sig", "replace")
            lines = t.splitlines()
            rec.update({"url": u, "code": r.status_code, "bytes": len(r.content), "n_lines": len(lines), "header": lines[0][:3000] if lines else "",
                        "row1": lines[1][:600] if len(lines) > 1 else "", "row2": lines[2][:600] if len(lines) > 2 else "", "last": lines[-1][:300] if lines else ""})
            if ds == "77144" or ds == "168209":
                rec["months"] = sorted(set(l.split(",")[0] for l in lines[1:2000]))[:20]
        out[ds] = rec
    except Exception as e:
        out[ds] = {"err": str(e)[:200]}
# 營業項目別資料集：找出整個系列的 dataset（搜尋 data.gov.tw）
for q in ["公司登記(依營業項目別)", "公司登記依營業項目別"]:
    for u in [f"https://data.gov.tw/api/v2/rest/dataset?q={q}&limit=50", f"https://data.gov.tw/api/front/dataset/list?q={q}&size=50"]:
        try:
            r = requests.get(u, headers=H, timeout=30)
            out["search " + u] = {"code": r.status_code, "head": r.text[:1500]}
        except Exception as e:
            out["search " + u] = {"err": str(e)[:150]}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
