# 台灣抓取站：在 Google Cloud 彰化機房（asia-east1，台灣 IP）每 15 分鐘被叫醒一次。
# 只負責「抓 → 轉成精簡 JSON → 存進 intel-vault 的 bucket」，怎麼解讀交給 GitHub 上的 fetch.py。
# Cloud Run job 每次執行都從 GitHub 讀這支最新版，所以改這裡不用重新部署。
#
# 省錢規則（2026-11：10 月曾超出免費額度）：
# - 計費看「跑了幾秒」：即時路況、YouBike 每次都抓（並行，目標 30 秒內）；慢的工作依「第幾個 15 分鐘」輪班，每段有時限。
# - 深夜 00–06 點只在整點跑。
# - 寫檔（Class A）每月免費 5,000 次：即時資料合成一個檔 relay/latest/live.json.gz；
#   其他檔內容沒變就不寫；state 沒變就不寫；原始存檔每 3 小時一份。
import gzip, hashlib, json, os, re, time, urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BUCKET = os.environ.get("BUCKET", "intel-vault-510704-vault")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
FW = "https://tisvcloud.freeway.gov.tw/history/motc20/"
THB = "https://thbtrafficapp.thb.gov.tw/opendata/"
YB2 = "https://apis.youbike.com.tw/json/station-yb2.json"

# 每輪都抓（會變的）
LIVE = {
    "fw_live": FW + "LiveTraffic.xml",            # 國道路段即時車速、旅行時間、壅塞等級
    "fw_events": FW + "LiveEvents.xml",           # 國道即時事件（事故、施工、管制）
    "fw_news": FW + "News.xml",                   # 高公局路況新聞
    "fw_cms": FW + "CMSLive.xml",                 # 國道資訊看板即時內容
    "thb_live": THB + "section/livetrafficdata/LiveTrafficList.xml",  # 省道路段即時
    "thb_news": THB + "new/info/NewsList.xml",    # 公路局路況新聞
    "thb_cms": THB + "cms/two/CMSLiveList.xml",   # 省道看板即時內容
    "fw_etag": FW + "ETagPairLive.xml",           # 國道 eTag 門架之間的實際旅行時間
    "thb_etag": THB + "etagpair/five/ETagPairLive.xml",  # 省道 eTag 旅行時間
}
# 一天更新一次（路段名稱、形狀、看板位置）
STATIC = {
    "fw_section": FW + "Section.xml",
    "fw_shape": FW + "SectionShape.xml",
    "fw_cmsinfo": FW + "CMS.xml",
    "fw_level": FW + "CongestionLevel.xml",
    "thb_section": THB + "section/sectioninfo/SectionList.xml",
    "thb_shape": THB + "section/sectionshapeinfo/SectionShapeList.xml",
    "thb_cmsinfo": THB + "cms/info/CMSList.xml",
    "thb_level": THB + "section/congetioninfo/CongestionLevelList.xml",
    "fw_etagpair": FW + "ETagPair.xml",
    "fw_etaginfo": FW + "ETag.xml",
    "thb_etagpair": THB + "etag/info/ETagPairList.xml",
    "thb_etaginfo": THB + "etag/info/ETagList.xml",
    "fw_cctv": FW + "CCTV.xml",                   # 國道攝影機（位置、即時影像網址）
    "thb_cctv2": "https://cctv-maintain.thb.gov.tw/opendataCCTVs.xml",   # 省道攝影機（公路局）
}

T_START = time.time()
TPE = timezone(timedelta(hours=8))
NOW = datetime.now(TPE)
NOW_ISO = NOW.replace(microsecond=0).isoformat()
SLOT = NOW.minute // 15            # 這小時第幾個 15 分鐘（0–3），慢工作照這個輪班
NIGHT = NOW.hour < 7               # 00–06 點只在整點跑
HARD_END = T_START + 200           # Cloud Run 上限 240 秒，留餘裕
_tok = {"v": None, "exp": 0}
OPS = {"a": 0, "b": 0}             # 本輪 GCS 寫入（Class A）、讀取（Class B）次數
SEC = {}                           # 本輪各段花的秒數
_sec_end = [HARD_END]              # 目前這段的時限；get() 的 timeout 不會超過它


def left():
    return min(_sec_end[0], HARD_END) - time.time()


def log(*a):
    print("RELAY", *a, flush=True)


def token():
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    j = json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}), timeout=10).read())
    _tok["v"], _tok["exp"] = j["access_token"], time.time() + int(j.get("expires_in", 3000))
    return _tok["v"]


def gcs_put(name, data, ctype="application/gzip"):
    OPS["a"] += 1
    q = urllib.parse.quote(name, safe="")
    urllib.request.urlopen(urllib.request.Request(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={q}",
        data=data, method="POST", headers={"Authorization": "Bearer " + token(), "Content-Type": ctype}), timeout=60).read()


def gcs_get(name):
    OPS["b"] += 1
    q = urllib.parse.quote(name, safe="")
    try:
        return urllib.request.urlopen(urllib.request.Request(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{q}?alt=media",
            headers={"Authorization": "Bearer " + token()}), timeout=30).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get(url, timeout=40):
    timeout = max(3, min(timeout, left()))
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=timeout)
    b = r.read()
    if r.headers.get("Content-Encoding") == "gzip" or b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return b


def _tag(e):
    return e.tag.rsplit("}", 1)[-1]


def _val(s):
    s = (s or "").strip()
    if re.fullmatch(r"-?(0|[1-9]\d{0,8})", s):  # 0 開頭的編號（如 0001）保留字串
        return int(s)
    if re.fullmatch(r"-?(0|[1-9]\d{0,8})\.\d{1,8}", s):
        return float(s)
    return s


def _flat(e, pre=""):
    d = {}
    kids = list(e)
    tags = [_tag(c) for c in kids]
    for c, t in zip(kids, tags):
        k = pre + t
        sub = list(c)
        if not sub:
            d.setdefault(k, (c.text or "").strip() if t.endswith("ID") else _val(c.text))  # 重複的葉節點（如多個 category）留第一個
        elif len(sub) > 1 and len({_tag(x) for x in sub}) == 1:  # 重複子元素 → 陣列
            d[k] = [(_flat(x) if list(x) else _val(x.text)) for x in sub]
        else:
            d.update(_flat(c, k + "."))
    return d


