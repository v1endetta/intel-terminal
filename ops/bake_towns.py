"""一次性：全台建物依「行政區」分檔（OpenStreetMap）。
地圖分三層：台灣（不放建物）› 縣市（簡化方塊 b_）› 行政區／街道（真實外形 p_、道路 r_、水域與公園 a_）。
每個鄉鎮市區一組檔案，放在 3d/tb/；超過 28 公里的大鄉切成幾塊（座標用 u16×0.5m，每塊不能超過 32.7 公里）。
檔案格式跟 ops/bake_buildings.py、ops/bake_city.py 完全一樣，原點是 index.json 裡每塊的 bbox 西南角（已含 2 公里邊界）。
建物、道路依中心點落在哪個行政區分；水域與公園切到行政區邊界裡（大河不會重複）。
資料：© OpenStreetMap contributors（ODbL）、內政部國土測繪中心 鄉鎮市區界線。"""
import json
import math
import os
import struct
import urllib.request
from pathlib import Path

import numpy as np
import osmium
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "3d" / "tb"
OUT.mkdir(parents=True, exist_ok=True)
TOWNS = json.loads((ROOT / "3d" / "towns.json").read_text(encoding="utf-8"))["towns"]
PART_KM, MARGIN_KM = 28.0, 2.0
LANDMARKS = [(121.5645, 25.0340), (120.3007, 22.6116)]   # 台北 101、高雄 85 大樓另外手做
ROAD = {"motorway": 1, "trunk": 2, "primary": 3, "secondary": 4, "tertiary": 5, "residential": 6, "unclassified": 6,
        "living_street": 7, "service": 7, "motorway_link": 1, "trunk_link": 2, "primary_link": 3, "secondary_link": 4, "tertiary_link": 5}
KY = 110570.0


def kx_at(lat):
    return 111320.0 * math.cos(math.radians(lat))


# ---- 行政區 → 一塊或幾塊 ----
ENT = []   # 每塊：{key, c, t, rect(lon0,lat0,lon1,lat1), org(lon0,lat0), kx, poly}
for ti, z in enumerate(TOWNS):
    polys = [Polygon(r).buffer(0) for r in z["r"] if len(r) >= 4]
    tp = unary_union([p for p in polys if not p.is_empty])
    if tp.is_empty:
        continue
    x0, y0, x1, y1 = tp.bounds
    kx = kx_at((y0 + y1) / 2)
    nx = max(1, math.ceil((x1 - x0) * kx / 1000 / PART_KM)); ny = max(1, math.ceil((y1 - y0) * KY / 1000 / PART_KM))
    for i in range(nx):
        for j in range(ny):
            r = (x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, x0 + (x1 - x0) * (i + 1) / nx, y0 + (y1 - y0) * (j + 1) / ny)
            part = tp.intersection(box(*r)) if nx * ny > 1 else tp
            if part.is_empty or part.area <= 0:
                continue
            k = len(ENT)
            ml, mt = MARGIN_KM * 1000 / kx, MARGIN_KM * 1000 / KY
            ENT.append({"key": f"t{k}", "c": z["c"], "t": z["t"], "rect": r, "org": (r[0] - ml, r[1] - mt), "kx": kx, "poly": part,
                        "B": [], "P": [], "R": [], "A": []})
print("pieces", len(ENT))
TREE = shapely.STRtree([e["poly"] for e in ENT])


def loc(e, lon, lat):
    return ((lon - e["org"][0]) * e["kx"], (lat - e["org"][1]) * KY)


# ---- 幾何小工具（跟 bake_city.py 一樣） ----
def dp(pts, tol):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1e-9
    i, dmax = 0, -1.0
    for k in range(1, len(pts) - 1):
        d = abs(dy * pts[k][0] - dx * pts[k][1] + x2 * y1 - y2 * x1) / L
        if d > dmax:
            i, dmax = k, d
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return dp(pts[:i + 1], tol)[:-1] + dp(pts[i:], tol)


def ring_simplify(pts, tol):
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return pts
    far = max(range(len(pts)), key=lambda k: (pts[k][0] - pts[0][0]) ** 2 + (pts[k][1] - pts[0][1]) ** 2)
    a = dp(pts[:far + 1], tol); b = dp(pts[far:] + [pts[0]], tol)
    return a[:-1] + b[:-1]


def hull(p):
    p = sorted(set(p))
    if len(p) < 3:
        return p
    def cr(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in p:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], q) <= 0: lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(up) >= 2 and cr(up[-2], up[-1], q) <= 0: up.pop()
        up.append(q)
    return lo[:-1] + up[:-1]


