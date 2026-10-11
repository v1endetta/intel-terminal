"""一次性：從 NASA GIBS（公有領域、免金鑰）抓台灣的白天衛星合成圖與夜間燈光圖，給 3D 頁面當地面材質。
範圍與 3d/dem.json 相同。輸出 3d/day.jpg、3d/night.jpg。"""
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance

OUT = Path(__file__).resolve().parent.parent / "3d"
M = json.loads((OUT / "dem.json").read_text())
W, H = 1160, 1400
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"


def get(layer, time=None, fmt="image/jpeg"):
    q = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:4326",
         "BBOX": f"{M['lat0']},{M['lon0']},{M['lat1']},{M['lon1']}", "WIDTH": W, "HEIGHT": H, "FORMAT": fmt}
    if time:
        q["TIME"] = time
    url = WMS + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=120) as r:
        b = r.read()
        ct = r.headers.get("Content-Type", "")
    if not ct.startswith("image"):
        raise RuntimeError(f"{layer}: {ct} {b[:200]!r}")
    return Image.open(io.BytesIO(b)).convert("RGB")


def first(cands, name):
    for layer, time in cands:
        try:
            im = get(layer, time)
            ext = im.getextrema()
            if max(e[1] for e in ext) < 10:
                raise RuntimeError("blank image")
            print(name, "←", layer, time, im.size)
            return im, layer
        except Exception as e:  # noqa: BLE001
            print(name, "✗", layer, time, str(e)[:200])
    raise SystemExit(f"{name}: no layer worked")


day, dl = first([("BlueMarble_NextGeneration", None), ("BlueMarble_ShadedRelief_Bathymetry", None), ("BlueMarble_ShadedRelief", None)], "day")
night, nl = first([("VIIRS_Black_Marble", "2016-01-01"), ("VIIRS_CityLights_2012", None), ("VIIRS_Black_Marble", None)], "night")
night = ImageEnhance.Contrast(night).enhance(1.3)
day.save(OUT / "day.jpg", quality=86, optimize=True, progressive=True)
night.save(OUT / "night.jpg", quality=86, optimize=True, progressive=True)
M["tex"] = {"day": dl, "night": nl, "w": W, "h": H, "credit": "NASA Blue Marble / Black Marble via GIBS"}
(OUT / "dem.json").write_text(json.dumps(M), encoding="utf-8")
print({k: (OUT / k).stat().st_size for k in ("day.jpg", "night.jpg")})
