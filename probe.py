import os, json, re, requests, xml.etree.ElementTree as ET
os.makedirs("out10", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"
Q = ["嘖嘖 集資", "嘖嘖 募資", "flyingV 募資", "集資 破千萬", "募資 破百萬", "集資 達標", "集資 刷新紀錄", "群眾集資 台灣 品牌",
     "貝殼放大", "群募貝果", "集資 趨勢", "募資平台 台灣", "集資 操盤"]
rep = {}
for q in Q:
    r = S.get("https://news.google.com/rss/search", params={"q": q, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}, timeout=30)
    root = ET.fromstring(r.content)
    rep[q] = [(it.findtext("pubDate"), it.findtext("title")) for it in root.iter("item")][:15]
json.dump(rep, open("out10/report.json", "w"), ensure_ascii=False, indent=1)
