"""一次性連線測試第二輪：海事局分站、NGA HYDROPAC 內容、日本統合幕僚監部替代路徑。"""
import io, re, time, json, datetime, requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8"}


def probe(k, u, show=260):
    t0 = time.time()
    try:
        r = requests.get(u, headers=H, timeout=(15, 30))
        txt = r.content.decode("utf-8", "ignore")
        head = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", txt, flags=re.S)))[:show]
        hits = {w: txt.count(w) for w in ["航行警告", "实弹", "射击", "军事", "台湾海峡", "中国海軍", "Just a moment"] if w in txt}
        print(f"PROBE {k} {'OK ' if r.ok else 'BAD'} {r.status_code} {len(r.content)}B {time.time()-t0:.1f}s final={r.url[:100]}\n   hits={hits}\n   head={head}")
        return r if r.ok else None
    except Exception as e:  # noqa: BLE001
        print(f"PROBE {k} ERR {repr(e)[:160]}")


# 1. 海事局各分站（台海相關：福建、廈門、廣東、浙江）
for k, u in [("fj", "https://www.fj.msa.gov.cn/"), ("xm", "https://www.xm.msa.gov.cn/"), ("gd", "https://www.gd.msa.gov.cn/"),
             ("zj", "https://www.zj.msa.gov.cn/"), ("sh_list", "https://www.sh.msa.gov.cn/hxtjgsj/index.jhtml")]:
    r = probe("msa_" + k, u)
    if r is not None:
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*(?:航行警告|航警|实弹|射击|军事)[^<]*)</a>', r.content.decode("utf-8", "ignore"))[:8]
        for h, t in links:
            print(f"   LINK {t.strip()[:50]} -> {h[:120]}")

# 2. NGA HYDROPAC：中國相關航警的數量、最新日期、樣本
r = requests.get("https://msi.nga.mil/api/publications/broadcast-warn?navArea=P&status=active&output=json", headers=H, timeout=30)
ws = r.json()["broadcast-warn"]
cn = [w for w in ws if re.search(r"CHINA|TAIWAN|EAST CHINA SEA|SOUTH CHINA SEA|YELLOW SEA|BOHAI", w["text"])]
print(f"PROBE nga total={len(ws)} china_related={len(cn)}")
for w in sorted(cn, key=lambda w: w.get("issueDate", ""), reverse=True)[:12]:
    t = re.sub(r"\s+", " ", w["text"])
    print(f"   NGA {w['msgYear']}/{w['msgNumber']} issue={w.get('issueDate')} auth={w.get('authority','')[:40]} | {t[:230]}")
print("   NGA keys=", list(ws[0].keys()))

# 3. 日本統合幕僚監部：列表頁被 Cloudflare 擋，試其他路徑
for k, u in [("js_top", "https://www.mod.go.jp/js/"), ("js_en", "https://www.mod.go.jp/js/en/"), ("mod_press", "https://www.mod.go.jp/j/press/index.html"),
             ("mod_rss", "https://www.mod.go.jp/rss/whatsnew.xml"), ("js_keikai_en", "https://www.mod.go.jp/js/en/activity/domestic/keikai2026.html")]:
    probe(k, u, 160)
# PDF 直接猜檔名：最近 5 天、每天 _01～_08
today = datetime.date(2026, 10, 17)
found = []
for d in range(0, 6):
    day = today - datetime.timedelta(days=d)
    for i in range(1, 9):
        u = f"https://www.mod.go.jp/js/pdf/{day.year}/p{day:%Y%m%d}_{i:02d}.pdf"
        try:
            s = requests.head(u, headers=H, timeout=15).status_code
        except Exception as e:  # noqa: BLE001
            s = repr(e)[:40]
        if s == 200:
            found.append(u)
print(f"PROBE js_pdf_guess found={len(found)} {found}")
try:
    import pypdf
    for u in found[:3]:
        b = requests.get(u, headers=H, timeout=30).content
        t = re.sub(r"\s+", "", "".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(b)).pages[:1]))
        print(f"   PDF {u[-20:]} {t[:200]}")
except Exception as e:  # noqa: BLE001
    print("   PDF parse err", repr(e)[:120])

# 4. 中國軍網：東部戰區相關
r = probe("81cn_dzzq", "http://www.81.cn/", 80)
if r is not None:
    for h, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*东部战区[^<]*)</a>', r.content.decode("utf-8", "ignore"))[:6]:
        print(f"   LINK {t.strip()[:50]} -> {h[:120]}")
print("PROBE_DONE")
