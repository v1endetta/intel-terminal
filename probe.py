import os, json, requests, time
os.makedirs("out20", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
rep = {}
def tree(o, d=0):
    if d > 4: return "…"
    if isinstance(o, dict): return {k: tree(v, d + 1) for k, v in list(o.items())[:20]}
    if isinstance(o, list): return [len(o), tree(o[0], d + 1)] if o else [0]
    return str(o)[:50]
U = {
 "lass_airbox": "https://pm25.lass-net.org/API-1.0.0/project/airbox/latest/",
 "lass_all": "https://pm25.lass-net.org/API-1.0.0/project/all/latest/",
 "civiliot_air": "https://sta.ci.taiwan.gov.tw/STA_AirQuality_v2/v1.0/Things?$top=2&$expand=Locations",
 "civiliot_water": "https://sta.ci.taiwan.gov.tw/STA_WaterResource_v2/v1.0/Things?$top=2&$expand=Locations",
 "civiliot_flood": "https://sta.ci.taiwan.gov.tw/STA_WaterResource_v2/v1.0/Things?$filter=substringof('淹水',name)&$top=2&$expand=Locations,Datastreams/Observations($top=1)",
 "civiliot_earth": "https://sta.ci.taiwan.gov.tw/STA_Earthquake_v2/v1.0/Things?$top=1",
 "moenv_aqi_nokey": "https://data.moenv.gov.tw/api/v2/aqx_p_432?format=json&limit=2",
 "pbs_road": "https://data.moi.gov.tw/MoiOD/System/DownloadFile.aspx?DATA=36384FA8-FACF-432E-BB5B-5F015E7BC1BE",
 "adsb_lol": "https://api.adsb.lol/v2/point/23.7/121/250",
 "opensky": "https://opensky-network.org/api/states/all?lamin=21.5&lomin=118&lamax=26.5&lomax=123",
 "plvr": "https://plvr.land.moi.gov.tw/DownloadSeason?season=115S3&type=zip&fileName=lvr_landcsv.zip",
 "taipei_1999": "https://data.taipei/api/v1/dataset/1bbde7d3-6e12-4d1d-8b2c-2ec2f5f9b6c5?scope=resourceAquire&limit=2",
 "ntpc_garbage": "https://data.ntpc.gov.tw/api/datasets/28ab4122-60e1-4065-98e5-abccb69aaca6/json?page=0&size=2",
 "taipower_outage": "https://service.taipower.com.tw/data/opendata/apply/file/d007008/001.json",
 "fire_tpe": "https://www.119.gov.taipei/detail.php?type=article&id=11519",
 "cctv_freeway": "https://cctv-ss04.thb.gov.tw:443/T2-1K+300",
 "thb_cctv_list": "https://thbapp.thb.gov.tw/opendata/cctv/list.xml",
 "atlas_npm": "https://registry.npmjs.org/taiwan-atlas",
 "gnews_town": "https://news.google.com/rss/search?q=%E4%BF%A1%E7%BE%A9%E5%8D%80+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
 "moenv_quake_free": "https://scweb.cwa.gov.tw/zh-tw/earthquake/data",
}
for k, u in U.items():
    try:
        t0 = time.time(); r = S.get(u, timeout=25, stream=True)
        body = r.raw.read(400000, decode_content=True)
        info = {"status": r.status_code, "ct": r.headers.get("content-type", "")[:40], "len": len(body), "cors": r.headers.get("access-control-allow-origin"), "sec": round(time.time()-t0,1)}
        try:
            j = json.loads(body); info["tree"] = tree(j)
        except Exception:
            info["head"] = body[:300].decode("utf-8", "replace")
        rep[k] = info
    except Exception as e:
        rep[k] = repr(e)[:160]
open("out20/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
