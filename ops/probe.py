"""臨時探測：盤點候選開放資料集（名稱、更新頻率、最後更新、欄位樣本）。跑完就刪。"""
import json, requests
from concurrent.futures import ThreadPoolExecutor
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
IDS = "124037 152983 30201 30202 113674 104388 103825 58683 13488 140144 20928 138739 138782 39291 39334 39283 39284 168341 39281 39282 39280 116069 133354 124152 149422 25961 33369 33357 121581 41448 143171 67730 132262 168350 168209 153896 168351 77144 177695 104872 106777 168148 167574 132486 132485 136714 138338".split()
def one(ds):
    try:
        res = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=30).json().get("result") or {}
        dist = [(d.get("resourceFormat"), d.get("resourceDownloadUrl")) for d in (res.get("distribution") or [])][:3]
        rec = {"title": res.get("title"), "org": res.get("publisher") or res.get("agency") or res.get("organization"), "freq": res.get("updateFrequency"),
               "mod": res.get("modifiedDate") or res.get("metadataModifiedDate") or res.get("updateDate"), "desc": (res.get("description") or res.get("notes") or "")[:200],
               "fields": (res.get("fieldDescription") or res.get("fields") or "")[:300] if isinstance(res.get("fieldDescription") or res.get("fields") or "", str) else str(res.get("fieldDescription"))[:300], "dist": dist}
        if dist and dist[0][1]:
            try:
                r = requests.get(dist[0][1], headers=H, timeout=40, stream=True)
                b = r.raw.read(1500, decode_content=True)
                rec["sample"] = {"code": r.status_code, "head": b.decode("utf-8-sig", "replace")[:600]}
            except Exception as e:
                rec["sample"] = {"err": str(e)[:120]}
        return ds, rec
    except Exception as e:
        return ds, {"err": str(e)[:150]}
out = {}
with ThreadPoolExecutor(8) as ex:
    for ds, rec in ex.map(one, IDS):
        out[ds] = rec
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
