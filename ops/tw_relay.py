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
}

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
    """Google 搜尋趨勢（台灣、近 90 天、每個關鍵字各自 0–100）。6 小時抓一次。"""
    if time.time() - state.get("gt_at3", 0) < 6 * 3600:
        return
    kws = json.loads(get("https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/voice_keywords.json"))["keywords"]
    out, errs, ck = {}, {}, {}
    for u0 in ("https://trends.google.com/?geo=TW", "https://trends.google.com/trends/explore?geo=TW&hl=zh-TW"):
        try:
            _gt_open(u0, ck)
        except Exception as e:  # noqa: BLE001
            errs["_home"] = repr(e)[:160]
    for kw in kws:
        q = kw["q"]
        try:
            req = {"comparisonItem": [{"keyword": q, "geo": "TW", "time": "today 3-m"}], "category": 0, "property": ""}
            u = "https://trends.google.com/trends/api/explore?" + urllib.parse.urlencode({"hl": "zh-TW", "tz": "-480", "req": json.dumps(req, ensure_ascii=False)})
            w = json.loads(_gt_open(u, ck)[4:])["widgets"]
            ts = [x for x in w if x["id"] == "TIMESERIES"][0]
            time.sleep(1.5)
            u2 = "https://trends.google.com/trends/api/widgetdata/multiline?" + urllib.parse.urlencode({"hl": "zh-TW", "tz": "-480", "req": json.dumps(ts["request"], ensure_ascii=False), "token": ts["token"]})
            tl = json.loads(_gt_open(u2, ck)[5:])["default"]["timelineData"]
            out[kw["k"]] = [[x.get("formattedAxisTime") or x.get("time"), (x.get("value") or [0])[0]] for x in tl]
        except Exception as e:  # noqa: BLE001
            errs[kw["k"]] = repr(e)[:160]
        time.sleep(3)
    errs["_cookies"] = ",".join(sorted(ck))
    gcs_put("relay/latest/gtrends.json.gz", gz({"at": NOW_ISO, "kw": out, "errs": errs}))
    state["gt_at3"] = time.time() if out else time.time() - 5 * 3600  # 全失敗的話一小時後再試
    log("gtrends", len(out), "ok", len(errs), "err", errs.get("_cookies"))


def main():
    t0 = time.time()
    state = json.loads(gcs_get("relay/state.json") or b"{}")
    hashes, static_at = state.setdefault("h", {}), state.setdefault("static_at", {})
    docs, errs = {}, {}

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
