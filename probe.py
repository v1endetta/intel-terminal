import os, json, re, requests, io, zipfile
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
j = S.get("https://data.gov.tw/api/v2/rest/dataset/5959", timeout=40).json()["result"]
rep["ds5959"] = {"title": j.get("title"), "freq": j.get("updateFrequency"), "notes": (j.get("notes") or "")[:800], "desc": (j.get("description") or "")[:400],
                 "dist": [(d.get("resourceDescription", "")[:60], d.get("resourceFormat"), d.get("resourceDownloadUrl")) for d in (j.get("distribution") or [])][:6]}
r = S.get("https://gazette.nat.gov.tw/old/OpenData/latest.jsp", timeout=40); r.encoding = r.apparent_encoding
rep["latest_jsp"] = {"status": r.status_code, "ct": r.headers.get("content-type"), "links": list(dict.fromkeys(re.findall(r'href="([^"]+)"', r.text)))[:40], "text": re.sub(r"<[^>]+>", " ", r.text)[:1500]}
for d in rep["ds5959"]["dist"][:2]:
    u = d[2]
    try:
        x = S.get(u, timeout=90)
        info = {"status": x.status_code, "ct": x.headers.get("content-type"), "len": len(x.content)}
        b = x.content
        if b[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(b)); info["zip"] = [(i.filename, i.file_size) for i in z.infolist()][:10]
            b = z.read(z.infolist()[0])
        t = b.decode("utf-8", "replace"); info["head"] = t[:3000]
        info["kinds"] = re.findall(r"<Category>([^<]+)</Category>|<類別>([^<]+)</類別>|<ChapterName>([^<]+)</ChapterName>", t)[:30]
        rep["dl " + u] = info
    except Exception as e:
        rep["dl " + u] = {"err": repr(e)[:200]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
