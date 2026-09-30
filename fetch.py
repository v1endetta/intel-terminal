#!/usr/bin/env python3
"""dalta 情報站 — 資料抓取腳本。

每個來源獨立抓、獨立失敗；抓失敗就保留上一次的值，並在 panel["error"] 留下原因。
輸出：
  data/all.json          所有面板最新值（頁面只讀這一個檔）
  data/history.json      每個指標的日序列（走勢圖用，保留最近 400 點）
  data/panels/<id>.json  各面板單檔（方便 agent 直接讀）
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import html as html_mod
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INTEL_DATA_DIR") or (ROOT / "data"))
PANELS = DATA / "panels"
PANELS.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
TIMEOUT = 25

TPE = timezone(timedelta(hours=8))
NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.replace(microsecond=0).isoformat().replace("+00:00", "Z")
TODAY_TPE = NOW.astimezone(TPE).date()

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
REDDIT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
REDDIT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
CWA_KEY = os.environ.get("CWA_API_KEY", "").strip()
TDX_ID = os.environ.get("TDX_CLIENT_ID", "").strip()
TDX_SECRET = os.environ.get("TDX_CLIENT_SECRET", "").strip()
GUARDIAN_KEY = os.environ.get("GUARDIAN_API_KEY", "").strip()
YOUTUBE_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "").strip()
CSE_CX = os.environ.get("GOOGLE_CSE_CX", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


# ---------- helpers ----------
def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    r = S.get(url, **kw)
    r.raise_for_status()
    return r


def gjson(url, **kw):
    return get(url, **kw).json()


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("%", "").replace("+", "").strip()
    if s in ("", "-", "--", "—", "X"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def roc_to_iso(s):
    s = str(s).strip()
    m = re.match(r"^(\d{3})(\d{2})(\d{2})$", s)
    if m:
        return f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{3})/(\d{2})/(\d{2})$", s)
    if m:
        return f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
    return s


def roc_ym(s):
    m = re.match(r"^(\d{3})(\d{2})$", str(s).strip())
    return f"{int(m.group(1)) + 1911}/{m.group(2)}" if m else str(s)


def write_json(path: Path, obj, **kw):
    """Atomic write: tmp file + os.replace, so a killed process never leaves a half file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, **kw), encoding="utf-8")
    os.replace(tmp, path)


def load_prev(pid):
    p = PANELS / f"{pid}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


