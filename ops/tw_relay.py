# 台灣抓取站：在 Google Cloud 彰化機房（asia-east1，台灣 IP）每 5 分鐘跑一次。
# 只負責「抓 → 轉成精簡 JSON → 存進 intel-vault 的 bucket」，怎麼解讀交給 GitHub 上的 fetch.py。
# Cloud Run job 每次執行都從 GitHub 讀這支最新版，所以改這裡不用重新部署。
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
    "fw_1968": FW + "1min_incident_data_1968.xml",  # 1968 每分鐘事故
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
_tok = {"v": None, "exp": 0}


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
    q = urllib.parse.quote(name, safe="")
    urllib.request.urlopen(urllib.request.Request(
        f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={q}",
        data=data, method="POST", headers={"Authorization": "Bearer " + token(), "Content-Type": ctype}), timeout=60).read()


def gcs_get(name):
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
    gcs_put("relay/latest/gtrends.json.gz", gz({"at": NOW_ISO, "span": "today 5-y", "kw": kwd, "kat": kat, "errs": errs}))
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
        if time.time() - t0 > 70 or n >= 3:   # Cloud Run 一次最多 240 秒，即時路況還要時間：每輪最多 3 項、70 秒，其餘下一輪（15 分鐘後）
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
                gcs_put(f"relay/static/{k}.json.gz", gz({"at": NOW_ISO, "src": u, "json": js}))
                at[k] = time.time() if rec["n_obs"] or k.startswith("dg_meta_") else time.time() - 86400 + 6 * 3600
            except ValueError:
                if txt.lstrip()[:1] == '"' and "<html" not in txt[:500].lower():   # 匯出的 CSV（第一列是分類名稱、之後一列一個月份）
                    rec["kind"] = "csv"; rec["head"] = txt[:400]; rec["n_lines"] = txt.count("\n")
                    gcs_put(f"relay/static/{k}.json.gz", gz({"at": NOW_ISO, "src": u, "csv": txt}))
                    at[k] = time.time()
                    summ[k] = rec; changed = True
                    continue
                rec["kind"] = "html"
                rec["title"] = (re.search(r"<title>(.*?)</title>", txt, re.S) or [None, ""])[1].strip()[:80]
                body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", txt)
                rec["head"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()[:600]
                if k.endswith("_menu"):   # 目錄頁：留下所有功能代碼和名稱，之後找表號用
                    rec["funids"] = sorted(set(re.findall(r"funid=([A-Za-z0-9_]+)", txt)))[:600]
                    gcs_put(f"relay/static/{k}.json.gz", gz({"at": NOW_ISO, "src": u, "html": txt[:600000]}))
                    at[k] = time.time()
                else:
                    at[k] = time.time() - 86400 + 6 * 3600
        except Exception as e:  # noqa: BLE001
            rec["err"] = repr(e)[:200]
            errs["stats:" + k] = rec["err"]
            at[k] = time.time() - 86400 + 6 * 3600
        summ[k] = rec
        changed = True
    if changed:
        gcs_put("relay/static/stats_summary.json.gz", gz({"at": NOW_ISO, "jobs": summ}))


CITY_CCTV = {   # 縣市交通局的路口攝影機（原始檔照存，fetch.py 解析）
    "tc_cctv": "https://newdatacenter.taichung.gov.tw/api/v1/no-auth/resource.download?rid=695dc746-4b1e-4d1d-98a8-a894e7d8dc81",
    "tn_cctv": "https://trafficopendata.tainan.gov.tw/opendata/json/cctv/latest",
}


def city_cctv(state, errs):
    at = state.setdefault("city_cctv_at", {})
    for k, u in CITY_CCTV.items():
        if time.time() - at.get(k, 0) < 86400:
            continue
        try:
            b = get(u, 60)
            txt = b.decode("utf-8-sig", "replace")
            if "\ufffd" in txt[:2000]:
                txt = b.decode("big5", "replace")
            gcs_put(f"relay/static/{k}.json.gz", gz({"at": NOW_ISO, "src": u, "raw": txt[:4_000_000]}))
            at[k] = time.time()
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:200]
            at[k] = time.time() - 86400 + 6 * 3600


MND = "https://www.mnd.gov.tw/"


