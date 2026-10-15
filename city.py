"""住哪裡：各鄉鎮的生活條件評分（每週跑一次，.github/workflows/city.yml）。
資料：Ookla Speedtest 開放資料（網路，CC BY-NC-SA 4.0，非商業）、OpenStreetMap（咖啡廳、共同工作空間、車站，ODbL）、
內政部戶政司（村里人口、年齡）、環境部（PM2.5 月值）、實價登錄租金（fetch.py 產生 data/rent_towns.json）、
情報站既有資料（健保診所、人口遷徙）。輸出 data/city_scores.json。
不估算：缺資料的項目就不算進總分，卡片上會標出來。"""
import csv
import io
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INTEL_DATA_DIR") or ROOT / "data")
S = requests.Session()
S.headers["User-Agent"] = "dalta-intel-terminal/1.0 (personal non-commercial; github.com/v1endetta/intel-terminal)"
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s[:200])


# ---------- 行政區外框 → 點落在哪個鄉鎮 ----------
TOWNS = json.loads((ROOT / "3d" / "towns.json").read_text(encoding="utf-8"))["towns"]
for t in TOWNS:
    xs = [p[0] for r in t["r"] for p in r]; ys = [p[1] for r in t["r"] for p in r]
    t["bb"] = (min(xs), min(ys), max(xs), max(ys))
    t["k"] = t["c"].replace("台", "臺") + t["t"]


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def town_at(lon, lat):
    for t in TOWNS:
        b = t["bb"]
        if b[0] <= lon <= b[2] and b[1] <= lat <= b[3] and any(_in_ring(lon, lat, r) for r in t["r"]):
            return t["k"]
    return None


# ---------- 人口（村里戶數、單一年齡人口）----------
def population():
    res = S.get("https://data.gov.tw/api/v2/rest/dataset/77132", timeout=60).json().get("result") or {}
    urls = [d["resourceDownloadUrl"] for d in res.get("distribution") or [] if (d.get("resourceFormat") or "").upper() == "CSV" and d.get("resourceDownloadUrl")]
    def head(u):
        try:
            r = S.get(u, timeout=(10, 30), stream=True)
            h = r.raw.read(6000, decode_content=True).decode("utf-8-sig", "replace"); r.close()
            m = re.search(r"\n\s*\"?(\d{5})\"?\s*,", h)
            return (m.group(1) if m else ""), u
        except Exception:  # noqa: BLE001
            return "", u
    with ThreadPoolExecutor(8) as ex:
        heads = sorted(ex.map(head, urls[:120]), reverse=True)
    if not heads or not heads[0][0]:
        raise RuntimeError("population: 找不到資料月份")
    ym, u = heads[0]
    rows = list(csv.DictReader(io.StringIO(S.get(u, timeout=180).content.decode("utf-8-sig", "replace"))))
    age_cols = []
    for k in rows[0].keys():
        m = re.search(r"(\d+)歲", k or "") or re.search(r"age_?(\d+)", k or "", re.I)
        if m and re.search(r"男|女|_m$|_f$|male|female", k or "", re.I):
            age_cols.append((int(m.group(1)), k))
    out = {}
    for r in rows[1:] if not re.match(r"^\d", str(list(rows[0].values())[0] or "")) else rows:
        area = (r.get("區域別") or r.get("site_id") or "").replace("台", "臺").replace("　", "").strip()
        if not area:
            continue
        num = lambda v: int(re.sub(r"[^\d]", "", str(v or "")) or 0)
        tot = sum(num(r[k]) for _, k in age_cols)
        if not tot:
            continue
        young = sum(num(r[k]) for a, k in age_cols if 20 <= a <= 39)
        old = sum(num(r[k]) for a, k in age_cols if a >= 65)
        o = out.setdefault(area, [0, 0, 0])
        o[0] += tot; o[1] += young; o[2] += old
    log("population", ym, len(out))
    return {"ym": ym, "towns": out}


# ---------- OpenStreetMap：咖啡廳、共同工作空間、車站 ----------
COUNTIES = sorted({t["c"].replace("台", "臺") for t in TOWNS})


def osm():
    out = {}
    for c in COUNTIES:
        q = (f'[out:json][timeout:120];area["name"="{c}"]["admin_level"="4"]->.a;('
             'node["amenity"="cafe"](area.a);way["amenity"="cafe"](area.a);'
             'node["amenity"="coworking_space"](area.a);way["amenity"="coworking_space"](area.a);node["office"="coworking"](area.a);'
             'node["railway"="station"](area.a);node["station"="subway"](area.a););out center tags;')
        EPS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
        for attempt in range(6):
            try:
                r = S.get(EPS[attempt % len(EPS)], params={"data": q}, timeout=180)
                if r.status_code == 200:
                    els = r.json().get("elements") or []
                    for e in els:
                        lo, la = (e.get("lon"), e.get("lat")) if e.get("type") == "node" else ((e.get("center") or {}).get("lon"), (e.get("center") or {}).get("lat"))
                        if lo is None:
                            continue
                        tk = town_at(lo, la)
                        if not tk:
                            continue
                        tg = e.get("tags") or {}
                        o = out.setdefault(tk, [0, 0, 0])
                        if tg.get("amenity") == "cafe":
                            o[0] += 1
                        elif tg.get("amenity") == "coworking_space" or tg.get("office") == "coworking":
                            o[1] += 1
                        else:
                            o[2] += 1
                    log("osm", c, len(els))
                    break
                log("osm", c, "http", r.status_code)
            except Exception as e:  # noqa: BLE001
                log("osm", c, repr(e)[:80])
            time.sleep(10 * (attempt + 1))
        time.sleep(4)
    return out