def parse_xml(b):
    """任何「表頭 + 一長串同名元素」的 XML → {meta, cols, rows}。"""
    root = ET.fromstring(b)
    meta = {_tag(c): _val(c.text) for c in root if not list(c)}
    best, bn = None, 0
    ch = root.find("channel")
    if ch is not None:  # RSS：channel 底下混著 title、link 和一串 item，直接取 item
        recs = [_flat(k) for k in ch.findall("item")]
        cols = []
        for r in recs:
            for k in r:
                if k not in cols:
                    cols.append(k)
        return {"meta": {}, "cols": cols, "rows": [[r.get(c) for c in cols] for r in recs]}
    for el in root.iter():
        kids = list(el)
        if len(kids) > bn and len({_tag(k) for k in kids}) == 1:
            best, bn = el, len(kids)
    recs = [_flat(k) for k in (list(best) if best is not None else [])]
    cols = []
    for r in recs:
        for k in r:
            if k not in cols:
                cols.append(k)
    return {"meta": meta, "cols": cols, "rows": [[r.get(c) for c in cols] for r in recs]}


def youbike():
    st = json.loads(get(YB2))
    live_cols = ["no", "area", "bikes", "ebikes", "empty", "cap", "status", "upd"]
    rows, meta = [], []
    for x in st:
        det = x.get("available_spaces_detail") or {}
        rows.append([x.get("station_no"), x.get("area_code"), _val(str(x.get("available_spaces", ""))),
                     _val(str(det.get("eyb2", det.get("eyb", "")) or "")), _val(str(x.get("empty_spaces", ""))),
                     _val(str(x.get("parking_spaces", ""))), x.get("status"), x.get("updated_at")])
        meta.append([x.get("station_no"), x.get("area_code"), x.get("district_tw"), x.get("name_tw"),
                     _val(str(x.get("lat", ""))), _val(str(x.get("lng", "")))])
    return ({"meta": {"n": len(rows)}, "cols": live_cols, "rows": rows},
            {"meta": {"n": len(meta)}, "cols": ["no", "area", "dist", "name", "lat", "lng"], "rows": meta})


def gz(obj):
    return gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)


STATE: dict = {}


def put_doc(name, obj, ignore=()):
    """存 relay/<name>.json.gz，但內容（不含 at）跟上次一樣就不寫。寫了就把版本記進 idx，fetch.py 用它判斷本機快取能不能用。"""
    h = hashlib.sha1(json.dumps({k: v for k, v in obj.items() if k not in ignore}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    sh = STATE.setdefault("sh", {})
    if sh.get(name) == h:
        return False
    gcs_put(f"relay/{name}.json.gz", gz({"at": NOW_ISO, **obj}))
    sh[name] = h
    STATE.setdefault("idx", {})[name] = NOW_ISO
    return True


def _gt_open(u, ck):
    """Trends 需要 NID cookie；被 429 時把回應帶的 cookie 收起來再試一次。"""
    for i in range(3):
        h = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9", "Referer": "https://trends.google.com/trends/explore?geo=TW"}
        if ck:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items())
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=30)
            _gt_cookie(r.headers, ck)
            return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            _gt_cookie(e.headers, ck)
            if e.code != 429 or i == 2:
                raise
            time.sleep(4 + 4 * i)


def _gt_cookie(headers, ck):
    for c in headers.get_all("Set-Cookie") or []:
        kv = c.split(";")[0]
        if "=" in kv:
            k, v = kv.split("=", 1)
            ck[k.strip()] = v


def gtrends(state):
    """Google 搜尋趨勢（台灣、近 5 年每週、每個關鍵字各自 0–100；日資料舊的那段常被 Google 填 0，週資料穩定得多）。
    一次最多抓 12 個字（再多會被擋）：先補還沒有資料的字，之後兩批輪流、每批每 6 小時更新一次。"""
    kws = json.loads(get("https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/voice_keywords.json"))["keywords"]
    names = [k["k"] for k in kws]
    try:
        prev = json.loads(gzip.decompress(gcs_get("relay/latest/gtrends.json.gz") or gz({})))
    except Exception:  # noqa: BLE001
        prev = {}
    if prev.get("span") != "today 5-y":  # 時間範圍換了就整批重抓
        prev = {}
    kwd = {k: v for k, v in (prev.get("kw") or {}).items() if k in names}
    kat = {k: v for k, v in (prev.get("kat") or {}).items() if k in names}
    errs = {k: v for k, v in (prev.get("errs") or {}).items() if k in names}
    now = time.time()
    tried = state.setdefault("gt_tried", {})
    missing = [k for k in kws if k["k"] not in kwd and now - tried.get(k["k"], 0) > 3600]
    if missing:
        todo = missing[:12]
    elif now - state.get("gt_at4", 0) >= 3 * 3600:
        bi = state.get("gt_b", 0) % 2
        todo = kws[bi::2]
        state["gt_b"] = bi + 1
        state["gt_at4"] = now
    else:
        return
    ck, ok = {}, 0
    for u0 in ("https://trends.google.com/?geo=TW", "https://trends.google.com/trends/explore?geo=TW&hl=zh-TW"):
        try:
            _gt_open(u0, ck)
        except Exception as e:  # noqa: BLE001
            errs["_home"] = repr(e)[:160]
    for kw in todo:
        if left() < 15:
            break
        k, q = kw["k"], kw["q"]
        tried[k] = now
        try:
            req = {"comparisonItem": [{"keyword": q, "geo": "TW", "time": "today 5-y"}], "category": 0, "property": ""}
            u = "https://trends.google.com/trends/api/explore?" + urllib.parse.urlencode({"hl": "zh-TW", "tz": "-480", "req": json.dumps(req, ensure_ascii=False)})
            w = json.loads(_gt_open(u, ck)[4:])["widgets"]
            ts = [x for x in w if x["id"] == "TIMESERIES"][0]
            time.sleep(1.5)
            u2 = "https://trends.google.com/trends/api/widgetdata/multiline?" + urllib.parse.urlencode({"hl": "zh-TW", "tz": "-480", "req": json.dumps(ts["request"], ensure_ascii=False), "token": ts["token"]})
            tl = json.loads(_gt_open(u2, ck)[5:])["default"]["timelineData"]
            kwd[k] = [[datetime.fromtimestamp(int(x["time"]), timezone.utc).strftime("%Y-%m-%d"), (x.get("value") or [0])[0]] for x in tl if not x.get("isPartial")]
            kat[k] = NOW_ISO
            errs.pop(k, None)
            ok += 1
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:160]
        time.sleep(3)
    if ok:
        errs.pop("_home", None)
    state["gt_tried"] = {k: v for k, v in tried.items() if k in names}
    put_doc("latest/gtrends", {"span": "today 5-y", "kw": kwd, "kat": kat, "errs": errs})
    log("gtrends", len(todo), "tried", ok, "ok", len(kwd), "have")


