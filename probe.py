import os, gzip, json, requests, traceback
os.makedirs("out6", exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session(); S.headers["User-Agent"] = UA
U = {
 "tpe_yb": ("GET", "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json", None),
 "yb_station": ("GET", "https://apis.youbike.com.tw/json/station-yb2.json", None),
 "yb_area": ("GET", "https://apis.youbike.com.tw/json/area-all.json", None),
 "yb_park": ("POST", "https://apis.youbike.com.tw/tw2/parkingInfo", {"station_no": ["500101001", "500101002"]}),
 "ntpc_yb": ("GET", "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json?page=0&size=5", None),
 "tc_yb": ("GET", "https://datacenter.taichung.gov.tw/swagger/OpenData/9af00e84-473a-4f3d-99be-b875d8e86256", None),
 "kh_yb": ("GET", "https://api.kcg.gov.tw/api/service/Get/b4dd9c40-9027-4125-8666-06bef1756092", None),
 "fw_pairlive": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/ETagPairLive.xml", None),
 "fw_pair": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/ETagPair.xml", None),
 "fw_etag": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/ETag.xml", None),
 "fw_secshape": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/SectionShape.xml", None),
 "fw_seclive": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/SectionLive.xml", None),
 "fw_section": ("GET", "https://tisvcloud.freeway.gov.tw/history/motc20/Section.xml", None),
 "tpe_air": ("GET", "https://www.taoyuan-airport.com/uploads/flightx/a_flight_v4.txt", None),
 "tpe_park_desc": ("GET", "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json", None),
 "tpe_park_av": ("GET", "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json", None),
 "tpe_vd": ("GET", "https://tcgbusfs.blob.core.windows.net/blobtisv/GetVDDATA.xml.gz", None),
}
rep = {}
for k, (m, u, body) in U.items():
    try:
        r = S.request(m, u, json=body, timeout=40)
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        txt = raw.decode("utf-8-sig", errors="replace")
        rep[k] = {"status": r.status_code, "bytes": len(r.content), "ct": r.headers.get("content-type"), "head": txt[:1500]}
        open(f"out6/{k}.txt", "w").write(txt[:400000])
    except Exception as e:
        rep[k] = {"err": repr(e)[:300]}
json.dump(rep, open("out6/report.json", "w"), ensure_ascii=False, indent=1)
