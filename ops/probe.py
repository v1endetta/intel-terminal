import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {"hits": []}
r = S.get("https://data.gov.tw/datasets/export/csv", timeout=120)
rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
for row in rows[1:]:
    t = row[1] if len(row) > 1 else ""
    if re.search(r"攝影機|CCTV|cctv|即時影像|監視器|路口影像|交通影像", t) and re.search(r"臺北|台北|臺中|台中|臺南|台南|高雄", t + (row[11] if len(row) > 11 else "")):
        out["hits"].append([c[:200] for c in (row[0], row[1], row[5], row[6], row[9], row[10], row[11], row[12])])
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
for h in out["hits"][:14]:
    for u in h[3].split(";")[:1]:
        try:
            rr = S.get(u, timeout=(8, 15), stream=True)
            h.append([rr.status_code, rr.headers.get("content-type"), rr.raw.read(1500, decode_content=True).decode("utf-8", "replace")])
        except Exception as e:
            h.append(repr(e)[:150])
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
