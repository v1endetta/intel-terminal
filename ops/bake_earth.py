"""一次性：從 NASA GIBS（公有領域、免金鑰）抓整顆地球的白天衛星合成圖與夜間燈光圖，給開場「從地球縮到台灣」用。
輸出 3d/earth_day.jpg、3d/earth_night.jpg（電腦 4096×2048）與 *_m.jpg（手機 2048×1024），等距圓柱投影。"""
import io
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance

OUT = Path(__file__).resolve().parent.parent / "3d"
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"


def tile(layer, time, bbox, w, h):
    q = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:4326",
         "BBOX": ",".join(map(str, bbox)), "WIDTH": w, "HEIGHT": h, "FORMAT": "image/jpeg"}
    if time:
        q["TIME"] = time
    with urllib.request.urlopen(WMS + "?" + urllib.parse.urlencode(q), timeout=180) as r:
        b = r.read(); ct = r.headers.get("Content-Type", "")
    if not ct.startswith("image"):
        raise RuntimeError(f"{layer}: {ct} {b[:200]!r}")
    return Image.open(io.BytesIO(b)).convert("RGB")


def world(layer, time):
    """分 4×2 塊抓再拼（單次請求太大會被拒）。EPSG:4326 的 BBOX 順序是 lat0,lon0,lat1,lon1。"""
    W, H = 4096, 2048
    im = Image.new("RGB", (W, H))
    for i in range(4):
        for j in range(2):
            lon0, lon1 = -180 + i * 90, -180 + (i + 1) * 90
            lat1, lat0 = 90 - j * 90, 90 - (j + 1) * 90
            im.paste(tile(layer, time, (lat0, lon0, lat1, lon1), W // 4, H // 2), (i * W // 4, j * H // 2))
    return im


def first(cands, name):
    for layer, time in cands:
        try:
            im = world(layer, time)
            if max(e[1] for e in im.getextrema()) < 10:
                raise RuntimeError("blank")
            print(name, "←", layer, time); return im
        except Exception as e:  # noqa: BLE001
            print(name, "✗", layer, time, str(e)[:200])
    raise SystemExit(f"{name}: no layer worked")


day = first([("BlueMarble_NextGeneration", None), ("BlueMarble_ShadedRelief_Bathymetry", None)], "day")
night = first([("VIIRS_Black_Marble", "2016-01-01"), ("VIIRS_CityLights_2012", None)], "night")
night = ImageEnhance.Contrast(night).enhance(1.25)
for name, im, q in (("earth_day", day, 84), ("earth_night", night, 80)):
    im.save(OUT / f"{name}.jpg", quality=q, optimize=True, progressive=True)
    im.resize((2048, 1024), Image.LANCZOS).save(OUT / f"{name}_m.jpg", quality=q, optimize=True, progressive=True)
print({p.name: p.stat().st_size for p in OUT.glob("earth_*.jpg")})