def obb(pts):
    h = hull(pts)
    if len(h) < 3:
        return None
    best = None
    for i in range(len(h)):
        x1, y1 = h[i]; x2, y2 = h[(i + 1) % len(h)]
        a = math.atan2(y2 - y1, x2 - x1); ca, sa = math.cos(a), math.sin(a)
        us = [x * ca + y * sa for x, y in h]; vs = [-x * sa + y * ca for x, y in h]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (area, cu * ca - cv * sa, cu * sa + cv * ca, max(us) - min(us), max(vs) - min(vs), a)
    return best


def num(v, d=None):
    try:
        return float(str(v).lower().replace("m", "").split(";")[0].strip())
    except (TypeError, ValueError):
        return d


def bheight(t):
    h = num(t.get("height"))
    if h is None and t.get("building:levels"):
        lv = num(t.get("building:levels"))
        h = lv * 3.3 + 1.5 if lv is not None else None
    if h is None:
        h = {"house": 9.0, "residential": 12.0, "apartments": 24.0, "commercial": 14.0, "retail": 8.0, "industrial": 10.0,
             "warehouse": 9.0, "school": 14.0, "temple": 10.0, "roof": 5.0, "garage": 4.0, "shed": 3.5}.get(t.get("building") or t.get("building:part"), 8.0)
    base = num(t.get("min_height"))
    if base is None and t.get("building:min_level"):
        ml = num(t.get("building:min_level")); base = ml * 3.3 if ml is not None else 0.0
    return max(3.0, min(h, 520.0)), max(0.0, min(base or 0.0, 500.0))


# ---- 第一輪：讀 OSM，先把原始資料收起來（經緯度），最後再一次分到行政區 ----
BLD, RDS, ARS = [], [], []   # 建物 (lon,lat 環, tags 高度)、道路 (cls, 點)、水域公園 (kind, 環)


class H(osmium.SimpleHandler):
    def area(self, a):
        t = a.tags
        isb = "building" in t or "building:part" in t
        kind = 0
        if t.get("natural") == "water" or t.get("waterway") == "riverbank" or t.get("landuse") in ("reservoir", "basin"):
            kind = 1
        elif t.get("leisure") in ("park", "garden", "pitch", "golf_course") or t.get("landuse") in ("grass", "recreation_ground", "cemetery"):
            kind = 2   # 森林不收（山區整片森林太大，玻璃風也不畫）
        if not isb and not kind:
            return
        if isb and t.get("building") in ("construction", "no"):
            return
        for outer in a.outer_rings():
            try:
                ll = [(n.lon, n.lat) for n in outer]
            except osmium.InvalidLocationError:
                continue
            if len(ll) < 4:
                continue
            if isb:
                h, base = bheight(t)
                if base >= h:
                    continue
                BLD.append((ll, h, base))
            else:
                ARS.append((kind, ll))

    def way(self, w):
        cls = ROAD.get(w.tags.get("highway"))
        if not cls:
            return
        try:
            ll = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(ll) >= 2:
            RDS.append((cls, ll))


print("downloading…")
os.path.exists("/tmp/tw.pbf") or urllib.request.urlretrieve("https://download.geofabrik.de/asia/taiwan-latest.osm.pbf", "/tmp/tw.pbf")
H().apply_file("/tmp/tw.pbf", locations=True)
print("buildings", len(BLD), "roads", len(RDS), "areas", len(ARS))


def assign(lons, lats):
    """每個點落在哪一塊（找不到 → -1，例如海上的點）。"""
    pts = shapely.points(np.asarray(lons), np.asarray(lats))
    q = TREE.query(pts, predicate="within")
    out = np.full(len(lons), -1, dtype=np.int64)
    out[q[0]] = q[1]
    return out


# 建物：中心點
cx = [sum(p[0] for p in b[0]) / len(b[0]) for b in BLD]; cy = [sum(p[1] for p in b[0]) / len(b[0]) for b in BLD]
idx = assign(cx, cy)
for (ll, h, base), i, lo, la in zip(BLD, idx, cx, cy):
    if i < 0:
        continue
    e = ENT[i]
    if any(abs(lo - lx) * e["kx"] < 90 and abs(la - ly) * KY < 90 for lx, ly in LANDMARKS):
        continue
    pts = [loc(e, a, b) for a, b in ll]
    s = ring_simplify(pts, 0.7)
    if len(s) < 3:
        continue
    ar = abs(sum(s[k][0] * s[(k + 1) % len(s)][1] - s[(k + 1) % len(s)][0] * s[k][1] for k in range(len(s)))) / 2
    if ar < 25:
        continue
    e["P"].append((s, h, base, ar * (h - base)))
    o = obb(pts)
    if o and o[0] >= 40:
        e["B"].append((o[1], o[2], o[3], o[4], o[5], h, o[0] * h))
