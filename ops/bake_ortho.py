#!/usr/bin/env python3
"""預先烘焙航空正射影像（國土測繪中心 PHOTO2，政府資料開放授權）。

在 Google Cloud Shell 執行（台灣 IP 抓得到，不收費）。兩層：
  市區：五都＋其他縣市市中心，z16（約 2 公尺一像素）→ out/3d/ortho/<city>/
  全島：台灣本島＋澎湖，z14（約 9 公尺一像素），只做有陸地的塊 → out/3d/ortho/base/
每 16×16 張圖磚拼成一塊 4096px（電腦版）與 2048px（手機版）JPEG，索引在 out/3d/ortho/index.json。
可中斷重跑：已下載的圖磚會跳過。
"""
import io, json, math, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

Z = 16                        # 市區層
ZB = 14                       # 全島底圖層
CH = 16                       # 一塊 = 16×16 張圖磚
URL = "https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/GoogleMapsCompatible/{z}/{y}/{x}"
CITIES = {                    # 與 3d/buildings.json 的範圍一致
    "taipei": [121.40, 24.96, 121.66, 25.14],
    "taoyuan": [121.18, 24.93, 121.36, 25.04],
    "taichung": [120.58, 24.08, 120.76, 24.23],
    "tainan": [120.15, 22.94, 120.27, 23.04],
    "kaohsiung": [120.26, 22.56, 120.38, 22.71],
    # 其他縣市的市中心（新北板橋已在台北範圍內；金門、連江不在 3D 地形範圍內，先不做）
    "keelung": [121.70, 25.10, 121.79, 25.16],
    "hsinchu": [120.93, 24.77, 121.03, 24.85],    # 新竹市＋竹北
    "miaoli": [120.79, 24.54, 120.85, 24.59],
    "changhua": [120.51, 24.05, 120.58, 24.11],
    "nantou": [120.66, 23.89, 120.71, 23.93],
    "douliu": [120.51, 23.69, 120.57, 23.73],
    "chiayi": [120.41, 23.45, 120.49, 23.50],
    "pingtung": [120.46, 22.64, 120.52, 22.70],
    "yilan": [121.72, 24.66, 121.79, 24.78],      # 宜蘭市＋羅東
    "hualien": [121.58, 23.95, 121.63, 24.01],
    "taitung": [121.11, 22.73, 121.17, 22.79],
    "penghu": [119.55, 23.55, 119.61, 23.59],     # 馬公
}
ISLAND = [119.30, 21.88, 122.02, 25.32]          # 3D 地形範圍內的本島＋澎湖
TILES = "tiles"
OUT = "out/3d/ortho"
UA = {"User-Agent": "dalta-intel-terminal/1.0 (personal, non-commercial)"}

def tx(lon, z): return (lon + 180) / 360 * 2 ** z
def ty(lat, z):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z
def lon_of(x, z): return x / 2 ** z * 360 - 180
def lat_of(y, z):
    n = math.pi - 2 * math.pi * y / 2 ** z
    return math.degrees(math.atan(math.sinh(n)))

def fetch(zxy):
    z, x, y = zxy
    p = f"{TILES}/{z}/{x}_{y}.jpg"
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return "skip"
    for k in range(4):
        try:
            req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
            if len(b) < 200:            # 範圍外常回空白小圖
                open(p, "wb").write(b"")
                return "empty"
            open(p, "wb").write(b)
            return "ok"
        except Exception as e:
            if getattr(e, "code", 0) == 404:
                open(p, "wb").write(b"")
                return "empty"
            time.sleep(2 + k * 3)
    return "fail"

def land_polys():
    """縣市界（repo 的 tw_counties.json）→ 外環座標列表，用來跳過全是海的塊。"""
    try:
        d = json.load(urllib.request.urlopen("https://raw.githubusercontent.com/v1endetta/intel-terminal/main/tw_counties.json", timeout=60))
    except Exception:
        return None
    rings = []
    for f in d["features"]:
        g = f["geometry"]; polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            r = poly[0]
            xs = [p[0] for p in r]; ys = [p[1] for p in r]
            rings.append((min(xs), min(ys), max(xs), max(ys), r))
    return rings

