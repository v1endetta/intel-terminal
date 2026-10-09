import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
for u in ["https://gazette.nat.gov.tw/old/OpenData/list.jsp?flag=115", "https://gazette.nat.gov.tw/old/OpenData/help.jsp", "https://gazette.nat.gov.tw/old/OpenData/history.jsp"]:
    r = S.get(u, timeout=40); r.encoding = r.apparent_encoding
    rep[u] = {"links": [l for l in dict.fromkeys(re.findall(r'href="([^"]+)"', r.text)) if re.search(r"download|xml|zip|Download|\.jsp\?", l)][:40],
              "text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[1200:3500]}
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1)