del BLD

# 道路：先切成每段不超過約 1 公里，再依每段中點分（不會超出那一塊的邊界太多）
segs = []
for cls, ll in RDS:
    cur = [ll[0]]; acc = 0.0
    for a, b in zip(ll, ll[1:]):
        acc += math.hypot((b[0] - a[0]) * 101500, (b[1] - a[1]) * KY); cur.append(b)
        if acc > 1000 or len(cur) >= 250:
            segs.append((cls, cur)); cur = [b]; acc = 0.0
    if len(cur) >= 2:
        segs.append((cls, cur))
del RDS
mx = [s[1][len(s[1]) // 2][0] for s in segs]; my = [s[1][len(s[1]) // 2][1] for s in segs]
idx = assign(mx, my)
for (cls, ll), i in zip(segs, idx):
    if i < 0:
        continue
    e = ENT[i]
    pts = dp([loc(e, a, b) for a, b in ll], 1.0)
    e["R"].append((cls, pts))
del segs

# 水域與公園：切到每塊的範圍裡（大河跨很多區，每區只留自己那段）
for kind, ll in ARS:
    try:
        poly = Polygon(ll).buffer(0)
    except Exception:  # noqa: BLE001
        continue
    if poly.is_empty:
        continue
    for i in TREE.query(poly, predicate="intersects"):
        e = ENT[i]
        g = poly if e["poly"].contains(poly) else poly.intersection(e["poly"])
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon" or p.area <= 0:
                continue
            pts = ring_simplify([loc(e, a, b) for a, b in p.exterior.coords], 2.0)
            if len(pts) >= 3:
                e["A"].append((kind, pts))
del ARS

# ---- 寫檔 ----
q = lambda v: max(0, min(65535, round(v * 2)))
meta = {"credit": "© OpenStreetMap contributors；鄉鎮市區界線：內政部國土測繪中心", "format": "同 buildings.json：b_ 方塊、p_ 外形、r_ 道路、a_ 水域公園", "towns": {}}
tot = 0
for e in ENT:
    if not (e["P"] or e["R"]):
        continue
    key = e["key"]
    B = sorted(e["B"], key=lambda r: -r[6])
    b = bytearray()
    for x, z, w, d, a, h, _ in B:
        a = a % math.pi
        b += struct.pack("<HHHHBH", q(x), q(z), min(65535, round(w * 10)), min(65535, round(d * 10)), round(a / math.pi * 255) % 256, min(65535, round(h * 10)))
    P = sorted(e["P"], key=lambda r: -r[3])
    p = bytearray()
    for s, h, base, _ in P:
        cx_ = sum(t[0] for t in s) / len(s); cz_ = sum(t[1] for t in s) / len(s)
        s = s[:255]
        p += struct.pack("<HHHHB", q(cx_), q(cz_), min(65535, round(h * 10)), min(65535, round(base * 10)), len(s))
        for x, z in s:
            p += struct.pack("<hh", max(-32768, min(32767, round((x - cx_) * 4))), max(-32768, min(32767, round((z - cz_) * 4))))
    r = bytearray()
    for cls, pts in e["R"]:
        r += struct.pack("<BB", cls, len(pts))
        for x, z in pts:
            r += struct.pack("<HH", q(x), q(z))
    a_ = bytearray()
    for kind, pts in e["A"]:
        pts = pts[:65535]
        a_ += struct.pack("<BH", kind, len(pts))
        for x, z in pts:
            a_ += struct.pack("<HH", q(x), q(z))
    for pre, buf in (("b", b), ("p", p), ("r", r), ("a", a_)):
        (OUT / f"{pre}_{key}.bin").write_bytes(bytes(buf))
    x0, y0, x1, y1 = e["rect"]
    meta["towns"][key] = {"c": e["c"], "t": e["t"], "bbox": [round(e["org"][0], 6), round(e["org"][1], 6), round(x1, 6), round(y1, 6)],
                          "rect": [round(v, 5) for v in e["rect"]], "kx": e["kx"], "ky": KY, "n": len(B), "pn": len(P),
                          "kb": round((len(b) + len(p) + len(r) + len(a_)) / 1024)}
    tot += len(b) + len(p) + len(r) + len(a_)
(OUT / "index.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("pieces written", len(meta["towns"]), "total MB", round(tot / 1e6, 1))
top = sorted(meta["towns"].values(), key=lambda v: -v["pn"])[:12]
for v in top:
    print(v["c"], v["t"], v["pn"], v["kb"], "KB")
