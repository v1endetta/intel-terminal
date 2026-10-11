"""一次性：六都精細模型資料（OpenStreetMap）。給 3D 頁面拉近市區時用。
輸出每個城市三個檔：
  p_<city>.bin 建物真實外形：u16 cx,cz(0.5m) u16 h(0.1m) u16 base(0.1m) u8 n ＋ n×(i16 dx,dz)(0.25m，相對中心)
  r_<city>.bin 道路：u8 等級 u8 n ＋ n×(u16 x,z)(0.5m)
  a_<city>.bin 水域與綠地：u8 種類(1 水 2 綠) u16 n ＋ n×(u16 x,z)(0.5m)
座標原點為 buildings.json 裡各城市 bbox 的西南角。© OpenStreetMap contributors（ODbL）。"""
import json
import math
import struct
import urllib.request
from pathlib import Path

import osmium

OUT = Path(__file__).resolve().parent.parent / "3d"
META = json.loads((OUT / "buildings.json").read_text(encoding="utf-8"))
CITIES = META["cities"]
LANDMARKS = [(121.5645, 25.0340), (120.3007, 22.6116)]
ROAD = {"motorway": 1, "trunk": 2, "primary": 3, "secondary": 4, "tertiary": 5, "residential": 6, "unclassified": 6,
        "living_street": 7, "service": 7, "motorway_link": 1, "trunk_link": 2, "primary_link": 3, "secondary_link": 4, "tertiary_link": 5}
for c in CITIES.values():
    c["B"], c["R"], c["A"] = [], [], []


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


def city_of(lon, lat):
    for k, c in CITIES.items():
        b = c["bbox"]
        if b[0] <= lon <= b[2] and b[1] <= lat <= b[3]:
            return k, c
    return None, None


def loc(c, lon, lat):
    return ((lon - c["bbox"][0]) * c["kx"], (lat - c["bbox"][1]) * c["ky"])


class H(osmium.SimpleHandler):
    def area(self, a):
        t = a.tags
        isb = "building" in t or "building:part" in t
        kind = 0
        if t.get("natural") == "water" or t.get("waterway") == "riverbank" or t.get("landuse") in ("reservoir", "basin"):
            kind = 1
        elif t.get("leisure") in ("park", "garden", "pitch", "golf_course") or t.get("landuse") in ("grass", "recreation_ground", "forest", "cemetery") or t.get("natural") == "wood":
            kind = 2
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
            cx = sum(p[0] for p in ll) / len(ll); cy = sum(p[1] for p in ll) / len(ll)
            k, c = city_of(cx, cy)
            if not c:
                continue
            pts = [loc(c, lo, la) for lo, la in ll]
            if isb:
                if any(abs(cx - lx) * c["kx"] < 90 and abs(cy - ly) * c["ky"] < 90 for lx, ly in LANDMARKS):
                    continue
                s = ring_simplify(pts, 0.7)
                if len(s) < 3:
                    continue
                ar = abs(sum(s[i][0] * s[(i + 1) % len(s)][1] - s[(i + 1) % len(s)][0] * s[i][1] for i in range(len(s)))) / 2
                if ar < 25:
                    continue
                h, base = bheight(t)
                if base >= h:
                    continue
                c["B"].append((s, h, base, ar * (h - base)))
            else:
                s = ring_simplify(pts, 2.0)
                if len(s) >= 3:
                    c["A"].append((kind, s))

    def way(self, w):
        cls = ROAD.get(w.tags.get("highway"))
        if not cls:
            return
        try:
            ll = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(ll) < 2:
            return
        k, c = city_of(ll[len(ll) // 2][0], ll[len(ll) // 2][1])
        if not c:
            return
        pts = dp([loc(c, lo, la) for lo, la in ll], 1.0)
        for i in range(0, len(pts) - 1, 250):
            c["R"].append((cls, pts[i:i + 251]))


print("downloading…")
urllib.request.urlretrieve("https://download.geofabrik.de/asia/taiwan-latest.osm.pbf", "/tmp/tw.pbf")
H().apply_file("/tmp/tw.pbf", locations=True)
q = lambda v: max(0, min(65535, round(v * 2)))
for key, c in CITIES.items():
    B = sorted(c["B"], key=lambda r: -r[3])[:300000]
    out = bytearray()
    for s, h, base, _ in B:
        cx = sum(p[0] for p in s) / len(s); cz = sum(p[1] for p in s) / len(s)
        s = s[:255]
        out += struct.pack("<HHHHB", q(cx), q(cz), min(65535, round(h * 10)), min(65535, round(base * 10)), len(s))
        for x, z in s:
            out += struct.pack("<hh", max(-32768, min(32767, round((x - cx) * 4))), max(-32768, min(32767, round((z - cz) * 4))))
    (OUT / f"p_{key}.bin").write_bytes(bytes(out))
    r = bytearray()
    for cls, pts in c["R"]:
        r += struct.pack("<BB", cls, len(pts))
        for x, z in pts:
            r += struct.pack("<HH", q(x), q(z))
    (OUT / f"r_{key}.bin").write_bytes(bytes(r))
    a = bytearray()
    for kind, pts in c["A"]:
        pts = pts[:65535]
        a += struct.pack("<BH", kind, len(pts))
        for x, z in pts:
            a += struct.pack("<HH", q(x), q(z))
    (OUT / f"a_{key}.bin").write_bytes(bytes(a))
    nr, na = len(c["R"]), len(c["A"])
    for f in ("B", "R", "A"):
        CITIES[key].pop(f, None)
    CITIES[key].update({"pn": len(B), "pbytes": len(out), "rn": nr, "rbytes": len(r), "an": na, "abytes": len(a)})
    print(key, "buildings", len(B), len(out) // 1024, "KB | roads", nr, len(r) // 1024, "KB | areas", na, len(a) // 1024, "KB")
META["detail"] = 1
(OUT / "buildings.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
