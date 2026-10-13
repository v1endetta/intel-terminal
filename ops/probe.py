"""臨時探測（第四輪）：觀光遊憩據點、住用率、主計總處 SDMX 時間格式。跑完就刪。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {"ds": {}, "sdmx": {}}
def get(u, n=700):
    try:
        r = requests.get(u, headers=H, timeout=40)
        return {"code": r.status_code, "len": len(r.content), "head": r.content[:n].decode("utf-8", "replace")}
    except Exception as e:
        return {"err": str(e)[:120]}
for ds in ["157193", "157197", "157200", "157202", "157204", "157205", "157206", "135460"]:
    try:
        res = requests.get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", headers=H, timeout=30).json().get("result") or {}
        rec = {"title": res.get("title"), "org": res.get("publisher") or res.get("agency"), "freq": res.get("updateFrequency"), "modified": res.get("modifiedDate") or res.get("metadataModifiedDate"),
               "dist": [(d.get("resourceFormat"), d.get("resourceDownloadUrl"), d.get("resourceDescription")) for d in (res.get("distribution") or [])][:3]}
        rec["sample"] = [get(d[1]) for d in rec["dist"][:1] if d[1]]
        out["ds"][ds] = rec
    except Exception as e:
        out["ds"][ds] = {"err": str(e)[:150]}
B = "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sdmx/A030101015/"
for name, q in [("all", "all"), ("t1", "1..M&startTime=2025-01&endTime=2026-12"), ("t2", "1.1.M&startTime=2025-01&endTime=2026-12"), ("t3", "1..M&startTime=2025-M01&endTime=2026-M12"),
                ("t4", "1.1+2+3+4.M&startTime=2025-01&endTime=2026-12"), ("t5", "..M&startTime=2026-01&endTime=2026-12")]:
    try:
        r = requests.get(B + q, headers={**H, "Accept": "application/json"}, timeout=60)
        rec = {"code": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.text)}
        try:
            js = r.json(); data = js.get("data") or {}
            st = data.get("structure") or js.get("structure") or {}
            rec["struct"] = json.dumps(st.get("dimensions") or st, ensure_ascii=False)[:9000]
            ser = (data.get("dataSets") or [{}])[0].get("series") or {}
            rec["n"] = len(ser); rec["sample"] = json.dumps(dict(list(ser.items())[:3]), ensure_ascii=False)[:900]
        except Exception as e:
            rec["perr"] = str(e)[:80]; rec["head"] = r.text[:150]
        out["sdmx"][name] = rec
    except Exception as e:
        out["sdmx"][name] = {"err": str(e)[:150]}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
