"""一次性連線測試：台海新來源從 GitHub 抓不抓得到（測完刪掉這個分支）。"""
import re, time, urllib.parse, requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
WARN = "9C219298-B27F-460E-995A-99401B3FF6AF"   # 海事局「航行警告」頻道
FJ = "7B084057-6038-4570-A0FB-44E9204C4B1D"     # 福建海事局
T = [
    ("msa_home", "GET", "https://www.msa.gov.cn/", None),
    ("msa_warn_page", "GET", f"https://www.msa.gov.cn/page/channelArticles.do?channelids={WARN}", None),
    ("msa_list_ajax", "POST", "https://www.msa.gov.cn/page/openInfo/articleList.do", {"channelId": WARN, "pageSize": "20", "pageNo": "1", "isParent": "0"}),
    ("msa_list_ajax_get", "GET", f"https://www.msa.gov.cn/page/openInfo/articleList.do?channelId={WARN}&pageSize=20&pageNo=1&isParent=0", None),
    ("msa_wap", "GET", f"https://www.msa.gov.cn/msacncms_wap//pages/info_report.do?channelId={WARN}", None),
    ("msa_fujian", "GET", f"https://www.msa.gov.cn/page/channelArticles.do?channelids={FJ}", None),
    ("sh_msa", "GET", "https://www.sh.msa.gov.cn/hxtjgsj/index.jhtml", None),
    ("nga_hydropac", "GET", "https://msi.nga.mil/api/publications/broadcast-warn?navArea=P&status=active&output=json", None),
    ("jcg_navarea11", "GET", "https://www1.kaiho.mlit.go.jp/TUHO/navarea/index.html", None),
    ("jp_js_keikai", "GET", "https://www.mod.go.jp/js/activity/domestic/keikai2026.html", None),
    ("jp_js_press", "GET", "https://www.mod.go.jp/js/press/", None),
    ("jp_js_pdf", "GET", "https://www.mod.go.jp/js/pdf/2026/p20261015_02.pdf", None),
    ("eastern_theater_weibo", "GET", "https://weibo.com/u/7480766035", None),
    ("chinamil_news", "GET", "http://www.81.cn/", None),
]
KW = ["航行警告", "实弹", "射击", "台湾海峡", "军事", "LIVE FIR", "GUNNERY", "TAIWAN", "CHINA", "中国海軍", "遼寧", "中国軍機"]
for k, m, u, data in T:
    t0 = time.time()
    try:
        r = requests.request(m, u, data=data, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=(15, 30), allow_redirects=True)
        b = r.content
        txt = b.decode(r.encoding or "utf-8", "ignore") if "pdf" not in r.headers.get("Content-Type", "") else ""
        hits = {w: txt.count(w) for w in KW if w in txt}
        head = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt))[:260]
        links = re.findall(r'href="([^"]*(?:article|detail|content|pdf)[^"]*)"', txt)[:6]
        print(f"PROBE {k} {'OK ' if r.ok else 'BAD'} {r.status_code} {len(b)}B {time.time()-t0:.1f}s final={r.url[:90]} ct={r.headers.get('Content-Type','')[:30]}")
        print(f"   hits={hits}")
        print(f"   head={head}")
        if links: print(f"   links={links}")
    except Exception as e:  # noqa: BLE001
        print(f"PROBE {k} ERR {time.time()-t0:.1f}s {repr(e)[:200]}")
print("PROBE_DONE")
