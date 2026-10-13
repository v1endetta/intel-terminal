"""臨時探測（第三輪）：觀光署 opendata 編號、主計總處 SDMX 寫法。跑完就刪。"""
import json, re, requests
from concurrent.futures import ThreadPoolExecutor
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {"stat": {}, "sdmx": {}}
def one(i):
    try:
        r = requests.get(f"https://stat.taiwan.net.tw/data/opendata/{i}", headers=H, timeout=30)
        t = r.content[:400].decode("utf-8", "replace")
        return i, {"code": r.status_code, "len": len(r.content), "head": t.split("\n")[0][:200], "row2": (t.split("\n") + ["", ""])[1][:160]}
    except Exception as e:
        return i, {"err": str(e)[:100]}
with ThreadPoolExecutor(6) as ex:
    for i, r in ex.map(one, range(1, 121)):
        out["stat"][i] = r
B1, B2 = "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sdmx/", "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/"
for name, u in [("a", B1 + "A030101015/1..M&startTime=2026-M1&endTime=2026-M8"), ("b", B1 + "A030101015/1.1.M&startTime=2026-M1&endTime=2026-M8"),
                ("c", B1 + "A030101015/1.1+2+3.M&startTime=2025-M1&endTime=2026-M8"), ("d", B1 + "A030101015/"), ("e", B1 + "A030101015/all"),
                ("f", B2 + "A030101015/1.1.M&startTime=2026-M1&endTime=2026-M8"), ("g", "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sys=210&funid=A030101015")]:
    try:
        r = requests.get(u, headers={**H, "Accept": "application/json"}, timeout=60)
        t = r.text
        rec = {"code": r.status_code, "ct": r.headers.get("content-type"), "len": len(t), "head": t[:300], "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1][:100]}
        try:
            js = r.json(); st = js.get("structure") or {}
            rec["dims"] = json.dumps(st.get("dimensions"), ensure_ascii=False)[:5000]
            ser = ((js.get("data") or {}).get("dataSets") or [{}])[0].get("series") or {}
            rec["n"] = len(ser); rec["sample"] = json.dumps(dict(list(ser.items())[:2]), ensure_ascii=False)[:600]
        except Exception as e:
            rec["perr"] = str(e)[:80]
        out["sdmx"][name] = rec
    except Exception as e:
        out["sdmx"][name] = {"err": str(e)[:150]}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
