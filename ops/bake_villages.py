"""一次性：村里中心點（內政部國土測繪中心 村里界圖 TWD97經緯度）→ 3d/villages.json：[[縣市, 鄉鎮, 村里, 經度, 緯度]]。
用來把「村里層級的人口遷徙」換算成任意半徑內的合計。"""
import io, json, sys, zipfile, urllib.request
import shapefile   # pyshp

URLS = ["https://www.tgos.tw/tgos/VirtualDir/Product/a04697c8-64db-450a-a105-3eb471c45abd/村(里)界(TWD97經緯度).zip"]


def main(out):
    import urllib.parse
    raw = None
    for u in URLS:
        q = urllib.parse.quote(u, safe=":/()")
        raw = urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()
        if raw:
            break
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    shp = next(n for n in names if n.lower().endswith(".shp"))
    base = shp[:-4]
    pick = lambda ext: next(n for n in names if n.lower() == (base + ext).lower())
    r = shapefile.Reader(shp=io.BytesIO(z.read(shp)), dbf=io.BytesIO(z.read(pick(".dbf"))), shx=io.BytesIO(z.read(pick(".shx"))), encoding="utf-8")
    flds = [f[0] for f in r.fields[1:]]
    try:
        r.record(0)
    except UnicodeDecodeError:
        r = shapefile.Reader(shp=io.BytesIO(z.read(shp)), dbf=io.BytesIO(z.read(pick(".dbf"))), shx=io.BytesIO(z.read(pick(".shx"))), encoding="cp950")
    g = lambda rec, *ks: next((str(rec[f]) for f in flds for k in ks if f.upper() == k), "")
    rows = []
    for sr in r.iterShapeRecords():
        pts = sr.shape.points
        if not pts:
            continue
        # 面積加權中心（最大的那一塊）
        parts = list(sr.shape.parts) + [len(pts)]
        best, bA = None, 0
        for i in range(len(parts) - 1):
            ring = pts[parts[i]:parts[i + 1]]
            A = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
                c = x0 * y1 - x1 * y0; A += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
            if abs(A) > bA and A:
                bA, best = abs(A), (cx / (3 * A), cy / (3 * A))
        if not best:
            continue
        rec = sr.record
        rows.append([g(rec, "COUNTYNAME").replace("台", "臺"), g(rec, "TOWNNAME"), g(rec, "VILLNAME"), round(best[0], 5), round(best[1], 5)])
    json.dump({"src": "內政部國土測繪中心 村里界圖（TWD97經緯度），面積加權中心", "fields": flds, "v": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(rows), flds)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "villages.json")