def inside(r, x, y):
    c = False; n = len(r)
    for i in range(n):
        x1, y1 = r[i]; x2, y2 = r[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

def has_land(rings, w, s, e, n):
    if rings is None:
        return True
    near = [r for r in rings if r[0] < e and r[2] > w and r[1] < n and r[3] > s]
    if not near:
        return False
    for _, _, _, _, r in near:                     # 縣市界的點落在這塊裡
        for x, y in r[::5]:
            if w <= x <= e and s <= y <= n:
                return True
    for i in range(9):                             # 或這塊裡的格點落在陸地上
        for j in range(9):
            x, y = w + (e - w) * (i + 0.5) / 9, s + (n - s) * (j + 0.5) / 9
            if any(inside(r[4], x, y) for r in near):
                return True
    return False

def bake(z, bbox, outdir, rings=None, q=(68, 70)):
    w, s, e, n = bbox
    x0, x1 = int(tx(w, z)) // CH, int(tx(e, z)) // CH
    y0, y1 = int(ty(n, z)) // CH, int(ty(s, z)) // CH
    cks = [(cx, cy) for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1)]
    if rings is not None:
        cks = [(cx, cy) for cx, cy in cks if has_land(rings, lon_of(cx * CH, z), lat_of((cy + 1) * CH, z), lon_of((cx + 1) * CH, z), lat_of(cy * CH, z))]
    need = [(z, cx * CH + i, cy * CH + j) for cx, cy in cks for i in range(CH) for j in range(CH)]
    print(f"  {len(cks)} 塊，{len(need)} 張圖磚", flush=True)
    stats = {}
    with ThreadPoolExecutor(8) as ex:
        for k, r in enumerate(ex.map(fetch, need)):
            stats[r] = stats.get(r, 0) + 1
            if k % 1000 == 999:
                print(f"  {k + 1}/{len(need)} {stats}", flush=True)
    print(f"  下載完成 {stats}", flush=True)
    os.makedirs(outdir, exist_ok=True)
    chunks = []
    for cx, cy in cks:
        im = Image.new("RGB", (CH * 256, CH * 256), (92, 96, 92))
        got = 0
        for i in range(CH):
            for j in range(CH):
                p = f"{TILES}/{z}/{cx * CH + i}_{cy * CH + j}.jpg"
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    try:
                        im.paste(Image.open(p).convert("RGB").resize((256, 256)), (i * 256, j * 256)); got += 1
                    except Exception:
                        pass
        if got < CH * CH * 0.1:
            continue
        name = f"{cx}_{cy}"
        im.save(f"{outdir}/{name}.jpg", quality=q[0], optimize=True, progressive=True)
        im.resize((2048, 2048), Image.LANCZOS).save(f"{outdir}/{name}_m.jpg", quality=q[1], optimize=True, progressive=True)
        X0, X1, Y0, Y1 = cx * CH, (cx + 1) * CH, cy * CH, (cy + 1) * CH
        chunks.append({"id": name, "w": lon_of(X0, z), "e": lon_of(X1, z), "n": lat_of(Y0, z), "s": lat_of(Y1, z), "fill": round(got / CH / CH, 2)})
    print(f"  {len(chunks)} 塊已輸出", flush=True)
    return chunks

def main():
    for z in (Z, ZB):
        os.makedirs(f"{TILES}/{z}", exist_ok=True)
    index = {"z": Z, "chunk": CH, "credit": "航照 © 內政部國土測繪中心", "cities": {}}
    for city, bbox in CITIES.items():
        print(f"{city}（z{Z}）", flush=True)
        index["cities"][city] = bake(Z, bbox, f"{OUT}/{city}")
    print(f"全島底圖（z{ZB}）", flush=True)
    index["base"] = {"z": ZB, "chunk": CH, "chunks": bake(ZB, ISLAND, f"{OUT}/base", rings=land_polys(), q=(62, 66))}
    json.dump(index, open(f"{OUT}/index.json", "w"), ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs)
    print(f"全部完成，輸出 {tot / 1e6:.1f} MB", flush=True)

if __name__ == "__main__":
    main()
