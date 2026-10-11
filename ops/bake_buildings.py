"""一次性：從 OpenStreetMap 台灣建物，做六都（台北＋新北核心、桃園、台中、台南、高雄）的白模資料給 3D 頁面。
每棟建物存成「最小外接矩形」：中心、長、寬、角度、高度。輸出 3d/b_<城市>.bin 與 3d/buildings.json。
格式（小端序）：每棟 11 bytes = x(u16, 0.5m) z(u16, 0.5m) w(u16, 0.1m) d(u16, 0.1m) a(u8, 0~180°) h(u16, 0.1m)
資料：© OpenStreetMap contributors（ODbL），經 Geofabrik 下載。"""
import json
import math
import struct
import urllib.request
from pathlib import Path

import osmium

OUT = Path(__file__).resolve().parent.parent / "3d"
CITIES = {
    "taipei":    {"name": "台北", "bbox": [121.40, 24.96, 121.66, 25.14]},
    "taoyuan":   {"name": "桃園", "bbox": [121.18, 24.93, 121.36, 25.04]},
    "taichung":  {"name": "台中", "bbox": [120.58, 24.08, 120.76, 24.23]},
    "tainan":    {"name": "台南", "bbox": [120.15, 22.94, 120.27, 23.04]},
    "kaohsiung": {"name": "高雄", "bbox": [120.26, 22.56, 120.38, 22.71]},
}
LANDMARKS = [(121.5645, 25.0340), (120.3007, 22.6116)]   # 台北 101、高雄 85 大樓：另外手做模型
MAX_PER_CITY = 260000

for c in CITIES.values():
    b = c["bbox"]; c["lon0"], c["lat0"] = b[0], b[1]
    c["kx"] = 111320 * math.cos(math.radians((b[1] + b[3]) / 2)); c["ky"] = 110570
    c["items"] = []


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


def height(t):
    try:
        if t.get("height"):
            return float(str(t.get("height")).lower().replace("m", "").split(";")[0].strip())
        if t.get("building:levels"):
            return float(str(t.get("building:levels")).split(";")[0]) * 3.3 + 1.5
    except ValueError:
        pass
    return {"house": 9.0, "residential": 12.0, "apartments": 24.0, "commercial": 14.0, "retail": 8.0, "industrial": 10.0,
            "warehouse": 9.0, "school": 14.0, "temple": 10.0, "roof": 5.0, "garage": 4.0, "shed": 3.5}.get(t.get("building"), 8.0)


class H(osmium.SimpleHandler):
    def way(self, w):
        t = w.tags
        if "building" not in t or t.get("building") in ("construction", "no"):
            return
        try:
            ll = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(ll) < 4:
            return
        cx = sum(p[0] for p in ll) / len(ll); cy = sum(p[1] for p in ll) / len(ll)
        for c in CITIES.values():
            b = c["bbox"]
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                if any(abs(cx - lx) * c["kx"] < 90 and abs(cy - ly) * c["ky"] < 90 for lx, ly in LANDMARKS):
                    return
                pts = [((lo - c["lon0"]) * c["kx"], (la - c["lat0"]) * c["ky"]) for lo, la in ll]
                o = obb(pts)
                if not o or o[0] < 40:
                    return
                hh = max(3.0, min(height(t), 520.0))
                c["items"].append((o[1], o[2], o[3], o[4], o[5], hh, o[0] * hh))
                return


print("downloading…")
urllib.request.urlretrieve("https://download.geofabrik.de/asia/taiwan-latest.osm.pbf", "/tmp/tw.pbf")
H().apply_file("/tmp/tw.pbf", locations=True)
meta = {"credit": "© OpenStreetMap contributors", "format": "x z w d a h", "cities": {}}
for key, c in CITIES.items():
    its = sorted(c["items"], key=lambda r: -r[6])[:MAX_PER_CITY]
    buf = bytearray()
    tall = 0
    for x, z, w, d, a, h, _ in its:
        a = a % math.pi
        buf += struct.pack("<HHHHBH", max(0, min(65535, round(x * 2))), max(0, min(65535, round(z * 2))),
                           min(65535, round(w * 10)), min(65535, round(d * 10)), round(a / math.pi * 255) % 256, min(65535, round(h * 10)))
        tall += h >= 60
    (OUT / f"b_{key}.bin").write_bytes(bytes(buf))
    meta["cities"][key] = {"name": c["name"], "bbox": c["bbox"], "kx": c["kx"], "ky": c["ky"], "n": len(its), "tall60": tall,
                           "bytes": len(buf)}
    print(key, len(c["items"]), "→", len(its), "tall≥60m", tall, len(buf) // 1024, "KB")
(OUT / "buildings.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