RESULTS: dict[str, dict] = {}
START_TS = time.time()
PANEL_CAP = {"geo": 420, "news": 300, "aiwire": 120, "devpulse": 200, "social": 150, "cofacts": 90, "threads_g": 120, "mood": 120, "macro": 200, "supply": 200, "tw_pulse": 150, "revenue": 200}
SOFT_DEADLINE = START_TS + 660  # workflow 硬上限 900 秒，留 4 分鐘給收尾與 commit
HISTORY: dict[str, dict[str, list]] = {}
HIST_PATH = DATA / "history.json"
if HIST_PATH.exists():
    try:
        HISTORY = json.loads(HIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        HISTORY = {}


def hist_put(group: str, key: str, date: str, value):
    """Upsert (date, value) into a date-keyed series; keeps it sorted; cap 400."""
    if value is None or date is None or not isinstance(value, (int, float)) or value != value:
        return
    series = HISTORY.setdefault(group, {}).setdefault(key, [])
    for row in reversed(series):
        if row[0] == date:
            row[1] = value
            return
        if row[0] < date:
            break
    series.append([date, value])
    series.sort(key=lambda r: r[0])
    if len(series) > 400:
        del series[: len(series) - 400]


def hist_get(group: str, key: str, n: int = 30):
    return [v for _, v in HISTORY.get(group, {}).get(key, [])[-n:]]


def safe_err(e) -> str:
    msg = re.sub(r"(api[_-]?key|key|token|secret|authorization)=[^&\s]+", r"\1=***", str(e), flags=re.I)  # 先遮再截
    return f"{type(e).__name__}: {msg[:160]}"[:180]


def run(pid: str, fn, keep_if_fresh_hours: float = 0):
    """Run one panel fetcher. keep_if_fresh_hours>0 skips re-fetch when the
    previous file is newer than that (for daily/weekly sources)."""
    prev = load_prev(pid)
    if time.time() > SOFT_DEADLINE:  # 本輪時間快用完：後面的面板沿用上一輪，保證有 commit
        if prev:
            RESULTS[pid] = prev
        log(f"[{pid}] over soft deadline, keep previous")
        return
    if prev and prev.get("error"):
        # 失敗退避：上次失敗距今不到 1 小時（或該面板的更新週期，取小者）就不重試
        try:
            err_ts = datetime.fromisoformat(prev["error"].split(" ")[0].replace("Z", "+00:00"))
            if NOW - err_ts < timedelta(hours=min(keep_if_fresh_hours or 0.2, 1)):  # 即時面板失敗 12 分鐘後就重試
                RESULTS[pid] = prev
                log(f"[{pid}] backoff after error, skip")
                return
        except Exception:
            pass
    elif keep_if_fresh_hours and prev and prev.get("updatedAt"):
        try:
            t = datetime.fromisoformat(prev["updatedAt"].replace("Z", "+00:00"))
            if NOW - t < timedelta(hours=keep_if_fresh_hours):
                RESULTS[pid] = prev
                log(f"[{pid}] fresh, skip")
                return
        except Exception:
            pass
    t0 = time.time()
    import signal
    def _alarm(signum, frame):
        raise TimeoutError(f"panel cap {PANEL_CAP.get(pid, 240)}s")
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(PANEL_CAP.get(pid, 240))  # 單一面板上限，超過當一般失敗，不拖垮整輪
    try:
        doc = fn()
        signal.alarm(0)
        doc["updatedAt"] = NOW_ISO
        doc.pop("error", None)
        RESULTS[pid] = doc
        write_json(PANELS / f"{pid}.json", doc, indent=1)
        log(f"[{pid}] ok {time.time() - t0:.1f}s")
    except BaseException as e:  # noqa: BLE001
        signal.alarm(0)
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        log(f"[{pid}] FAIL {type(e).__name__}: {e}")
        if prev:
            prev["error"] = f"{NOW_ISO} {safe_err(e)}"
            RESULTS[pid] = prev
            write_json(PANELS / f"{pid}.json", prev, indent=1)
        else:
            RESULTS[pid] = {"updatedAt": None, "error": f"{NOW_ISO} {safe_err(e)}", "items": []}


# ---------- Yahoo Finance (batch quotes + 1 month series) ----------
_yahoo_cache: dict[str, dict] = {}
YAHOO_DOWN = False  # 收到 429 後本輪不再打 Yahoo，讓各面板保留舊值


def _yahoo_get(sym, params):
    global YAHOO_DOWN
    if YAHOO_DOWN:
        raise RuntimeError("yahoo rate-limited this run")
    try:
        return gjson(f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}", params=params)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            YAHOO_DOWN = True
            raise RuntimeError("yahoo 429") from None
        raise


def yahoo_chart(sym: str, rng="1mo", interval="1d"):
    if sym in _yahoo_cache:
        return _yahoo_cache[sym]
    try:
        j = _yahoo_get(sym, {"range": rng, "interval": interval, "includePrePost": "false"})
    except Exception as e:  # noqa: BLE001
        if sym not in STOOQ or interval != "1d":
            raise
        log("yahoo_chart→stooq", sym, e)
        rows = stooq_daily(STOOQ[sym])
        series = [(d, c) for d, c, _ in rows]
        price = series[-1][1] if series else None
        prev = series[-2][1] if len(series) >= 2 else None
        out = {"price": price, "chg_pct": (price - prev) / prev * 100 if price and prev else None, "ccy": None, "series": series,
               "asOf": series[-1][0] if series else None, "thin": False, "source": "stooq"}
        _yahoo_cache[sym] = out
        return out
    res = j["chart"]["result"][0]
    meta = res["meta"]
    closes = res["indicators"]["quote"][0].get("close") or []
    ts = res.get("timestamp") or []
    off = meta.get("gmtoffset") or 0
    series = [(datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat(), c) for t, c in zip(ts, closes) if c is not None]
    # 一律以 K 棒序列為準：最新價＝最後一根收盤（盤中為當日未完成棒），前收＝前一根。
    # 不用 regularMarketPrice／previousClose：期貨換月時那兩個值常來自不同合約，會出現 +60% 這種假漲跌。
    mkt_ts = meta.get("regularMarketTime")
    mkt_day = series[-1][0] if series else (datetime.fromtimestamp(mkt_ts + off, tz=timezone.utc).date().isoformat() if mkt_ts else None)
    price = series[-1][1] if series else meta.get("regularMarketPrice")
    prev, thin = None, False
    if len(series) >= 2:
        d_prev, c_prev = series[-2]
        gap = (datetime.fromisoformat(mkt_day) - datetime.fromisoformat(d_prev)).days
        if gap <= 7:
            prev = c_prev
        thin = gap > 3
    chg_pct = (price - prev) / prev * 100 if price is not None and prev else None
    out = {"price": price, "chg_pct": chg_pct, "ccy": meta.get("currency"), "series": series, "asOf": mkt_day, "thin": thin}
    _yahoo_cache[sym] = out
    return out


# ---------- panels ----------
def p_taiex():
    rows = gjson("https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK")
    if not rows:
        prev = load_prev("taiex")
        if prev:  # 月初尚無交易日：沿用上月最後值，不算錯誤
            prev.pop("error", None)
            return prev
        raise RuntimeError("empty")
    last = rows[-1]
    series = [(roc_to_iso(r["Date"]), num(r["TAIEX"])) for r in rows]
    for d, v in series:
        hist_put("taiex", "TAIEX", d, v)
    out = {
        "date": roc_to_iso(last["Date"]),
        "index": num(last["TAIEX"]),
        "change": num(last["Change"]),
        "value": num(last["TradeValue"]),
        "transactions": num(last["Transaction"]),
        "series": [v for _, v in series],
        "history": HISTORY.get("taiex", {}).get("TAIEX", [])[-60:],
    }
    try:  # 日檔（FMTQIK）收盤後才更新：盤中與傍晚用 MIS 即時值
        q = twse_mis()
        day = NOW.astimezone(TPE).strftime("%Y-%m-%d")
        if q.get("price") and q.get("prev") and day > out["date"] and q.get("asOf") and (NOW.timestamp() - q["asOf"]) < 12 * 3600:
            out.update({"index": q["price"], "change": round(q["price"] - q["prev"], 2), "date": day,
                        "live": datetime.fromtimestamp(q["asOf"], TPE).strftime("%H:%M"), "value": None, "transactions": None})
    except Exception as e:  # noqa: BLE001
        log("taiex mis", e)
    return out


TW_WATCH = [("1476", "儒鴻", "紡織"), ("1477", "聚陽", "紡織"), ("1402", "遠東新", "紡織"),
            ("2912", "統一超", "通路"), ("1216", "統一", "通路"), ("2903", "遠百", "通路")]


def p_tw_stocks():
    rows = gjson("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    by = {r["Code"]: r for r in rows}
    items, date = [], None
    for code, name, group in TW_WATCH:
        r = by.get(code)
        if not r:
            continue
        date = date or roc_to_iso(r["Date"])
        px, ch = num(r["ClosingPrice"]), num(r["Change"])
        hist_put("tw_stocks", code, roc_to_iso(r["Date"]), px)
        items.append({"code": code, "name": name, "group": group, "price": px, "chg": ch,
                      "spark": hist_get("tw_stocks", code)})
    if not items:
        raise RuntimeError("no watch rows")
    try:
        qs = twse_mis_quotes([c for c, _, _ in TW_WATCH])
        live = [it for it in items if _mis_override(it, qs.get(it["code"]), date)]
        if live:
            date = max(it["date"] for it in live)
    except Exception as e:  # noqa: BLE001
        log("tw_stocks mis", e)
    return {"date": date, "items": items}


def p_fx():
    r = get("https://rate.bot.com.tw/xrt/flcsv/0/day")
    r.encoding = "utf-8-sig"
    rows = list(csv.reader(io.StringIO(r.text)))
    header = rows[0]
    # 欄位：幣別, 匯率(現金/即期), 現金買入, 即期買入, ..., 匯率, 現金賣出, 即期賣出 ...
    # 台銀 CSV 的列：幣別, 現金買入, 即期買入, 遠期..., 現金賣出, 即期賣出, ...
    want = {"USD": "美元", "EUR": "歐元", "JPY": "日圓", "CNY": "人民幣"}
    items = []
    idx_buy = [i for i, h in enumerate(header) if "即期" in h]
    for row in rows[1:]:
        if not row:
            continue
        code = row[0].strip()
        if code in want and len(idx_buy) >= 2:
            buy, sell = num(row[idx_buy[0]]), num(row[idx_buy[1]])
            if buy is None:
                continue
            hist_put("fx", code, TODAY_TPE.isoformat(), (buy + sell) / 2 if sell else buy)
            items.append({"code": code, "name": want[code], "buy": buy, "sell": sell,
                          "spark": hist_get("fx", code)})
    order = ["USD", "EUR", "JPY", "CNY"]
    if items:
        items.sort(key=lambda x: order.index(x["code"]))
        return {"label": "台銀即期", "source": "bot", "items": items}
    raise RuntimeError("no fx rows; header=" + "|".join(header)[:120])


def p_fx_yahoo():
    pairs = [("USD", "美元", "TWD=X"), ("EUR", "歐元", "EURTWD=X"), ("JPY", "日圓", "JPYTWD=X"), ("CNY", "人民幣", "CNYTWD=X")]
    items = []
    for code, name, sym in pairs:
        try:
            q = yahoo_chart(sym)
        except Exception as e:  # noqa: BLE001
            log("fx yahoo", sym, e)
            continue
        for d, v in q["series"]:
            hist_put("fx_yahoo", code, d, v)
        items.append({"code": code, "name": name, "mid": q["price"], "chg_pct": q["chg_pct"],
                      "spark": [v for _, v in q["series"][-30:]]})
    if not items:
        raise RuntimeError("yahoo fx failed")
    return {"label": "Yahoo 中價", "source": "yahoo", "items": items}


def p_fx_any():
    try:
        return p_fx()
    except Exception as e:  # noqa: BLE001
        log("fx bot", e)
        return p_fx_yahoo()


SPORTY = re.compile(r"\b(vs\.?|@)\b|spread|o/u|over/under|\bnfl\b|\bnba\b|\bmlb\b|\bnhl\b|\bufc\b|\bmls\b|premier league|la liga|serie a|bundesliga|ligue 1|champions league|europa|ncaa|grand prix|\batp\b|\bwta\b|\bf1\b|super bowl|world series|stanley cup|world cup|\bcup\b|playoffs?|finals?\b|win the 20\d\d|\bmvp\b|heisman|ballon", re.I)


def p_poly():
    rows = gjson("https://gamma-api.polymarket.com/markets", params={
        "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false", "limit": 60})
    items = []
    for m in rows:
        if m.get("sportsMarketType") or m.get("gameStartTime") or SPORTY.search(m.get("question") or ""):
            continue
        try:
            yes = float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100
        except Exception:
            yes = None
        d1 = m.get("oneDayPriceChange")
        ev = (m.get("events") or [{}])[0]
        items.append({"question": m.get("question"), "slug": ev.get("slug") or m.get("slug"),
                      "yes": yes, "d1": d1 * 100 if isinstance(d1, (int, float)) else None,
                      "vol24h": m.get("volume24hr")})
        if len(items) >= 10:
            break
    if not items:
        raise RuntimeError("no non-sports markets")
    return {"items": items}


HN_KW = re.compile(r"OpenAI|Anthropic|Claude|GPT|Gemini|DeepMind|Google|Meta\b|Llama|Mistral|DeepSeek|Qwen|agent|LLM|model|Nvidia|Apple|Figma|Adobe|design", re.I)


def p_tech():
    since = (NOW - timedelta(days=7)).date().isoformat()
    out = {}
    try:
        gh = gjson("https://api.github.com/search/repositories",
                   params={"q": f"created:>{since}", "sort": "stars", "order": "desc", "per_page": 8},
                   headers={"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})})
        out["github"] = [{"name": r["full_name"], "url": r["html_url"], "stars": r["stargazers_count"],
                          "lang": r.get("language"), "desc": (r.get("description") or "")[:90]} for r in gh["items"]]
    except Exception as e:  # noqa: BLE001
        log("github", e)
    try:
        hf = gjson("https://huggingface.co/api/models", params={"sort": "trendingScore", "limit": 8})
        out["hf"] = [{"id": m.get("modelId") or m.get("id"), "downloads": m.get("downloads"), "likes": m.get("likes"),
                      "task": m.get("pipeline_tag")} for m in hf]
    except Exception as e:  # noqa: BLE001
        log("hf", e)
    try:
        # 前 60 則裡先挑 AI／大廠相關，再依分數補滿 8 則（原本直接取前 8 則會被遊戲、雜聞埋掉發布新聞）
        ids = gjson("https://hacker-news.firebaseio.com/v0/topstories.json")[:60]
        hn = []
        for i in ids:
            s = gjson(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
            if s and s.get("title"):
                t = s["title"]
                hot = bool(HN_KW.search(t))
                hn.append({"title": t, "url": s.get("url") or f"https://news.ycombinator.com/item?id={i}",
                           "score": s.get("score"), "comments": s.get("descendants"), "hot": hot})
        hn.sort(key=lambda x: (not x["hot"], -(x["score"] or 0)))
        out["hn"] = hn[:8]
    except Exception as e:  # noqa: BLE001
        log("hn", e)
    if not out:
        raise RuntimeError("all three failed")
    return out


def p_trends():
    r = get("https://trends.google.com/trending/rss", params={"geo": "TW"})
    root = ET.fromstring(r.content)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        traffic = (it.findtext("ht:approx_traffic", namespaces=ns) or "").strip()
        news = it.find("ht:news_item", ns)
        headline, link = "", ""
        if news is not None:
            headline = (news.findtext("ht:news_item_title", namespaces=ns) or "").strip()
            link = (news.findtext("ht:news_item_url", namespaces=ns) or "").strip()
        # 過濾非繁中／英文標題（簡體、日文）
        if re.search(r"[぀-ヿ]", headline) or re.search(r"[们这个说时会为发对]", headline):
            headline = ""
        items.append({"title": title, "traffic": traffic, "news": headline[:48], "url": link})
        if len(items) >= 12:
            break
    if not items:
        raise RuntimeError("empty rss")
    return {"items": items}


LUX = [("MC.PA", "LVMH"), ("KER.PA", "Kering"), ("RMS.PA", "Hermès"), ("ITX.MC", "Inditex"),
       ("9983.T", "Fast Retailing"), ("NKE", "Nike"), ("1913.HK", "Prada"), ("BRBY.L", "Burberry")]


def p_luxury():
    items, as_of = [], None
    for sym, name in LUX:
        try:
            q = yahoo_chart(sym)
        except Exception as e:  # noqa: BLE001
            log("lux", sym, e)
            continue
        as_of = max(as_of or "", q["asOf"] or "")
        for d, v in q["series"]:
            hist_put("luxury", sym, d, v)
        items.append({"sym": sym, "name": name, "price": q["price"], "chg_pct": q["chg_pct"], "ccy": q["ccy"],
                      "spark": [v for _, v in q["series"][-30:]]})
    if not items:
        raise RuntimeError("no quotes")
    return {"label": "最近收盤", "asOf": as_of, "items": items}


CMD = [("CT=F", "棉花", "USc/lb"), ("CL=F", "WTI 原油", "USD/bbl"), ("BZ=F", "Brent 原油", "USD/bbl"),
       ("HG=F", "銅", "USD/lb"), ("ALI=F", "鋁", "USD/t"), ("GC=F", "黃金", "USD/oz"), ("SI=F", "白銀", "USD/oz"),
       ("TIO=F", "鐵礦砂 62%", "USD/t"), ("HRC=F", "熱軋鋼捲", "USD/t")]
FRED_SERIES = {"CT=F": "PCOTTINDUSDM", "CL=F": "DCOILWTICO", "BZ=F": "DCOILBRENTEU", "HG=F": "PCOPPUSDM", "ALI=F": "PALUMUSDM"}


def fred(series_id, n=40):
    j = gjson("https://api.stlouisfed.org/fred/series/observations",
              params={"series_id": series_id, "api_key": FRED_KEY, "file_type": "json", "sort_order": "desc", "limit": n})
    obs = [(o["date"], num(o["value"])) for o in j["observations"] if num(o["value"]) is not None]
    obs.reverse()
    return obs


def p_commodities():
    items, as_of = [], None
    for sym, name, unit in CMD:
        q = None
        try:
            q = yahoo_chart(sym)
        except Exception as e:  # noqa: BLE001
            log("cmdty yahoo", sym, e)
            if FRED_KEY and sym in FRED_SERIES:
                try:
                    obs = fred(FRED_SERIES[sym])
                    q = {"price": obs[-1][1], "chg_pct": (obs[-1][1] - obs[-2][1]) / obs[-2][1] * 100 if len(obs) > 1 else None,
                         "ccy": "USD", "series": obs, "asOf": obs[-1][0], "fred": True}
                except Exception as e2:  # noqa: BLE001
                    log("cmdty fred", sym, e2)
        if not q:
            continue
        as_of = max(as_of or "", q["asOf"] or "")
        for d, v in q["series"]:
            hist_put("commodities", sym + ("_fred" if q.get("fred") else ""), d, v)
        items.append({"sym": sym, "name": name, "unit": unit, "price": q["price"], "chg_pct": q["chg_pct"],
                      "spark": [v for _, v in q["series"][-30:]]})
    shipping = []
    try:
        html = re.sub(r"<[^>]+>", " ", get("https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry").text)
        # 只看含 "per 40ft" 的那一句，避免抓到頁面其他數字
        sent = next((x for x in re.split(r"(?<=[.!?])\s+", html) if re.search(r"per\s*40ft", x, re.I) and re.search(r"\$[\d,]{4,6}", x)), "")
        m = re.search(r"\$([\d,]{4,6})\s*per\s*40ft", sent)
        pct = re.search(r"(decreased|increased|fell|rose|down|up)\s+(?:by\s+)?(\d+(?:\.\d+)?)%", sent, re.I)
        dt = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+20\d\d)", sent) or re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+20\d\d)", html)
        if m:
            val = num(m.group(1))
            chg = None
            if pct:
                chg = num(pct.group(2)) * (-1 if pct.group(1).lower() in ("decreased", "fell", "down") else 1)
            key_date = TODAY_TPE.isoformat()
            if dt:
                for fmt_ in ("%d %b %Y", "%d %B %Y"):
                    try:
                        key_date = datetime.strptime(dt.group(1), fmt_).date().isoformat()
                        break
                    except ValueError:
                        continue
            hist_put("shipping", "WCI", key_date, val)
            shipping.append({"name": "Drewry WCI", "value": val, "unit": "USD/40ft", "date": dt.group(1) if dt else "",
                             "chg_pct": chg, "chg_label": "週%", "spark": hist_get("shipping", "WCI", 20)})
    except Exception as e:  # noqa: BLE001
        log("drewry", e)
    prev = load_prev("commodities") or {}
    if not shipping and prev.get("shipping"):
        shipping = prev["shipping"]
    if not items:
        raise RuntimeError("no commodity quotes")
    return {"label": "期貨近月", "asOf": as_of, "items": items, "shipping": shipping}


REV_WATCH = {"2912": "統一超", "5903": "全家", "5904": "寶雅", "2903": "遠百", "8454": "momo", "8044": "PChome", "1216": "統一",
             "2330": "台積電", "2317": "鴻海", "2382": "廣達"}
REV_GROUP = {"2330": "供應鏈", "2317": "供應鏈", "2382": "供應鏈"}  # 其餘＝通路


def p_revenue():
    items = {}
    # 1) FinMind 一次拿上市＋上櫃（免 token 也可，額度較低）
    try:
        start = (TODAY_TPE - timedelta(days=430)).isoformat()
        headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {}
        for code, name in REV_WATCH.items():
            try:
                j = gjson("https://api.finmindtrade.com/api/v4/data",
                          params={"dataset": "TaiwanStockMonthRevenue", "data_id": code, "start_date": start}, headers=headers)
                rows = j.get("data") or []
                if len(rows) < 2:
                    continue
                rows.sort(key=lambda r: (r["revenue_year"], r["revenue_month"]))
                last, prevm = rows[-1], rows[-2]
                yoy = next((r for r in rows if r["revenue_year"] == last["revenue_year"] - 1 and r["revenue_month"] == last["revenue_month"]), None)
                rev = last["revenue"] / 1000  # 元 → 千元
                items[code] = {"code": code, "name": name, "rev": rev, "group": REV_GROUP.get(code, "通路"),
                               "mom": (last["revenue"] - prevm["revenue"]) / prevm["revenue"] * 100 if prevm["revenue"] else None,
                               "yoy": (last["revenue"] - yoy["revenue"]) / yoy["revenue"] * 100 if yoy and yoy["revenue"] else None,
                               "period": f"{last['revenue_year']}/{last['revenue_month']:02d}",
                               "spark": [r["revenue"] / 1000 for r in rows[-13:]]}
            except Exception as e:  # noqa: BLE001
                log("finmind", code, e)
            time.sleep(0.4)
    except Exception as e:  # noqa: BLE001
        log("finmind revenue", e)
    # 2) 證交所／櫃買 備援
    if len(items) < len(REV_WATCH):
        for url in ("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"):
            try:
                for r in gjson(url):
                    code = r.get("公司代號")
                    if code in REV_WATCH and code not in items:
                        items[code] = {"code": code, "name": REV_WATCH[code], "group": REV_GROUP.get(code, "通路"),
                                       "rev": num(r.get("營業收入-當月營收")),
                                       "mom": num(r.get("營業收入-上月比較增減(%)")),
                                       "yoy": num(r.get("營業收入-去年同月增減(%)")),
                                       "period": roc_ym(r.get("資料年月"))}
            except Exception as e:  # noqa: BLE001
                log("revenue fallback", url, e)
    if not items:
        raise RuntimeError("no revenue rows")
    order = list(REV_WATCH)
    return {"items": sorted(items.values(), key=lambda x: order.index(x["code"]))}


def p_media():
    items = []
    try:
        root = ET.fromstring(get("https://wwd.com/feed").content)
        build = root.findtext("./channel/lastBuildDate") or ""
        for it in root.iter("item"):
            d = it.findtext("pubDate") or ""
            try:
                dd = datetime.strptime(d[:25].strip(), "%a, %d %b %Y %H:%M:%S").strftime("%m-%d")
            except Exception:
                dd = d[5:11]
            items.append({"source": "WWD", "title": (it.findtext("title") or "").strip(), "url": it.findtext("link"), "date": dd})
            if len(items) >= 6:
                break
    except Exception as e:  # noqa: BLE001
        log("wwd", e)
    for q, src in (("site:businessoffashion.com", "BoF"), ("site:vogue.com.tw OR site:elle.com/tw", "TW")):
        try:
            root = ET.fromstring(get("https://www.bing.com/news/search", params={"q": q, "format": "rss"}).content)
            n = 0
            for it in root.iter("item"):
                d = it.findtext("pubDate") or ""
                try:
                    dd = datetime.strptime(d[:25].strip(), "%a, %d %b %Y %H:%M:%S").strftime("%m-%d")
                except Exception:
                    dd = d[5:11]
                items.append({"source": src, "title": (it.findtext("title") or "").strip(), "url": it.findtext("link"), "date": dd})
                n += 1
                if n >= 4:
                    break
        except Exception as e:  # noqa: BLE001
            log("bing news", src, e)
    if not items:
        raise RuntimeError("no media items")
    return {"items": items}


SUBS = ["taiwan", "fashion", "malefashionadvice", "marketing", "design", "artificial"]


def p_reddit():
    headers = {"User-Agent": "dalta-intel/1.0 (personal terminal)"}
    base = "https://www.reddit.com"
    if REDDIT_ID and REDDIT_SECRET:
        tok = S.post("https://www.reddit.com/api/v1/access_token", auth=(REDDIT_ID, REDDIT_SECRET),
                     data={"grant_type": "client_credentials"}, headers=headers, timeout=TIMEOUT).json()["access_token"]
        headers["Authorization"] = f"bearer {tok}"
        base = "https://oauth.reddit.com"
    items = []
    for sub in SUBS:
        try:
            j = gjson(f"{base}/r/{sub}/hot.json", params={"limit": 6, "raw_json": 1}, headers=headers)
            n = 0
            for c in j["data"]["children"]:
                d = c["data"]
                if d.get("stickied"):
                    continue
                items.append({"sub": sub, "title": d["title"], "score": d["score"], "comments": d["num_comments"],
                              "url": "https://www.reddit.com" + d["permalink"]})
                n += 1
                if n >= 3:
                    break
            time.sleep(1.2)
        except Exception as e:  # noqa: BLE001
            log("reddit", sub, e)
    if not items:
        raise RuntimeError("reddit blocked (set REDDIT_CLIENT_ID/SECRET)")
    return {"items": items}


def p_lyst():
    # 找最新一季：從今年往回試
    y, q = TODAY_TPE.year, (TODAY_TPE.month - 1) // 3 + 1
    tried = []
    for _ in range(6):
        url = f"https://www.lyst.com/the-lyst-index/Q{q}-{str(y)[2:]}"
        tried.append(url)
        r = S.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and "Hottest" in r.text:
            html = r.text
            quarter = f"Q{q} {y}"
            break
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    else:
        raise RuntimeError("no lyst page: " + tried[-1])
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def grab(anchor):
        out = []
        try:
            i = next(k for k, l in enumerate(lines) if anchor.lower() in l.lower())
        except StopIteration:
            return out
        for l in lines[i + 1:i + 80]:
            m = re.match(r"^(\d{1,2})\.?\s*(.+)$", l)
            if m and int(m.group(1)) == len(out) + 1:
                out.append(m.group(2).strip())
                if len(out) == 10:
                    break
        return out

    brands = grab("hottest brands")
    products = grab("hottest products")
    if not brands:
        raise RuntimeError("could not parse brands")
    prev = load_prev("lyst") or {}
    if prev.get("quarter") == quarter:
        # 同一季：沿用上一季名單算 move，並保留手動補的欄位（例如 products.brand）
        prev_brands = prev.get("prevQuarterBrands") or []
        old_products = {p.get("name"): p for p in prev.get("products", [])}
    else:
        prev_brands = [b.get("brand") for b in prev.get("brands", [])]
        old_products = {}
    out_b = []
    for i, b in enumerate(brands):
        move = (prev_brands.index(b) - i) if b in prev_brands else 0
        out_b.append({"brand": b, "move": move})
    out_p = [{**old_products.get(p, {}), "name": p, "move": old_products.get(p, {}).get("move", 0)} for p in products]
    return {"quarter": quarter, "brands": out_b, "products": out_p, "prevQuarterBrands": prev_brands}


def p_macro():
    """手動維護的 items（CPI 等）＋ 自動抓的央行、房價、景氣燈號、主計 SDMX。"""
    prev = load_prev("macro") or {"items": []}
    items = {it["label"]: it for it in prev.get("items", []) if not it.get("auto")}
    auto, errs = {}, []
    # 央行利率
    try:
        j = gjson("https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EG2AM01")
        labels = [l.get("data", l) if isinstance(l, dict) else l for l in j["data"]["structure"]["Table1"]]
        row = j["data"]["dataSets"][-1]
        i = next(k for k, l in enumerate(labels) if "重貼現" in str(l))
        auto["rate"] = {"label": "重貼現率", "value": f"{float(row[i + 1]):.3f}%", "period": row[0].replace("M", "-"), "auto": True}
    except Exception as e:  # noqa: BLE001
        log("cbc rate", e); errs.append("cbc rate: " + safe_err(e))
    # M1B / M2 年增率
    try:
        j = gjson("https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EF15M01")
        labels = [l.get("data", l) if isinstance(l, dict) else l for l in j["data"]["structure"]["Table1"]]
        rows = [r for r in j["data"]["dataSets"] if r and r[0]]
        row, prow = rows[-1], rows[-2]
        # 每個標籤佔兩欄：金額、年增率；標籤用全形 Ｍ１Ｂ／Ｍ２
        def col(name_part):
            fw = name_part.replace("M", "Ｍ").replace("1", "１").replace("2", "２").replace("B", "Ｂ")
            idx = [k for k, l in enumerate(labels) if l.endswith(fw) or l.endswith(name_part)]
            return 2 + 2 * idx[0] if idx else None
        for key, name in (("M1B", "M1B 年增"), ("M2", "M2 年增")):
            c = col(key)
            if c and row[c] not in ("-", ""):
                auto[key] = {"label": name, "value": f"{float(row[c]):.2f}%", "period": row[0].replace("M", "-"),
                             "prev": f"{float(prow[c]):.2f}%" if prow[c] not in ("-", "") else None,
                             "tone": "up" if prow[c] not in ("-", "") and float(row[c]) > float(prow[c]) else "down" if prow[c] not in ("-", "") and float(row[c]) < float(prow[c]) else "", "auto": True}
                hist_put("macro", key, row[0].replace("M", "-"), float(row[c]))
    except Exception as e:  # noqa: BLE001
        log("cbc money", e); errs.append("cbc money: " + safe_err(e))
    # 信義房價季指數（全台）
    try:
        raw = get("https://www.sinyinews.com.tw/quarterly").text
        qmap = {"一": 1, "二": 2, "三": 3, "四": 4}
        pm = re.search(r"(20\d\d)年第([一二三四])季", raw)
        period = f"{pm.group(1)}/Q{qmap[pm.group(2)]}" if pm else ""
        chg = re.search(r'"area"\s*:\s*"台灣"[^}]*?"增減率\(qoq\)"\s*:\s*(-?[\d.]+)[^}]*?"增減率\(yoy\)"\s*:\s*(-?[\d.]+)', raw, re.S)
        idx = (re.search(r"台灣</p>\s*</dt>\s*<dd>\s*<p>\s*([\d.]+)", raw)
               or re.search(r"台灣\s*</t[dh]>\s*<td[^>]*>\s*([\d.]+)", raw))
        if chg and idx:
            q, y = float(chg.group(1)), float(chg.group(2))
            auto["house"] = {"label": "信義房價指數（全台）", "value": idx.group(1), "period": period,
                             "sub": f"季 {q:+.2f}% · 年 {y:+.2f}%", "tone": "up" if y > 0 else "down", "auto": True}
            if period:
                hist_put("macro", "house", period, float(idx.group(1)))
        else:
            errs.append(f"sinyi parse: chg={bool(chg)} idx={bool(idx)}")
    except Exception as e:  # noqa: BLE001
        log("sinyi", e); errs.append("sinyi: " + safe_err(e))
    # 景氣燈號（國發會 SPA，用 Playwright 渲染）
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(user_agent=UA, locale="zh-TW")
            pg.goto("https://index.ndc.gov.tw/n/zh_tw/lightscore", wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(2500)
            txt = pg.inner_text("body")
            b.close()
        mm = re.search(r"(1\d\d|20\d\d)\s*年\s*(\d{1,2})\s*月", txt)
        score = re.search(r"綜合判斷分數[^\d]{0,20}(\d{1,2})\s*分", txt) or re.search(r"(\d{1,2})\s*分", txt)
        light = re.search(r"(紅燈|黃紅燈|綠燈|黃藍燈|藍燈)", txt)
        if score and light:
            y = int(mm.group(1)) if mm else None
            if y and y < 1911:
                y += 1911
            period = f"{y}-{int(mm.group(2)):02d}" if mm else ""
            auto["light"] = {"label": "景氣燈號", "value": light.group(1), "score": int(score.group(1)), "period": period, "auto": True}
            if period:
                hist_put("macro", "light_score", period, int(score.group(1)))
    except Exception as e:  # noqa: BLE001
        log("ndc light", e); errs.append("ndc light: " + safe_err(e))
    # 主計總處 SDMX：CPI 年增（成功才覆蓋手動值）
    try:
        url = ("https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/A030101015/1.1.M"
               f"&startTime={TODAY_TPE.year - 2}-M01&endTime={TODAY_TPE.year}-M12")
        j = gjson(url, headers={"Accept": "application/json"})
        ds = j["data"]["dataSets"][0]["series"]
        first = next(iter(ds.values()))["observations"]
        vals = [float(v[0]) for _, v in sorted(first.items(), key=lambda kv: int(kv[0]))]
        periods = [x["id"] for x in j["data"]["structure"]["dimensions"]["observation"][0]["values"]]
        if len(vals) >= 14 and len(periods) == len(vals):
            cur, last, prevv, prevlast = vals[-1], vals[-13], vals[-2], vals[-14]
            yoy, yoy_prev = (cur - last) / last * 100, (prevv - prevlast) / prevlast * 100
            period = periods[-1].replace("-M", "-")
            if items.get("CPI 年增", {}).get("period") != period:
                items["CPI 年增"] = {"label": "CPI 年增", "value": f"{yoy:.2f}%", "period": period, "prev": f"{yoy_prev:.2f}%",
                                   "tone": "up" if yoy > yoy_prev else "down" if yoy < yoy_prev else ""}
    except Exception as e:  # noqa: BLE001
        log("dgbas sdmx", e)
    # 自動項目：這輪沒抓到就沿用上一版
    old_auto = {it["label"]: it for it in prev.get("items", []) if it.get("auto")}
    order = ["light", "rate", "M1B", "M2", "house"]
    auto_items = [auto[k] for k in order if k in auto]
    got = {a["label"] for a in auto_items}
    auto_items += [v for k, v in old_auto.items() if k not in got]
    if not items and not auto_items:
        raise RuntimeError("no macro items; edit data/panels/macro.json by hand")
    note = ("自動：景氣燈號（國發會）· 重貼現率、M1B、M2（央行）· 房價指數（信義）。"
            "手動：CPI、核心 CPI、PPI、失業率、GDP、CCI（主計總處 SDMX 擋 GitHub IP，公布日跟我說一聲就更新）")
    return {"items": list(items.values()) + auto_items, "note": note, "auto_errors": errs}



# ---------- pulse: 24 小時會動的東西（盤中 5 分鐘線） ----------
PULSE = [("^TWII", "台股加權", "TWD"), ("BTC-USD", "Bitcoin", "USD"), ("ETH-USD", "Ethereum", "USD"),
         ("ES=F", "S&P 500 期貨", "USD"), ("NQ=F", "Nasdaq 期貨", "USD"), ("DX-Y.NYB", "美元指數", "")]


def yahoo_intraday(sym):
    j = _yahoo_get(sym, {"range": "1d", "interval": "5m", "includePrePost": "false"})
    res = j["chart"]["result"][0]
    meta = res["meta"]
    closes = res["indicators"]["quote"][0].get("close") or []
    ts = res.get("timestamp") or []
    series = [(t, c) for t, c in zip(ts, closes) if c is not None]
    price = meta.get("regularMarketPrice") or (series[-1][1] if series else None)
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    # 盤中／休市：chart API 不給 marketState，用當日正常交易時段判斷
    state = "CLOSED"
    try:
        reg = meta["currentTradingPeriod"]["regular"]
        now_ts = int(NOW.timestamp())
        if reg["start"] <= now_ts < reg["end"]:
            state = "REGULAR"
        elif now_ts < reg["start"]:
            state = "PRE"
        else:
            state = "POST"
    except Exception:
        pass
    if sym.endswith("-USD"):
        state = "REGULAR"  # 加密貨幣 24 小時
    return {"price": price, "prev": prev, "chg_pct": (price - prev) / prev * 100 if price and prev else None,
            "series": [c for _, c in series][-80:], "asOf": series[-1][0] if series else meta.get("regularMarketTime"),
            "state": state}



INTRADAY_PATH = DATA / "intraday.json"


def _intraday_series(key: str, ts: int, price: float, day: str):
    """把即時價累積成當日 5 分鐘序列（官方端點只給現價，走勢自己累積）。"""
    db = {}
    if INTRADAY_PATH.exists():
        try:
            db = json.loads(INTRADAY_PATH.read_text(encoding="utf-8"))
        except Exception:
            db = {}
    rec = db.get(key) or {}
    if rec.get("day") != day:
        rec = {"day": day, "pts": []}
    if not rec["pts"] or ts - rec["pts"][-1][0] >= 240:
        rec["pts"].append([ts, price])
    rec["pts"] = rec["pts"][-80:]
    db[key] = rec
    write_json(INTRADAY_PATH, db, separators=(",", ":"))
    return [p for _, p in rec["pts"]]


def coingecko(coin: str):
    j = gjson(f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart", params={"vs_currency": "usd", "days": 1},
              headers={"Accept": "application/json"})
    pts = [(int(t / 1000), p) for t, p in j.get("prices", []) if p]
    if not pts:
        raise RuntimeError("coingecko empty")
    price, prev = pts[-1][1], pts[0][1]
    return {"price": price, "prev": prev, "chg_pct": (price - prev) / prev * 100, "series": [p for _, p in pts][-80:],
            "asOf": pts[-1][0], "state": "REGULAR"}


def twse_mis():
    """證交所官方即時：加權指數現值、昨收、時間。"""
    r = S.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp", params={"ex_ch": "tse_t00.tw", "json": "1", "delay": "0", "_": int(time.time() * 1000)},
              headers={"Referer": "https://mis.twse.com.tw/stock/index.jsp", "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    m = (r.json().get("msgArray") or [{}])[0]
    price, prev = num(m.get("z")) or num(m.get("y")), num(m.get("y"))
    if not price:
        raise RuntimeError("mis: no price")
    tlong = int(m.get("tlong") or 0) // 1000
    day = m.get("d") or NOW.astimezone(TPE).strftime("%Y%m%d")
    now_t = NOW.astimezone(TPE)
    state = "REGULAR" if now_t.weekday() < 5 and (9, 0) <= (now_t.hour, now_t.minute) < (13, 35) else "CLOSED"
    series = _intraday_series("TWII", tlong or int(NOW.timestamp()), price, day) if state == "REGULAR" else None
    if series is None:
        db = json.loads(INTRADAY_PATH.read_text(encoding="utf-8")) if INTRADAY_PATH.exists() else {}
        series = [p for _, p in (db.get("TWII") or {}).get("pts", [])]
    return {"price": price, "prev": prev, "chg_pct": (price - prev) / prev * 100 if prev else None,
            "series": series, "asOf": tlong or int(NOW.timestamp()), "state": state}


def twse_mis_quotes(codes):
    """證交所官方即時（個股批次）：回 {code: {price, prev, chg, pct, day, time}}；未成交（z='-'）就略過該檔。"""
    ex = "|".join(f"tse_{c}.tw" for c in codes)
    r = S.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp", params={"ex_ch": ex, "json": "1", "delay": "0", "_": int(time.time() * 1000)},
              headers={"Referer": "https://mis.twse.com.tw/stock/index.jsp", "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = {}
    for m in r.json().get("msgArray") or []:
        c = m.get("c"); z = num(m.get("z")); y = num(m.get("y"))
        if not c or not z or not y:
            continue
        d = m.get("d") or ""
        out[c] = {"price": z, "prev": y, "chg": round(z - y, 2), "pct": (z - y) / y * 100, "day": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "",
                  "time": (m.get("t") or "")[:5]}
    return out


def _mis_override(item, q, daily_date):
    """MIS 的日期比 OpenAPI 日資料新（盤中或收盤後尚未出日檔）就用即時值蓋掉。"""
    if not q or not q.get("day") or (daily_date and q["day"] <= daily_date):
        return False
    item.update({"price": q["price"], "chg": q["chg"], "pct": q["pct"], "date": q["day"], "live": q["time"]})
    return True


def p_pulse():
    items = []
    for sym, name, ccy in PULSE:
        q = None
        try:  # 官方／專用來源優先，Yahoo 備援
            if sym == "^TWII":
                q = twse_mis()
            elif sym in ("BTC-USD", "ETH-USD"):
                q = coingecko("bitcoin" if sym.startswith("BTC") else "ethereum")
        except Exception as e:  # noqa: BLE001
            log("pulse primary", sym, e)
        if q is None:
            try:
                q = yahoo_intraday(sym)
            except Exception as e:  # noqa: BLE001
                log("pulse", sym, e)
                continue
        elif sym == "^TWII" and not q.get("series"):
            try:  # 官方端點沒有整日走勢：收盤後用 Yahoo 的 5 分鐘序列補圖
                q["series"] = yahoo_intraday(sym)["series"]
            except Exception as e:  # noqa: BLE001
                log("pulse twii spark", e)
        items.append({"sym": sym, "name": name, "ccy": ccy, "price": q["price"], "chg_pct": q["chg_pct"],
                      "spark": q["series"], "asOf": q["asOf"], "state": q["state"]})
    if not items:
        raise RuntimeError("no pulse quotes")
    return {"label": "5 分鐘線", "items": items}


# ---------- 第二階段：氣象（CWA） ----------
CWA = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"


def cwa(dataset, **params):
    if not CWA_KEY:
        raise RuntimeError("no CWA_API_KEY")
    j = gjson(CWA + dataset, params={"Authorization": CWA_KEY, "format": "JSON", **params})
    if str(j.get("success")).lower() != "true":
        raise RuntimeError(f"cwa {dataset}: {str(j)[:100]}")
    return j["records"]


def _cwa_num(v):
    x = num(v)
    return None if x is None or x <= -90 else x


def p_weather():
    cities = [("臺北", "臺北市", "台北"), ("臺中", "臺中市", "台中")]
    out = []
    now_obs = {st["StationName"]: st for st in cwa("O-A0003-001", StationName="臺北,臺中").get("Station", [])}
    rain = {st["StationName"]: st for st in cwa("O-A0002-001", StationName="臺北,臺中").get("Station", [])}
    fc = {loc["locationName"]: loc for loc in cwa("F-C0032-001", locationName="臺北市,臺中市").get("location", [])}
    for st_name, county, label in cities:
        o = now_obs.get(st_name, {})
        we = o.get("WeatherElement", {})
        r = rain.get(st_name, {}).get("RainfallElement", {})
        f = fc.get(county, {})
        els = {e["elementName"]: e["time"] for e in f.get("weatherElement", [])}
        def fparam(name, i=0):
            try:
                return els[name][i]["parameter"]["parameterName"]
            except Exception:
                return None
        out.append({
            "city": label,
            "temp": _cwa_num(we.get("AirTemperature")), "rh": _cwa_num(we.get("RelativeHumidity")),
            "weather": we.get("Weather"), "wind": _cwa_num(we.get("WindSpeed")),
            "rain10": _cwa_num((r.get("Past10Min") or {}).get("Precipitation")),
            "rain1h": _cwa_num((r.get("Past1hr") or {}).get("Precipitation")),
            "rain24h": _cwa_num((r.get("Past24hr") or {}).get("Precipitation")),
            "obsTime": (o.get("ObsTime") or {}).get("DateTime"),
            "forecast": [{"start": els.get("Wx", [{}])[i].get("startTime", "")[5:16] if els.get("Wx") and len(els["Wx"]) > i else "",
                          "wx": fparam("Wx", i), "pop": fparam("PoP", i), "minT": fparam("MinT", i), "maxT": fparam("MaxT", i)}
                         for i in range(3)],
        })
        if out[-1]["temp"] is not None:
            hist_put("weather", label + "_temp", NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M"), out[-1]["temp"])
    warns = []
    try:
        for loc in cwa("W-C0033-001").get("location", []):
            hz = (loc.get("hazardConditions") or {}).get("hazards") or []
            for h in hz:
                info = h.get("info") or {}
                if info.get("phenomena"):
                    warns.append({"where": loc.get("locationName"), "what": info.get("phenomena"), "level": info.get("significance")})
    except Exception as e:  # noqa: BLE001
        log("cwa warn", e)
    return {"label": "氣象署", "items": out, "warnings": warns[:12]}


# ---------- 第二階段：台灣脈搏（TDX：YouBike＋國道） ----------
TDX = "https://tdx.transportdata.tw/api/basic/v2/"
_tdx_token = None
_tdx_last = 0.0
_tdx_cache: dict = {}


def tdx(path, **params):
    global _tdx_token
    headers = {}
    if TDX_ID and TDX_SECRET:
        if not _tdx_token:
            r = S.post("https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token",
                       data={"grant_type": "client_credentials", "client_id": TDX_ID, "client_secret": TDX_SECRET}, timeout=TIMEOUT)
            r.raise_for_status()
            _tdx_token = r.json()["access_token"]
        headers["Authorization"] = "Bearer " + _tdx_token
    base = TDX.replace("/v2/", "/v1/") if path.startswith("v1:") else TDX
    ck = path + json.dumps(params, sort_keys=True)
    if ck in _tdx_cache:  # 同一輪內同一端點只打一次（YouBike 可借數兩個面板共用）
        return _tdx_cache[ck]
    # TDX 對連續呼叫會回 429：每次間隔 2 秒，429 時退避重試
    global _tdx_last
    for attempt in range(4):
        wait = max(0.0, 2.0 - (time.time() - _tdx_last))
        if wait:
            time.sleep(wait)
        _tdx_last = time.time()
        try:
            out = gjson(base + path.replace("v1:", ""), params={"$format": "JSON", **params}, headers=headers)
            _tdx_cache[ck] = out
            return out
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                if attempt < 3:
                    time.sleep(5 * (2 ** attempt))  # 5 / 10 / 20 秒；TDX 是每個來源 IP 每秒 50 次，GitHub runner 共用 IP
                    continue
                raise RuntimeError(f"429 on {path} body={e.response.text[:160]!r}")
            raise


def p_tw_pulse():
    """全台脈搏：沿用地圖那一輪的 TDX 快取（不多打 API）。YouBike／停車場依縣市，國道依路線方向。"""
    st = {}
    if GEO_STATIC_PATH.exists():
        try:
            st = json.loads(GEO_STATIC_PATH.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    avail = st.get("avail", {})
    key = NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M")
    bikes = []
    for city, meta in GEO_CITIES.items():
        if not avail.get(city, {}).get("bikes"):
            continue
        try:
            rows = _tdx_opt(f"Bike/Availability/City/{city}") or []
        except Exception as e:  # noqa: BLE001
            log("tw_pulse bikes", city, e); continue
        rows = [r for r in rows if r.get("ServiceStatus", 1) == 1]
        if not rows:
            continue
        rent = sum(r.get("AvailableRentBikes") or 0 for r in rows)
        empty = sum(1 for r in rows if (r.get("AvailableRentBikes") or 0) == 0)
        full = sum(1 for r in rows if (r.get("AvailableReturnBikes") or 0) == 0)
        label = meta["label"]
        hist_put("youbike", label, key, rent)
        park = None
        if avail.get(city, {}).get("parking"):
            try:
                tot = av_ = 0
                for r in _tdx_opt(f"v1:Parking/OffStreet/ParkingAvailability/City/{city}") or []:
                    t_, a_ = r.get("TotalSpaces"), r.get("AvailableSpaces")
                    car = next((a for a in r.get("Availabilities") or [] if a.get("SpaceType") == 1), None)
                    if car and car.get("NumberOfSpaces"):
                        t_, a_ = car["NumberOfSpaces"], car.get("AvailableSpaces")
                    if t_ and a_ is not None and a_ >= 0 and t_ >= 20:
                        tot += t_; av_ += a_
                if tot:
                    park = round(av_ / tot * 100, 1)
            except Exception as e:  # noqa: BLE001
                log("tw_pulse parking", city, e)
        bikes.append({"city": label, "stations": len(rows), "rent": rent, "empty": empty, "full": full, "park_pct": park,
                      "spark": hist_get("youbike", label, 48)})
    bikes.sort(key=lambda b: -b["stations"])
    # 國道：各國道南北向小客車平均區間速率
    live = tdx("Road/Traffic/Live/ETag/Freeway")
    agg = {}
    for pr in live.get("ETagPairLives", []):
        pid = pr.get("ETagPairID", "")
        m = re.match(r"^(\d{2})F\d{4}([NSEW])", pid)
        if not m:
            continue
        for fl in pr.get("Flows", []):
            if fl.get("VehicleType") == 31 and (fl.get("SpaceMeanSpeed") or 0) > 0 and (fl.get("VehicleCount") or 0) > 0:
                k = (m.group(1), m.group(2))
                a = agg.setdefault(k, [0.0, 0])
                a[0] += fl["SpaceMeanSpeed"] * fl["VehicleCount"]
                a[1] += fl["VehicleCount"]
    dirn = {"N": "北", "S": "南", "E": "東", "W": "西"}
    roads = []
    for (no, d), (w, c) in sorted(agg.items()):
        if no in ("01", "03", "05") and c > 0:
            spd = w / c
            hist_put("freeway", f"{no}{d}", key, round(spd, 1))
            roads.append({"road": f"國道{int(no)}", "dir": dirn.get(d, d), "speed": round(spd, 1), "count": c,
                          "spark": hist_get("freeway", f"{no}{d}", 48)})
    # 最塞的區間（名稱來自地圖的靜態表）
    names = {pid: desc for pid, desc, _ in st.get("etag", [])}
    worst = []
    for pr in live.get("ETagPairLives", []):
        for fl in pr.get("Flows", []):
            if fl.get("VehicleType") == 31 and 0 < (fl.get("SpaceMeanSpeed") or 0) < 40 and (fl.get("VehicleCount") or 0) >= 30:
                worst.append((fl["SpaceMeanSpeed"], pr.get("ETagPairID")))
    worst.sort()
    jams = [{"section": names.get(pid, pid), "speed": round(spd, 0)} for spd, pid in worst[:6]]
    if not bikes and not roads:
        raise RuntimeError("tw_pulse: nothing")
    return {"label": "TDX", "bikes": bikes, "roads": roads, "jams": jams, "roadTime": live.get("UpdateTime")}


# ---------- 第二階段：PTT（curl_cffi 模擬瀏覽器） ----------
PTT_BOARDS = [  # (板, 中文, 情緒面向)
    ("Gossiping", "八卦", "大眾"), ("HatePolitics", "政黑", "政治"), ("Stock", "股板", "市場"), ("WomenTalk", "女板", "生活"),
    ("Lifeismoney", "省錢", "消費"), ("home-sale", "房產", "消費"), ("car", "汽車", "消費"), ("e-shopping", "網購", "消費"),
    ("Tech_Job", "科技業", "職場"), ("MakeUp", "美妝", "消費"), ("BeautySalon", "美容", "消費"), ("movie", "電影", "文化"),
]
PTT_PAGES = 2  # 每板抓最新兩頁（約 40 篇），才有足夠樣本算情緒


def _ptt_page(sess, board, idx=None):
    url = f"https://www.ptt.cc/bbs/{board}/index{'' if idx is None else idx}.html"
    html = sess.get(url, timeout=20).text
    if "r-ent" not in html:
        raise RuntimeError("blocked or empty")
    prev = re.search(r'href="/bbs/' + re.escape(board) + r'/index(\d+)\.html">&lsaquo; 上頁', html)
    rows = []
    for ent in html.split('<div class="r-ent">')[1:]:  # 用切割而不是 regex 配對，meta 裡的巢狀 div 才不會截斷日期
        ent = ent.split('<div class="r-list-sep">')[0]
        nrec = re.search(r'<div class="nrec">(?:<span class="hl f\d">)?([^<]*)', ent)
        t = re.search(r'<div class="title">\s*<a href="([^"]+)">([^<]+)</a>', ent)
        d = re.search(r'<div class="date">\s*([^<]+)</div>', ent)
        if not t:
            continue
        push_raw = (nrec.group(1) if nrec else "").strip()
        if push_raw == "爆":
            push = 100
        elif push_raw.startswith("X"):
            push = -10 if push_raw == "XX" else -int(num(push_raw[1:]) or 1)
        else:
            push = int(num(push_raw) or 0)
        rows.append({"board": board, "title": t.group(2).strip(), "push": push, "url": "https://www.ptt.cc" + t.group(1), "date": (d.group(1) if d else "").strip()})
    return rows, (int(prev.group(1)) if prev else None)


def p_ptt():
    try:
        from curl_cffi import requests as cffi
    except ImportError:
        raise RuntimeError("curl_cffi not installed")
    sess = cffi.Session(impersonate="chrome")
    sess.cookies.set("over18", "1", domain="www.ptt.cc")
    items, boards = [], []
    today_md = NOW.astimezone(TPE).strftime("%m/%d").lstrip("0").replace("/0", "/")
    for board, zh, facet in PTT_BOARDS:
        rows = []
        try:
            page, prev_idx = _ptt_page(sess, board)
            rows += page
            for _ in range(PTT_PAGES - 1):
                if prev_idx is None:
                    break
                time.sleep(0.5)
                page, prev_idx = _ptt_page(sess, board, prev_idx)
                rows += page
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            log("ptt", board, e); continue
        seen_u, uniq = set(), []
        for r in rows:  # 置底文會在每頁重複出現
            if r["url"] not in seen_u and not r["title"].startswith(("[公告]", "Fw: [公告]")):
                seen_u.add(r["url"]); uniq.append(r)
        rows = uniq
        if not rows:
            continue
        pushes = [r["push"] for r in rows]
        hot = [r for r in rows if r["push"] >= 30]
        boom = sum(1 for r in rows if r["push"] >= 100); boo = sum(1 for r in rows if r["push"] < 0)
        heat = sum(max(x, 0) for x in pushes)
        today = sum(1 for r in rows if r["date"].strip() == today_md)
        # 情緒：正推比例（>0 的文章占比）減噓文占比 → -1..1；每輪存歷史畫小圖
        mood = round((sum(1 for x in pushes if x > 0) - boo) / len(pushes), 2)
        hist_put("ptt", board, NOW_ISO[:13], heat)  # 每小時一點
        boards.append({"board": board, "zh": zh, "facet": facet, "n": len(rows), "today": today, "heat": heat, "boom": boom, "boo": boo, "mood": mood,
                       "spark": hist_get("ptt", board, 48), "top": sorted(hot, key=lambda r: -r["push"])[:3]})
        items += hot
    if not items and not boards:
        raise RuntimeError("ptt: nothing fetched (blocked?)")
    items.sort(key=lambda x: -x["push"])
    # 爆卦／新聞標籤：八卦板的 [爆卦] 是最早的突發訊號
    breaking = [r for r in items if r["title"].startswith("[爆卦]")][:5]
    return {"label": "推文 ≥30", "items": items[:24], "boards": boards, "breaking": breaking}


# ---------- 第二階段：TikTok TW 熱門 hashtag（Playwright 渲染，每日一次，可能失敗） ----------
def p_tiktok():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")
    url = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/zh-TW?region=TW&period=7"
    items = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(user_agent=UA, locale="zh-TW")
        captured = []
        pg.on("response", lambda r: captured.append(r) if "popular_trend/hashtag/list" in r.url else None)
        pg.goto(url, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(3000)
        for r in captured:
            try:
                j = r.json()
                for h in (j.get("data") or {}).get("list") or []:
                    items.append({"tag": h.get("hashtag_name"), "posts": h.get("publish_cnt"), "views": h.get("video_views"),
                                  "rank": h.get("rank"), "trend": h.get("rank_diff")})
            except Exception:
                pass
        if not items:  # 退而求其次：讀 DOM 文字
            txt = pg.inner_text("body")
            for m in re.finditer(r"#\s?([\w\u4e00-\u9fff]{2,30})", txt):
                tag = m.group(1)
                if tag not in [i["tag"] for i in items]:
                    items.append({"tag": tag})
                if len(items) >= 15:
                    break
        b.close()
    if not items:
        raise RuntimeError("tiktok: no hashtags captured")
    return {"label": "近 7 天 · TW", "items": items[:15]}


# ---------- 台股大盤加值：法人、漲跌家數、類股、台積電、台指期夜盤、櫃買、融資融券 ----------
SECTORS = [("電子工業類指數", "電子"), ("半導體類指數", "半導體"), ("金融保險類指數", "金融"), ("未含電子指數", "非電子"),
           ("航運類指數", "航運"), ("生技醫療類指數", "生技"), ("鋼鐵類指數", "鋼鐵"), ("紡織纖維類指數", "紡織"),
           ("觀光餐旅類指數", "觀光餐旅"), ("貿易百貨類指數", "百貨")]


def _rwd(url, **params):
    return gjson(url, params={"response": "json", **params}, headers={"Referer": "https://www.twse.com.tw/"})


def _cffi_json(url, **params):
    from curl_cffi import requests as cffi
    r = cffi.get(url, params=params, impersonate="chrome", timeout=25)
    r.raise_for_status()
    return r.json()


def p_tw_market():
    out = {}
    # 三大法人（元 → 億）
    try:
        j = _rwd("https://www.twse.com.tw/rwd/zh/fund/BFI82U")
        rows = {r[0]: num(r[3]) for r in j.get("data", [])}
        foreign = (rows.get("外資及陸資(不含外資自營商)") or 0) + (rows.get("外資自營商") or 0)
        dealer = (rows.get("自營商(自行買賣)") or 0) + (rows.get("自營商(避險)") or 0)
        out["institutions"] = {"date": j.get("date"), "items": [
            {"name": "外資", "net": round(foreign / 1e8, 1)}, {"name": "投信", "net": round((rows.get("投信") or 0) / 1e8, 1)},
            {"name": "自營商", "net": round(dealer / 1e8, 1)}, {"name": "合計", "net": round((rows.get("合計") or 0) / 1e8, 1)}]}
        for it in out["institutions"]["items"]:
            hist_put("institutions", it["name"], roc_to_iso(j.get("date", "")), it["net"])
    except Exception as e:  # noqa: BLE001
        log("BFI82U", e)
    # 漲跌家數（股票欄）
    try:
        j = _rwd("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX", type="MS")
        tbl = next(t for t in j.get("tables", []) if "漲跌證券數" in (t.get("title") or ""))
        cnt = {}
        for r in tbl.get("data", []):
            m = re.match(r"^([\d,]+)(?:\((\d+)\))?", str(r[2]))
            if m:
                cnt[r[0].split("(")[0]] = {"n": int(m.group(1).replace(",", "")), "limit": int(m.group(2) or 0)}
        out["breadth"] = {"up": cnt.get("上漲", {}).get("n"), "up_limit": cnt.get("上漲", {}).get("limit"),
                          "down": cnt.get("下跌", {}).get("n"), "down_limit": cnt.get("下跌", {}).get("limit"),
                          "flat": cnt.get("持平", {}).get("n")}
    except Exception as e:  # noqa: BLE001
        log("breadth", e)
    # 類股
    try:
        rows = {r["指數"]: r for r in gjson("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX")}
        secs = []
        for key, label in SECTORS:
            r = rows.get(key)
            if not r:
                continue
            pct = num(r.get("漲跌百分比"))
            if pct is not None and r.get("漲跌") == "-":
                pct = -abs(pct)
            secs.append({"name": label, "close": num(r.get("收盤指數")), "pct": pct})
            hist_put("sectors", label, roc_to_iso(r.get("日期", "")), num(r.get("收盤指數")))
        out["sectors"] = sorted(secs, key=lambda x: -(x["pct"] or 0))
    except Exception as e:  # noqa: BLE001
        log("sectors", e)
    # 台積電
    try:
        r = next(x for x in gjson("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL") if x.get("Code") == "2330")
        px, ch = num(r["ClosingPrice"]), num(r["Change"])
        hist_put("tw_stocks", "2330", roc_to_iso(r["Date"]), px)
        out["tsmc"] = {"price": px, "chg": ch, "pct": ch / (px - ch) * 100 if px and ch is not None else None,
                       "date": roc_to_iso(r["Date"]), "spark": hist_get("tw_stocks", "2330")}
    except Exception as e:  # noqa: BLE001
        log("tsmc", e)
    try:  # 盤中／收盤後日檔還沒出：用 MIS 即時蓋掉（日檔通常 16:00 後才更新）
        q = twse_mis_quotes(["2330"]).get("2330")
        if out.get("tsmc") is None and q:
            out["tsmc"] = {"spark": hist_get("tw_stocks", "2330")}
        if out.get("tsmc") is not None:
            _mis_override(out["tsmc"], q, out["tsmc"].get("date"))
    except Exception as e:  # noqa: BLE001
        log("tsmc mis", e)
    # 台指期（FinMind）：日盤與夜盤
    try:
        start = (TODAY_TPE - timedelta(days=10)).isoformat()
        headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {}
        rows = gjson("https://api.finmindtrade.com/api/v4/data",
                     params={"dataset": "TaiwanFuturesDaily", "data_id": "TX", "start_date": start}, headers=headers).get("data", [])
        rows = [r for r in rows if r.get("volume", 0) > 0 and re.match(r"^\d{6}$", str(r.get("contract_date", "")))]
        if rows:
            def latest(session):
                cand = [r for r in rows if r["trading_session"] == session]
                if not cand:
                    return None
                d = max(r["date"] for r in cand)
                near = min(r["contract_date"] for r in cand if r["date"] == d)
                return next(r for r in cand if r["date"] == d and r["contract_date"] == near)
            day, night = latest("position"), latest("after_market")
            out["tx"] = {"contract": (night or day)["contract_date"],
                         "day": {"date": day["date"], "close": day["close"], "pct": day["spread_per"]} if day else None,
                         "night": {"date": night["date"], "close": night["close"], "pct": night["spread_per"],
                                   "vs_day": round(night["close"] - day["close"], 0) if (day and day["contract_date"] == night["contract_date"]) else None} if night else None}
    except Exception as e:  # noqa: BLE001
        log("tx futures", e)
    # 櫃買（TPEx openapi 擋一般 UA，用 curl_cffi）
    try:
        j = _cffi_json("https://www.tpex.org.tw/openapi/v1/tpex_mainborad_highlight")
        row = j[0] if isinstance(j, list) and j else j
        idx, chg = num(row.get("CloseIndex")), num(row.get("IndexChange"))
        d = roc_to_iso(row.get("Date", ""))
        out["tpex"] = {"date": d, "index": idx, "chg": chg, "pct": chg / (idx - chg) * 100 if idx and chg is not None else None,
                       "up": num(row.get("PriceRiseCompanyNumbers")), "down": num(row.get("PriceDeclineCompanyNumbers")),
                       "flat": num(row.get("PriceFlatCompanyNumbers")), "value": num(row.get("DailyTradingValue"))}
        if idx:
            hist_put("tpex", "OTC", d, idx)
        out["tpex"]["spark"] = hist_get("tpex", "OTC")
    except Exception as e:  # noqa: BLE001
        log("tpex", e)
    # 融資融券市場合計
    try:
        j = _rwd("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN", selectType="MS")
        tbls = j.get("tables") or [{"fields": j.get("fields"), "data": j.get("data"), "title": j.get("title")}]
        t0 = tbls[0]
        rows = {r[0]: r for r in (t0.get("data") or [])}
        def pick(key, i):
            r = rows.get(key)
            return num(r[i]) if r else None
        amt_today, amt_prev = pick("融資金額(仟元)", 5), pick("融資金額(仟元)", 4)
        out["margin"] = {"date": (t0.get("title") or "")[:11],
                         "margin_amt": round(amt_today / 1e5, 1) if amt_today else None,  # 仟元 → 億
                         "margin_amt_chg": round((amt_today - amt_prev) / 1e5, 1) if amt_today and amt_prev else None,
                         "margin_units": pick("融資(交易單位)", 5), "margin_units_chg": (pick("融資(交易單位)", 5) or 0) - (pick("融資(交易單位)", 4) or 0),
                         "short_units": pick("融券(交易單位)", 5), "short_units_chg": (pick("融券(交易單位)", 5) or 0) - (pick("融券(交易單位)", 4) or 0)}
        if amt_today:
            hist_put("margin", "amt", TODAY_TPE.isoformat(), round(amt_today / 1e5, 1))
    except Exception as e:  # noqa: BLE001
        log("margin", e)
    if not out:
        raise RuntimeError("tw_market: nothing")
    return out


# ---------- 地圖：停車場剩餘、YouBike、車速（台北／台中） ----------
# 全台縣市（TDX 代碼）：label、bbox、center、zoom。圖層有無由 TDX 回應決定（404 記在靜態快取，一天重試一次）
GEO_CITIES = {
    "Taipei": {"label": "台北市", "bbox": [121.45, 24.95, 121.67, 25.22], "center": [121.54, 25.05], "zoom": 11.3},
    "NewTaipei": {"label": "新北市", "bbox": [121.28, 24.67, 122.01, 25.30], "center": [121.50, 25.02], "zoom": 10.2},
    "Keelung": {"label": "基隆市", "bbox": [121.62, 25.05, 121.82, 25.20], "center": [121.74, 25.13], "zoom": 12},
    "Taoyuan": {"label": "桃園市", "bbox": [121.00, 24.60, 121.45, 25.12], "center": [121.25, 24.95], "zoom": 10.8},
    "Hsinchu": {"label": "新竹市", "bbox": [120.88, 24.72, 121.05, 24.86], "center": [120.97, 24.80], "zoom": 12},
    "HsinchuCounty": {"label": "新竹縣", "bbox": [120.90, 24.40, 121.40, 24.95], "center": [121.10, 24.75], "zoom": 10.5},
    "MiaoliCounty": {"label": "苗栗縣", "bbox": [120.60, 24.25, 121.30, 24.75], "center": [120.90, 24.50], "zoom": 10.3},
    "Taichung": {"label": "台中市", "bbox": [120.45, 23.95, 121.35, 24.45], "center": [120.68, 24.16], "zoom": 11},
    "ChanghuaCounty": {"label": "彰化縣", "bbox": [120.25, 23.80, 120.75, 24.20], "center": [120.50, 24.00], "zoom": 10.8},
    "NantouCounty": {"label": "南投縣", "bbox": [120.60, 23.40, 121.35, 24.20], "center": [120.90, 23.85], "zoom": 9.8},
    "YunlinCounty": {"label": "雲林縣", "bbox": [120.10, 23.50, 120.75, 23.85], "center": [120.40, 23.70], "zoom": 10.8},
    "Chiayi": {"label": "嘉義市", "bbox": [120.38, 23.43, 120.52, 23.53], "center": [120.45, 23.48], "zoom": 12.5},
    "ChiayiCounty": {"label": "嘉義縣", "bbox": [120.10, 23.20, 120.95, 23.65], "center": [120.40, 23.45], "zoom": 10.3},
    "Tainan": {"label": "台南市", "bbox": [120.00, 22.88, 120.70, 23.45], "center": [120.20, 23.00], "zoom": 11},
    "Kaohsiung": {"label": "高雄市", "bbox": [120.15, 22.45, 121.05, 23.50], "center": [120.32, 22.63], "zoom": 11},
    "PingtungCounty": {"label": "屏東縣", "bbox": [120.35, 21.85, 120.95, 22.90], "center": [120.50, 22.55], "zoom": 10.3},
    "YilanCounty": {"label": "宜蘭縣", "bbox": [121.30, 24.30, 122.00, 24.95], "center": [121.70, 24.70], "zoom": 10.3},
    "HualienCounty": {"label": "花蓮縣", "bbox": [120.90, 23.10, 121.80, 24.40], "center": [121.55, 23.90], "zoom": 9.5},
    "TaitungCounty": {"label": "台東縣", "bbox": [120.70, 21.90, 121.65, 23.45], "center": [121.10, 22.75], "zoom": 9.5},
    "PenghuCounty": {"label": "澎湖縣", "bbox": [119.30, 23.20, 119.75, 23.80], "center": [119.58, 23.57], "zoom": 11},
    "KinmenCounty": {"label": "金門縣", "bbox": [118.15, 24.35, 118.55, 24.55], "center": [118.35, 24.45], "zoom": 11.5},
    "LienchiangCounty": {"label": "連江縣", "bbox": [119.85, 25.90, 120.55, 26.40], "center": [119.95, 26.15], "zoom": 10.5},
}
GEO_STATIC_PATH = DATA / "geo_static.json"
GEO_PATH = DATA / "geo.json"
GEO_ERRS: list = []


def _in_bbox(lon, lat, b):
    return lon is not None and lat is not None and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]


def _tdx_opt(path, **params):
    """TDX 呼叫；404／空表示該縣市沒有這個資料集 → 回 None，不當錯誤。"""
    try:
        out = tdx(path, **params)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (404, 400):
            return None
        raise
    if isinstance(out, dict):
        for k in ("CarParks", "VDs", "ParkingAvailabilities", "VDLives", "ETagPairs", "ETagPairLives"):
            if k in out:
                return out[k] or None
        return out or None
    return out or None


def _geo_static():
    """靜態表（停車場座標、YouBike 站點、各縣市 VD 位置、國道 ETag 路段幾何）。
    一天重建一次，但分批：每輪最多做 5 個縣市，做完的記在 done，全部完成才更新 fetchedAt。
    沒有的圖層記 avail=False；429 不算沒有，留給下一輪。"""
    st = {}
    if GEO_STATIC_PATH.exists():
        try:
            st = json.loads(GEO_STATIC_PATH.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    for k, dflt in (("carparks", {}), ("bikes", {}), ("vd", {}), ("etag", []), ("avail", {}), ("done", [])):
        st.setdefault(k, dflt)
    try:
        t = datetime.fromisoformat(st.get("fetchedAt", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
    except Exception:
        t = datetime(2000, 1, 1, tzinfo=timezone.utc)
    fresh = NOW - t < timedelta(hours=24) and st["avail"]
    if fresh and not st["done"]:
        return st
    todo = [c for c in GEO_CITIES if c not in st["done"]]
    for city in todo[:5]:
        if time.time() > SOFT_DEADLINE - 240:
            break
        av = dict(st["avail"].get(city) or {"parking": False, "bikes": False, "vd": False})
        ok = True
        for key, path, parse in (
            ("parking", f"v1:Parking/OffStreet/CarPark/City/{city}",
             lambda rows: {c["CarParkID"]: [round(c["CarParkPosition"]["PositionLon"], 5), round(c["CarParkPosition"]["PositionLat"], 5),
                                            (c.get("CarParkName") or {}).get("Zh_tw", "")] for c in rows if (c.get("CarParkPosition") or {}).get("PositionLat")}),
            ("bikes", f"Bike/Station/City/{city}",
             lambda rows: {b["StationUID"]: [round(b["StationPosition"]["PositionLon"], 5), round(b["StationPosition"]["PositionLat"], 5),
                                             (b.get("StationName") or {}).get("Zh_tw", "").replace("YouBike2.0_", ""), b.get("BikesCapacity") or 0]
                           for b in rows if (b.get("StationPosition") or {}).get("PositionLat")}),
            ("vd", f"Road/Traffic/VD/City/{city}",
             lambda rows: {v["VDID"]: [round(v["PositionLon"], 5), round(v["PositionLat"], 5), v.get("RoadName", "")] for v in rows if v.get("PositionLat")}),
        ):
            store = {"parking": "carparks", "bikes": "bikes", "vd": "vd"}[key]
            try:
                rows = _tdx_opt(path)
                if rows:
                    st[store][city] = parse(rows)
                    av[key] = bool(st[store][city])
                else:
                    st[store].pop(city, None); av[key] = False
            except Exception as e:  # noqa: BLE001
                ok = False
                log("geo static", key, city, e); GEO_ERRS.append(f"static {key} {city}: " + safe_err(e))
                break
        st["avail"][city] = av
        if ok:
            st["done"].append(city)
        else:
            break  # 這輪 TDX 不順，剩下的縣市下一輪再建
    if not st["etag"] or not fresh:
        try:
            et = []
            for ep in tdx("Road/Traffic/ETagPair/Freeway").get("ETagPairs", []):
                g = ep.get("Geometry") or ""
                pts = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", g)
                if pts:
                    et.append([ep["ETagPairID"], ep.get("Description", ""), [[round(float(a), 4), round(float(b), 4)] for a, b in pts[::max(1, len(pts) // 12)]]])
            if et:
                st["etag"] = et
        except Exception as e:  # noqa: BLE001
            log("geo etag static", e); GEO_ERRS.append("etag static: " + safe_err(e))
    if all(c in st["done"] for c in GEO_CITIES):
        st["fetchedAt"] = NOW_ISO; st["done"] = []
    st["progress"] = f'{len(st["done"])}/{len(GEO_CITIES)}' if st["done"] else "完成"
    write_json(GEO_STATIC_PATH, st, separators=(",", ":"))
    return st


def p_geo():
    GEO_ERRS.clear()
    st = _geo_static()
    avail = st.get("avail", {})
    geo = {"generatedAt": NOW_ISO, "labels": {k: v["label"] for k, v in GEO_CITIES.items()},
           "views": {k: [v["center"], v["zoom"]] for k, v in GEO_CITIES.items()}, "avail": avail, "cities": {}, "freeway": []}
    prev_geo = {}
    if GEO_PATH.exists():
        try:
            prev_geo = json.loads(GEO_PATH.read_text(encoding="utf-8")).get("cities", {})
        except Exception:
            prev_geo = {}
    for city in GEO_CITIES:
        c = {"parking": [], "bikes": [], "speed": []}
        av = avail.get(city, {})
        if time.time() > SOFT_DEADLINE - 120:  # 時間不夠：這個縣市沿用上一輪
            geo["cities"][city] = prev_geo.get(city, c); continue
        if av.get("parking"):
            try:
                for r in _tdx_opt(f"v1:Parking/OffStreet/ParkingAvailability/City/{city}") or []:
                    pos = st["carparks"].get(city, {}).get(r.get("CarParkID"))
                    if not pos:
                        continue
                    total, avail_n = r.get("TotalSpaces"), r.get("AvailableSpaces")
                    car = next((a for a in r.get("Availabilities") or [] if a.get("SpaceType") == 1), None)
                    if car and car.get("NumberOfSpaces"):
                        total, avail_n = car["NumberOfSpaces"], car.get("AvailableSpaces")
                    if not total or avail_n is None or avail_n < 0 or total < 20:
                        continue
                    c["parking"].append([pos[0], pos[1], int(avail_n), int(total), pos[2][:18]])
            except Exception as e:  # noqa: BLE001
                log("geo parking", city, e); GEO_ERRS.append(f"parking {city}: " + safe_err(e))
                c["parking"] = (prev_geo.get(city) or {}).get("parking", [])  # 429 等：沿用上一輪
        if av.get("bikes"):
            try:
                for r in _tdx_opt(f"Bike/Availability/City/{city}") or []:
                    pos = st["bikes"].get(city, {}).get(r.get("StationUID"))
                    if pos and r.get("ServiceStatus", 1) == 1:
                        c["bikes"].append([pos[0], pos[1], int(r.get("AvailableRentBikes") or 0), int(pos[3] or 0), pos[2][:14]])
            except Exception as e:  # noqa: BLE001
                log("geo bikes", city, e); GEO_ERRS.append(f"bikes {city}: " + safe_err(e))
                c["bikes"] = (prev_geo.get(city) or {}).get("bikes", [])  # 429 等：沿用上一輪
        if av.get("vd"):
            try:
                for v in _tdx_opt(f"Road/Traffic/Live/VD/City/{city}") or []:
                    pos = st["vd"].get(city, {}).get(v.get("VDID"))
                    if not pos:
                        continue
                    sp = [ln.get("Speed") for lf in v.get("LinkFlows") or [] for ln in lf.get("Lanes") or [] if (ln.get("Speed") or 0) > 0]
                    if sp:
                        c["speed"].append([pos[0], pos[1], round(sum(sp) / len(sp)), pos[2][:10]])
            except Exception as e:  # noqa: BLE001
                log("geo vd live", city, e); GEO_ERRS.append(f"vd {city}: " + safe_err(e))
                c["speed"] = (prev_geo.get(city) or {}).get("speed", [])  # 429 等：沿用上一輪
        geo["cities"][city] = c
    # 國道 ETag 路段車速（全台，畫線）
    try:
        live = {pr["ETagPairID"]: next((f["SpaceMeanSpeed"] for f in pr.get("Flows", []) if f.get("VehicleType") == 31 and (f.get("SpaceMeanSpeed") or 0) > 0), None)
                for pr in tdx("Road/Traffic/Live/ETag/Freeway").get("ETagPairLives", [])}
        for pid, desc, pts in st.get("etag", []):
            spd = live.get(pid)
            if spd is not None:
                geo["freeway"].append([pts, round(spd), desc[:16]])
    except Exception as e:  # noqa: BLE001
        log("geo etag live", e); GEO_ERRS.append("etag live: " + safe_err(e))
    write_json(GEO_PATH, geo, separators=(",", ":"))
    summary = {city: {k: len(v) for k, v in c.items() if v} for city, c in geo["cities"].items()}
    summary = {k: v for k, v in summary.items() if v}
    if not summary and not geo["freeway"]:
        raise RuntimeError(f"geo: nothing errs={GEO_ERRS[:6]}")
    return {"label": "TDX", "cities_with_data": len(summary), "freeway": len(geo["freeway"]), "static": st.get("progress", ""),
            "totals": {k: sum(c.get(k, 0) for c in summary.values()) for k in ("parking", "bikes", "speed")}, "errs": GEO_ERRS[:12]}


# ---------- 時事：台灣 / 國際 / 關鍵字 / 訊號 ----------
# Vin 的關注領域（Google News 繁中）：每組顯示最新 3 則。帶引號＝精準比對。改這裡。
NEWS_GROUPS = [
    ("廣告與代理商", ['"廣告代理商"', "比稿 OR 廣告 得標", "廣告不實 OR 誇大不實 開罰", "廣告量 OR 行銷預算"]),
    ("品牌與設計", ['"品牌重塑" OR "品牌升級"', "台灣設計展 OR 文博會 OR 金點設計獎", '"視覺識別" OR "包裝設計"', "家具展 OR 室內設計 OR 設計師品牌"]),
    ("AI 大廠與模型", ["OpenAI OR Anthropic OR DeepMind 發布 OR 推出", "ChatGPT OR Claude OR Gemini 新功能 OR 新模型", "AI agent OR AI 代理人 OR 智慧代理",
                  "en:OpenAI OR Anthropic OR \"Google DeepMind\" launches OR announces OR releases", "en:\"AI agent\" OR agentic launch"]),
    ("AI 與製作工具", ["Sora OR Runway OR Kling 影片", "生成式AI 廣告 OR 生成式AI 版權", "Figma OR Canva 新功能", "開源模型 OR Ollama OR 本地部署"]),
    ("市場與投資", ["槓桿ETF OR 00631L OR 00675L", "聯準會 利率 OR FOMC", "台積電 法說 OR 台積電 ADR"]),
    ("地緣與科技政策", ["台海 OR 共機 OR 軍演", "關稅 台灣 OR 232條款", "半導體 出口管制 OR 晶片法案"]),
    ("時尚與奢華", ["LVMH OR Kering OR Hermès OR 愛馬仕", '"quiet luxury" OR 老錢風 OR 靜奢', "時裝週 OR 創意總監 上任", "精品 台灣 OR 精品 業績"]),
    ("文化與生活", ["廟宇 OR 媽祖 OR 民間信仰", "紀念幣 OR 錢幣 拍賣", "獨立書店 OR 誠品", "灣區 OR 舊金山 OR 加州 台灣人", "潭子 OR 台中 北屯"]),
]
NEWS_ERRS: list = []
HOT_POOL: list = []


def _rss_date(d: str) -> str:
    d = (d or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(d.replace("GMT", "+0000") if fmt.endswith("%z") else d, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TPE if "T" not in fmt else timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except Exception:
            continue
    return ""


def _rss(url, source, limit=8, strip_source=False, **params):
    try:
        raw = get(url, params=params or None).content
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 429):
            from curl_cffi import requests as cffi
            r = cffi.get(url, params=params or None, impersonate="chrome", timeout=25); r.raise_for_status(); raw = r.content
        else:
            raise
    root = ET.fromstring(raw.lstrip(b"\xef\xbb\xbf \r\n\t"))
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = source
        if strip_source and " - " in title:  # Google News：標題 - 來源
            title, tail = title.rsplit(" - ", 1)
            src = source or tail
        if not title:
            continue
        out.append({"source": src[:12], "title": title[:90], "url": (it.findtext("link") or "").strip(), "at": _rss_date(it.findtext("pubDate") or "")})
        if len(out) >= limit:
            break
    return out


def _gnews(q, source="", limit=6, lang="zh"):
    loc = {"hl": "en-US", "gl": "US", "ceid": "US:en"} if lang == "en" else {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    return _rss("https://news.google.com/rss/search", source, limit, strip_source=True, q=q, **loc)


def _try(name, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:  # noqa: BLE001
        log("news", name, e); NEWS_ERRS.append(f"{name}: {safe_err(e)}"); return []


def _dedupe_sort(items, limit):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x.get("at") or "", reverse=True):
        k = re.sub(r"\W+", "", it["title"])[:30]
        if k in seen:
            continue
        seen.add(k); out.append(it)
        if len(out) >= limit:
            break
    return out


def _gdelt_signal():
    """全球英文新聞提到 Taiwan 的量（近 24h vs 前 48h）與平均語調。"""
    sig = {}
    vol = None
    for attempt in range(3):  # GDELT 對 GitHub 共用 IP 很常 429，退避重試
        try:
            vol = gjson("https://api.gdeltproject.org/api/v2/doc/doc", params={"query": "Taiwan", "mode": "timelinevol", "timespan": "3d", "format": "json"})
            break
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429 and attempt < 2:
                time.sleep(20 * (attempt + 1)); continue
            raise
    pts = [(p["date"], float(p["value"])) for p in vol["timeline"][0]["data"] if p.get("value") is not None]
    cut = (NOW - timedelta(hours=24)).strftime("%Y%m%dT%H%M%SZ")
    recent = [v for d, v in pts if d >= cut]; before = [v for d, v in pts if d < cut]
    if recent and before:
        sig["vol"] = round(sum(recent) / len(recent), 3)
        sig["vol_ratio"] = round((sum(recent) / len(recent)) / max(1e-6, sum(before) / len(before)), 2)
    prev_g = (load_prev("news") or {}).get("signals", {}).get("gdelt") or {}
    tone_fresh = prev_g.get("tone_at") and (NOW - datetime.fromisoformat(prev_g["tone_at"].replace("Z", "+00:00"))) < timedelta(hours=1)
    for attempt in range(0 if tone_fresh else 2):  # 語調一小時內有值就不重抓；GDELT 大約一分鐘只肯給一次
        time.sleep(20 if attempt == 0 else 40)
        try:
            tone = gjson("https://api.gdeltproject.org/api/v2/doc/doc", params={"query": "Taiwan", "mode": "timelinetone", "timespan": "24h", "format": "json"})
            tp = [float(p["value"]) for p in tone["timeline"][0]["data"] if p.get("value") is not None]
            if tp:
                sig["tone"] = round(sum(tp) / len(tp), 2); sig["tone_at"] = NOW_ISO
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 1:
                log("gdelt tone", e)
    if "tone" not in sig:
        prev = (load_prev("news") or {}).get("signals", {}).get("gdelt") or {}
        if prev.get("tone") is not None and prev.get("tone_at") and (NOW - datetime.fromisoformat(prev["tone_at"].replace("Z", "+00:00"))) < timedelta(hours=6):
            sig["tone"], sig["tone_at"] = prev["tone"], prev["tone_at"]
    if not sig:
        raise RuntimeError("gdelt empty")
    return sig


try:
    from opencc import OpenCC
    _cc = OpenCC("s2twp")  # 維基標題常是簡體，轉台灣用語
except Exception:  # noqa: BLE001
    _cc = None


def _wiki_top(lang, limit=5):
    js = None
    for back in (1, 2):  # 昨日統計通常 UTC 上午才出，沒有就退一天
        d = (NOW - timedelta(days=back)).strftime("%Y/%m/%d")
        try:
            js = gjson(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{lang}.wikipedia/all-access/{d}",
                       headers={"User-Agent": "dalta-intel/1.0 (personal dashboard)"})
            break
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404 and back == 1:
                continue
            raise
    skip = re.compile(r"^(Main_Page|Wikipedia:|Special:|特殊:|File:|Portal:|Help:|Talk:|Category:|Wikipedia：|首页|首頁|-)")
    out = []
    for a in js["items"][0]["articles"]:
        t = a["article"]
        if skip.search(t) or ":" in t:
            continue
        title = t.replace("_", " ")
        if lang == "zh" and _cc:
            title = _cc.convert(title)
        out.append({"title": title[:30], "views": a["views"], "url": f"https://{lang}.wikipedia.org/wiki/{t}"})
        if len(out) >= limit:
            break
    return out


def p_news():
    NEWS_ERRS.clear(); HOT_POOL.clear()
    tw = []
    for feed in ("politics", "finance", "technology"):
        tw += _try("cna " + feed, _rss, f"https://feeds.feedburner.com/rsscna/{feed}", "中央社", 6)
    if not tw:
        tw += _try("cna gnews", _gnews, "site:cna.com.tw", "中央社", 8)
    pts = _try("pts", _rss, "https://news.pts.org.tw/xml/newsfeed.xml", "公視", 6) or _try("pts gnews", _gnews, "site:news.pts.org.tw", "公視", 5)
    tw = _dedupe_sort(_dedupe_sort(tw, 8) + _dedupe_sort(pts, 4), 12)  # 保證兩家都出現，不讓中央社洗版

    intl = _try("bbc", _rss, "https://feeds.bbci.co.uk/news/world/rss.xml", "BBC", 8)
    if GUARDIAN_KEY:
        def _guardian():
            js = gjson("https://content.guardianapis.com/search", params={"section": "world|business", "order-by": "newest", "page-size": 12, "api-key": GUARDIAN_KEY})
            return [{"source": "Guardian", "title": r["webTitle"][:90], "url": r["webUrl"], "at": r["webPublicationDate"], "sec": r.get("sectionName", "")} for r in js["response"]["results"]]
        intl += _try("guardian", _guardian)
    else:
        NEWS_ERRS.append("guardian: 未設定 GUARDIAN_API_KEY")
    intl = _dedupe_sort(intl, 12)

    groups = []
    for name, qs in NEWS_GROUPS:
        got = []
        for q in qs:
            lang = "en" if q.startswith("en:") else "zh"
            for it in _try("kw " + q, _gnews, q[3:] if lang == "en" else q, "", 3, lang):
                it["kw"] = q; got.append(it)
            time.sleep(0.8)
        # 每組 3 則：關鍵字輪流各出一則（避免單一話題洗版），標題前 14 字相同視為同一則
        fresh_cut = (NOW - timedelta(days=21)).isoformat()
        got = [g for g in got if (g.get("at") or "") >= fresh_cut]  # 三週以上的舊聞不進 Watchlist
        HOT_POOL.extend(got)  # 熱詞引擎看全部命中，不只面板挑出的 3 則
        by_kw = {q: _dedupe_sort([g for g in got if g["kw"] == q], 3) for q in qs}
        picked, seen = [], set()
        for rnd in range(3):
            for q in qs:
                if len(picked) >= 3:
                    break
                for it in by_kw[q][rnd:rnd + 1]:
                    k = re.sub(r"\W+", "", it["title"])[:14]
                    if k not in seen:
                        seen.add(k); picked.append(it)
        groups.append({"name": name, "items": picked})

    signals = {}
    g = _try("gdelt", _gdelt_signal)
    if g:
        signals["gdelt"] = g
        hist_put("news", "gdelt_vol", TODAY_TPE.isoformat(), g.get("vol"))
        signals["gdelt"]["spark"] = hist_get("news", "gdelt_vol", 14)
        signals["gdelt"]["at"] = NOW_ISO
    else:  # 抓不到就沿用上一輪（最多 6 小時）
        prev = (load_prev("news") or {}).get("signals", {}).get("gdelt")
        if prev and prev.get("at") and (NOW - datetime.fromisoformat(prev["at"].replace("Z", "+00:00"))) < timedelta(hours=6):
            signals["gdelt"] = prev
    wz = _try("wiki zh", _wiki_top, "zh"); we = _try("wiki en", _wiki_top, "en")
    if wz or we:
        signals["wiki"] = {"zh": wz, "en": we}
    if not (tw or intl or any(g["items"] for g in groups)):
        raise RuntimeError(f"news: nothing errs={NEWS_ERRS[:5]}")
    out = {"tw": tw, "intl": intl, "groups": groups, "signals": signals, "errs": NEWS_ERRS[:8]}
    try:
        signals["hot"] = _hot_terms(out)
    except Exception as e:  # noqa: BLE001
        log("hot", e); NEWS_ERRS.append("hot: " + safe_err(e))
    return out



# ---------- AI 快線：五家（OpenAI / Anthropic / Google / DeepSeek / xAI）部落格＋發布偵測 ----------
AI_FEEDS = [  # (url, source, vendor)
    ("https://openai.com/news/rss.xml", "OpenAI", "openai"),
    ("https://blog.google/technology/ai/rss/", "Google AI", "google"),
    ("https://blog.google/products/gemini/rss/", "Gemini", "google"),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge", ""),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch", ""),
]
AI_VENDOR_RE = [("openai", re.compile(r"OpenAI|ChatGPT|GPT-?\d|Sora|DevDay", re.I)), ("anthropic", re.compile(r"Anthropic|Claude", re.I)),
                ("google", re.compile(r"Gemini|DeepMind|Google", re.I)), ("deepseek", re.compile(r"DeepSeek", re.I)), ("xai", re.compile(r"\bxAI\b|Grok", re.I))]
AI_LAUNCH = re.compile(r"introduc|launch|announc|releas|available|now in|new model|preview|rolling out|推出|發布|上線|開放", re.I)


def _html_get(url):
    """一般 GET；403/429 改用瀏覽器指紋。回傳 HTML 文字。"""
    try:
        return get(url).text
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 429):
            from curl_cffi import requests as cffi
            r = cffi.get(url, impersonate="chrome", timeout=25); r.raise_for_status(); return r.text
        raise


def _html_links(url, pat, base, source, limit=6):
    """從 HTML 抓 <a href=pat>標題</a>：Anthropic news、x.ai/news、DeepSeek news 這類沒有 RSS 的頁面。"""
    html = _html_get(url)
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(' + pat + r')"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, inner = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        title = re.sub(r"\s+", " ", html_mod.unescape(inner)).strip()
        if len(title) < 8 or href in seen:
            continue
        seen.add(href)
        out.append({"source": source, "title": title[:90], "url": href if href.startswith("http") else base + href, "at": ""})
        if len(out) >= limit:
            break
    return out


TITLE_DATE = re.compile(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+20\d\d)", re.I)
TITLE_CAT = re.compile(r"^(?:Announcements?|Product|Research|Policy|Company|News|Engineering|Blog|Safety|Featured|Science|Interpretability|Alignment|Education|Economics?|Societal Impacts?|Case Study)\s+", re.I)


def _parse_date(txt):
    for fmt in ("%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(txt.replace("Sept", "Sep").replace(".", "").strip() if "%b" in fmt else txt.strip(), fmt).replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
    return None


def _clean_link_title(it):
    """官方頁面連結文字常是「Sep 18, 2026 Announcements 標題」或「Grok 4.7 Sep 21, 2026 Introducing …」：抽日期、去分類字。"""
    t = it["title"]
    m = TITLE_DATE.search(t)
    if m:
        d = _parse_date(m.group(1))
        if d and not it.get("at"):
            it["at"] = d.isoformat().replace("+00:00", "Z")
        after = t[m.end():].strip()
        if len(after) >= 8:
            t = after
        else:
            t = t[:m.start()].strip()
    t = TITLE_CAT.sub("", t).strip(" -·|:")
    it["title"] = t[:90]
    return it


def _vendor(title, default=""):
    for v, rx in AI_VENDOR_RE:
        if rx.search(title):
            return v
    return default


def p_aiwire():
    errs, items = [], []
    for url, src, vendor in AI_FEEDS:
        try:
            for i in _rss(url, src, 8):
                i["vendor"] = vendor or _vendor(i["title"]); items.append(i)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{src}: {safe_err(e)}")
    # 沒有 RSS 的三家：抓官方頁面的連結，失敗就用英文 Google News 補
    for name, fn, args, gq, vendor in (
        ("anthropic", _html_links, ("https://www.anthropic.com/news", r"/news/[a-z0-9-]+", "https://www.anthropic.com", "Anthropic"), "Anthropic Claude", "anthropic"),
        ("xai", _html_links, ("https://x.ai/news", r"(?:https://x\.ai)?/news/[a-z0-9-]+", "https://x.ai", "xAI"), "xAI Grok", "xai"),
        ("deepseek", _html_links, ("https://api-docs.deepseek.com/news/", r"/news/news[a-z0-9-]+/?", "https://api-docs.deepseek.com", "DeepSeek"), "DeepSeek", "deepseek"),
    ):
        got = []
        try:
            got = fn(*args)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {safe_err(e)}")
        got = [_clean_link_title(i) for i in got]
        for i in got:
            i["official"] = True
        if len(got) < 2:
            errs.append(f"{name}: 官方頁只抓到 {len(got)} 則，改用 Google News 補")
            got += _try(name + " gnews", _gnews, gq, "", 4, "en")
        for i in got:
            i["vendor"] = vendor; items.append(i)
    # 發布偵測：DeepSeek / xAI 的新 GitHub repo 與 Hugging Face 新模型（權重通常比新聞早半天到一天）
    gh_hdr = {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})}
    for org, vendor in (("deepseek-ai", "deepseek"), ("xai-org", "xai")):
        try:
            for r in gjson(f"https://api.github.com/orgs/{org}/repos", params={"sort": "created", "per_page": 3}, headers=gh_hdr):
                items.append({"source": "GitHub", "title": f"新 repo {r['full_name']}：{(r.get('description') or '')[:60]}", "url": r["html_url"], "at": r.get("created_at") or "", "vendor": vendor, "detect": True})
        except Exception as e:  # noqa: BLE001
            errs.append(f"gh {org}: {safe_err(e)}")
        try:
            for m in gjson("https://huggingface.co/api/models", params={"author": org, "sort": "lastModified", "direction": -1, "limit": 3}):
                mid = m.get("modelId") or m.get("id")
                items.append({"source": "HF", "title": f"模型更新 {mid}", "url": f"https://huggingface.co/{mid}", "at": (m.get("lastModified") or "")[:19] + ("Z" if m.get("lastModified") else ""), "vendor": vendor, "detect": True})
        except Exception as e:  # noqa: BLE001
            errs.append(f"hf {org}: {safe_err(e)}")
    cut = (NOW - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    cut_official = (NOW - timedelta(days=21)).isoformat().replace("+00:00", "Z")  # 官方頁貼文少，放寬到三週才不會整家消失
    items = [i for i in items if not i.get("at") or i["at"] >= (cut_official if i.get("official") else cut)]
    for i in items:
        i["launch"] = bool(i.get("detect")) or bool(AI_LAUNCH.search(i["title"]))
    items = _dedupe_sort(items, 80)
    # 發布優先、再依時間；每個來源最多 4 則，避免單一媒體洗版
    ranked = sorted(items, key=lambda x: (x["launch"], x.get("at") or ""), reverse=True)
    # 先保證五家各至少 3 則（Anthropic／xAI 官方頁沒有時間戳，純依時間排會被媒體洗掉），再依排序補滿
    per_src, out, seen = {}, [], set()
    for vendor in ("openai", "anthropic", "google", "deepseek", "xai"):
        for i in [x for x in ranked if x.get("vendor") == vendor][:3]:
            out.append(i); seen.add(id(i)); per_src[i["source"]] = per_src.get(i["source"], 0) + 1
    for i in ranked:
        if id(i) in seen or per_src.get(i["source"], 0) >= 4:
            continue
        per_src[i["source"]] = per_src.get(i["source"], 0) + 1
        out.append(i); seen.add(id(i))
        if len(out) >= 20:
            break
    out.sort(key=lambda x: (x["launch"], x.get("at") or ""), reverse=True)
    if not out:
        raise RuntimeError(f"aiwire: nothing {errs[:3]}")
    return {"items": out, "errs": errs[:6]}


# ---------- Dev Pulse：兩個官方論壇當日熱串 ＋ 五家 changelog（不發部落格的悄悄改動） ----------
DEV_FORUMS = [("https://community.openai.com", "OpenAI 論壇", "openai"), ("https://discuss.ai.google.dev", "Google AI 論壇", "google")]
DEV_CHANGELOGS = [  # (url, source, vendor) — 先試 .md（OpenAI／Claude／xAI 文件站都有 markdown 版），再退回 HTML 文字
    ("https://developers.openai.com/api/docs/changelog.md", "OpenAI changelog", "openai"),
    ("https://platform.claude.com/docs/en/release-notes/overview.md", "Claude release notes", "anthropic"),
    ("https://ai.google.dev/gemini-api/docs/changelog?hl=en", "Gemini changelog", "google"),
    ("https://api-docs.deepseek.com/updates/", "DeepSeek updates", "deepseek"),
    ("https://docs.x.ai/developers/release-notes", "xAI release notes", "xai"),
]
MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_CORE = rf"(?:{MONTHS}\s+\d{{1,2}}(?:,?\s+20\d\d)?|\d{{1,2}}\s+{MONTHS}(?:\s+20\d\d)?|20\d\d[-/.]\d{{1,2}}[-/.]\d{{1,2}})"
DATE_LINE = re.compile(rf"^(?:Date|Updated|Released|Posted)?[:：]?\s*({DATE_CORE})\s*$", re.I)
DATE_START = re.compile(rf"^(?:Date|Updated|Released|Posted)?[:：]?\s*({DATE_CORE})\b(.*)$", re.I)
DATE_HEAD_MD = re.compile(rf"^#{{1,4}}\s+({DATE_CORE})\s*$", re.I)
KIND_LINE = re.compile(r"^(Feature|Fix|Deprecation|Deprecated|Update|Breaking|Improvement|New|Change|Removed|Announcement)s?\b", re.I)


def _parse_date_any(txt):
    """接受沒有年份的「September 25」：年份用今年，若月份在未來就算去年。"""
    t = txt.strip()
    d = _parse_date(t)
    if d:
        return d
    m = re.match(rf"^({MONTHS})\s+(\d{{1,2}})$", t, re.I) or re.match(rf"^(\d{{1,2}})\s+({MONTHS})$", t, re.I)
    if not m:
        return None
    mon, day = (m.group(1), m.group(2)) if re.match(r"[A-Za-z]", m.group(1)) else (m.group(2), m.group(1))
    for y in (NOW.year, NOW.year - 1):
        d = _parse_date(f"{mon[:3]} {day}, {y}")
        if d and d <= NOW + timedelta(days=2):
            return d
    return None


def _md_clean(t):
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # [text](url) → text
    t = re.sub(r"[*_`>#]+", "", t)
    return re.sub(r"\s+", " ", t).strip(" -•·")


def _changelog_md(text, source, vendor, url, limit):
    """markdown 版：### 日期 標題段落；同一日期可有多條。"""
    out, cur, buf = [], None, []

    def flush():
        if cur and buf:
            kind = None
            body = []
            for l in buf:
                if KIND_LINE.match(l) and "·" in l or KIND_LINE.fullmatch(l.strip()):
                    kind = l.split("·")[0].strip(); continue
                if l.startswith("<") or l.startswith("---"):
                    continue
                body.append(_md_clean(l))
            body = [b for b in body if len(b) >= 12]
            if body:
                title = re.split(r"(?<=[.!?])\s+(?=[A-Z])", body[0])[0][:140]
                d = _parse_date_any(cur)
                out.append({"source": source, "vendor": vendor, "date": cur, "kind": kind, "title": title, "url": url.replace(".md", ""), "at": d.isoformat().replace("+00:00", "Z") if d else ""})

    for raw in text.splitlines():
        l = raw.rstrip()
        m = DATE_HEAD_MD.match(l.strip())
        if m:
            flush(); cur, buf = m.group(1), []
            continue
        if re.match(r"^#{1,4}\s", l) and cur:  # 非日期標題 → 這段結束
            flush(); cur, buf = None, []
            continue
        if cur and l.strip():
            buf.append(l.strip())
    flush()
    out.sort(key=lambda o: o.get("at") or "", reverse=True)
    return out[:limit]


def _page_text(url):
    """先用 requests 拆 HTML 成文字；文字太短（SPA）就用 Playwright 渲染。"""
    html = ""
    try:
        html = _html_get(url)
    except Exception:  # noqa: BLE001
        pass
    txt = ""
    if html:
        body = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        body = re.sub(r"</?(a|code|strong|em|b|i|span|small|kbd|abbr|sup|sub)\b[^>]*>", "", body, flags=re.I)  # 行內標籤不換行，避免句子碎掉
        txt = html_mod.unescape(re.sub(r"<[^>]+>", "\n", body))
    if len(re.sub(r"\s", "", txt)) < 800:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(user_agent=UA)
            pg.goto(url, wait_until="networkidle", timeout=45000)
            pg.wait_for_timeout(1500)
            txt = pg.inner_text("body")
            b.close()
    return txt


def _changelog(url, source, vendor, limit=4):
    # 1) markdown（.md 直接抓；非 .md 也先試加 .md）
    for u in ([url] if url.endswith(".md") else [url.split("?")[0].rstrip("/") + ".md"]):
        try:
            txt = _html_get(u)
            if "<html" not in txt[:300].lower():
                got = _changelog_md(txt, source, vendor, u, limit)
                if len(got) >= 2:
                    return got
                CL_DIAG.append(f"{source} md: {len(txt)}b {len(got)} entries head={txt[:60]!r}")
            else:
                CL_DIAG.append(f"{source} md: got html {len(txt)}b")
        except Exception as e:  # noqa: BLE001
            CL_DIAG.append(f"{source} md: {safe_err(e)[:80]}")
    # 2) HTML 文字（若其實是 markdown，去掉行首 # 再比對日期）
    lines = [re.sub(r"^#{1,6}\s+", "", re.sub(r"\s+", " ", l).strip()) for l in _page_text(url).splitlines()]
    lines = [l for l in lines if l]
    out = []

    def heading_like(x):
        return (12 <= len(x) <= 140 and not DATE_LINE.match(x) and not x.endswith((",", ";", ":")) and not re.match(r"^[a-z,;.)]", x)
                and not re.match(r"^(?:https?://|www\.)", x))

    for i, l in enumerate(lines):
        ms = DATE_START.match(l)
        if ms and not DATE_LINE.match(l):  # 「2026-09-29 – DeepSeek V4 released」同一行就有標題
            rest = ms.group(2).strip(" -–—:|·")
            if len(rest) >= 12 and not any(o["title"] == rest for o in out):
                d = _parse_date_any(ms.group(1))
                out.append({"source": source, "vendor": vendor, "date": ms.group(1), "title": rest[:140], "url": url, "at": d.isoformat().replace("+00:00", "Z") if d else ""})
            continue
        if DATE_LINE.match(l):
            cands = [lines[j] for j in list(range(i + 1, min(i + 5, len(lines)))) + [i - 1] if 0 <= j < len(lines) and heading_like(lines[j])]
            if not cands:
                continue
            title = re.split(r"(?<=[.!?])\s+(?=[A-Z])", cands[0])[0]
            if any(o["title"] == title for o in out):
                continue
            d = _parse_date_any(DATE_LINE.match(l).group(1))
            out.append({"source": source, "vendor": vendor, "date": l, "title": title[:140], "url": url, "at": d.isoformat().replace("+00:00", "Z") if d else ""})
    out.sort(key=lambda o: o.get("at") or "", reverse=True)  # 頁面可能先列棄用表，一律依日期新到舊
    return out[:limit]


def _discourse_top(base, source, vendor, limit=5):
    try:
        js = gjson(base + "/top.json", params={"period": "daily"})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 429):
            from curl_cffi import requests as cffi
            js = cffi.get(base + "/top.json?period=daily", impersonate="chrome", timeout=25).json()
        else:
            raise
    out = []
    for t in (js.get("topic_list") or {}).get("topics") or []:
        if t.get("pinned"):
            continue
        out.append({"source": source, "vendor": vendor, "title": (t.get("title") or "")[:90], "url": f"{base}/t/{t.get('slug')}/{t.get('id')}",
                    "replies": max((t.get("posts_count") or 1) - 1, 0), "likes": t.get("like_count") or 0, "views": t.get("views") or 0, "at": (t.get("created_at") or "")[:19] + "Z"})
        if len(out) >= limit:
            break
    return out


CL_DIAG: list = []


def p_devpulse():
    errs, forums, logs = [], [], []
    CL_DIAG.clear()
    for base, src, vendor in DEV_FORUMS:
        try:
            forums += _discourse_top(base, src, vendor)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{src}: {safe_err(e)}")
    for url, src, vendor in DEV_CHANGELOGS:
        try:
            got = _changelog(url, src, vendor)
            if not got:
                errs.append(f"{src}: 沒抓到日期段落")
            logs += got
        except Exception as e:  # noqa: BLE001
            errs.append(f"{src}: {safe_err(e)}")
    # Anthropic 沒有論壇：用 claude-code 的 GitHub Releases 當「工程端動態」
    try:
        gh_hdr = {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})}
        for r in gjson("https://api.github.com/repos/anthropics/claude-code/releases", params={"per_page": 3}, headers=gh_hdr):
            logs.append({"source": "claude-code release", "vendor": "anthropic", "date": (r.get("published_at") or "")[:10], "title": (r.get("name") or r.get("tag_name") or "")[:120], "url": r.get("html_url"), "at": r.get("published_at") or ""})
    except Exception as e:  # noqa: BLE001
        errs.append("claude-code: " + safe_err(e))
    if not forums and not logs:
        raise RuntimeError(f"devpulse: nothing {errs[:3]}")
    return {"forums": forums, "changelogs": logs, "errs": errs[:8], "diag": CL_DIAG[:8]}


# ---------- 熱詞引擎：同一實體詞在 12 小時內出現在 ≥3 個不同來源就算「在燒」 ----------
HOT_STOP_EN = set("introducing introduces announcing announces announcements launch launches launched release releases released update updates updated model models api apps app agent agents jan feb mar apr may jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday the a an and or of to in on for with from by at as is are was were be been this that these those new how why what when who which will can its it into over after before about more than not no yes up down out all one two three first last year years day days week today says said say show shows video live news report reports update ai us uk eu china taiwan taipei japan korea india world government president people man woman men women police court city state county".split())
HOT_STOP_ZH = set("推出 發布 上線 代理 宣布 公布 曝光 揭曉 亮相 登場 開賣 開放 更新 升級 首度 首次 正式 全新 最新 安全 大安 中正 信義 台灣 台北 台中 高雄 新北 桃園 台南 中國 美國 日本 韓國 香港 全球 國際 國內 總統 政府 國會 立法院 立委 民眾 網友 記者 新聞 報導 影片 直播 專家 分析 表示 指出 認為 今天 今日 明天 昨天 上午 下午 晚間 凌晨 目前 最新 快訊 獨家 焦點 專題 系列 問題 情況 市場 公司 企業 產業 業者 消費者 用戶 台股 股市 大盤 個股 早盤 盤中 收盤 開盤 新台幣 美元 億元 萬元 億 萬 人 年 月 日 時 分 點 元 台 家 名 位 次 種 項 條 件 個 ETF 基金 投資人 股價 新功能 功能 模型 工具 服務 平台 系統 技術 應用 發展 影響 未來 時代 世界 生活 文化 設計 品牌 廣告 行銷 網路 社群 粉絲 議題 話題 討論 聲明 回應 消息 傳出 曝光 揭露 現場 畫面 一次 全部 這樣 這個 那個 什麼 怎麼 為何 為什麼 竟然 卻 竟 恐 將 再 也 都 又 就 才 最 更 很 太 還 已 已經 沒有 不是 就是 可以 可能 需要 應該 因為 所以 如果 但是 然而 以及 或者 之後 之前 之間 以上 以下 對於 關於 根據 透過 針對 包括 除了 另外 其中 其他 此外".split())
HOT_LAT = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z][A-Za-z0-9]{2,}(?:[ -][A-Z][A-Za-z0-9]+)?|[A-Z]{2,}[A-Za-z]*-?\d[\w.]*|GPT-?[\w.]*|iPhone\s?\d+)(?![A-Za-z0-9])")


HOT_EDGE = set("的了在是與和及等將被對為把讓向從以就也都又再才卻更最很太還已沒不無非但而或者之其此該這那些個們者著過來去上下中內外前後間裡時年月日點元億萬千百十人次件家場位名種項條")
HOT_FUNC = set("的了在是與和及等將被對為把讓向從以就也都又再才卻更最很太還已沒不無非但而或者之其此該這那些個們者著過來去")


def _hot_terms_from(items):
    """items: [{title, source, at}] → 依「不同來源數」排序的熱詞。
    中文用 2–4 字 n-gram 跨來源計數（不靠斷詞字典，台積電、賴清德這類實體自然浮出），
    只留「最長」的一段：若某段的來源集合和更長的段一樣就丟掉（避免 台積／台積電 同時出現）。"""
    cut = (NOW - timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    hits: dict = {}

    def add(w, src, it):
        k = w.lower()
        h = hits.setdefault(k, {"term": w, "n": 0, "sources": set(), "sample": {"title": (it.get("title") or "")[:60], "url": it.get("url")}})
        h["n"] += 1; h["sources"].add(src)

    for it in items:
        t = it.get("title") or ""
        if not t or (it.get("at") and it["at"] < cut):
            continue
        src = (it.get("source") or "?").strip()
        terms = set()
        for m in HOT_LAT.findall(t):
            w = m.strip()
            for part in {w, re.split(r"[ -]", w)[0]}:  # 「OpenAI Agent」同時算 OpenAI
                if part.lower() not in HOT_STOP_EN and len(part) >= 3:
                    terms.add(part)
        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", t):
            for n in (2, 3, 4):
                for i in range(len(seg) - n + 1):
                    g = seg[i:i + n]
                    if g[0] in HOT_EDGE or g[-1] in HOT_EDGE or any(c in HOT_FUNC for c in g) or g in HOT_STOP_ZH:
                        continue
                    terms.add(g)
        for w in terms:
            add(w, src, it)
    cands = [h for h in hits.values() if len(h["sources"]) >= 2]
    # 最長匹配：短段若被某個更長的段涵蓋且來源集合相同 → 丟
    keep = []
    for h in cands:
        dominated = any(o is not h and h["term"] in o["term"] and len(o["term"]) > len(h["term"]) and o["sources"] >= h["sources"] for o in cands)
        if not dominated:
            keep.append(h)
    out = [{"term": h["term"], "n": h["n"], "src": len(h["sources"]), "sources": sorted(h["sources"])[:6], "sample": h["sample"], "hot": len(h["sources"]) >= 3} for h in keep]
    out.sort(key=lambda x: (-x["src"], -x["n"], -len(x["term"])))
    return out[:10]


def _hot_terms(news):
    pool = list(news.get("tw") or []) + list(news.get("intl") or []) + list(HOT_POOL)
    for pid in ("aiwire", "design"):
        pool += (load_prev(pid) or {}).get("items") or []
    for r in ((load_prev("ptt") or {}).get("items") or [])[:40]:
        pool.append({"title": r.get("title"), "source": "PTT", "url": r.get("url"), "at": NOW_ISO})
    dp = load_prev("devpulse") or {}
    for f in (dp.get("forums") or []) + (dp.get("changelogs") or []):
        pool.append({"title": f.get("title"), "source": f.get("source"), "url": f.get("url"), "at": f.get("at") or NOW_ISO})
    for h in (load_prev("tech") or {}).get("hn") or []:
        pool.append({"title": h.get("title"), "source": "HN", "url": h.get("url"), "at": NOW_ISO})
    for w in ((news.get("signals") or {}).get("wiki") or {}).get("zh") or []:
        pool.append({"title": w.get("title"), "source": "Wiki", "url": w.get("url"), "at": NOW_ISO})
    return _hot_terms_from(pool)




# ---------- 社群脈搏：Dcard ＋ Bluesky（Threads 搜尋需登入／App Review，改用這兩個補「台灣人正在怎麼講」） ----------
# 固定詞：看「大眾情緒」而不是事件。台灣三個看生活壓力與對政府的怨氣，國外三個看經濟焦慮（跟總經面板對照）。
# 刻意不放政治人物：Bluesky 上那是同溫層表態，不是情緒。
SOCIAL_FIXED = [("tariffs", "外"), ("inflation", "外"), ("layoffs", "外")]  # 台灣情緒 Bluesky 撐不起，台灣端另找來源


def _social_seeds():
    hot = ((load_prev("news") or {}).get("signals") or {}).get("hot") or []
    seeds = []
    for h in sorted(hot, key=lambda x: (-x.get("src", 0), -x.get("n", 0))):
        t = h.get("term") or ""
        if t in [k for k, _ in SOCIAL_FIXED] or len(t) < 2 or t.lower() in HOT_STOP_EN or t in HOT_STOP_ZH:
            continue
        if re.search(r"[\u4e00-\u9fff]", t):  # 中文熱詞在 Bluesky 沒量，只帶英文熱詞
            continue
        seeds.append({"kw": t, "kind": "hot", "src": h.get("src"), "region": "外"})
        if len(seeds) >= 4:
            break
    return [{"kw": k, "kind": "fixed", "region": r} for k, r in SOCIAL_FIXED] + seeds


def _dcard_get(path, **params):
    url = "https://www.dcard.tw/service/api/v2/" + path
    hdr = {"Accept": "application/json", "Referer": "https://www.dcard.tw/"}
    try:
        r = S.get(url, params=params, headers=hdr, timeout=TIMEOUT)
        if r.status_code in (403, 429):
            raise requests.HTTPError(response=r)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError:
        from curl_cffi import requests as cffi
        r = cffi.get(url, params=params, headers=hdr, impersonate="chrome", timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(f"dcard {r.status_code} {r.text[:80]!r}")
        return r.json()


def _dcard_posts(rows):
    out = []
    for d in rows or []:
        if not isinstance(d, dict) or not d.get("id"):
            continue
        out.append({"src": "Dcard", "text": re.sub(r"\s+", " ", (d.get("title") or "") + (("：" + d["excerpt"]) if d.get("excerpt") else ""))[:140],
                    "user": d.get("forumName") or d.get("forumAlias") or "", "url": f"https://www.dcard.tw/f/{d.get('forumAlias')}/p/{d['id']}",
                    "at": (d.get("createdAt") or "")[:19] + ("Z" if d.get("createdAt") else ""), "likes": d.get("likeCount"), "replies": d.get("commentCount")})
    return out


def _is_traditional(t):
    """粗判繁體：轉成簡體後改變的字數比例；簡體或日文假名多的就不是台灣語境。"""
    zh = re.findall(r"[\u4e00-\u9fff]", t)
    if not zh:
        return True
    if re.search(r"[\u3040-\u30ff]", t):  # 平假名／片假名
        return False
    try:
        from opencc import OpenCC
        conv = OpenCC("t2s").convert(t)
        changed = sum(1 for a, b in zip(t, conv) if a != b)
        return changed / max(len(zh), 1) >= 0.05 or len(zh) < 6  # 繁→簡會變很多字；完全不變的多半是簡體原文
    except Exception:  # noqa: BLE001
        return True


def _bsky_search(q, limit=25):
    j, last = None, None
    is_zh = bool(re.search(r"[\u4e00-\u9fff]", q))
    for host in ("https://public.api.bsky.app", "https://api.bsky.app"):
        try:
            r = requests.get(f"{host}/xrpc/app.bsky.feed.searchPosts", params={"q": q, "sort": "latest", "limit": limit, "lang": "zh" if is_zh else "en"},
                             headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}, timeout=TIMEOUT)
            if r.status_code >= 400:
                last = RuntimeError(f"bsky {r.status_code} {r.text[:100]!r}")
                continue
            j = r.json(); break
        except Exception as e:  # noqa: BLE001
            last = e
    if j is None:
        raise last or RuntimeError("bsky: no response")
    out = []
    for p_ in j.get("posts") or []:
        rec = p_.get("record") or {}
        handle = (p_.get("author") or {}).get("handle") or ""
        rkey = (p_.get("uri") or "").rsplit("/", 1)[-1]
        text = re.sub(r"\s+", " ", rec.get("text") or "")
        if is_zh and not _is_traditional(text):
            continue
        out.append({"src": "Bluesky", "text": text[:140], "user": handle,
                    "url": f"https://bsky.app/profile/{handle}/post/{rkey}", "at": (rec.get("createdAt") or "")[:19] + ("Z" if rec.get("createdAt") else ""),
                    "likes": p_.get("likeCount"), "replies": p_.get("replyCount"), "reposts": p_.get("repostCount")})
    return out


def p_social():
    errs, out = [], {"keywords": [], "dcard_popular": [], "sources": {"dcard": False, "bsky": False}}
    cut24 = (NOW - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    dcard_ok = False  # Dcard 走 Cloudflare 驗證，GitHub IP 被擋（403 challenge），先不抓
    for sd in _social_seeds():
        posts = []
        if dcard_ok:
            try:
                posts += _dcard_posts(_dcard_get("posts/search", query=sd["kw"], limit=20))
            except Exception as e:  # noqa: BLE001
                errs.append(f"dcard {sd['kw']}: {safe_err(e)[:60]}")
            time.sleep(0.8)
        try:
            b = _bsky_search(sd["kw"])
            posts += b
            if b:
                out["sources"]["bsky"] = True
        except Exception as e:  # noqa: BLE001
            errs.append(f"bsky {sd['kw']}: {safe_err(e)[:60]}")
        posts.sort(key=lambda x: x.get("at") or "", reverse=True)
        rec = {**sd, "n_24h": sum(1 for x in posts if x["at"] and x["at"] >= cut24),
               "n_dcard": sum(1 for x in posts if x["src"] == "Dcard"), "n_bsky": sum(1 for x in posts if x["src"] == "Bluesky"),
               "top": sorted(posts, key=lambda x: -(x.get("likes") or 0))[:3], "recent": posts[:3]}
        out["keywords"].append(rec)
    if not out["dcard_popular"] and not any(k["top"] for k in out["keywords"]):
        raise RuntimeError(f"social: nothing {errs[:3]}")
    return {**out, "errs": errs[:8]}



# ---------- Cofacts 真的假的：LINE 群組正在轉傳、被拿去查證的訊息（開放資料，免金鑰） ----------
COFACTS_TYPE = {"RUMOR": "含錯誤訊息", "NOT_RUMOR": "含正確訊息", "OPINIONATED": "個人意見", "NOT_ARTICLE": "不在查證範圍"}


def p_cofacts():
    since = (NOW - timedelta(days=7)).isoformat()
    q = """query($since: String!) {
      hot: ListArticles(filter: {createdAt: {GTE: $since}}, orderBy: [{replyRequestCount: DESC}], first: 25) {
        edges { node { id text replyRequestCount createdAt lastRequestedAt
          articleReplies(statuses: [NORMAL]) { reply { type } } } } }
      fresh: ListArticles(orderBy: [{lastRequestedAt: DESC}], first: 15) {
        edges { node { id text replyRequestCount createdAt lastRequestedAt
          articleReplies(statuses: [NORMAL]) { reply { type } } } } }
    }"""
    r = S.post("https://api.cofacts.tw/graphql", json={"query": q, "variables": {"since": since}}, headers={"Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    js = r.json()
    if js.get("errors"):
        raise RuntimeError("cofacts: " + str(js["errors"][0].get("message"))[:120])

    def rows(key):
        out = []
        for e in ((js.get("data") or {}).get(key) or {}).get("edges") or []:
            n = e.get("node") or {}
            types = [ (ar.get("reply") or {}).get("type") for ar in n.get("articleReplies") or [] ]
            verdict = next((COFACTS_TYPE[t] for t in ("RUMOR", "NOT_RUMOR", "OPINIONATED", "NOT_ARTICLE") if t in types), "尚未查核")
            out.append({"id": n["id"], "text": re.sub(r"\s+", " ", n.get("text") or "")[:120], "requests": n.get("replyRequestCount") or 0,
                        "verdict": verdict, "checked": bool(types), "at": (n.get("lastRequestedAt") or n.get("createdAt") or "")[:19] + "Z",
                        "created": (n.get("createdAt") or "")[:10], "url": f"https://cofacts.tw/article/{n['id']}"})
        return out
    hot, fresh = rows("hot"), rows("fresh")
    if not hot and not fresh:
        raise RuntimeError("cofacts: empty")
    unchecked = sum(1 for h in hot if not h["checked"])
    rumor = sum(1 for h in hot if h["verdict"] == "含錯誤訊息")
    hist_put("cofacts", "requests", NOW_ISO[:13], sum(h["requests"] for h in hot))
    return {"hot": hot, "fresh": fresh[:8], "stats": {"hot_n": len(hot), "unchecked": unchecked, "rumor": rumor,
            "requests_total": sum(h["requests"] for h in hot), "spark": hist_get("cofacts", "requests", 48)}}


# ---------- Threads（走 Google Programmable Search 索引）：每天 100 次免費，程式端鎖 90 次 ----------
THREADS_G_FIXED = ["物價", "房價", "政府"]
CSE_QUOTA_PATH = DATA / "cse_quota.json"
CSE_DAILY_CAP = 90


def _cse_quota():
    q = {}
    if CSE_QUOTA_PATH.exists():
        try:
            q = json.loads(CSE_QUOTA_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            q = {}
    today = NOW.astimezone(TPE).strftime("%Y-%m-%d")  # Google 配額以太平洋時間重置，這裡用台北日期偏保守
    if q.get("date") != today:
        q = {"date": today, "used": 0}
    return q


def _cse(q, num=10, date_restrict="d1"):
    r = S.get("https://www.googleapis.com/customsearch/v1", params={"key": CSE_KEY, "cx": CSE_CX, "q": q, "num": num, "dateRestrict": date_restrict, "sort": "date"}, timeout=TIMEOUT)
    if r.status_code >= 400:
        try:
            msg = (r.json().get("error") or {}).get("message", "")
        except ValueError:
            msg = r.text[:100]
        raise RuntimeError(f"cse {r.status_code}: {msg[:140]}")
    js = r.json()
    out = []
    for it in js.get("items") or []:
        link = it.get("link") or ""
        m = re.search(r"threads\.(?:com|net)/@([^/]+)/post/", link)
        user = m.group(1) if m else ""
        snippet = re.sub(r"\s+", " ", it.get("snippet") or "")
        title = re.sub(r"\s+", " ", it.get("title") or "")
        text = snippet if len(snippet) > 20 else title
        text = re.sub(r"^\d+\s*(?:天|小時|分鐘|days?|hours?|minutes?)\s*(?:前|ago)\s*[·—-]*\s*", "", text)
        out.append({"src": "Threads", "user": user, "text": text[:140], "url": link, "title": title[:80]})
    return out, int((js.get("searchInformation") or {}).get("totalResults") or 0)


def _threads_grounded(kw):
    """Custom Search JSON API 已不收新客戶（403）；改用 Gemini 的 Google 搜尋 grounding 找 threads.com 貼文。"""
    prompt = f"""用 Google 搜尋找出 threads.com 上「最近一天」提到「{kw}」的公開貼文（搜尋時加上 site:threads.com）。
只回傳 JSON 物件，格式 {{"posts":[{{"user":"帳號","text":"貼文原文摘錄 60 字內（保留原本語氣，不要改寫成新聞腔）","url":"貼文網址"}}], "n_hint": 你判斷有多少則相關貼文的整數估計}}。
最多 6 則，找不到就回 {{"posts":[],"n_hint":0}}。不要加任何 JSON 以外的文字。"""
    data, model = _gemini_json(prompt, tools=[{"google_search": {}}])
    posts = []
    chunks = {(c.get("web") or {}).get("title", ""): (c.get("web") or {}).get("uri", "") for c in data.get("_grounding") or []}
    for p_ in data.get("posts") or []:
        url = p_.get("url") or ""
        if "threads" not in url and chunks:  # 模型給的網址不可靠時改用 grounding 的來源連結
            for t, u in chunks.items():
                if p_.get("user") and p_["user"].lstrip("@") in t:
                    url = u; break
        posts.append({"src": "Threads", "user": (p_.get("user") or "").lstrip("@")[:30], "text": re.sub(r"\s+", " ", p_.get("text") or "")[:140], "url": url, "title": ""})
    return posts, int(data.get("n_hint") or len(posts)), model


def p_threads_g():
    if not (CSE_KEY and CSE_CX) and not GEMINI_KEY:
        raise RuntimeError("未設定 GOOGLE_CSE_KEY／GOOGLE_CSE_CX 或 GEMINI_API_KEY")
    quota = _cse_quota()
    errs, out = [], {"keywords": [], "quota": None}
    hot = ((load_prev("news") or {}).get("signals") or {}).get("hot") or []
    seeds = [{"kw": k, "kind": "fixed"} for k in THREADS_G_FIXED]
    for h in sorted(hot, key=lambda x: (-x.get("src", 0), -x.get("n", 0))):
        t = h.get("term") or ""
        if re.search(r"[一-鿿]", t) and t not in THREADS_G_FIXED and t not in HOT_STOP_ZH and len(t) >= 2:
            seeds.append({"kw": t, "kind": "hot", "src": h.get("src")})
        if len(seeds) >= 6:
            break
    for sd in seeds:
        if quota["used"] >= CSE_DAILY_CAP:
            errs.append(f"今日配額用完（{quota['used']}/{CSE_DAILY_CAP}），其餘關鍵字沿用上一輪")
            prev = {k["kw"]: k for k in (load_prev("threads_g") or {}).get("keywords") or []}
            if sd["kw"] in prev:
                out["keywords"].append(prev[sd["kw"]])
            continue
        try:
            if quota.get("cse_dead"):
                raise RuntimeError("cse closed")
            posts, total = _cse(sd["kw"])
            quota["used"] += 1
            out["keywords"].append({**sd, "n_24h": total, "posts": posts[:4], "via": "cse"})
        except Exception as e:  # noqa: BLE001
            if "cse 403" in str(e) or "cse closed" in str(e):
                quota["cse_dead"] = True  # 這個專案沒有 Custom Search 權限（新客戶已關閉），這天別再打
            else:
                errs.append(f"{sd['kw']}: {safe_err(e)[:80]}")
            if GEMINI_KEY:
                try:
                    posts, total, model = _threads_grounded(sd["kw"])
                    quota["used"] += 1  # grounding 也算一次，同樣鎖 90 次／天
                    out["keywords"].append({**sd, "n_24h": total, "posts": posts[:4], "via": "gemini:" + model})
                except Exception as e2:  # noqa: BLE001
                    errs.append(f"{sd['kw']} grounding: {safe_err(e2)[:80]}")
        time.sleep(0.5)
    write_json(CSE_QUOTA_PATH, quota)
    out["quota"] = {"used": quota["used"], "cap": CSE_DAILY_CAP, "date": quota["date"]}
    if not any(k.get("posts") for k in out["keywords"]):
        raise RuntimeError(f"threads_g: nothing {errs[:3]}")
    return {**out, "errs": errs[:6]}


# ---------- 台灣情緒（Gemini）：把 PTT／Cofacts／Threads／Bluesky 的文字丟給模型，出情緒分數與一句判讀 ----------
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]


def _gemini_models():
    """列出帳號可用的模型，挑 flash 系列最新版（模型名稱會隨時間退役，不寫死）。"""
    try:
        js = gjson("https://generativelanguage.googleapis.com/v1beta/models", params={"key": GEMINI_KEY, "pageSize": 100})
        names = [m["name"].split("/", 1)[1] for m in js.get("models") or [] if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n and "live" not in n and "audio" not in n and "exp" not in n]
        # 版本號大的優先；lite 放後面
        flash.sort(key=lambda n: (("lite" in n), -float(re.search(r"(\d+(?:\.\d+)?)", n).group(1)) if re.search(r"\d", n) else 0, n))
        return flash[:4] or names[:3]
    except Exception as e:  # noqa: BLE001
        log("gemini models", e); return []


def _gemini_call(prompt, model, json_mode=True, tools=None, max_tokens=1200):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}}
    if json_mode and not tools:  # 開了搜尋工具就不能強制 JSON，改由 prompt 要求
        body["generationConfig"]["responseMimeType"] = "application/json"
    if tools:
        body["tools"] = tools
    r = S.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", params={"key": GEMINI_KEY}, json=body, timeout=90)
    return r


def _gemini_json(prompt, schema_hint=None, tools=None):
    last = None
    for model in (_gemini_models() or GEMINI_MODELS):
        try:
            r = _gemini_call(prompt, model, tools=tools)
            if r.status_code in (404, 429, 503):  # 沒這個模型／額度滿／過載 → 換下一個
                last = RuntimeError(f"{model} {r.status_code}"); time.sleep(2); continue
            if r.status_code >= 400:
                raise RuntimeError(f"gemini {r.status_code} {r.text[:120]}")
            js = r.json()
            cand = js["candidates"][0]
            txt = "".join(p_.get("text", "") for p_ in cand["content"]["parts"])
            m = re.search(r"\{.*\}|\[.*\]", txt, re.S)
            data = json.loads(m.group(0) if m else txt)
            if isinstance(data, dict):
                data["_grounding"] = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
            return data, model
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
            last = RuntimeError(f"{model} parse: {str(e)[:60]}")
    raise last or RuntimeError("gemini: no model")


def p_mood():
    if not GEMINI_KEY:
        raise RuntimeError("未設定 GEMINI_API_KEY")
    ptt = load_prev("ptt") or {}
    cof = load_prev("cofacts") or {}
    thg = load_prev("threads_g") or {}
    soc = load_prev("social") or {}
    blocks = {}
    blocks["PTT"] = [f"[{r['board']}] {r['title']}" for r in (ptt.get("items") or [])[:40]]
    blocks["LINE（Cofacts）"] = [f"（被查 {h['requests']} 次）{h['text'][:80]}" for h in (cof.get("hot") or [])[:15]]
    blocks["Threads"] = [f"[{k['kw']}] {p_['text'][:90]}" for k in (thg.get("keywords") or []) for p_ in (k.get("posts") or [])[:3]]
    blocks["Bluesky（國外）"] = [f"[{k['kw']}] {p_['text'][:90]}" for k in (soc.get("keywords") or []) for p_ in (k.get("top") or [])[:2]]
    if sum(len(v) for v in blocks.values()) < 10:
        raise RuntimeError("mood: 素材不足")
    material = "\n\n".join(f"## {k}\n" + "\n".join(f"- {x}" for x in v) for k, v in blocks.items() if v)
    prompt = f"""你是台灣的輿情分析師。下面是今天從四個來源抓到的原文（PTT 熱文標題、LINE 群組正在轉傳並被拿去查證的訊息、Threads 貼文、Bluesky 英文貼文）。
請只根據這些文字判斷「大眾情緒」，不要加入你自己的時事知識。用繁體中文、台灣用語，不要用「不是…而是…」句型，不要空泛。

輸出 JSON，格式：
{{
  "taiwan": {{"score": -1到1的小數（-1 極負面、0 中性、1 極正面）, "label": "兩到四個字的情緒標籤，例如 焦慮、亢奮、無感、憤怒", "themes": ["最多三個正在燒的主題，各 2-6 字"], "line": "一句 40 字內的判讀：台灣人今天在意什麼、語氣如何"}},
  "overseas": {{"score": 同上, "label": 同上, "themes": [...], "line": "一句 40 字內的判讀（英文貼文的情緒）"}},
  "sources": {{"PTT": {{"score": 小數, "note": "15 字內"}}, "LINE": {{"score": 小數, "note": "15 字內"}}, "Threads": {{"score": 小數, "note": "15 字內"}}}},
  "watch": "一句 30 字內：如果只能盯一件事，盯什麼"
}}
來源沒有資料就把該來源 score 設為 null。

{material}"""
    js, model = _gemini_json(prompt, None)
    tw = js.get("taiwan") or {}
    hist_put("mood", "taiwan", NOW_ISO[:13], tw.get("score"))
    hist_put("mood", "overseas", NOW_ISO[:13], (js.get("overseas") or {}).get("score"))
    return {**js, "model": model, "spark_tw": hist_get("mood", "taiwan", 72), "spark_os": hist_get("mood", "overseas", 72),
            "n_inputs": {k: len(v) for k, v in blocks.items()}}


# ---------- 第三批（免新金鑰）：標案 / 設計廣告媒體 / 地震 / 台電 / 桃機 ----------
PCC_KW = ["行銷", "品牌", "影片", "廣告", "視覺設計"]
PCC_EXCLUDE = ("拆除", "租賃", "印刷", "看板", "招牌", "廣告物", "廣告牌", "設備", "工程")
PCC_CACHE = DATA / "pcc_cache.json"
_pcc_search_cache: dict = {}


def _pcc_search(kw):
    if kw not in _pcc_search_cache:
        _pcc_search_cache[kw] = _cffi_json("https://pcc-api.openfun.app/api/searchbytitle", query=kw, page=1)
        time.sleep(1)
    return _pcc_search_cache[kw]


def p_tenders():
    """政府採購網（g0v 鏡像）：關鍵字命中的最新招標公告，補預算金額。"""
    cache = {}
    if PCC_CACHE.exists():
        try:
            cache = json.loads(PCC_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    found, errs = {}, []
    for kw in PCC_KW:
        try:
            js = _pcc_search(kw)
            for r in js.get("records", []):
                b = r.get("brief") or {}
                typ = b.get("type") or ""
                if "決標" in typ or not any(k in typ for k in ("招標公告", "公開取得", "限制性招標", "公開評選", "公開徵求")):
                    continue
                if any(x in (b.get("title") or "") for x in PCC_EXCLUDE):
                    continue
                key = f'{r.get("unit_id")}/{r.get("job_number")}'
                if key in found:
                    found[key]["kw"].append(kw); continue
                found[key] = {"key": key, "title": (b.get("title") or "")[:60], "unit": (r.get("unit_name") or "")[:18],
                              "date": str(r.get("date") or ""), "type": typ[:6], "kw": [kw],
                              "url": f'https://openfunltd.github.io/pcc-viewer/tender.html?unit_id={r.get("unit_id")}&job_number={r.get("job_number")}'}
        except Exception as e:  # noqa: BLE001
            log("pcc", kw, e); errs.append(f"{kw}: {safe_err(e)}")
        time.sleep(1)
    items = sorted(found.values(), key=lambda x: x["date"], reverse=True)[:14]
    # 預算：每輪最多補 6 筆新的，其餘用快取
    filled = 0
    for it in items:
        if it["key"] in cache:  # 值可能是 None（抓不到預算），也算查過
            it["budget"] = cache[it["key"]]; continue
        if filled >= 6:
            continue
        try:
            time.sleep(1)
            uid, job = it["key"].split("/", 1)
            d = _cffi_json("https://pcc-api.openfun.app/api/tender", unit_id=uid, job_number=job)
            det = ((d.get("records") or [{}])[0].get("detail") or {})
            raw = det.get("採購資料:預算金額") or det.get("已公開閱覽資料:預算金額") or det.get("招標資料:預算金額") or ""
            m = re.search(r"[\d,]+", str(raw).replace("元", ""))
            it["budget"] = int(m.group(0).replace(",", "")) if m else None
            cache[it["key"]] = it["budget"]; filled += 1
        except Exception as e:  # noqa: BLE001
            log("pcc detail", it["key"], e); it["budget"] = None
    if len(cache) > 600:
        cache = dict(list(cache.items())[-400:])
    write_json(PCC_CACHE, cache)
    if not items:
        raise RuntimeError(f"pcc: nothing errs={errs[:3]}")
    return {"items": items, "keywords": PCC_KW, "errs": errs[:4]}


DESIGN_FEEDS = [("https://www.dezeen.com/feed/", "Dezeen", "site:dezeen.com"),
                ("https://www.itsnicethat.com/feed.rss", "INT", "site:itsnicethat.com"),
                ("https://campaignbriefasia.com/feed/", "CB Asia", "site:campaignbriefasia.com"),
                ("https://www.creativereview.co.uk/feed/", "CR", "site:creativereview.co.uk")]


def p_design():
    items, errs = [], []
    for url, src, q in DESIGN_FEEDS:
        got = []
        try:
            got = _rss(url, src, 5)
        except Exception as e:  # noqa: BLE001
            log("design rss", src, e); errs.append(f"{src}: {safe_err(e)}")
            try:
                got = _rss("https://news.google.com/rss/search", src, 4, q=q, hl="en-US", gl="US", ceid="US:en")
            except Exception as e2:  # noqa: BLE001
                log("design gnews", src, e2)
        items += got
    fresh_cut = (NOW - timedelta(days=30)).isoformat()
    items = _dedupe_sort([i for i in items if (i.get("at") or "") >= fresh_cut], 14)
    if not items:
        raise RuntimeError(f"design: nothing errs={errs[:3]}")
    return {"items": items, "errs": errs[:4]}


def p_quake():
    """氣象署顯著有感地震報告（近 5 筆）。"""
    rec = cwa("E-A0015-001", limit=6)
    out = []
    for q in rec.get("Earthquake", []):
        info = q.get("EarthquakeInfo") or {}
        mag = ((info.get("EarthquakeMagnitude") or {}).get("MagnitudeValue"))
        epi = info.get("Epicenter") or {}
        t = (info.get("OriginTime") or "").replace("/", "-")
        at = ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(t[:25], fmt)
                dt = dt if dt.tzinfo else dt.replace(tzinfo=TPE)
                at = dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"); break
            except Exception:
                continue
        # 最大震度：Intensity.ShakingArea[].AreaIntensity
        mx = ""
        for a in ((q.get("Intensity") or {}).get("ShakingArea") or []):
            v = a.get("AreaIntensity") or ""
            if v and (not mx or v > mx):
                mx = v
        out.append({"at": at, "mag": num(mag), "loc": (epi.get("Location") or "")[:40], "depth": num(info.get("FocalDepth")),
                    "intensity": mx[:4], "url": q.get("Web") or "https://scweb.cwa.gov.tw/", "no": q.get("EarthquakeNo")})
    out.sort(key=lambda x: x["at"], reverse=True)
    if not out:
        raise RuntimeError("no quake records")
    return {"items": out[:5]}


def p_power():
    """台電今日電力資訊（d006020）：目前用電、預估尖峰負載與備轉容量率。單位萬瓩→MW。"""
    js, last = None, None
    for attempt in range(3):  # 台電這台主機偶爾很慢：40 秒逾時、重試兩次
        try:
            from curl_cffi import requests as cffi
            r = cffi.get("https://service.taipower.com.tw/data/opendata/apply/file/d006020/001.json", impersonate="chrome", timeout=40)
            r.raise_for_status(); js = r.json(); break
        except Exception as e:  # noqa: BLE001
            last = e; time.sleep(3)
    if js is None:
        prev = load_prev("power") or {}
        if prev.get("reserve_pct") is not None and prev.get("updatedAt"):
            log("taipower carry-over", last)
            return {k: v for k, v in prev.items() if k not in ("error", "updatedAt")}  # 沿用上一輪，不標失敗
        raise last
    rec = {}
    for r in js.get("records") or []:
        rec.update(r)
    mw = lambda k: (num(rec.get(k)) or 0) * 10 or None  # noqa: E731
    reserve = num(rec.get("fore_peak_resv_rate"))
    if reserve is None and rec.get("curr_load") is None:
        raise RuntimeError(f"taipower fields: {list(rec)[:8]}")
    ind = {"G": "綠", "Y": "黃", "O": "橘", "R": "紅"}.get(str(rec.get("fore_peak_resv_indicator") or "").upper(), "")
    level = ind or ("綠" if (reserve or 0) >= 10 else "黃" if (reserve or 0) >= 6 else "橘" if (reserve or 0) >= 3 else "紅")
    hist_put("power", "reserve", TODAY_TPE.isoformat(), reserve)
    return {"curr_mw": mw("curr_load"), "util_pct": num(rec.get("curr_util_rate")), "peak_mw": mw("fore_peak_dema_load"),
            "reserve_pct": reserve, "reserve_mw": mw("fore_peak_resv_capacity"), "level": level, "peak_hours": rec.get("fore_peak_hour_range", ""),
            "yday_reserve_pct": num(rec.get("yday_peak_resv_rate")), "spark": hist_get("power", "reserve", 30), "asof": str(rec.get("publish_time") or "")[:20]}


def p_airport():
    """桃機今日出發／抵達：班次、延誤、取消，與接下來 8 班出發。"""
    out = {}
    for kind, path in (("dep", "Air/FIDS/Airport/Departure/TPE"), ("arr", "Air/FIDS/Airport/Arrival/TPE")):
        rows = tdx(path)
        if isinstance(rows, dict):
            rows = rows.get("FIDS") or rows.get("Departures") or rows.get("Arrivals") or []
        # 共掛班號（JL802／AA8424／CI9902 同一架）只算一次：以表定時間＋對方機場＋登機門去重
        seen, uniq = set(), []
        for r in rows:
            k = (r.get("ScheduleDepartureTime") if kind == "dep" else r.get("ScheduleArrivalTime"),
                 r.get("ArrivalAirportID") if kind == "dep" else r.get("DepartureAirportID"), r.get("Gate") or r.get("Terminal"))
            if k in seen:
                continue
            seen.add(k); uniq.append(r)
        rows = uniq
        tot = len(rows); delayed = cancelled = 0; upcoming = []
        now_tpe = NOW.astimezone(TPE)
        for r in rows:
            rk = re.sub(r"[A-Za-z ]+", "", (r.get("DepartureRemark") if kind == "dep" else r.get("ArrivalRemark")) or "")
            if "取消" in rk:
                cancelled += 1
            elif "延" in rk:
                delayed += 1
            sched = r.get("ScheduleDepartureTime") if kind == "dep" else r.get("ScheduleArrivalTime")
            est = r.get("EstimatedDepartureTime") if kind == "dep" else r.get("EstimatedArrivalTime")
            try:
                st = datetime.fromisoformat(sched)
                st = st if st.tzinfo else st.replace(tzinfo=TPE)
            except Exception:
                continue
            if kind == "dep" and st >= now_tpe - timedelta(minutes=5) and len(upcoming) < 8 and "取消" not in rk and "出發" not in rk:
                upcoming.append({"flight": f'{r.get("AirlineID","")}{r.get("FlightNumber","")}', "to": r.get("ArrivalAirportID", ""),
                                 "sched": st.strftime("%H:%M"), "est": (est or "")[11:16], "remark": rk[:4], "gate": (r.get("Gate") or "")[:4]})
        upcoming.sort(key=lambda x: x["sched"])
        out[kind] = {"total": tot, "delayed": delayed, "cancelled": cancelled, "upcoming": upcoming}
    if not out["dep"]["total"] and not out["arr"]["total"]:
        raise RuntimeError("airport: empty")
    return out


# ---------- 全球大盤 / 美股板塊輪動 / 恐慌結構 ----------

# Stooq（免金鑰日線 CSV）：Yahoo 掛掉時的備援。鍵＝Yahoo 代碼，值＝Stooq 代碼
STOOQ = {"^GSPC": "^spx", "^IXIC": "^ndq", "^DJI": "^dji", "^N225": "^nkx", "^HSI": "^hsi", "000001.SS": "^shc",
         "^KS11": "^kospi", "^NSEI": "^nifty50", "^GDAXI": "^dax", "^STOXX50E": "^stoxx50e", "^VIX": "^vix",
         "SPY": "spy.us", "XLK": "xlk.us", "XLC": "xlc.us", "XLY": "xly.us", "XLF": "xlf.us", "XLV": "xlv.us", "XLI": "xli.us",
         "XLP": "xlp.us", "XLE": "xle.us", "XLU": "xlu.us", "XLRE": "xlre.us", "XLB": "xlb.us",
         "MC.PA": "mc.fr", "KER.PA": "ker.fr", "RMS.PA": "rms.fr", "ITX.MC": "itx.es", "9983.T": "9983.jp", "NKE": "nke.us",
         "1913.HK": "1913.hk", "BRBY.L": "brby.uk"}
_stooq_cache: dict = {}


def stooq_daily(code: str):
    """回 [(date, close, volume)]，最近 ~70 個交易日。"""
    if code in _stooq_cache:
        return _stooq_cache[code]
    r = get("https://stooq.com/q/d/l/", params={"s": code, "i": "d"}, headers={"Referer": "https://stooq.com/"})
    rows = []
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 5 and num(parts[4]) is not None:
            rows.append((parts[0], num(parts[4]), num(parts[5]) if len(parts) > 5 else None))
    rows = rows[-70:]
    _stooq_cache[code] = rows
    time.sleep(0.5)
    return rows


def yahoo_daily(sym: str, rng="3mo"):
    """日線收盤＋成交量＋是否盤中（chart API 一次拿完）。"""
    key = "daily:" + sym
    if key in _yahoo_cache:
        return _yahoo_cache[key]
    source, meta, is_open = "yahoo", {}, False
    try:
        j = _yahoo_get(sym, {"range": rng, "interval": "1d", "includePrePost": "false"})
        res = j["chart"]["result"][0]; meta = res["meta"]
        q = res["indicators"]["quote"][0]
        closes, vols, ts = q.get("close") or [], q.get("volume") or [], res.get("timestamp") or []
        off = meta.get("gmtoffset") or 0
        rows = [(datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat(), c, v) for t, c, v in zip(ts, closes, vols) if c is not None]
        reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        now_ts = int(NOW.timestamp())
        is_open = bool(reg) and reg.get("start", 0) <= now_ts < reg.get("end", 0)
    except Exception as e:  # noqa: BLE001
        if sym not in STOOQ:
            raise
        log("yahoo→stooq", sym, e)
        rows = stooq_daily(STOOQ[sym]); source = "stooq"
        if not rows:
            raise
    price = rows[-1][1] if rows else None
    prev = rows[-2][1] if len(rows) >= 2 else None
    def pct(a, b):
        return (a - b) / b * 100 if a is not None and b else None
    out = {"price": price, "chg_pct": pct(price, prev), "chg5_pct": pct(price, rows[-6][1]) if len(rows) >= 6 else None,
           "asOf": rows[-1][0] if rows else None, "open": is_open, "ccy": meta.get("currency"), "source": source,
           "closes": [c for _, c, _ in rows], "vols": [v for _, _, v in rows], "dates": [d for d, _, _ in rows]}
    _yahoo_cache[key] = out
    return out


WORLD = [("^GSPC", "S&P 500", "美"), ("^IXIC", "Nasdaq", "美"), ("^DJI", "道瓊", "美"), ("^N225", "日經 225", "日"),
         ("^HSI", "恆生", "港"), ("000001.SS", "上證", "中"), ("^KS11", "KOSPI", "韓"), ("^NSEI", "Nifty 50", "印"),
         ("^GDAXI", "DAX", "德"), ("^STOXX50E", "STOXX 50", "歐")]


def p_world():
    items, errs = [], []
    for sym, name, flag in WORLD:
        try:
            q = yahoo_daily(sym, "2mo")
        except Exception as e:  # noqa: BLE001
            log("world", sym, e); errs.append(f"{name}: {safe_err(e)}"); continue
        items.append({"sym": sym, "name": name, "flag": flag, "price": q["price"], "chg_pct": q["chg_pct"], "chg5_pct": q["chg5_pct"],
                      "open": q["open"], "asOf": q["asOf"], "spark": q["closes"][-30:], "src": q["source"]})
    if not items:
        raise RuntimeError(f"world: nothing {errs[:2]}")
    return {"items": items, "errs": errs[:3], "label": "Stooq 備援" if any(i["src"] == "stooq" for i in items) else ""}


US_SECTORS = [("XLK", "科技"), ("XLC", "通訊"), ("XLY", "非必需"), ("XLF", "金融"), ("XLV", "醫療"), ("XLI", "工業"),
           ("XLP", "必需"), ("XLE", "能源"), ("XLU", "公用"), ("XLRE", "地產"), ("XLB", "原物料")]


def p_sectors():
    spy = yahoo_daily("SPY")
    items, errs = [], []
    for sym, name in US_SECTORS:
        try:
            q = yahoo_daily(sym)
        except Exception as e:  # noqa: BLE001
            log("sector", sym, e); errs.append(f"{sym}: {safe_err(e)}"); continue
        vols = [v for v in q["vols"] if v]
        # 相對成交量：今天（或最近一根完整日）÷ 前 20 日均量；盤中那根量不完整，用前一根
        idx = -2 if q["open"] and len(vols) >= 22 else -1
        base = vols[idx - 20:idx] if len(vols) >= 21 else []
        rvol = (vols[idx] / (sum(base) / len(base))) if base and vols[idx] else None
        items.append({"sym": sym, "name": name, "chg_pct": q["chg_pct"], "chg5_pct": q["chg5_pct"],
                      "rel5_pct": (q["chg5_pct"] - spy["chg5_pct"]) if q["chg5_pct"] is not None and spy["chg5_pct"] is not None else None,
                      "rvol": round(rvol, 2) if rvol else None})
    if not items:
        raise RuntimeError(f"sectors: nothing {errs[:2]}")
    items.sort(key=lambda x: (x["rel5_pct"] if x["rel5_pct"] is not None else -999), reverse=True)
    # 風險偏好：XLY/XLP 比值 30 天
    ratio = []
    try:
        y, p_ = yahoo_daily("XLY"), yahoo_daily("XLP")
        n = min(len(y["closes"]), len(p_["closes"]))
        ratio = [round(a / b, 4) for a, b in zip(y["closes"][-n:], p_["closes"][-n:])][-30:]
    except Exception as e:  # noqa: BLE001
        log("risk ratio", e)
    return {"spy_chg_pct": spy["chg_pct"], "spy_chg5_pct": spy["chg5_pct"], "open": spy["open"], "asOf": spy["asOf"],
            "items": items, "risk_ratio": ratio, "errs": errs[:3], "label": "Stooq 備援" if spy["source"] == "stooq" else ""}


FEAR = [("^VIX", "VIX", "波動", (15, 25)), ("^VVIX", "VVIX", "波動的波動", (110, 135)),
        ("^SKEW", "SKEW", "尾部厚度", (130, 145))]
FEAR_MEAN = {"VIX": 19, "VVIX": 86, "SKEW": 100, "VIX/VIX3M": 0.9}  # 長期參照：VIX 均值、VVIX 均值、SKEW=100 為常態分布


CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/"


CBOE_CACHE = DATA / "cboe_cache.json"


def cboe_hist(name: str, n=60):
    """CBOE 官方每日收盤 CSV → [(date, close)]。VIX/VIX3M 是 OHLC，VVIX/SKEW 是兩欄。
    整檔從 1990 起數百 KB，一天只抓一次（快取 6 小時），盤中由 Yahoo 補最後一點。"""
    cache = {}
    if CBOE_CACHE.exists():
        try:
            cache = json.loads(CBOE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    c = cache.get(name)
    if c and (NOW - datetime.fromisoformat(c["at"].replace("Z", "+00:00"))) < timedelta(hours=6):
        return [tuple(x) for x in c["rows"]][-n:]
    r = get(CBOE + f"{name}_History.csv", headers={"Referer": "https://www.cboe.com/"})
    rows = []
    for line in r.text.strip().splitlines()[1:]:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 2:
            d = parts[0]
            try:
                d = datetime.strptime(d, "%m/%d/%Y").date().isoformat()
            except Exception:
                pass
            v = num(parts[-1])
            if v is not None:
                rows.append((d, v))
    cache[name] = {"at": NOW_ISO, "rows": rows[-120:]}
    try:
        write_json(CBOE_CACHE, cache, separators=(",", ":"))
    except Exception as e:  # noqa: BLE001
        log("cboe cache", e)
    return rows[-n:]


def p_fear():
    items, errs, src = [], [], "CBOE"
    yahoo_live = {}
    for sym, name, sub, (lo, hi) in FEAR:
        hist = []
        try:
            hist = cboe_hist(name)
        except Exception as e:  # noqa: BLE001
            log("cboe", name, e); errs.append(f"CBOE {name}: " + safe_err(e))
        live = None
        try:  # 盤中值：Yahoo 比 CBOE 日檔新的話才用
            q = yahoo_daily(sym, "1mo")
            if q["asOf"] and (not hist or q["asOf"] > hist[-1][0]):
                live = (q["asOf"], q["price"])
            if not hist:
                hist = list(zip(q["dates"], q["closes"])); src = "Yahoo"
        except Exception as e:  # noqa: BLE001
            log("fear yahoo", sym, e)
        if not hist:
            errs.append(f"{name}: 無資料"); continue
        series = hist + ([live] if live else [])
        v, prev = series[-1][1], series[-2][1] if len(series) >= 2 else None
        for d, c in hist:
            hist_put("fear", name, d, c)
        v5 = series[-6][1] if len(series) >= 6 else None
        items.append({"sym": sym, "name": name, "sub": sub, "value": v, "chg_pct": (v - prev) / prev * 100 if prev else None,
                      "chg5": round(v - v5, 2) if v5 is not None else None, "mean": FEAR_MEAN.get(name),
                      "level": "green" if v < lo else "yellow" if v < hi else "red", "lo": lo, "hi": hi,
                      "spark": [c for _, c in series[-30:]], "asOf": series[-1][0], "live": bool(live)})
        yahoo_live[name] = series
    # 期限結構：VIX / VIX3M，>1 = backwardation（近月比遠月貴，恐慌當下而非預期）
    try:
        v3 = cboe_hist("VIX3M")
        vix = yahoo_live.get("VIX") or []
        dv = dict(vix); d3 = dict(v3)
        common = [d for d in dv if d in d3]
        series = [round(dv[d] / d3[d], 3) for d in common]
        if vix and v3 and vix[-1][0] > v3[-1][0]:  # VIX 有盤中值但 VIX3M 只有昨收 → 用 Yahoo 的 VIX3M 補
            try:
                q3 = yahoo_daily("^VIX3M", "1mo")
                if q3["price"]:
                    series.append(round(vix[-1][1] / q3["price"], 3)); common.append(vix[-1][0])
            except Exception:
                pass
        r = series[-1] if series else None
        items.append({"sym": "^VIX/^VIX3M", "name": "VIX/VIX3M", "sub": "期限結構", "value": r, "chg_pct": None, "mean": 0.9,
                      "level": "green" if r is not None and r < 0.9 else "yellow" if r is not None and r < 1.0 else "red",
                      "lo": 0.9, "hi": 1.0, "spark": series[-30:], "asOf": common[-1] if common else None})
    except Exception as e:  # noqa: BLE001
        log("fear term", e); errs.append("VIX3M: " + safe_err(e))
    if not items:
        raise RuntimeError(f"fear: nothing {errs[:2]}")
    # 組合判讀（優先序由上而下）
    by = {i["name"]: i for i in items}
    vix, vvix, skew, term = by.get("VIX"), by.get("VVIX"), by.get("SKEW"), by.get("VIX/VIX3M")
    lv = lambda i: i["level"] if i else None  # noqa: E731
    regime, why, tone = "中性", "指標互相抵銷，沒有一致方向", "flat"
    if term and term["level"] == "red":
        regime, why, tone = "恐慌當下", f"VIX/VIX3M {term['value']} > 1：近月比遠月貴，避險需求集中在現在，不是預期", "red"
    elif lv(vix) == "red":
        regime, why, tone = "恐慌區", f"VIX {vix['value']:.1f} 已過 25", "red"
    elif vix and vvix and (vix.get("chg5") or 0) > 0 and (vvix.get("chg5") or 0) > 0 and lv(vvix) != "green":
        regime, why, tone = "波動放大中", f"VIX 與 VVIX 近 5 日同步上升（+{vix['chg5']}、+{vvix['chg5']}），VVIX {vvix['value']:.0f} 過門檻，通常不是一日行情", "yellow"
    elif lv(vix) in ("green", "yellow") and (lv(vvix) == "red" or lv(skew) == "red"):
        parts = []
        if lv(vvix) == "red":
            parts.append(f"VVIX {vvix['value']:.0f}")
        if lv(skew) == "red":
            parts.append(f"SKEW {skew['value']:.0f}（常態 100）")
        regime, why, tone = "暴風雨前的平靜", f"VIX {vix['value']:.1f} 不高，但 {'、'.join(parts)} 顯示有人在買尾部保護", "yellow"
    elif all(lv(i) == "green" for i in (vix, vvix, skew) if i):
        regime, why, tone = "風平浪靜", "三個指標都在低檔，市場沒在防守", "green"
    return {"items": items, "errs": errs[:3], "label": src, "regime": regime, "why": why, "tone": tone}


# ---------- 全球總經（FRED） ----------
GMACRO = [  # (group, label, series, kind) kind: yoy=指數換年增, level=直接值, pct=已是百分比
    ("美國", "CPI 年增", "CPIAUCSL", "yoy"), ("美國", "核心 PCE 年增", "PCEPILFE", "yoy"), ("美國", "失業率", "UNRATE", "pct"),
    ("美國", "聯邦資金利率", "DFF", "pct"), ("美國", "10 年公債", "DGS10", "pct"), ("美國", "2 年公債", "DGS2", "pct"),
    ("美國", "GDP 季增年率", "A191RL1Q225SBEA", "pct"), ("美國", "初領失業金", "ICSA", "k"), ("美國", "密大消費信心", "UMCSENT", "level"),
    ("美國", "費城聯準會製造業", "GACDFSA066MSFRBPHI", "level"), ("美國", "紐約聯準會製造業", "GACDISA066MSFRBNY", "level"), ("美國", "CFNAI 全國活動", "CFNAI", "level2"),
    ("歐元區", "HICP 年增", "CP0000EZ19M086NEST", "yoy"), ("歐元區", "ECB 存款利率", "ECBDFR", "pct"),
    ("日本", "政策利率", "IRSTCI01JPM156N|IRSTCB01JPM156N", "pct|pct"),
    # 日本／中國 CPI：FRED 的 OECD 系列 2025 起停更，免費且免金鑰的官方 API 目前沒有，先不放
]
GMACRO_MAX_AGE_DAYS = 200  # FRED 上 OECD 系列常停更；太舊就不顯示，免得誤導


def p_gmacro():
    if not FRED_KEY:
        raise RuntimeError("no FRED_API_KEY")
    items, errs = [], []
    for group, label, sids, kinds in GMACRO:
        try:
            obs, sid, kind = [], None, None
            for sid, kind in zip(sids.split("|"), kinds.split("|")):  # 依序試候選系列，取最新且沒停更的
                try:
                    cand = fred(sid, 30)
                except Exception as e:  # noqa: BLE001
                    log("gmacro cand", sid, e); continue
                if cand and (NOW.date() - datetime.fromisoformat(cand[-1][0]).date()).days <= GMACRO_MAX_AGE_DAYS:
                    obs = cand; break
            if not obs:
                raise RuntimeError("停更或無資料")
            if kind == "yoy":
                # 月資料：與 12 期前比
                vals = [(d, (v / obs[i - 12][1] - 1) * 100) for i, (d, v) in enumerate(obs) if i >= 12 and obs[i - 12][1]]
            else:
                vals = obs
            if not vals:
                raise RuntimeError("too short")
            d, v = vals[-1]; pv = vals[-2][1] if len(vals) >= 2 else None
            if kind == "k":
                txt, ptxt = f"{v / 1000:.0f}k", f"{pv / 1000:.0f}k" if pv is not None else ""
            elif kind == "level":
                txt, ptxt = f"{v:.1f}", f"{pv:.1f}" if pv is not None else ""
            elif kind == "level2":
                txt, ptxt = f"{v:+.2f}", f"{pv:+.2f}" if pv is not None else ""
            else:
                txt, ptxt = f"{v:.2f}%", f"{pv:.2f}%" if pv is not None else ""
            items.append({"group": group, "label": label, "value": txt, "raw": round(v, 3), "prev": ptxt, "period": d[:7] if kind != "pct" or "DGS" not in sid and sid != "DFF" else d,
                          "delta": round(v - pv, 3) if pv is not None else None, "spark": [round(x, 3) for _, x in vals[-18:]],
                          "dot": ("up" if v > 0 else "down") if sid in ("GACDFSA066MSFRBPHI", "GACDISA066MSFRBNY", "CFNAI") else None})
        except Exception as e:  # noqa: BLE001
            log("gmacro", sid, e); errs.append(f"{group}{label}: {safe_err(e)}")
        time.sleep(0.3)
    # ISM PMI：官網新聞稿（擋爬蟲機率高，抓到才顯示）
    for name, path in (("ISM 製造業 PMI", "pmi"), ("ISM 服務業 PMI", "services")):
        try:
            from curl_cffi import requests as cffi
            r = cffi.get(f"https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/{path}/", impersonate="chrome", timeout=25)
            r.raise_for_status()
            txt = re.sub(r"<[^>]+>", " ", r.text)
            m = re.search(r"(?:PMI|Services PMI)[^\d]{0,40}(\d{2}\.\d)\s*percent", txt, re.I) or re.search(r"registered\s+(\d{2}\.\d)\s*percent", txt, re.I)
            mo = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)", txt)
            if m:
                v = float(m.group(1))
                items.insert(0, {"group": "美國", "label": name, "value": f"{v:.1f}", "raw": v, "prev": "", "period": f"{mo.group(2)}-{mo.group(1)[:3]}" if mo else "",
                                 "delta": None, "spark": [], "dot": "up" if v >= 50 else "down"})
        except Exception as e:  # noqa: BLE001
            log("ism", path, e); errs.append(f"{name}: 官網擋爬，改看聯準會區域指數")
    # 英國 CPI：FRED 的 OECD 系列停更，改用 ONS 官方 API（免金鑰）
    try:
        js = gjson("https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23/data", headers={"Accept": "application/json"})
        ms = [(m["date"], num(m["value"])) for m in js.get("months", []) if num(m.get("value")) is not None]
        if ms:
            v, pv = ms[-1][1], ms[-2][1] if len(ms) >= 2 else None
            items.append({"group": "英國", "label": "CPI 年增", "value": f"{v:.2f}%", "raw": v, "prev": f"{pv:.2f}%" if pv is not None else "",
                          "period": ms[-1][0], "delta": round(v - pv, 3) if pv is not None else None, "spark": [x for _, x in ms[-18:]]})
    except Exception as e:  # noqa: BLE001
        log("ons cpi", e); errs.append("英國 CPI: " + safe_err(e))
    # 利差：10Y − 2Y
    d10 = next((i for i in items if i["label"] == "10 年公債"), None); d2 = next((i for i in items if i["label"] == "2 年公債"), None)
    if d10 and d2:
        sp = round(d10["raw"] - d2["raw"], 2)
        items.insert(items.index(d2) + 1, {"group": "美國", "label": "10Y−2Y 利差", "value": f"{sp:+.2f}%", "raw": sp, "prev": "", "period": d10["period"],
                                           "delta": None, "spark": [round(a - b, 3) for a, b in zip(d10["spark"], d2["spark"])], "tone": "down" if sp < 0 else ""})
    if not items:
        raise RuntimeError(f"gmacro: nothing {errs[:2]}")
    return {"items": items, "errs": errs[:4]}


# ---------- YouTube 發燒榜（Data API v3，每次 1 單位） ----------
YT_CATS = [("all", "全部", None), ("music", "音樂", "10"), ("ent", "娛樂", "24"), ("news", "新聞", "25")]


def _yt_popular(region, category=None, n=10):
    params = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": n, "key": YOUTUBE_KEY}
    if category:
        params["videoCategoryId"] = category
    js = gjson("https://www.googleapis.com/youtube/v3/videos", params=params)
    out = []
    for v in js.get("items", []):
        sn, st = v.get("snippet") or {}, v.get("statistics") or {}
        out.append({"id": v.get("id"), "title": (sn.get("title") or "")[:70], "channel": (sn.get("channelTitle") or "")[:20],
                    "views": num(st.get("viewCount")), "likes": num(st.get("likeCount")), "at": sn.get("publishedAt"),
                    "url": f"https://www.youtube.com/watch?v={v.get('id')}"})
    return out


def p_youtube():
    if not YOUTUBE_KEY:
        raise RuntimeError("no YOUTUBE_API_KEY")
    tw, errs = {}, []
    for key, label, cat in YT_CATS:
        try:
            tw[key] = _yt_popular("TW", cat, 10)
        except Exception as e:  # noqa: BLE001
            log("yt", key, e); errs.append(f"TW {label}: {safe_err(e)}")
    us = []
    try:
        us = _yt_popular("US", None, 5)
    except Exception as e:  # noqa: BLE001
        log("yt us", e); errs.append("US: " + safe_err(e))
    if not tw.get("all") and not us:
        raise RuntimeError(f"youtube: nothing {errs[:2]}")
    return {"tw": tw, "us": us, "cats": [(k, l) for k, l, _ in YT_CATS], "errs": errs[:3]}


# ---------- 事件行事曆 / 決標公告 / 供應鏈與通路 ----------
FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]  # 決議日（Fed 公布時程）
FRED_RELEASES = {"Consumer Price Index": "美國 CPI", "Employment Situation": "美國非農就業", "Gross Domestic Product": "美國 GDP",
                 "Personal Income and Outlays": "美國 PCE", "Producer Price Index": "美國 PPI", "Advance Monthly Sales for Retail and Food Services": "美國零售銷售",
                 "Surveys of Consumers": "密大消費信心", "Job Openings and Labor Turnover Survey": "美國 JOLTS"}


def _third_thursday(y, m):
    from calendar import monthrange
    d1 = datetime(y, m, 1).weekday()  # Mon=0
    first_thu = 1 + (3 - d1) % 7
    return datetime(y, m, first_thu + 14).date()


def p_calendar():
    today = TODAY_TPE
    horizon = today + timedelta(days=21)
    ev = []
    def add(d, label, region, approx=False, kind=""):
        if isinstance(d, str):
            d = datetime.fromisoformat(d).date()
        if today <= d <= horizon:
            ev.append({"date": d.isoformat(), "label": label, "region": region, "approx": approx, "kind": kind})
    # 美國：FRED 發布時程（官方）
    errs = []
    if FRED_KEY:
        try:
            j = gjson("https://api.stlouisfed.org/fred/releases/dates", params={"api_key": FRED_KEY, "file_type": "json", "realtime_start": today.isoformat(),
                      "realtime_end": horizon.isoformat(), "include_release_dates_with_no_data": "true", "limit": 1000, "sort_order": "asc"})
            for r in j.get("release_dates", []):
                name = (r.get("release_name") or "").strip()
                lab = FRED_RELEASES.get(name)
                if lab:
                    add(r["date"], lab, "美", kind="data")
        except Exception as e:  # noqa: BLE001
            log("fred releases", e); errs.append("FRED: " + safe_err(e))
    for d in FOMC_2026:
        add(d, "FOMC 利率決議", "美", kind="cb")
    # 台灣：固定時程（主計總處／央行／國發會／中經院），標「約」
    for mo in (today.month, (today.month % 12) + 1):
        y = today.year + (1 if mo < today.month else 0)
        from calendar import monthrange
        last = monthrange(y, mo)[1]
        add(datetime(y, mo, 1).date(), "台灣 PMI／NMI（中經院）", "台", kind="data")
        add(datetime(y, mo, 6).date(), "台灣 CPI／PPI（主計總處）", "台", approx=True, kind="data")
        add(datetime(y, mo, 20).date(), "外銷訂單（經濟部）", "台", approx=True, kind="data")
        add(datetime(y, mo, 22).date(), "失業率（主計總處）", "台", approx=True, kind="data")
        add(datetime(y, mo, 27).date(), "景氣燈號（國發會）", "台", approx=True, kind="data")
        if mo in (1, 4, 7, 10):
            add(datetime(y, mo, last).date(), "GDP 概估（主計總處）", "台", approx=True, kind="data")
        if mo in (3, 6, 9, 12):
            add(_third_thursday(y, mo), "央行理監事會", "台", approx=True, kind="cb")
    # 台股休市（證交所 openapi）
    try:
        for r in gjson("https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"):
            raw = str(r.get("Date") or r.get("日期") or "")
            d = roc_to_iso(raw) if raw and not raw.startswith("20") else raw[:10]
            if d:
                add(d, f"台股休市：{(r.get('Name') or r.get('名稱') or '')[:12]}", "台", kind="holiday")
    except Exception as e:  # noqa: BLE001
        log("twse holidays", e); errs.append("休市: " + safe_err(e))
    # 去重、排序
    seen, out = set(), []
    for e in sorted(ev, key=lambda x: (x["date"], x["region"])):
        k = (e["date"], e["label"])
        if k not in seen:
            seen.add(k); out.append(e)
    if not out:
        raise RuntimeError(f"calendar: nothing {errs[:2]}")
    return {"items": out, "from": today.isoformat(), "to": horizon.isoformat(), "errs": errs[:3]}


AWARD_CACHE = DATA / "award_cache.json"


def p_awards():
    """決標公告：行銷／品牌／影片／廣告類標案誰得標、決標金額。"""
    cache = {}
    if AWARD_CACHE.exists():
        try:
            cache = json.loads(AWARD_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    found, errs = {}, []
    for kw in PCC_KW:
        try:
            js = _pcc_search(kw)
            for r in js.get("records", []):
                b = r.get("brief") or {}
                typ = b.get("type") or ""
                if "決標公告" not in typ or "無法決標" in typ:
                    continue
                title = b.get("title") or ""
                if any(x in title for x in PCC_EXCLUDE):
                    continue
                key = f'{r.get("unit_id")}/{r.get("job_number")}'
                if key in found:
                    continue
                comp = b.get("companies") or r.get("companies") or {}
                names = []
                if isinstance(comp, dict):
                    names = comp.get("names") or comp.get("name") or []
                    if isinstance(names, dict):
                        names = list(names.values())
                elif isinstance(comp, list):
                    names = [c.get("name") if isinstance(c, dict) else str(c) for c in comp]
                found[key] = {"key": key, "title": title[:60], "unit": (r.get("unit_name") or "")[:18], "date": str(r.get("date") or ""),
                              "winner": "、".join(str(n_)[:16] for n_ in names[:2]) if names else "",
                              "url": f'https://openfunltd.github.io/pcc-viewer/tender.html?unit_id={r.get("unit_id")}&job_number={r.get("job_number")}'}
        except Exception as e:  # noqa: BLE001
            log("awards", kw, e); errs.append(f"{kw}: {safe_err(e)}")
        time.sleep(1)
    items = sorted(found.values(), key=lambda x: x["date"], reverse=True)[:14]
    filled = 0
    for it in items:
        if it["key"] in cache:
            c = cache[it["key"]] or {}
            it["amount"], it["winner"] = c.get("amount"), it["winner"] or c.get("winner", ""); continue
        if filled >= 6:
            continue
        try:
            time.sleep(1)
            uid, job = it["key"].split("/", 1)
            d = _cffi_json("https://pcc-api.openfun.app/api/tender", unit_id=uid, job_number=job)
            recs = d.get("records") or []
            det = {}
            for rec in recs:  # 取最新的決標公告那份 detail
                if "決標" in ((rec.get("brief") or {}).get("type") or ""):
                    det = rec.get("detail") or {}
            det = det or (recs[-1].get("detail") if recs else {}) or {}
            amt = None
            for k, v in det.items():
                if "決標金額" in k or "總決標金額" in k:
                    m = re.search(r"[\d,]+", str(v).replace("元", ""))
                    if m:
                        amt = int(m.group(0).replace(",", "")); break
            if not it["winner"]:
                for k, v in det.items():
                    if "得標廠商" in k and "名稱" in k and v:
                        it["winner"] = str(v)[:16]; break
            it["amount"] = amt
            cache[it["key"]] = {"amount": amt, "winner": it["winner"]}; filled += 1
        except Exception as e:  # noqa: BLE001
            log("award detail", it["key"], e); it["amount"] = None
    if len(cache) > 600:
        cache = dict(list(cache.items())[-400:])
    write_json(AWARD_CACHE, cache)
    if not items:
        raise RuntimeError(f"awards: nothing errs={errs[:3]}")
    return {"items": items, "errs": errs[:3]}


RETAIL_CSV = ("https://service.moea.gov.tw/EE520/opendata/%E7%B6%93%E6%BF%9F%E9%83%A8%E7%B5%B1%E8%A8%88%E8%99%95_%E6%89%B9%E7%99%BC%E3%80%81"
              "%E9%9B%B6%E5%94%AE%E5%8F%8A%E9%A4%90%E9%A3%B2%E6%A5%AD%E7%87%9F%E6%A5%AD%E9%A1%8D%E6%8C%87%E6%95%B8.csv")
RETAIL_WATCH = ["零售業", "超級市場", "便利商店", "百貨公司", "電子購物", "化粧品", "家庭器具", "布疋及服飾品零售", "餐飲業"]


def _ndc_pmi(page):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(user_agent=UA, locale="zh-TW")
        pg.goto(f"https://index.ndc.gov.tw/n/zh_tw/{page}", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(2500)
        txt = pg.inner_text("body")
        b.close()
    head = re.search(r"擴張（Expansion）\s*(?:\d+\s*){7}(\d+\.?\d*)\s*%", txt)
    orders = re.search(r"新增訂單[^\n]*\n(?:\s*\d+\s*\n){4}\s*(\d+\.?\d*)\s*%", txt)
    ym = re.search(r"(20\d\d)\n(\d{1,2})月", txt)
    chg = re.search(r"較上月變化\s*([+-]?\d+(?:\.\d+)?)\s*百分點", txt)
    nxt = re.search(r"下次發布日期\s*:\s*(\d{4}-\d{2}-\d{2})", txt)
    if not head:
        raise RuntimeError(f"ndc {page} parse")
    return {"value": float(head.group(1)), "orders": float(orders.group(1)) if orders else None,
            "period": f"{ym.group(1)}-{int(ym.group(2)):02d}" if ym else "", "chg": float(chg.group(1)) if chg else None,
            "next": nxt.group(1) if nxt else ""}


def p_supply():
    out, errs = {"pmi": None, "nmi": None, "retail": []}, []
    for key, page in (("pmi", "PMI"), ("nmi", "NMI")):
        try:
            out[key] = _ndc_pmi(page)
            if out[key]["period"]:
                hist_put("supply", key, out[key]["period"], out[key]["value"])
            out[key]["spark"] = hist_get("supply", key, 24)
        except Exception as e:  # noqa: BLE001
            log("ndc", page, e); errs.append(f"{page}: {safe_err(e)}")
    # 經濟部零售業營業額指數（分業別）→ 年增率
    try:
        r = get(RETAIL_CSV, headers={"Referer": "https://data.gov.tw/"})
        raw = r.content
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("big5", errors="ignore")
        import csv as _csv
        rows = list(_csv.reader(txt.splitlines()))
        hdr = rows[0]
        ci = {h: i for i, h in enumerate(hdr)}
        def col(*names):
            for n_ in names:
                for h, i in ci.items():
                    if n_ in h:
                        return i
            return None
        c_ind, c_per, c_val = col("行業別"), col("資料期"), col("統計值")
        series = {}
        for row in rows[1:]:
            if len(row) <= max(c_ind, c_per, c_val):
                continue
            ind, per, val = row[c_ind].strip(), row[c_per].strip(), num(row[c_val])
            m = re.match(r"^(\d{2,3})(\d{2})$", per) or re.match(r"(\d{2,3})\D+(\d{1,2})", per)  # 11508＝民國 115 年 8 月
            if not m or val is None:
                continue
            y = int(m.group(1)); y = y + 1911 if y < 1911 else y
            series.setdefault(ind, {})[f"{y}-{int(m.group(2)):02d}"] = val
        for w in RETAIL_WATCH:
            name = next((k for k in series if k.startswith(w) or w in k), None)
            if not name:
                continue
            ser = sorted(series[name].items())
            if len(ser) < 13:
                continue
            (p_last, v_last) = ser[-1]
            y, m_ = p_last.split("-")
            prev_year = f"{int(y) - 1}-{m_}"
            v_prev = series[name].get(prev_year)
            if (TODAY_TPE - datetime.fromisoformat(p_last + "-01").date()).days > 150:
                errs.append(f"零售指數停在 {p_last}"); break
            if v_prev:
                out["retail"].append({"name": name[:10], "period": p_last, "yoy": round((v_last / v_prev - 1) * 100, 1),
                                      "spark": [v for _, v in ser[-13:]]})
        if not out["retail"]:
            errs.append(f"零售: 行業={list(series)[:6]} sample={rows[1][:6] if len(rows) > 1 else None} last={rows[-1][:6]} nrows={len(rows)}")
    except Exception as e:  # noqa: BLE001
        log("retail csv", e); errs.append("零售指數: " + safe_err(e))
    if not out["pmi"] and not out["nmi"] and not out["retail"]:
        raise RuntimeError(f"supply: nothing {errs[:3]}")
    return {**out, "errs": errs[:4]}


# ---------- 美元流動性（NY Fed API ＋ FRED） ----------
def p_liquidity():
    if not FRED_KEY:
        raise RuntimeError("no FRED_API_KEY")
    errs, out = [], {}
    # 利率：NY Fed 官方 API（免金鑰），失敗退 FRED
    rates = {}
    try:
        js = gjson("https://markets.newyorkfed.org/api/rates/all/latest.json", headers={"Accept": "application/json"})
        for r in js.get("refRates", []) + js.get("unsecuredRates", []) + js.get("securedRates", []):
            t = (r.get("type") or "").upper()
            if t in ("SOFR", "EFFR") and num(r.get("percentRate")) is not None:
                rates[t] = {"value": num(r.get("percentRate")), "date": r.get("effectiveDate")}
    except Exception as e:  # noqa: BLE001
        log("nyfed rates", e); errs.append("NY Fed rates: " + safe_err(e))
    for t in ("SOFR", "EFFR"):
        if t not in rates:
            try:
                obs = fred(t, 5); rates[t] = {"value": obs[-1][1], "date": obs[-1][0]}
            except Exception as e:  # noqa: BLE001
                errs.append(f"{t}: {safe_err(e)}")
    try:
        obs = fred("IORB", 5); rates["IORB"] = {"value": obs[-1][1], "date": obs[-1][0]}
    except Exception as e:  # noqa: BLE001
        errs.append("IORB: " + safe_err(e))
    out["rates"] = rates
    if "SOFR" in rates and "IORB" in rates:
        out["sofr_iorb"] = round(rates["SOFR"]["value"] - rates["IORB"]["value"], 3)
    # 數量：FRED（十億美元）
    def ser(sid, n=60, scale=1.0):
        obs = fred(sid, n)
        return [(d, v * scale) for d, v in obs]
    try:
        rrp = ser("RRPONTSYD", 80)            # ON RRP，十億，日
        out["rrp"] = {"value": rrp[-1][1], "date": rrp[-1][0], "spark": [v for _, v in rrp[-40:]]}
        hist_put("liq", "rrp", rrp[-1][0], rrp[-1][1])
    except Exception as e:  # noqa: BLE001
        errs.append("RRP: " + safe_err(e)); rrp = []
    try:
        srf = ser("RPONTSYD", 20)
        out["srf"] = {"value": srf[-1][1], "date": srf[-1][0]}
    except Exception as e:  # noqa: BLE001
        log("srf", e)
    try:
        walcl = ser("WALCL", 40, 0.001)        # 百萬→十億，週三
        tga = ser("WTREGEN", 40, 0.001)        # 百萬→十億，週三
        res = ser("WRESBAL", 40, 0.001)        # 百萬→十億，週三
        out["walcl"] = {"value": walcl[-1][1], "date": walcl[-1][0], "spark": [v for _, v in walcl[-30:]]}
        out["tga"] = {"value": tga[-1][1], "date": tga[-1][0], "spark": [v for _, v in tga[-30:]]}
        out["reserves"] = {"value": res[-1][1], "date": res[-1][0], "spark": [v for _, v in res[-30:]]}
        # 淨流動性 = 資產 − TGA − RRP，按 WALCL 的週三對齊（RRP 取該日或之前最近一筆）
        tga_d = dict(tga); rrp_sorted = rrp
        def rrp_at(d):
            best = None
            for dd, v in rrp_sorted:
                if dd <= d:
                    best = v
            return best
        net = []
        for d, a in walcl[-30:]:
            t_, r_ = tga_d.get(d), rrp_at(d)
            if t_ is not None and r_ is not None:
                net.append((d, round(a - t_ - r_, 1)))
        if net:
            out["net"] = {"value": net[-1][1], "date": net[-1][0], "spark": [v for _, v in net],
                          "chg4w": round(net[-1][1] - net[-5][1], 1) if len(net) >= 5 else None}
    except Exception as e:  # noqa: BLE001
        errs.append("FRED weekly: " + safe_err(e))
    if not out.get("rrp") and not out.get("net"):
        raise RuntimeError(f"liquidity: nothing {errs[:2]}")
    return {**out, "errs": errs[:4]}

# ---------- run ----------
run("pulse", p_pulse)
run("taiex", p_taiex)
run("tw_market", p_tw_market, keep_if_fresh_hours=0.5)
run("tw_stocks", p_tw_stocks)
run("fx", p_fx_any)
run("poly", p_poly)
run("tech", p_tech)
run("trends", p_trends)
run("youtube", p_youtube, keep_if_fresh_hours=0.5)
run("luxury", p_luxury, keep_if_fresh_hours=3)
run("world", p_world, keep_if_fresh_hours=0.25)
run("sectors", p_sectors, keep_if_fresh_hours=0.5)
run("fear", p_fear, keep_if_fresh_hours=0.5)
run("commodities", p_commodities, keep_if_fresh_hours=3)
run("revenue", p_revenue, keep_if_fresh_hours=20)
run("media", p_media, keep_if_fresh_hours=6)
# run("reddit", p_reddit, keep_if_fresh_hours=1)  # 改用 PTT；有金鑰再開
run("lyst", p_lyst, keep_if_fresh_hours=24 * 6)
run("macro", p_macro, keep_if_fresh_hours=6)
run("gmacro", p_gmacro, keep_if_fresh_hours=6)
run("liquidity", p_liquidity, keep_if_fresh_hours=3)
run("calendar", p_calendar, keep_if_fresh_hours=6)
run("awards", p_awards, keep_if_fresh_hours=1)
run("supply", p_supply, keep_if_fresh_hours=6)
run("weather", p_weather)
run("ptt", p_ptt, keep_if_fresh_hours=0.5)
run("aiwire", p_aiwire, keep_if_fresh_hours=0.25)
run("devpulse", p_devpulse, keep_if_fresh_hours=1)
run("news", p_news, keep_if_fresh_hours=0.25)
run("social", p_social, keep_if_fresh_hours=0.5)
run("cofacts", p_cofacts, keep_if_fresh_hours=0.5)
run("threads_g", p_threads_g, keep_if_fresh_hours=2)
run("mood", p_mood, keep_if_fresh_hours=1)
run("tenders", p_tenders, keep_if_fresh_hours=0.5)
run("design", p_design, keep_if_fresh_hours=1)
run("quake", p_quake)
run("power", p_power, keep_if_fresh_hours=0.25)
run("airport", p_airport, keep_if_fresh_hours=0.25)
# run("tiktok", p_tiktok, keep_if_fresh_hours=20)  # Creative Center 擋資料中心 IP，每輪白耗 60 秒，先停

DATA.mkdir(exist_ok=True)
run("geo", p_geo, keep_if_fresh_hours=0.15)  # 最重，放最後；超過軟性期限就沿用上一輪
run("tw_pulse", p_tw_pulse)  # 吃地圖那輪的快取，幾乎不多打 API
FINISHED_ISO = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
try:
    write_json(HIST_PATH, HISTORY, separators=(",", ":"))
    write_json(DATA / "all.json", {"generatedAt": NOW_ISO, "finishedAt": FINISHED_ISO, "panels": RESULTS}, separators=(",", ":"))
except ValueError as e:
    log("NaN in output, not writing:", e)
    sys.exit(1)
ok = [k for k, v in RESULTS.items() if not v.get("error")]
bad = [k for k, v in RESULTS.items() if v.get("error")]
log(f"done ok={ok} failed={bad}")
