import os, json, re, io, csv, requests, collections
os.makedirs("out25", exist_ok=True)
H = {"User-Agent": "intel-terminal/1.0 (personal research)"}
rep = {}
r = requests.get("https://data.gov.tw/datasets/export/csv", headers=H, timeout=180)
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "ignore"))))
hdr = rows[0]; idx = {h: i for i, h in enumerate(hdr)}
meta = {row[idx["資料集識別碼"]]: row for row in rows[1:] if len(row) > idx["資料下載網址"]}
for i in ("40331", "40317", "161861"):
    m = meta.get(i)
    rep["raw_" + i] = m[idx["資料下載網址"]][:3000] if m else None
    rep["fmt_" + i] = m[idx["檔案格式"]] if m else None
# 也找其他農產品進口相關資料集
rep["agri_imp"] = [(row[idx["資料集識別碼"]], row[idx["資料集名稱"]][:50], row[idx["更新頻率"]]) for row in rows[1:] if re.search(r"進口.*(貿易|量|值)", row[idx["資料集名稱"]]) and "農" in row[idx["提供機關"]]][:30]
# 試 MOA API 的不同群組
base = "https://data.moa.gov.tw/service/opendata/agrstatUnit.aspx"
for g1 in ("GA01", "GA02", "GA03", "GA04", "GA05", "GA06", "GA07", "GA08", "GA09", "GA10"):
    try:
        x = requests.get(base, params={"item_code": "GA0410", "dimension_group_code_1": g1, "dimension_group_code_2": "XX32", "IsTransData": "1", "UnitId": "634"}, headers=H, timeout=90)
        js = x.json() if x.ok and x.content[:1] == b"[" else []
        names = collections.Counter(j["dname1"] for j in js)
        rep["g_" + g1] = {"status": x.status_code, "n": len(js), "names": list(names)[:12], "dates": sorted(set(j["date"] for j in js))[-4:] if js else None}
    except Exception as e:
        rep["g_" + g1] = {"err": repr(e)[:150]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
