"""一次性：從公開的 Terrarium 高程圖磚（AWS Open Data，免金鑰）烤出台灣本島＋澎湖的高程圖，給 3D 頁面用。
輸出 3d/dem.png（R*256+G = (高程+500)*10，單位公尺）與 3d/dem.json（範圍與解碼參數）。"""
import io
import json
import math
import urllib.request
from pathlib import Path

from PIL import Image

Z = 9
LON0, LON1, LAT0, LAT1 = 119.25, 122.15, 21.85, 25.35   # 西、東、南、北
STEP = 0.005                                           # 約 500 公尺一格
OUT = Path(__file__).resolve().parent.parent / "3d"
N = 256 * 2 ** Z


def gx(lon):
    return (lon + 180) / 360 * N


def gy(lat):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * N


tiles = {}


def tile(tx, ty):
    if (tx, ty) not in tiles:
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
        with urllib.request.urlopen(url, timeout=60) as r:
            tiles[(tx, ty)] = Image.open(io.BytesIO(r.read())).convert("RGB").load()
    return tiles[(tx, ty)]


def elev_px(px, py):
    tx, ty = int(px // 256), int(py // 256)
    r, g, b = tile(tx, ty)[int(px) % 256, int(py) % 256]
    return r * 256 + g + b / 256 - 32768


def elev(lon, lat):
    px, py = gx(lon) - 0.5, gy(lat) - 0.5
    x0, y0 = math.floor(px), math.floor(py)
    fx, fy = px - x0, py - y0
    a, b = elev_px(x0, y0), elev_px(x0 + 1, y0)
    c, d = elev_px(x0, y0 + 1), elev_px(x0 + 1, y0 + 1)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


W = round((LON1 - LON0) / STEP) + 1
H = round((LAT1 - LAT0) / STEP) + 1
img = Image.new("RGB", (W, H))
pix = img.load()
lo, hi = 1e9, -1e9
for j in range(H):
    lat = LAT1 - j * STEP
    for i in range(W):
        e = elev(LON0 + i * STEP, lat)
        lo, hi = min(lo, e), max(hi, e)
        v = int(round((max(-500.0, min(5999.0, e)) + 500) * 10))
        pix[i, j] = (v >> 8, v & 255, 0)
OUT.mkdir(exist_ok=True)
img.save(OUT / "dem.png", optimize=True)
meta = {"lon0": LON0, "lon1": LON1, "lat0": LAT0, "lat1": LAT1, "w": W, "h": H, "offset": -500, "scale": 0.1,
        "min": round(lo), "max": round(hi), "source": "Terrarium elevation tiles (AWS Open Data / Mapzen), z9"}
(OUT / "dem.json").write_text(json.dumps(meta), encoding="utf-8")
print(meta, len(tiles), "tiles", (OUT / "dem.png").stat().st_size, "bytes")