# ---------- Ookla Speedtest（每季，約 600 公尺一格）----------
def _qk(x, y, z):
    s = ""
    for i in range(z, 0, -1):
        d, m = 0, 1 << (i - 1)
        if x & m: d += 1
        if y & m: d += 2
        s += str(d)
    return s


def _tile(lon, lat, z):
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def ookla():
    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    pre = set()   # 台灣範圍在 zoom 9 的 quadkey 前綴
    x0, y0 = _tile(118.1, 26.5, 9); x1, y1 = _tile(122.2, 21.8, 9)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            pre.add(_qk(x, y, 9))
    out, meta = {}, {}
    for kind in ("fixed", "mobile"):
        key = None
        for yr in (2026, 2025):
            lst = S.get(f"https://ookla-open-data.s3.amazonaws.com/?list-type=2&prefix=parquet/performance/type={kind}/year={yr}/", timeout=30).text
            ks = [k for k in re.findall(r"<Key>(.*?)</Key>", lst) if k.endswith(".parquet")]
            if ks:
                key = sorted(ks)[-1]; break
        if not key:
            continue
        meta[kind] = key
        inlist = ",".join(f"'{p}'" for p in sorted(pre))
        rows = con.execute(f"SELECT quadkey, avg_d_kbps, avg_lat_ms, tests FROM read_parquet('s3://ookla-open-data/{key}') WHERE substr(quadkey, 1, 9) IN ({inlist})").fetchall()
        log("ookla", kind, key, len(rows))
        for qk, d, lat_ms, tests in rows:
            # quadkey → 格子中心經緯度
            x = y = 0; z = len(qk)
            for i, ch in enumerate(qk):
                m = 1 << (z - 1 - i); v = int(ch)
                if v & 1: x |= m
                if v & 2: y |= m
            n = 1 << z
            lon = (x + 0.5) / n * 360 - 180
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
            tk = town_at(lon, lat)
            if not tk:
                continue
            o = out.setdefault(tk, {}).setdefault(kind, [0.0, 0.0, 0])   # 加權下載、加權延遲、測試次數
            o[0] += d * tests; o[1] += lat_ms * tests; o[2] += tests
    res = {}
    for tk, v in out.items():
        res[tk] = {k: [round(a[0] / a[2] / 1000, 1), round(a[1] / a[2]), a[2]] for k, a in v.items() if a[2]}
    return {"meta": meta, "towns": res}


# ---------- 空氣：PM2.5 月平均（環境部），每個鄉鎮用最近的測站 ----------
AQ_KEY = "e75b1660-e564-4107-aad5-a8be1f905dd9"   # 政府資料開放平臺上公開附在下載連結裡的金鑰


def _moenv(ds, **kw):
    r = S.get(f"https://data.moenv.gov.tw/api/v2/{ds}", params={"api_key": AQ_KEY, "format": "JSON", **kw}, timeout=60)
    try:
        return r.json()
    except ValueError:
        log("moenv", ds, r.status_code, r.text[:160].replace("\n", " "))
        raise


def air():
    st = _moenv("aqx_p_07", limit=1000)
    st = st.get("records") if isinstance(st, dict) else st
    pos = {}
    for s_ in st or []:
        try:
            pos[s_.get("sitename")] = (float(s_.get("twd97lon") or s_.get("longitude")), float(s_.get("twd97lat") or s_.get("latitude")))
        except (TypeError, ValueError):
            pass
    mv = _moenv("aqx_p_08", limit=3000, sort="monitormonth desc")
    mv = mv.get("records") if isinstance(mv, dict) else mv
    pm, month = {}, ""
    for r in mv or []:
        if "PM2.5" not in str(r.get("itemengname") or r.get("itemname") or "") or "PM10" in str(r.get("itemengname")):
            continue
        mo = str(r.get("monitormonth") or "")
        month = month or mo
        if mo != month:
            continue
        try:
            pm[r.get("sitename")] = float(r.get("concentration"))
        except (TypeError, ValueError):
            pass
    out = {}
    for t in TOWNS:
        cx = sum(p[0] for p in t["r"][0]) / len(t["r"][0]); cy = sum(p[1] for p in t["r"][0]) / len(t["r"][0])
        best = min(((math.hypot((pos[s_][0] - cx) * 101, (pos[s_][1] - cy) * 111), s_) for s_ in pm if s_ in pos), default=None)
        if best and best[0] < 25:
            out[t["k"]] = [pm[best[1]], best[1], round(best[0], 1)]
    log("air", month, len(pm), len(out))
    return {"month": month, "towns": out}


