import requests, json, csv, io, re, time
S = requests.Session(); S.headers["User-Agent"] = "dalta-intel-terminal/1.0 (personal, non-commercial; contact via github v1endetta)"
out = {}
def save(): json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
try:
    r = S.get("https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/C21E9008-2AC7-4574-BC7D-933E17F4418F/resource/033BCBB8-BA6A-4998-830A-9A6DE72AC3E0/download", timeout=(10, 60), stream=True)
    out["mig_head"] = r.raw.read(3000, decode_content=True).decode("utf-8-sig", "replace")
except Exception as e:
    out["mig_err"] = repr(e)[:200]
save()
try:
    r = S.get("https://data.gov.tw/datasets/export/csv", timeout=120)
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
    out["vill"] = [[c[:160] for c in (x[0], x[1], x[5], x[6], x[10], x[11], x[12])] for x in rows[1:] if re.search(r"村.?里.?界|村里.*(坐標|座標|中心)|最小統計區|門牌.*(坐標|座標)", x[1])][:40]
except Exception as e:
    out["cat_err"] = repr(e)[:200]
save()
# 地址轉座標：拿健保診所檔的地址試 25 筆
try:
    r = S.get("https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D21004-009", timeout=(10, 120))
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
    out["nhi_cols"] = list(rows[0].keys())
    import random; random.seed(7); smp = random.sample(rows, 25)
    res = []
    for x in smp:
        a = x.get("地址") or x.get("醫事機構地址") or ""
        a2 = re.sub(r"\(.*?\)|（.*?）", "", a); a2 = re.sub(r"(\d+號).*$", r"\1", a2)
        hit = None
        for q in (a2, re.sub(r"\d+號$", "", re.sub(r"\d+[巷弄].*$", "", a2))):
            try:
                j = S.get("https://nominatim.openstreetmap.org/search", params={"q": q, "countrycodes": "tw", "format": "jsonv2", "limit": 1}, timeout=20).json()
            except Exception as e:
                j = []
            time.sleep(1.1)
            if j:
                hit = {"q": q, "lat": j[0]["lat"], "lon": j[0]["lon"], "type": j[0].get("addresstype") or j[0].get("type"), "name": j[0].get("display_name", "")[:80]}
                break
        res.append({"addr": a, "hit": hit})
    out["geo"] = res
except Exception as e:
    out["geo_err"] = repr(e)[:300]
save()
