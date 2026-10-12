#!/usr/bin/env python3
"""預先烘焙五都市區的航空正射影像（國土測繪中心 PHOTO2，政府資料開放授權）。

在 Google Cloud Shell 執行（台灣 IP 抓得到，不收費）：
  抓 z16 圖磚 → 每 16×16 張拼成一塊 4096px（電腦版）與 2048px（手機版）JPEG
  → 輸出到 out/3d/ortho/<city>/ 與 out/3d/ortho/index.json
可中斷重跑：已下載的圖磚會跳過。
"""
import io, json, math, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

Z = 16
CH = 16                       # 一塊 = 16×16 張圖磚
URL = "https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/GoogleMapsCompatible/{z}/{y}/{x}"
CITIES = {                    # 與 3d/buildings.json 的範圍一致
    "taipei": [121.40, 24.96, 121.66, 25.14],
    "taoyuan": [121.18, 24.93, 121.36, 25.04],
    "taichung": [120.58, 24.08, 120.76, 24.23],
    "tainan": [120.15, 22.94, 120.27, 23.04],
    "kaohsiung": [120.26, 22.56, 120.38, 22.71],
}
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

def fetch(xy):
    x, y = xy
    p = f"{TILES}/{Z}/{x}_{y}.jpg"
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return "skip"
    for k in range(4):
        try:
            req = urllib.request.Request(URL.format(z=Z, x=x, y=y), headers=UA)
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

def main():
    os.makedirs(f"{TILES}/{Z}", exist_ok=True)
    index = {"z": Z, "chunk": CH, "credit": "航照 © 內政部國土測繪中心", "cities": {}}
    for city, (w, s, e, n) in CITIES.items():
        x0, x1 = int(tx(w, Z)) // CH, int(tx(e, Z)) // CH
        y0, y1 = int(ty(n, Z)) // CH, int(ty(s, Z)) // CH
        need = [(cx * CH + i, cy * CH + j) for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1) for i in range(CH) for j in range(CH)]
        print(f"{city}: {x1 - x0 + 1}×{y1 - y0 + 1} 塊，{len(need)} 張圖磚", flush=True)
        stats = {}
        with ThreadPoolExecutor(8) as ex:
            for k, r in enumerate(ex.map(fetch, need)):
                stats[r] = stats.get(r, 0) + 1
                if k % 500 == 499:
                    print(f"  {k + 1}/{len(need)} {stats}", flush=True)
        print(f"  完成 {stats}", flush=True)
        os.makedirs(f"{OUT}/{city}", exist_ok=True)
        chunks = []
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                im = Image.new("RGB", (CH * 256, CH * 256), (92, 96, 92))
                got = 0
                for i in range(CH):
                    for j in range(CH):
                        p = f"{TILES}/{Z}/{cx * CH + i}_{cy * CH + j}.jpg"
                        if os.path.exists(p) and os.path.getsize(p) > 0:
                            try:
                                im.paste(Image.open(p).convert("RGB").resize((256, 256)), (i * 256, j * 256)); got += 1
                            except Exception:
                                pass
                if got < CH * CH * 0.1:
                    continue
                name = f"{cx}_{cy}"
                im.save(f"{OUT}/{city}/{name}.jpg", quality=68, optimize=True, progressive=True)
                im.resize((2048, 2048), Image.LANCZOS).save(f"{OUT}/{city}/{name}_m.jpg", quality=70, optimize=True, progressive=True)
                X0, X1, Y0, Y1 = cx * CH, (cx + 1) * CH, cy * CH, (cy + 1) * CH
                chunks.append({"id": name, "w": lon_of(X0, Z), "e": lon_of(X1, Z), "n": lat_of(Y0, Z), "s": lat_of(Y1, Z), "fill": round(got / CH / CH, 2)})
        index["cities"][city] = chunks
        print(f"  {len(chunks)} 塊已輸出", flush=True)
    json.dump(index, open(f"{OUT}/index.json", "w"), ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs)
    print(f"全部完成，輸出 {tot / 1e6:.1f} MB", flush=True)

if __name__ == "__main__":
    main()