def _pct(vals, v, higher_better=True):
    xs = sorted(vals)
    if not xs or v is None:
        return None
    i = sum(1 for x in xs if x < v) + 0.5 * sum(1 for x in xs if x == v)
    p = i / len(xs)
    return round((p if higher_better else 1 - p) * 100)


def main():
    parts, errs = {}, {}
    for name, fn in (("pop", population), ("osm", osm), ("net", ookla), ("air", air)):
        try:
            parts[name] = fn()
        except Exception as e:  # noqa: BLE001
            errs[name] = repr(e)[:200]; log("fail", name, repr(e)[:200])
    def load(p):
        try:
            return json.loads((DATA / p).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    rent = load("rent_towns.json").get("towns") or {}
    clinics = {(r[0].replace("台", "臺") + r[1]): r for r in (load("panels/clinics.json").get("towns") or [])}
    mig = {(r[0].replace("台", "臺") + r[1]): r for r in (load("panels/migration.json").get("towns") or [])}
    pop = (parts.get("pop") or {}).get("towns") or {}
    rows = []
    for t in TOWNS:
        k = t["k"]; p = pop.get(k)
        if not p or p[0] < 30000:   # 太小的鄉鎮不排（樣本太少，分數會亂跳）
            continue
        o = (parts.get("osm") or {}).get(k) or [0, 0, 0]
        n = ((parts.get("net") or {}).get("towns") or {}).get(k) or {}
        a = ((parts.get("air") or {}).get("towns") or {}).get(k)
        cl = clinics.get(k); mg = mig.get(k); rt = rent.get(k)
        per10k = lambda x: round(x / p[0] * 1e4, 2)
        rows.append({"k": k, "c": t["c"].replace("臺", "台"), "t": t["t"], "pop": p[0], "young": round(p[1] / p[0] * 100, 1), "old": round(p[2] / p[0] * 100, 1),
                     "cafe": o[0], "cowork": o[1], "station": o[2], "cafe_n": o[0] + o[1] * 3,
                     "net_fixed": (n.get("fixed") or [None])[0], "net_mobile": (n.get("mobile") or [None])[0], "lat_ms": (n.get("fixed") or [None, None])[1],
                     "pm25": a[0] if a else None, "pm_site": a[1] if a else "",
                     "rent": rt[0] if rt else None, "rent_n": rt[1] if rt else 0,
                     "clinic10k": per10k(cl[4]) if cl else None, "net_mig": mg[5] if mg else None, "mig10k": per10k(mg[5]) if mg else None})
    # 各項排名（全台百分位，越高越好）
    M = {"net": ("net_fixed", True), "mobile": ("net_mobile", True), "cafe": ("cafe_n", True), "rent": ("rent", False), "air": ("pm25", False),
         "transit": ("station", True), "clinic": ("clinic10k", True), "young": ("young", True), "growth": ("mig10k", True)}
    for key, (f, hb) in M.items():
        vals = [r[f] for r in rows if r.get(f) is not None]
        for r in rows:
            r.setdefault("p", {})[key] = _pct(vals, r.get(f), hb) if r.get(f) is not None else None
    SCENES = {"遠端工作": {"net": 3, "cafe": 3, "rent": 2, "mobile": 1, "air": 1, "transit": 1},
              "年輕成家": {"clinic": 2, "air": 2, "rent": 2, "growth": 2, "transit": 1, "young": 1},
              "生活機能": {"cafe": 2, "transit": 2, "clinic": 2, "net": 1, "growth": 1}}
    for r in rows:
        r["score"] = {}
        for sc, w in SCENES.items():
            have = [(r["p"][k], ww) for k, ww in w.items() if r["p"].get(k) is not None]
            tw = sum(ww for _, ww in have)
            r["score"][sc] = round(sum(v * ww for v, ww in have) / tw) if have and tw >= sum(w.values()) * 0.6 else None
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scenes": {k: list(v) for k, v in SCENES.items()},
           "pop_ym": (parts.get("pop") or {}).get("ym"), "net_src": (parts.get("net") or {}).get("meta"), "air_month": (parts.get("air") or {}).get("month"),
           "rent_season": load("rent_towns.json").get("season"), "rows": rows, "errs": errs, "log": LOG[-30:],
           "src": "Ookla Speedtest 開放資料（CC BY-NC-SA 4.0）・OpenStreetMap（ODbL）・內政部戶政司・環境部・實價登錄租賃・健保署・內政部遷入遷出"}
    (DATA / "city_scores.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log("rows", len(rows), "errs", errs)


if __name__ == "__main__":
    main()