# ---------- 官方統計（主計總處、交通部）：這些網站擋 GitHub／海外 IP，改在台灣抓。一天一次，失敗 6 小時後再試 ----------
DG = "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/"
DG_META = ["A030101015", "A030102015", "A030103015", "A030201015", "A030202015", "A030301015", "A040101010", "A040101020", "A040102010",
           "A018101010", "A018102010", "A018102080", "A018201010", "A030401015", "A030402015", "A030501015", "A030601015", "A030201010", "A030301010"]
# 跟台北市主計處同一套系統的「匯出 CSV」寫法（SDMX 只給結構不給數值）
DGW = "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sys=220&kind=21&type=0&outmode=12&compmode=00&outkind=3&deflst=2"


def stats_jobs():
    y = NOW.year
    cats = "+".join(str(i) for i in range(1, 82))
    jobs = {   # 主計總處「匯出 CSV」（SDMX 只給結構不給數值；試路用的項目已拿掉）
        "dgc2_cpi_basic": DGW + f"&ymf={y - 1913}01&ymt={y - 1911}12&funid=A030101015&cycle=1",
        "dgc2_cpi_special": DGW + f"&ymf={y - 1913}01&ymt={y - 1911}12&funid=A030103015&cycle=1",
        "dgc2_labor": DGW + f"&ymf={y - 1913}01&ymt={y - 1911}12&funid=A040101020&cycle=1",
        "dgc2_sa": DGW + f"&ymf={y - 1913}01&ymt={y - 1911}12&funid=A030601015&cycle=1",   # 季調表：可能有 PPI、進口物價
        "dgc2_gdp_q": DGW + f"&ymf={y - 1916}1&ymt={y - 1911}4&funid=A018101010&cycle=3",
        "dgc2_gdp_q2": DGW + f"&ymf={y - 1916}01&ymt={y - 1911}04&funid=A018101010&cycle=2",
    }
    return jobs


def stats_daily(state, errs):
    at = state.setdefault("stats_at", {})
    summ = state.setdefault("stats_summary", {})
    changed, t0, n = False, time.time(), 0
    for k, u in stats_jobs().items():
        if time.time() - at.get(k, 0) < 86400:
            continue
        if left() < 20 or n >= 3:   # 每輪最多 3 項、在這段時限內，其餘下一輪
            break
        n += 1
        rec = {"at": NOW_ISO, "url": u}
        try:
            b = get(u, 90)
            txt = b.decode("utf-8-sig", "replace")
            rec["len"] = len(b)
            try:
                js = json.loads(txt)
                rec["kind"] = "json"
                st = (js.get("data") or {}).get("structure") or js.get("structure") or {}
                dims = st.get("dimensions") or {}
                rec["dims"] = [[d.get("id"), d.get("name"), len(d.get("values") or []), [v.get("name") for v in (d.get("values") or [])][:12],
                                [v.get("id") for v in (d.get("values") or [])][:4] + [v.get("id") for v in (d.get("values") or [])][-3:]]
                               for grp in ("series", "observation") for d in (dims.get(grp) or [])]
                ser = (((js.get("data") or {}).get("dataSets") or [{}])[0].get("series")) or {}
                rec["n_series"] = len(ser)
                rec["n_obs"] = sum(len((v or {}).get("observations") or {}) for v in ser.values())
                put_doc(f"static/{k}", {"src": u, "json": js})
                at[k] = time.time() if rec["n_obs"] or k.startswith("dg_meta_") else time.time() - 86400 + 6 * 3600
            except ValueError:
                if txt.lstrip()[:1] == '"' and "<html" not in txt[:500].lower():   # 匯出的 CSV（第一列是分類名稱、之後一列一個月份）
                    rec["kind"] = "csv"; rec["head"] = txt[:400]; rec["n_lines"] = txt.count("\n")
                    put_doc(f"static/{k}", {"src": u, "csv": txt})
                    at[k] = time.time()
                    summ[k] = rec; changed = True
                    continue
                rec["kind"] = "html"
                rec["title"] = (re.search(r"<title>(.*?)</title>", txt, re.S) or [None, ""])[1].strip()[:80]
                body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", txt)
                rec["head"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()[:600]
                if k.endswith("_menu"):   # 目錄頁：留下所有功能代碼和名稱，之後找表號用
                    rec["funids"] = sorted(set(re.findall(r"funid=([A-Za-z0-9_]+)", txt)))[:600]
                    put_doc(f"static/{k}", {"src": u, "html": txt[:600000]})
                    at[k] = time.time()
                else:
                    at[k] = time.time() - 86400 + 6 * 3600
        except Exception as e:  # noqa: BLE001
            rec["err"] = repr(e)[:200]
            errs["stats:" + k] = rec["err"]
            at[k] = time.time() - 86400 + 6 * 3600
        summ[k] = rec
        changed = True
    if changed:   # 摘要裡的 at／len 每天會變；只在內容（種類、列數、錯誤）變了才寫
        put_doc("static/stats_summary", {"jobs": {k: {kk: vv for kk, vv in v.items() if kk not in ("at",)} for k, v in summ.items()}})


MOEA = {   # 經濟部統計處 2026-10 起對國外機房回 403：台灣 IP 每天代抓一次原始 CSV，fetch.py 抓不到時讀這份
    "moea_orders": "https://service.moea.gov.tw/EE520/opendata/b.csv",
    "moea_retail": "https://service.moea.gov.tw/EE520/opendata/%E7%B6%93%E6%BF%9F%E9%83%A8%E7%B5%B1%E8%A8%88%E8%99%95_%E6%89%B9%E7%99%BC%E3%80%81"
                   "%E9%9B%B6%E5%94%AE%E5%8F%8A%E9%A4%90%E9%A3%B2%E6%A5%AD%E7%87%9F%E6%A5%AD%E9%A1%8D%E6%8C%87%E6%95%B8.csv",
}


def moea_daily(state, errs):
    at = state.setdefault("moea_at", {})
    for k, u in MOEA.items():
        if time.time() - at.get(k, 0) < 86400:
            continue
        if left() < 15:
            break
        try:
            b = get(u, 60)
            try:
                txt = b.decode("utf-8-sig")
            except UnicodeDecodeError:
                txt = b.decode("big5", errors="ignore")
            if "<html" in txt[:500].lower() or len(txt) < 200:
                raise RuntimeError(f"not csv ({len(txt)}b)")
            put_doc(f"static/{k}", {"src": u, "csv": txt})
            at[k] = time.time()
        except Exception as e:  # noqa: BLE001
            errs["moea:" + k] = repr(e)[:200]
            at[k] = time.time() - 86400 + 6 * 3600   # 失敗的 6 小時後再試


CITY_CCTV = {   # 縣市交通局的路口攝影機（原始檔照存，fetch.py 解析）
    "tc_cctv": "https://newdatacenter.taichung.gov.tw/api/v1/no-auth/resource.download?rid=695dc746-4b1e-4d1d-98a8-a894e7d8dc81",
    "tn_cctv": "https://trafficopendata.tainan.gov.tw/opendata/json/cctv/latest",
}


def city_cctv(state, errs):
    at = state.setdefault("city_cctv_at", {})
    for k, u in CITY_CCTV.items():
        if time.time() - at.get(k, 0) < 86400:
            continue
        if left() < 15:
            break
        try:
            b = get(u, 60)
            txt = b.decode("utf-8-sig", "replace")
            if "\ufffd" in txt[:2000]:
                txt = b.decode("big5", "replace")
            put_doc(f"static/{k}", {"src": u, "raw": txt[:4_000_000]})
            at[k] = time.time()
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:200]
            at[k] = time.time() - 86400 + 6 * 3600


