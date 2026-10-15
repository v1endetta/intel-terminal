import requests, json, csv, io, re
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
out = {}


def dec(b):
    for enc in ("utf-8-sig", "cp950"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def rows(u):
    r = S.get(u, timeout=60)
    return r, list(csv.reader(io.StringIO(dec(r.content))))


try:
    r, rd = rows("https://service.moea.gov.tw/EE520/opendata/ea.csv")
    o = {"hd": rd[0], "n": len(rd), "last": rd[-3:]}
    codes = {}
    for x in rd[1:]:
        if len(x) >= 5:
            k = (x[0], x[1], x[2])
            codes.setdefault(k, [0, ""])
            codes[k][0] += 1
            codes[k][1] = max(codes[k][1], x[3])
    o["codes"] = [list(k) + v for k, v in codes.items()]
    o["units"] = sorted({x[5] for x in rd[1:] if len(x) > 5})
    out["6842"] = o
except Exception as e:
    out["6842"] = repr(e)

try:
    r, rd = rows("https://www.nccc.com.tw/dataDownload/EC/BANK_EC_ALL.CSV")
    out["62945"] = {"hd": rd[0], "n": len(rd), "last": rd[-8:], "cats": sorted({x[2] for x in rd[1:] if len(x) > 2}), "c1": sorted({x[1] for x in rd[1:] if len(x) > 1})[:10]}
    r, rd = rows("https://www.nccc.com.tw/dataDownload/Billing Address/BANK_LCSUM_IDSUM_BA.CSV")
    out["175018"] = {"n": len(rd), "last": rd[-3:], "areas": sorted({x[1] for x in rd[1:] if len(x) > 1}), "cats": sorted({x[2] for x in rd[1:] if len(x) > 2})}
except Exception as e:
    out["cards"] = repr(e)

try:
    res = S.get("https://data.gov.tw/api/v2/rest/dataset/157994", timeout=30).json()["result"]
    dist = res["distribution"]
    d = sorted(dist, key=lambda x: x.get("resourceDescription") or "")[-1]
    r, rd = rows(d["resourceDownloadUrl"])
    out["157994"] = {"desc": [x.get("resourceDescription")[:5] for x in dist], "hd": rd[0], "n": len(rd), "s": rd[1:30], "kinds": sorted({x[4] for x in rd[1:] if len(x) > 4})}
except Exception as e:
    out["157994"] = repr(e)

try:
    u = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/A4AA6738-3DBB-40A8-BD87-9EFAE9CBC367/resource/DAD5CED7-439C-4942-86BB-92042E5FE6FB/download"
    r = S.get(u, timeout=60)
    res = S.get("https://data.gov.tw/api/v2/rest/dataset/21293", timeout=30).json().get("result", {})
    out["21293"] = {"h": dict(r.headers), "res": {k: v for k, v in res.items() if k != "distribution"}}
except Exception as e:
    out["21293"] = repr(e)

try:  # 目錄裡找建照/使照/開工
    t = S.get("https://data.gov.tw/datasets/export/csv", timeout=90).content.decode("utf-8-sig", "replace")
    hits = []
    for x in csv.reader(io.StringIO(t)):
        if len(x) > 12 and re.search(r"建造執照|使用執照|開工|建照|建築執照", x[1]):
            hits.append([x[0], x[1][:40], x[5][:20], x[11][:20], x[12][:10], x[10][:120]])
    out["permit_cat"] = hits[:80]
except Exception as e:
    out["permit_cat"] = repr(e)

json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
