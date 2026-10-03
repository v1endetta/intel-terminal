import os, json, requests
os.makedirs("out16", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
U = {"dgpa": "https://www.dgpa.gov.tw/typh/daily/nds.html",
     "wra_res": "https://fhy.wra.gov.tw/WraApi/v1/Reservoir/RealTimeInfo",
     "wra_res2": "https://data.wra.gov.tw/Service/OpenData.aspx?format=json&id=1602CA19-B224-4CC3-AA31-11B1B124530F",
     "cpc": "https://vipmbr.cpc.com.tw/cpcstn/ListPriceWebService.asmx/getCPCMainProdListPrice_XML",
     "pbs_ds": "https://data.gov.tw/api/v2/rest/dataset/15221",
     "pbs": "https://od.moi.gov.tw/MOI/v1/pbs",
     "aqi_nokey": "https://data.moenv.gov.tw/api/v2/aqx_p_432?format=json&limit=5",
     "tpe_mrt_crowd": "https://api.metro.taipei/metroapi/CarWeight.asmx",
     "ncdr": "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx",
     "ncdr2": "https://alerts.ncdr.nat.gov.tw/JSONAtomFeeds.ashx",
     "tpe_rain": "https://wic.heo.taipei/OpenData/API/Rain/Get?stationNo=&loginId=open_rain&dataKey=85452C1D",
     "kh_park": "https://api.kcg.gov.tw/api/service/Get/2c1d4e8c-2b5b-4bbd-a6f2-cfc22e1a4e19",
     "tpe_bus_eta": "https://tcgbusfs.blob.core.windows.net/blobbus/GetEstimateTime.gz",
     "tpe_mrt_info": "https://tcgbusfs.blob.core.windows.net/dotapp/news.json",
     "taipower_out": "https://www.taipower.com.tw/d006/loadGraph/loadGraph/data/genloadareaperc.csv"}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=30); t = r.content[:600]
        try: t = t.decode("utf-8", "replace")
        except Exception: t = str(t)
        rep[k] = {"status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "head": t}
    except Exception as e:
        rep[k] = {"err": repr(e)[:150]}
json.dump(rep, open("out16/report.json", "w"), ensure_ascii=False, indent=1)