VILL_ZIP = "https://www.tgos.tw/tgos/VirtualDir/Product/a04697c8-64db-450a-a105-3eb471c45abd/" + urllib.parse.quote("村(里)界(TWD97經緯度).zip", safe="()")


def _shp_dbf_centroids(zbytes):
    """純標準函式庫讀 SHP＋DBF（國土測繪中心村里界）→ [[縣市, 鄉鎮, 村里, 經度, 緯度]]，中心用最大那塊的面積加權。"""
    import io, struct, zipfile
    z = zipfile.ZipFile(io.BytesIO(zbytes)); names = z.namelist()
    shp_n = next(n for n in names if n.lower().endswith(".shp")); base = shp_n[:-4]
    find = lambda ext: next((n for n in names if n.lower() == (base + ext).lower()), None)
    shp, dbf = z.read(shp_n), z.read(find(".dbf"))
    cpg = z.read(find(".cpg")).decode("ascii", "ignore").strip().lower() if find(".cpg") else ""
    enc = "utf-8" if "utf" in cpg else "cp950"
    nrec, hlen, rlen = struct.unpack("<IHH", dbf[4:12])
    fields, off = [], 32
    while dbf[off] != 0x0D:
        nm = dbf[off:off + 11].split(b"\0")[0].decode("ascii", "ignore"); fl = dbf[off + 16]; fields.append((nm, fl)); off += 32
    recs = []
    for i in range(nrec):
        r = dbf[hlen + i * rlen: hlen + (i + 1) * rlen]; pos, d = 1, {}
        for nm, fl in fields:
            raw = r[pos:pos + fl]
            try:
                d[nm] = raw.decode(enc).strip()
            except UnicodeDecodeError:
                d[nm] = raw.decode("cp950" if enc == "utf-8" else "utf-8", "replace").strip()
            pos += fl
        recs.append(d)
    out, pos, k = [], 100, 0
    while pos + 8 <= len(shp) and k < len(recs):
        clen = struct.unpack(">i", shp[pos + 4:pos + 8])[0] * 2; c = shp[pos + 8:pos + 8 + clen]; pos += 8 + clen
        rec = recs[k]; k += 1
        if len(c) < 44 or struct.unpack("<i", c[:4])[0] not in (5, 15, 25):
            continue
        npart, npt = struct.unpack("<ii", c[36:44])
        parts = list(struct.unpack(f"<{npart}i", c[44:44 + 4 * npart])) + [npt]
        p0 = 44 + 4 * npart
        pts = [struct.unpack("<dd", c[p0 + 16 * j:p0 + 16 * j + 16]) for j in range(npt)]
        best, bA = None, 0.0
        for i in range(npart):
            ring = pts[parts[i]:parts[i + 1]]
            A = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
                cr = x0 * y1 - x1 * y0; A += cr; cx += (x0 + x1) * cr; cy += (y0 + y1) * cr
            if A and abs(A) > bA:
                bA, best = abs(A), (cx / (3 * A), cy / (3 * A))
        if best:
            g = lambda *ks: next((rec[f] for f in rec for kk in ks if f.upper() == kk), "")
            out.append([g("COUNTYNAME").replace("台", "臺"), g("TOWNNAME"), g("VILLNAME"), round(best[0], 5), round(best[1], 5)])
    return out, [f[0] for f in fields]


