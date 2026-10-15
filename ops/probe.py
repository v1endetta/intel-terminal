import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
t = S.get("https://data.gov.tw/datasets/export/csv", timeout=120).content.decode("utf-8-sig", "replace")
out = {}
pat = {"都更": r"都市更新|都更|危老|老舊建築物重建", "重劃": r"重劃|區段徵收", "產業園區": r"產業園區|工業區|科學園區|科技產業園區|加工出口區"}
for x in csv.reader(io.StringIO(t)):
    if len(x) < 13:
        continue
    for k, p in pat.items():
        if re.search(p, x[1]):
            out.setdefault(k, []).append([x[0], x[1][:50], x[5][:15], x[11][:16], x[12][:8], x[10][:160]])
for k in out:
    out[k] = out[k][:70]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
