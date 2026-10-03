import os, requests, time
os.makedirs("out17", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
for k, u in {"ncdr": "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx", "dgpa": "https://www.dgpa.gov.tw/typh/daily/nds.html",
             "cpc": "https://vipmbr.cpc.com.tw/cpcstn/ListPriceWebService.asmx/getCPCMainProdListPrice_XML",
             "ncdr_json": "https://alerts.ncdr.nat.gov.tw/JSONAtomFeeds.ashx"}.items():
    try:
        r = S.get(u, timeout=40); open(f"out17/{k}.txt", "wb").write(r.content[:900000])
    except Exception as e:
        open(f"out17/{k}.txt", "w").write("ERR " + repr(e))
    time.sleep(4)