def villages_once(state, errs):
    st = state.setdefault("vill", {"done": 0, "try": 0})
    if st.get("done") or time.time() - st.get("try", 0) < 6 * 3600 or left() < 60:
        return
    st["try"] = time.time()
    try:
        rows, flds = _shp_dbf_centroids(get(VILL_ZIP, 120))
        put_doc("static/villages", {"src": "內政部國土測繪中心 村里界圖（TWD97經緯度），面積加權中心", "fields": flds, "v": rows})
        st["done"] = time.time(); st["n"] = len(rows)
    except Exception as e:  # noqa: BLE001
        errs["villages"] = repr(e)[:200]



# ---------- 門牌級地址轉座標：fetch.py 上傳待辦地址（relay/in/geo_pending），這裡逐檔讀各縣市公開的門牌座標，比對到的存 relay/static/geo_b ----------
GEO_DS = {"高雄市": "177859", "桃園市": "157689", "臺南市": "120044", "新竹市": "157547", "苗栗縣": "178083", "臺東縣": "165619"}
_FW = str.maketrans("０１２３４５６７８９－–—ＡＢＣＤＥＦ　", "0123456789---ABCDEF ")
_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn2n(s):
    if s.isdigit():
        return s
    if s == "十":
        return "10"
    if s.startswith("十"):
        return str(10 + _CN.get(s[1:], 0))
    if s.endswith("十"):
        return str(_CN.get(s[0], 0) * 10)
    if "十" in s:
        a, b = s.split("十", 1)
        return str(_CN.get(a, 0) * 10 + _CN.get(b, 0))
    return str(_CN.get(s, 0)) if s in _CN else s


def addr_parts(addr):
    """地址 → (縣市, 鄉鎮, 街路段, 巷, 弄, 號)；號只取主號（7之6 → 7之6，285、285-1 → 285）。對不上回傳 None。"""
    a = str(addr or "").translate(_FW).replace(" ", "").replace("台", "臺")
    a = re.sub(r"^\d{3,6}", "", a)
    a = re.sub(r"[（(].*?[)）]", "", a)
    m = re.match(r"^(.{2}[縣市])(.{1,3}?[鄉鎮市區])(.*)$", a)
    if not m:
        return None
    cty, town, rest = m.groups()
    rest = re.sub(r"^[一-鿿]{1,3}[村里](?=[一-鿿0-9]*?(?:路|街|大道|道))", "", rest)   # 村里名
    rest = re.sub(r"^\d+鄰", "", rest)
    rest = re.sub(r"([一二三四五六七八九十]+)段", lambda x: _cn2n(x.group(1)) + "段", rest)
    rest = re.sub(r"([一二三四五六七八九十]+)(?=路)", lambda x: x.group(1), rest)
    m = re.match(r"^(.+?(?:路|街|大道|道)(?:\d+段)?|.+?段)(?:(\d+)巷)?(?:(\d+)弄)?(\d+)(?:之(\d+)|-(\d+))?(?:號|[、,，及和])", rest)
    if not m:
        m2 = re.match(r"^(.+?(?:路|街|大道|道)(?:\d+段)?)", rest)
        return (cty, town, m2.group(1), "", "", "") if m2 else None
    road, lane, alley, no, z1, z2 = m.groups()
    sub = z1 or z2
    return (cty, town, road, lane or "", alley or "", no + (f"之{sub}" if sub else ""))


def addr_key(p):
    return "|".join(p) if p else ""


def _twd97_to_wgs84(x: float, y: float):
    """TWD97 TM2（中央經線 121°）→ WGS84 經緯度。"""
    import math
    a, b = 6378137.0, 6356752.314245
    lon0, k0, dx = math.radians(121), 0.9999, 250000.0
    e = math.sqrt(1 - (b / a) ** 2)
    x -= dx
    m = y / k0
    mu = m / (a * (1 - e ** 2 / 4 - 3 * e ** 4 / 64 - 5 * e ** 6 / 256))
    e1 = (1 - math.sqrt(1 - e ** 2)) / (1 + math.sqrt(1 - e ** 2))
    fp = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    e2 = (e * a / b) ** 2
    c1 = e2 * math.cos(fp) ** 2
    t1 = math.tan(fp) ** 2
    r1 = a * (1 - e ** 2) / (1 - e ** 2 * math.sin(fp) ** 2) ** 1.5
    n1 = a / math.sqrt(1 - e ** 2 * math.sin(fp) ** 2)
    d = x / (n1 * k0)
    lat = fp - (n1 * math.tan(fp) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * e2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * e2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * e2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(fp)
    return round(math.degrees(lon), 5), round(math.degrees(lat), 5)


def _geo_resources(did):
    """資料集 → 要讀的 CSV 網址：有分年月的只取最新一期，分區的全取。"""
    res = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{did}", 40)).get("result") or {}
    ds = [d for d in res.get("distribution") or [] if (d.get("resourceFormat") or "").upper() == "CSV" and d.get("resourceDownloadUrl")]
    def ym(d):
        m = re.search(r"(\d{2,3})\s*年\s*(\d{1,2})?\s*月?", (d.get("resourceDescription") or "") + (d.get("resourceName") or ""))
        return (int(m.group(1)), int(m.group(2) or 0)) if m else None
    tags = [ym(d) for d in ds]
    if tags and all(tags) and len(set(tags)) > 1:
        last = max(tags)
        ds = [d for d, t in zip(ds, tags) if t == last]
    return [d["resourceDownloadUrl"].strip() for d in ds]


def _geo_scan(url, need, budget):
    """串流讀一個門牌座標 CSV；need: {街路段|巷|弄|號: [完整 key...]} → {完整 key: [[經度, 緯度], ...]}（同一門牌可能在不同鄉鎮，交給呼叫端挑）。"""
    import csv, io
    t0 = time.time()
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60)
    head = r.read(65536)
    enc = "utf-8-sig"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        enc = "cp950"
    def lines():
        buf = head
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            buf += chunk
            i = buf.rfind(b"\n")
            if i >= 0:
                yield from buf[:i + 1].decode(enc, "replace").splitlines()
                buf = buf[i + 1:]
            if time.time() - t0 > budget:
                raise TimeoutError("geo scan over budget")
        if buf:
            yield from buf.decode(enc, "replace").splitlines()
    rd = csv.reader(lines())
    hdr = [h.strip() for h in next(rd)]
    def col(*ks, avoid=()):
        for i, h in enumerate(hdr):
            if any(k in h for k in ks) and not any(a in h for a in avoid):
                return i
        return None
    i_road, i_area = col("街路段", "街道", "路段", "街路"), col("地區")
    i_lane, i_alley, i_no = col("巷"), col("弄"), col("號", avoid=("代碼", "序號"))
    i_x, i_y = col("橫坐標", "橫座標", "TWD97X", "X坐標", "X座標", "x"), col("縱坐標", "縱座標", "TWD97Y", "Y坐標", "Y座標", "y")
    if None in (i_no, i_x, i_y) or (i_road is None and i_area is None):
        raise ValueError(f"欄位對不上 {hdr[:14]}")
    num = lambda v, suf: re.sub(suf + "$", "", str(v or "").strip())
    found = {}
    for row in rd:
        try:
            road = (row[i_road] if i_road is not None else "") or (row[i_area] if i_area is not None else "")
            if not road:
                continue
            lane = num(row[i_lane], "巷") if i_lane is not None else ""
            alley = num(row[i_alley], "弄") if i_alley is not None else ""
            no = num(row[i_no], "號")
            pt = addr_parts(f"臺北市某某區{road}{lane + '巷' if lane else ''}{alley + '弄' if alley else ''}{no}號")
            if not pt:
                continue
            ks = need.get("|".join(pt[2:]))
            if not ks:
                continue
            x, y = float(row[i_x]), float(row[i_y])
            lo, la = (x, y) if x < 200 else _twd97_to_wgs84(x, y)
            for k in ks:
                found.setdefault(k, []).append([lo, la])
        except (IndexError, ValueError):
            continue
    return found