def mnd_plaact(state, errs):
    """國防部「中共解放軍臺海周邊海、空域動態」：從美國抓常常逾時，改由台灣抓列表＋內文，存原始內文給 fetch.py 解析。
    沒補齊前每輪都抓（每輪最多 12 篇、45 秒），補齊後一小時看一次有沒有新的。"""
    st = state.setdefault("mnd", {"at": 0, "pages": 0})
    try:
        old = json.loads(gzip.decompress(gcs_get("relay/static/mnd_plaact.json.gz") or gz({"items": {}})))
    except Exception:  # noqa: BLE001
        old = {"items": {}}
    items = old.get("items") or {}
    backlog = st.get("pages", 0) < 22
    if not backlog and time.time() - st.get("at", 0) < 3600:
        return
    t1 = time.time()
    entries = []
    for page in range(1, 23):
        if time.time() - t1 > 25:
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
        if n >= 12 or time.time() - t1 > 45:
            break
        try:
            d = get(MND + f"news/plaact/{pid}", 20).decode("utf-8", "replace")
            m = re.search(r'<div class="maincontent">(.*?)<div class="keyword', d, re.S)
            items[pid] = {"date": dt, "title": title, "body": (m.group(1) if m else "")[:4000]}
            n += 1
        except Exception as e:  # noqa: BLE001
            errs["mnd_item"] = repr(e)[:160]
    keep = sorted(items, key=int)[-260:]
    gcs_put("relay/static/mnd_plaact.json.gz", gz({"at": NOW_ISO, "items": {k: items[k] for k in keep}}))
    st["at"] = time.time()


def main():
    t0 = time.time()
    state = json.loads(gcs_get("relay/state.json") or b"{}")
    hashes, static_at = state.setdefault("h", {}), state.setdefault("static_at", {})
    docs, errs = {}, {}

    try:   # 官方統計排最前面（自己限時 70 秒），免得被後面的即時路況吃掉時間
        stats_daily(state, errs)
    except Exception as e:  # noqa: BLE001
        errs["stats"] = repr(e)[:200]

    try:
        city_cctv(state, errs)
    except Exception as e:  # noqa: BLE001
        errs["city_cctv"] = repr(e)[:200]

    try:
        mnd_plaact(state, errs)
    except Exception as e:  # noqa: BLE001
        errs["mnd"] = repr(e)[:200]

    try:
        docs["yb"], yb_meta = youbike()
        if time.time() - static_at.get("yb_meta", 0) > 86400:
            gcs_put("relay/static/yb_meta.json.gz", gz({"at": NOW_ISO, **yb_meta}))
            static_at["yb_meta"] = time.time()
    except Exception as e:  # noqa: BLE001
        errs["yb"] = repr(e)[:200]

    for k, u in LIVE.items():
        try:
            docs[k] = parse_xml(get(u))
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:200]

    for k, u in STATIC.items():
        if time.time() - static_at.get(k, 0) < 86400:
            continue
        try:
            gcs_put(f"relay/static/{k}.json.gz", gz({"at": NOW_ISO, "src": u, **parse_xml(get(u, 90))}))
            static_at[k] = time.time()
        except Exception as e:  # noqa: BLE001
            errs[k] = repr(e)[:200]
            static_at[k] = time.time() - 86400 + 6 * 3600   # 失敗的 6 小時後再試，不要每 5 分鐘白打

    try:
        gtrends(state)
    except Exception as e:  # noqa: BLE001
        errs["gtrends"] = repr(e)[:200]

    lines, changed = [], []
    for k, d in docs.items():
        body = json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        gcs_put(f"relay/latest/{k}.json.gz", gz({"at": NOW_ISO, **d}))
        h = hashlib.sha1(body.encode("utf-8")).hexdigest()
        if hashes.get(k) != h:
            hashes[k] = h
            changed.append(k)
            lines.append(json.dumps({"ts": NOW_ISO, "src": k, "doc": body}, ensure_ascii=False))
    if lines:
        obj = f"relay/raw/dt={NOW:%Y-%m-%d}/{NOW:%H%M%S}.ndjson.gz"
        gcs_put(obj, gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), 9))
    state["last"] = {"at": NOW_ISO, "ok": sorted(docs), "changed": changed, "errs": errs,
                     "rows": {k: len(d["rows"]) for k, d in docs.items()}, "sec": round(time.time() - t0, 1)}
    gcs_put("relay/state.json", json.dumps(state, ensure_ascii=False).encode("utf-8"), "application/json")
    log("done", json.dumps(state["last"], ensure_ascii=False))


main()
