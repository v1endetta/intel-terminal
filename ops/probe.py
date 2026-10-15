import requests, json, csv, io, re, time
S = requests.Session(); S.headers["User-Agent"] = "dalta-intel-terminal/1.0 (personal non-commercial)"
out = {}
def save(): json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
# 1. 戶政人口（村里、年齡）資料集
try:
    r = S.get("https://data.gov.tw/datasets/export/csv", timeout=120)
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
    out["pop"] = [[x[0], x[1][:50], x[5][:15], x[11][:12], x[12][:8], x[6][:150]] for x in rows[1:] if re.search(r"村里.*(人口|戶數)|鄉鎮.*人口.*年齡|單一年齡|人口數按", x[1]) and re.search(r"戶政|內政部|統計處", x[11])][:20]
    out["aqi"] = [[x[0], x[1][:50], x[5][:15], x[6][:200]] for x in rows[1:] if x[0] in ("28202", "167835")]
    out["yb"] = [[x[0], x[1][:50], x[11][:12]] for x in rows[1:] if re.search(r"YouBike|公共自行車", x[1])][:6]
except Exception as e:
    out["cat_err"] = repr(e)[:150]
save()
# 2. Overpass（GET）
try:
    q = '[out:json][timeout:60];area["ISO3166-1"="TW"][admin_level=2]->.a;(node["amenity"="coworking_space"](area.a);node["office"="coworking"](area.a);way["amenity"="coworking_space"](area.a););out center 5;'
    r = S.get("https://overpass-api.de/api/interpreter", params={"data": q}, timeout=90); out["overpass"] = [r.status_code, r.text[:600]]
    q2 = '[out:json][timeout:90];area["ISO3166-1"="TW"][admin_level=2]->.a;node["amenity"="cafe"](area.a);out count;'
    r = S.get("https://overpass-api.de/api/interpreter", params={"data": q2}, timeout=120); out["overpass_cafe"] = [r.status_code, r.text[:400]]
except Exception as e:
    out["overpass"] = repr(e)[:150]
save()
# 3. Ookla（DuckDB 直接讀 S3 上的 parquet，只取台灣範圍）
try:
    import duckdb
    con = duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    t0 = time.time()
    lst = S.get("https://ookla-open-data.s3.amazonaws.com/?list-type=2&prefix=parquet/performance/type=fixed/year=2026/", timeout=30).text
    keys = re.findall(r"<Key>(.*?)</Key>", lst); out["ookla_keys"] = keys[:6]
    if not keys:
        lst = S.get("https://ookla-open-data.s3.amazonaws.com/?list-type=2&prefix=parquet/performance/type=fixed/year=2025/", timeout=30).text
        keys = re.findall(r"<Key>(.*?)</Key>", lst); out["ookla_keys25"] = keys[:6]
    k = [x for x in keys if x.endswith(".parquet")][-1]
    cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('s3://ookla-open-data/{k}')").fetchall(); out["ookla_cols"] = [c[0] for c in cols]
    # 台灣：zoom 16 quadkey 前綴（大約經度 119.3–122.2、緯度 21.8–25.4）用 tile_x / tile_y 或 quadkey 比對
    q = f"SELECT count(*), avg(avg_d_kbps) FROM read_parquet('s3://ookla-open-data/{k}') WHERE quadkey LIKE '1321%'"
    out["ookla_cnt"] = [str(x) for x in con.execute(q).fetchall()]; out["ookla_sec"] = round(time.time() - t0, 1)
except Exception as e:
    out["ookla_err"] = repr(e)[:300]
save()