def geo_b(state, errs):
    if left() < 30:
        return
    raw = gcs_get("relay/in/geo_pending.json.gz")
    pend = (json.loads(gzip.decompress(raw)).get("p") or {}) if raw else {}
    if not pend:
        return
    st = state.setdefault("geob", {})
    if not any(c in GEO_DS and ks and not (st.get(c, {}).get("fin") and time.time() - st[c]["fin"] < 7 * 86400)
               for c, ks in pend.items()):
        return   # 每個縣市這週都掃過了，不用讀其他檔
    old = gcs_get("relay/static/geo_b.json.gz")
    res = json.loads(gzip.decompress(old)) if old else {"k": {}, "done": {}}
    K, done = res.setdefault("k", {}), res.setdefault("done", {})
    tc = {}   # 鄉鎮中心（村里中心平均），同一門牌出現在不同鄉鎮時挑最近的
    try:
        vv = gcs_get("relay/static/villages.json.gz")
        for c, t, _, lo, la in (json.loads(gzip.decompress(vv)).get("v") or []) if vv else []:
            a = tc.setdefault(c + t, [0, 0, 0]); a[0] += lo; a[1] += la; a[2] += 1
    except Exception:  # noqa: BLE001
        pass
    tc = {k: (a[0] / a[2], a[1] / a[2]) for k, a in tc.items() if a[2]}
    changed = False
    for cty, keys in sorted(pend.items(), key=lambda kv: st.get(kv[0], {}).get("try", 0)):   # 輪流：最久沒試的縣市先
        if cty not in GEO_DS or left() < 30:
            continue
        need_keys = [k for k in keys if k not in K]
        cs = st.setdefault(cty, {"i": 0})
        if not need_keys or (cs.get("fin") and time.time() - cs["fin"] < 7 * 86400):
            continue
        cs["try"] = time.time()
        try:
            if not cs.get("res"):
                cs["res"], cs["i"] = _geo_resources(GEO_DS[cty]), 0
            if cs["i"] < len(cs["res"]):
                need = {}
                for k in need_keys:
                    p = k.split("|")
                    need.setdefault("|".join(p[2:]), []).append(k)
                found = _geo_scan(cs["res"][cs["i"]], need, budget=max(20, left() - 5))
                for k, cands in found.items():
                    p = k.split("|"); ctr = tc.get(p[0] + p[1])
                    best = min(cands, key=lambda c: (c[0] - ctr[0]) ** 2 + (c[1] - ctr[1]) ** 2) if ctr else (cands[0] if len(cands) == 1 else None)
                    if best and (not ctr or ((best[0] - ctr[0]) ** 2 + (best[1] - ctr[1]) ** 2) ** 0.5 < 0.12):
                        K[k] = [round(best[0], 6), round(best[1], 6)]
                cs["i"] += 1; changed = True
            if cs["i"] >= len(cs.get("res") or []):
                cs["fin"], cs["res"] = time.time(), None; done[cty] = NOW_ISO; changed = True
        except Exception as e:  # noqa: BLE001
            errs["geo_" + cty] = repr(e)[:160]
            cs["fail"] = cs.get("fail", 0) + 1
            if "欄位" in repr(e) or cs["fail"] >= 3:   # 同一個檔失敗三次就跳過
                cs["i"] = cs.get("i", 0) + 1; cs["fail"] = 0
            changed = True
        break   # 一輪只處理一個縣市的一個檔
    if changed:
        put_doc("static/geo_b", {"k": K, "done": done})

MND = "https://www.mnd.gov.tw/"


