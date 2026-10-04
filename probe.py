import os, json, requests
os.makedirs("out18", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
U = {"culture_exh": "https://cloud.culture.tw/frontsite/trans/SearchShowAction.do?method=doFindTypeJ&category=6",
     "culture_show": "https://cloud.culture.tw/frontsite/trans/SearchShowAction.do?method=doFindTypeJ&category=1",
     "cdc_dengue": "https://od.cdc.gov.tw/eic/Dengue_Daily_last12m.json",
     "cdc_ili": "https://od.cdc.gov.tw/eic/NHI_InfluenzaLike.json",
     "moa_veg": "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx?$top=5",
     "ntpc_park_ds": "https://data.gov.tw/api/v2/rest/dataset/57826",
     "ntpc_park": "https://data.ntpc.gov.tw/api/datasets/e09b35a5-a738-48cc-b0f5-570b67ad9c78/json?page=0&size=3",
     "tpe_fire": "https://data.taipei/api/v1/dataset/0b544701-fb47-4fa9-90f1-15b1987da0f5?scope=resourceAquire&limit=3",
     "taiwan_events": "https://media.taiwan.net.tw/XMLReleaseALL_public/activity_C_f.json",
     "tourism_ds": "https://data.gov.tw/api/v2/rest/dataset/7279",
     "plvr": "https://plvr.land.moi.gov.tw/DownloadSeason?season=115S2&type=zip&fileName=lvr_landcsv.zip",
     "cwa_radar_png": "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Observation/O-A0058-003.png"}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=40, stream=True); b = r.raw.read(1500, decode_content=True); r.close()
        rep[k] = {"status": r.status_code, "ct": r.headers.get("content-type"), "len": r.headers.get("content-length"), "head": b[:700].decode("utf-8", "replace")}
    except Exception as e:
        rep[k] = {"err": repr(e)[:160]}
json.dump(rep, open("out18/report.json", "w"), ensure_ascii=False, indent=1)
