"""一次性：做出「夜間燈光強度」圖給 3D 頁面用。
1) 重抓 NASA 夜光圖（不加對比，保留亮度層次）→ 3d/night.jpg
2) 從 OpenStreetMap 台灣全部建物算每格的樓地板面積（面積 × 樓層），代表城市密度 → 3d/lights.png
   大城市核心樓多樓高，會比郊區亮，這是 NASA 圖裡已經飽和、分不出來的部分。
OSM 資料：© OpenStreetMap contributors（ODbL），經 Geofabrik 下載。"""
import io
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import osmium
from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "3d"
M = json.loads((OUT / "dem.json").read_text())
W, H = 1160, 1400
LON0, LON1, LAT0, LAT1 = M["lon0"], M["lon1"], M["lat0"], M["lat1"]

# 1) NASA 夜光圖（原始層次）
q = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": M["tex"]["night"], "STYLES": "", "CRS": "EPSG:4326",
     "BBOX": f"{LAT0},{LON0},{LAT1},{LON1}", "WIDTH": W, "HEIGHT": H, "FORMAT": "image/png"}
if M["tex"]["night"] == "VIIRS_Black_Marble":
    q["TIME"] = "2016-01-01"
with urllib.request.urlopen("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?" + urllib.parse.urlencode(q), timeout=120) as r:
    night = Image.open(io.BytesIO(r.read())).convert("RGB")
night.save(OUT / "night.jpg", quality=88, optimize=True, progressive=True)
g = np.asarray(night.convert("L"), dtype=np.float32)
print("night saturated share (land-ish):", float((g >= 250).sum() / max((g > 20).sum(), 1)))

# 2) OSM 建物樓地板面積
grid = np.zeros((H, W), dtype=np.float64)
KX = 111320 * math.cos(math.radians(23.7)); KY = 110570


class B(osmium.SimpleHandler):
    n = 0

    def way(self, w):
        t = w.tags
        if "building" not in t:
            return
        try:
            pts = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 4:
            return
        a = 0.0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            a += (x1 * KX) * (y2 * KY) - (x2 * KX) * (y1 * KY)
        a = abs(a) / 2
        lv = 1.0
        try:
            if t.get("building:levels"):
                lv = float(str(t.get("building:levels")).split(";")[0])
            elif t.get("height"):
                lv = float(str(t.get("height")).replace("m", "").split(";")[0]) / 3.2
        except ValueError:
            pass
        lv = max(1.0, min(lv, 110.0))
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        i = int((cx - LON0) / (LON1 - LON0) * W); j = int((LAT1 - cy) / (LAT1 - LAT0) * H)
        if 0 <= i < W and 0 <= j < H:
            grid[j, i] += a * lv
            self.n += 1


urllib.request.urlretrieve("https://download.geofabrik.de/asia/taiwan-latest.osm.pbf", "/tmp/tw.pbf")
h = B()
h.apply_file("/tmp/tw.pbf", locations=True)
print("buildings:", h.n)
# 稍微擴散（一格約 270 公尺），再取對數，讓核心和郊區都有層次
k = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.float64); k /= k.sum()
pad = np.pad(grid, 1)
sm = sum(k[a, b] * pad[a:a + H, b:b + W] for a in range(3) for b in range(3))
v = np.log1p(sm / 2000.0)
v = v / np.percentile(v[v > 0], 99.7)
img = (np.clip(v, 0, 1) * 255).astype(np.uint8)
Image.fromarray(img, "L").save(OUT / "lights.png", optimize=True)
cells = {"台北信義": (121.565, 25.035), "台中西屯": (120.645, 24.165), "高雄前鎮": (120.31, 22.6), "花蓮市": (121.605, 23.98), "南投埔里": (120.97, 23.965)}
print({k2: int(img[int((LAT1 - la) / (LAT1 - LAT0) * H), int((lo - LON0) / (LON1 - LON0) * W)]) for k2, (lo, la) in cells.items()})
M["tex"]["lights"] = "OSM building floor area (log)"
M["tex"]["credit"] = "NASA Black Marble via GIBS · © OpenStreetMap contributors"
(OUT / "dem.json").write_text(json.dumps(M), encoding="utf-8")
print({f: (OUT / f).stat().st_size for f in ("night.jpg", "lights.png")})