def mnd_plaact(state, errs):
    """國防部「中共解放軍臺海周邊海、空域動態」：從美國抓常常逾時，改由台灣抓列表＋內文，存原始內文給 fetch.py 解析。
    由 main() 每小時叫一次（第 1 個 15 分鐘）；每次最多 12 篇。"""
    st = state.setdefault("mnd", {"pages": 0})
    st.pop("at", None)
    try:
        old = json.loads(gzip.decompress(gcs_get("relay/static/mnd_plaact.json.gz") or gz({"items": {}})))
    except Exception:  # noqa: BLE001
        old = {"items": {}}
    items = old.get("items") or {}
    backlog = st.get("pages", 0) < 22
    entries = []
    for page in range(1, 23):
        if left() < 25:
            break
        try:
            t = get(MND + "news/plaactlist" + (f"/{page}" if page > 1 else ""), 20).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            errs["mnd_list"] = repr(e)[:160]; break
        got = re.findall(r'<a href="news/plaact/(\d+)" class="news_list">\s*<div class="date[^"]*">([\d.]+)</div>\s*<div class="title[^"]*">(.*?)</div>', t, re.S)
        if not got:
            break
        entries += got
        st["pages"] = max(st.get("pages", 0), page)
        if not backlog and page >= 2:   # 補齊後只看前兩頁
            break
    n = 0
    for pid, dt, title in entries:
        if pid in items:
            continue
        if n >= 12 or left() < 10:
            break
        try:
            d = get(MND + f"news/plaact/{pid}", 20).decode("utf-8", "replace")
            m = re.search(r'<div class="maincontent">(.*?)<div class="keyword', d, re.S)
            items[pid] = {"date": dt, "title": title, "body": (m.group(1) if m else "")[:4000]}
            n += 1
        except Exception as e:  # noqa: BLE001
            errs["mnd_item"] = repr(e)[:160]
    keep = sorted(items, key=int)[-260:]
    put_doc("static/mnd_plaact", {"items": {k: items[k] for k in keep}})


# ---------- 國道貨運車流（高公局車輛偵測 TDCS M03A：每個門架每 5 分鐘、分車種的通過量）----------
# 每天加總全台各車種的通過量（是「車次×門架」的活動量，不是車輛數）：31 小客車、32 小貨車、41 大客車、42 大貨車、5 聯結車
# 每天補前一天；歷史從 2021/6 起「每週三」抽一天補（省運算），每輪最多 3 天、限時約 60 秒（整支要在 240 秒內跑完）
TDCS_M03A = "https://tisvcloud.freeway.gov.tw/history/TDCS/M03A/"


def _tdcs_day(d):
    import tarfile, io as _io
    from concurrent.futures import ThreadPoolExecutor
    tot, n = {}, 0
    def add(txt):
        for line in txt.splitlines():
            p = line.split(",")
            if len(p) >= 5:
                try:
                    tot[p[3]] = tot.get(p[3], 0) + int(p[4])
                except ValueError:
                    pass
    try:
        b = get(f"{TDCS_M03A}M03A_{d}.tar.gz", 120)
        with tarfile.open(fileobj=_io.BytesIO(b)) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".csv"):
                    add(tf.extractfile(m).read().decode("utf-8", "ignore")); n += 1
        return tot, n
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    urls = [f"{TDCS_M03A}{d}/{h:02d}/TDCS_M03A_{d}_{h:02d}{mi:02d}00.csv" for h in range(24) for mi in range(0, 60, 5)]
    def one(u):
        try:
            return get(u, 25).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(12) as ex:
        for txt in ex.map(one, urls):
            if txt:
                add(txt); n += 1
    return tot, n


def tdcs_daily(state, errs):
    """每天補前一天＋歷史每週三。補齊之後一天只讀一次存檔（state["tdcs_day"] 記哪天已經沒事做）。"""
    today = NOW.date().isoformat()
    if state.get("tdcs_day") == today or NOW.hour < 3:
        return
    store = json.loads(gzip.decompress(gcs_get("relay/static/tdcs_daily.json.gz") or gz({"days": {}}))).get("days", {})
    want = []
    y = (NOW - timedelta(days=1)).date()
    if y.isoformat() not in store:
        want.append(y)
    d = datetime(2021, 6, 23).date()   # 第一個有資料的週三
    while d < y - timedelta(days=6):
        if d.isoformat() not in store and state.get("tdcs_bad", {}).get(d.isoformat(), 0) < 3:
            want.append(d)
        d += timedelta(days=7)
    if not want:
        state["tdcs_day"] = today
        return
    changed = False
    for d in want[:3]:
        if left() < 45:
            break
        k = d.isoformat()
        try:
            tot, n = _tdcs_day(d.strftime("%Y%m%d"))
            if n >= 270:
                store[k] = {**tot, "n": n}; changed = True
            else:
                bad = state.setdefault("tdcs_bad", {}); bad[k] = bad.get(k, 0) + 1
                errs["tdcs:" + k] = f"只有 {n} 個檔"
        except Exception as e:  # noqa: BLE001
            errs["tdcs:" + k] = repr(e)[:160]
            bad = state.setdefault("tdcs_bad", {}); bad[k] = bad.get(k, 0) + 1   # 失敗三次就不再試，免得每小時白跑
    if changed:
        gcs_put("relay/static/tdcs_daily.json.gz", gz({"at": NOW_ISO, "days": dict(sorted(store.items()))}))
        STATE.setdefault("idx", {})["static/tdcs_daily"] = NOW_ISO


def section(name, fn, budget, errs):
    """跑一段慢工作：最多 budget 秒（get() 的 timeout 會被壓到剩下的時間），記下花了幾秒。"""
    if left() < 20:
        return
    t = time.time()
    _sec_end[0] = min(HARD_END, t + budget)
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        errs[name] = repr(e)[:200]
    finally:
        _sec_end[0] = HARD_END
        SEC[name] = round(time.time() - t, 1)


