"""臨時探測（第五輪）：主計總處 SDMX 數值查詢、交通部月統計。跑完就刪。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {"sdmx": {}, "motc": {}}
B = "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sdmx/A030101015/"
for name, q in [("a", "1.M&startTime=2025-01&endTime=2026-12"), ("b", "1+10+13.M&startTime=2025-M1&endTime=2026-M12"), ("c", ".M&startTime=2025-01&endTime=2026-12"),
                ("d", "1.M&startTime=2025&endTime=2026")]:
    try:
        r = requests.get(B + q, headers={**H, "Accept": "application/json"}, timeout=90)
        rec = {"code": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.text)}
        try:
            js = r.json(); data = js.get("data") or {}
            st = data.get("structure") or {}
            rec["obs"] = json.dumps((st.get("dimensions") or {}).get("observation"), ensure_ascii=False)[:1500]
            ser = (data.get("dataSets") or [{}])[0].get("series") or {}
            rec["n"] = len(ser); rec["sample"] = json.dumps(dict(list(ser.items())[:2]), ensure_ascii=False)[:1200]
        except Exception as e:
            rec["perr"] = str(e)[:80]; rec["title"] = (re.search(r"<title>(.*?)</title>", r.text, re.S) or [None, ""])[1][:80]
            m = re.search(r"(錯誤|error)[^<]{0,120}", r.text, re.I); rec["msg"] = m.group(0) if m else ""
        out["sdmx"][name] = rec
    except Exception as e:
        out["sdmx"][name] = {"err": str(e)[:150]}
for name, u in [("motc_home", "https://stat.motc.gov.tw/mocdb/stmain.jsp?sys=100"), ("motc_api", "https://stat.motc.gov.tw/mocdb/stmain.jsp?sys=220&ym=11401&ymt=11408&kind=21&type=1&funid=b5201&cycle=1&outmode=8&compmode=0&outkind=1&fldspc=0,1,&codspc0=0,30,&rdm=R1"),
                ("tourism_month", "https://stat.taiwan.net.tw/data/opendata/18"), ("tourism_month2", "https://stat.taiwan.net.tw/data/opendata/20")]:
    try:
        r = requests.get(u, headers=H, timeout=40)
        out["motc"][name] = {"code": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "head": r.content[:500].decode("utf-8", "replace")}
    except Exception as e:
        out["motc"][name] = {"err": str(e)[:150]}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
