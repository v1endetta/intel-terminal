import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}
def dist(i):
    r = S.get(f"https://data.gov.tw/api/v2/rest/dataset/{i}", timeout=30).json()["result"]
    return r.get("modifiedDate"), [(d.get("resourceDescription"), d.get("resourceDownloadUrl")) for d in r["distribution"]]
for i in (8201, 8202, 8796, 7597, 32554, 83957, 122883):
    try:
        mod, ds = dist(i)
        u = next(x for _, x in ds if x)
        b = S.get(u, timeout=60).content
        try: t = b.decode("utf-8-sig")
        except UnicodeDecodeError: t = b.decode("cp950", "replace")
        rows = list(csv.reader(io.StringIO(t)))
        out[i] = {"mod": mod, "n": len(rows), "hd": rows[0][:12], "tail": rows[-3:], "head": rows[1:3]}
    except Exception as e:
        out[i] = repr(e)[:200]
t = S.get("https://data.gov.tw/datasets/export/csv", timeout=120).content.decode("utf-8-sig", "replace")
out["weilao"] = [[x[0], x[1][:50], x[11][:16], x[12][:8], x[10][:120]] for x in csv.reader(io.StringIO(t)) if len(x) > 12 and re.search(r"危險及老舊|危老", x[1])][:30]
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