def insinfo_probe(state, errs):
    """暫時探測（2026-11-11，Vin 同意用台灣 IP）：保險業公開資訊觀測站只開放台灣連線，看首頁與再保險相關頁的結構。成功一次就不再跑；確認完整段刪掉。"""
    if state.get("insinfo_probe_ok") or time.time() - state.get("insinfo_probe_try", 0) < 6 * 3600:
        return
    state["insinfo_probe_try"] = time.time()
    from urllib.parse import urljoin, urlparse
    pages, seen, queue = [], set(), ["https://ins-info.ib.gov.tw/"]
    while queue and len(pages) < 10 and left() > 15:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            b = get(u, 30)
            for enc in ("utf-8", "big5"):
                try:
                    h = b.decode(enc); break
                except UnicodeDecodeError:
                    h = b.decode("utf-8", "replace")
            pages.append({"url": u, "len": len(b), "html": h[:150000]})
            for l, t in re.findall(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', h, re.S | re.I):
                lu = urljoin(u, l.strip())
                if urlparse(lu).netloc == "ins-info.ib.gov.tw" and re.search("再保|公開資訊|財務|業務", re.sub(r"<[^>]+>", "", t) + lu):
                    queue.append(lu)
        except Exception as e:  # noqa: BLE001
            pages.append({"url": u, "err": repr(e)[:200]})
    put_doc("static/insinfo_probe", {"pages": pages})
    if any("html" in x for x in pages):
        state["insinfo_probe_ok"] = 1
    else:
        errs["insinfo_probe"] = (pages[0].get("err") if pages else "no page")


def static_daily(state, errs):
    static_at = state.setdefault("static_at", {})
    for k, u in STATIC.items():
        if time.time() - static_at.get(k, 0) < 86400:
            continue
        if left() < 20:
            break
        try:
            put_doc(f"static/{k}", {"src": u, **parse_xml(get(u, 90))}, ignore=("meta",))   # meta 只有更新時間，不算內容變動
            static_at[k] = time.time()
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:200]
            static_at[k] = time.time() - 86400 + 6 * 3600   # 失敗的 6 小時後再試


def fetch_live(errs):
    """即時資料：全部同時抓（大部分時間在等對方伺服器，並行可以把等待疊在一起）。"""
    from concurrent.futures import ThreadPoolExecutor
    jobs = {k: (lambda u=u: parse_xml(get(u, 25))) for k, u in LIVE.items()}
    jobs["yb"] = youbike
    docs = {}
    with ThreadPoolExecutor(len(jobs)) as ex:
        futs = {k: ex.submit(f) for k, f in jobs.items()}
        for k, f in futs.items():
            try:
                docs[k] = f.result()
            except Exception as e:  # noqa: BLE001
                errs[k] = repr(e)[:200]
    if "yb" in docs:
        docs["yb"], yb_meta = docs["yb"]
        put_doc("static/yb_meta", yb_meta)
    return docs


SEED = ["static/" + k for k in STATIC] + ["static/" + k for k in ("stats_summary", "moea_orders", "moea_retail", "tc_cctv", "tn_cctv",
                                                                  "villages", "geo_b", "mnd_plaact", "tdcs_daily", "yb_meta",
                                                                  "dgc2_cpi_basic", "dgc2_cpi_special", "dgc2_labor", "dgc2_sa",
                                                                  "dgc2_gdp_q", "dgc2_gdp_q2")] + ["latest/gtrends"]


def main():
    global STATE
    if NIGHT and SLOT:
        log("night: skip (only on the hour)")
        return
    raw0 = gcs_get("relay/state.json") or b"{}"
    state = STATE = json.loads(raw0)
    for k in ("h", "last"):   # 舊版欄位：即時資料每輪都變，不再放 state（放 live.json.gz）
        state.pop(k, None)
    for k in SEED:            # 既有的檔先給一個固定版本號，fetch.py 才能快取；之後內容一變就換成寫入時間
        state.setdefault("idx", {}).setdefault(k, "v0")
    before = json.dumps(state, ensure_ascii=False, sort_keys=True)
    errs = {}

    t = time.time(); _sec_end[0] = T_START + 60
    docs = fetch_live(errs)
    _sec_end[0] = HARD_END; SEC["live"] = round(time.time() - t, 1)

    # 慢工作輪班：每小時第 1 段國防部＋搜尋趨勢；第 2 段門牌（每 3 小時）＋國道車流；每段都看一下有沒有到期的每日工作
    if SLOT == 1:
        section("mnd", lambda: mnd_plaact(state, errs), 50, errs)
        section("gtrends", lambda: gtrends(state), 70, errs)
    if SLOT == 2:
        section("tdcs", lambda: tdcs_daily(state, errs), 100, errs)
        if NOW.hour % 3 == 0:
            section("geo_b", lambda: geo_b(state, errs), 90, errs)
    section("stats", lambda: stats_daily(state, errs), 60, errs)
    section("moea", lambda: moea_daily(state, errs), 30, errs)
    section("city_cctv", lambda: city_cctv(state, errs), 30, errs)
    section("static", lambda: static_daily(state, errs), 60, errs)
    section("villages", lambda: villages_once(state, errs), 150, errs)
    section("insinfo_probe", lambda: insinfo_probe(state, errs), 60, errs)   # 暫時探測，確認完刪掉

    last = {"at": NOW_ISO, "ok": sorted(docs), "errs": errs, "rows": {k: len(d["rows"]) for k, d in docs.items()},
            "sec": round(time.time() - T_START, 1), "sections": {k: v for k, v in SEC.items() if v >= 0.1}}
    if NOW.hour % 3 == 0 and SLOT == 0 and docs:   # 原始存檔（BigQuery tw_detail 表）：每 3 小時一份
        lines = [json.dumps({"ts": NOW_ISO, "src": k, "doc": json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True)},
                            ensure_ascii=False) for k, d in docs.items()]
        gcs_put(f"relay/raw/dt={NOW:%Y-%m-%d}/{NOW:%H%M%S}.ndjson.gz", gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), 9))
    if json.dumps(state, ensure_ascii=False, sort_keys=True) != before:
        gcs_put("relay/state.json", json.dumps(state, ensure_ascii=False).encode("utf-8"), "application/json")
        last["state_saved"] = 1
    last["ops"] = dict(OPS); last["ops"]["a"] += 1   # 含下面這次寫入
    last["sec"] = round(time.time() - T_START, 1)
    geob = {c: {kk: vv for kk, vv in v.items() if kk != "res"} for c, v in (state.get("geob") or {}).items()}
    bundle = {"at": NOW_ISO, "docs": {k: {"at": NOW_ISO, **d} for k, d in docs.items()}, "idx": state.get("idx") or {},
              "last": last, "relay": {"mnd": state.get("mnd"), "vill": state.get("vill"), "geob": geob}}
    gcs_put("relay/latest/live.json.gz", gz(bundle))
    log("done", json.dumps(last, ensure_ascii=False))


main()
