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
    msg = f"{type(e).__name__}: {str(e)[:160]}"
    return re.sub(r"(api_key|token|secret|authorization)=[^&\s]+", r"\1=***", msg, flags=re.I)[:140]


def run(pid: str, fn, keep_if_fresh_hours: float = 0):
    """Run one panel fetcher. keep_if_fresh_hours>0 skips re-fetch when the
    previous file is newer than that (for daily/weekly sources)."""
    prev = load_prev(pid)
    if prev and prev.get("error"):
        # 失敗退避：上次失敗距今不到 1 小時（或該面板的更新週期，取小者）就不重試
        try:
            err_ts = datetime.fromisoformat(prev["error"].split(" ")[0].replace("Z", "+00:00"))
            if NOW - err_ts < timedelta(hours=min(keep_if_fresh_hours or 1, 1)):
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
    try:
        doc = fn()
        doc["updatedAt"] = NOW_ISO
        doc.pop("error", None)
        RESULTS[pid] = doc
        write_json(PANELS / f"{pid}.json", doc, indent=1)
        log(f"[{pid}] ok {time.time() - t0:.1f}s")
    except Exception as e:  # noqa: BLE001
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
    j = _yahoo_get(sym, {"range": rng, "interval": interval, "includePrePost": "false"})
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
    return {
        "date": roc_to_iso(last["Date"]),
        "index": num(last["TAIEX"]),
        "change": num(last["Change"]),
        "value": num(last["TradeValue"]),
        "transactions": num(last["Transaction"]),
        "series": [v for _, v in series],
        "history": HISTORY.get("taiex", {}).get("TAIEX", [])[-60:],
    }


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
        ids = gjson("https://hacker-news.firebaseio.com/v0/topstories.json")[:8]
        hn = []
        for i in ids:
            s = gjson(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
            if s:
                hn.append({"title": s.get("title"), "url": s.get("url") or f"https://news.ycombinator.com/item?id={i}",
                           "score": s.get("score"), "comments": s.get("descendants")})
        out["hn"] = hn
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


REV_WATCH = {"2912": "統一超", "1216": "統一", "2903": "遠百", "5904": "寶雅", "5903": "全家", "8454": "momo", "8044": "PChome"}


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
                items[code] = {"code": code, "name": name, "rev": rev,
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
                        items[code] = {"code": code, "name": REV_WATCH[code],
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
    return {"items": list(items.values()) + auto_items, "note": prev.get("note", ""), "auto_errors": errs}



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


def p_pulse():
    items = []
    for sym, name, ccy in PULSE:
        try:
            q = yahoo_intraday(sym)
        except Exception as e:  # noqa: BLE001
            log("pulse", sym, e)
            continue
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
            if e.response is not None and e.response.status_code == 429 and attempt < 3:
                time.sleep(6 * (attempt + 1))
                continue
            raise


def p_tw_pulse():
    bikes = []
    for city, label in (("Taipei", "台北"), ("Taichung", "台中")):
        rows = tdx(f"Bike/Availability/City/{city}")
        rows = [r for r in rows if r.get("ServiceStatus", 1) == 1]
        rent = sum(r.get("AvailableRentBikes") or 0 for r in rows)
        empty = sum(1 for r in rows if (r.get("AvailableRentBikes") or 0) == 0)
        full = sum(1 for r in rows if (r.get("AvailableReturnBikes") or 0) == 0)
        key = NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M")
        hist_put("youbike", label, key, rent)
        bikes.append({"city": label, "stations": len(rows), "rent": rent, "empty": empty, "full": full,
                      "spark": hist_get("youbike", label, 48)})
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
            hist_put("freeway", f"{no}{d}", NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M"), round(spd, 1))
            roads.append({"road": f"國道{int(no)}", "dir": dirn.get(d, d), "speed": round(spd, 1), "count": c,
                          "spark": hist_get("freeway", f"{no}{d}", 48)})
    # 最塞的三個區間
    worst = []
    for pr in live.get("ETagPairLives", []):
        for fl in pr.get("Flows", []):
            if fl.get("VehicleType") == 31 and 0 < (fl.get("SpaceMeanSpeed") or 0) < 40 and (fl.get("VehicleCount") or 0) >= 30:
                worst.append((fl["SpaceMeanSpeed"], pr.get("ETagPairID")))
    worst.sort()
    names = {}
    if worst:
        try:
            for ep in tdx("Road/Traffic/ETagPair/Freeway").get("ETagPairs", []):
                names[ep.get("ETagPairID")] = ep.get("Description")
        except Exception as e:  # noqa: BLE001
            log("etagpair names", e)
    jams = [{"section": names.get(pid, pid), "speed": round(spd, 0)} for spd, pid in worst[:5]]
    return {"label": "TDX", "bikes": bikes, "roads": roads, "jams": jams, "roadTime": live.get("UpdateTime")}


# ---------- 第二階段：PTT（curl_cffi 模擬瀏覽器） ----------
PTT_BOARDS = ["Gossiping", "Lifeismoney", "e-shopping", "MakeUp", "BeautySalon", "Tech_Job", "home-sale", "movie"]


def p_ptt():
    try:
        from curl_cffi import requests as cffi
    except ImportError:
        raise RuntimeError("curl_cffi not installed")
    sess = cffi.Session(impersonate="chrome")
    sess.cookies.set("over18", "1", domain="www.ptt.cc")
    items = []
    for board in PTT_BOARDS:
        try:
            html = sess.get(f"https://www.ptt.cc/bbs/{board}/index.html", timeout=20).text
            if "r-ent" not in html:
                raise RuntimeError("blocked or empty")
            for ent in re.findall(r'<div class="r-ent">(.*?)</div>\s*</div>', html, re.S):
                nrec = re.search(r'<div class="nrec">(?:<span class="hl f\d">)?([^<]*)', ent)
                t = re.search(r'<div class="title">\s*<a href="([^"]+)">([^<]+)</a>', ent)
                if not t:
                    continue
                push_raw = (nrec.group(1) if nrec else "").strip()
                push = 100 if push_raw == "爆" else (num(push_raw) or 0) if not push_raw.startswith("X") else 0
                title = t.group(2).strip()
                if push >= 30 and not title.startswith("[公告]"):
                    items.append({"board": board, "title": title, "push": int(push), "url": "https://www.ptt.cc" + t.group(1)})
            time.sleep(0.6)
        except Exception as e:  # noqa: BLE001
            log("ptt", board, e)
    if not items:
        raise RuntimeError("ptt: nothing fetched (blocked?)")
    items.sort(key=lambda x: -x["push"])
    return {"label": "推文 ≥30", "items": items[:20]}


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
GEO_CITIES = {"Taipei": {"label": "台北", "bbox": [121.40, 24.95, 121.70, 25.22]},
              "Taichung": {"label": "台中", "bbox": [120.50, 24.05, 120.80, 24.32]}}
GEO_STATIC_PATH = DATA / "geo_static.json"
GEO_PATH = DATA / "geo.json"


def _in_bbox(lon, lat, b):
    return lon is not None and lat is not None and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]


def _geo_static():
    """靜態表（停車場座標、YouBike 站點、國道 ETag 路段幾何、台北 VD 位置）每天更新一次。"""
    st = {}
    if GEO_STATIC_PATH.exists():
        try:
            st = json.loads(GEO_STATIC_PATH.read_text(encoding="utf-8"))
            t = datetime.fromisoformat(st.get("fetchedAt", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
            if NOW - t < timedelta(hours=24) and st.get("carparks") and st.get("bikes"):
                return st
        except Exception:
            st = {}
    out = {"fetchedAt": NOW_ISO, "carparks": {}, "bikes": {}, "vd": {}, "etag": []}
    for city in GEO_CITIES:
        try:
            cps = tdx(f"v1:Parking/OffStreet/CarPark/City/{city}").get("CarParks", [])
            out["carparks"][city] = {c["CarParkID"]: [round(c["CarParkPosition"]["PositionLon"], 5), round(c["CarParkPosition"]["PositionLat"], 5),
                                                      (c.get("CarParkName") or {}).get("Zh_tw", "")] for c in cps if c.get("CarParkPosition", {}).get("PositionLat")}
        except Exception as e:  # noqa: BLE001
            log("geo carpark static", city, e); GEO_ERRS.append(f"geo carpark static {city}: " + safe_err(e))
        try:
            sts = tdx(f"Bike/Station/City/{city}")
            out["bikes"][city] = {b["StationUID"]: [round(b["StationPosition"]["PositionLon"], 5), round(b["StationPosition"]["PositionLat"], 5),
                                                    (b.get("StationName") or {}).get("Zh_tw", "").replace("YouBike2.0_", ""), b.get("BikesCapacity") or 0]
                                  for b in sts if b.get("StationPosition", {}).get("PositionLat")}
        except Exception as e:  # noqa: BLE001
            log("geo bike static", city, e); GEO_ERRS.append(f"geo bike static {city}: " + safe_err(e))
    try:
        vds = tdx("Road/Traffic/VD/City/Taipei").get("VDs", [])
        out["vd"]["Taipei"] = {v["VDID"]: [round(v["PositionLon"], 5), round(v["PositionLat"], 5), v.get("RoadName", "")] for v in vds if v.get("PositionLat")}
    except Exception as e:  # noqa: BLE001
        log("geo vd static", e); GEO_ERRS.append("geo vd static: " + safe_err(e))
    try:
        for ep in tdx("Road/Traffic/ETagPair/Freeway").get("ETagPairs", []):
            g = ep.get("Geometry") or ""
            pts = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", g)
            if pts:
                out["etag"].append([ep["ETagPairID"], ep.get("Description", ""), [[round(float(a), 4), round(float(b), 4)] for a, b in pts[::max(1, len(pts) // 12)]]])
    except Exception as e:  # noqa: BLE001
        log("geo etag static", e); GEO_ERRS.append("geo etag static: " + safe_err(e))
    if out["carparks"] and out["bikes"]:
        write_json(GEO_STATIC_PATH, out, separators=(",", ":"))
    return out


GEO_ERRS = []


def p_geo():
    GEO_ERRS.clear()
    st = _geo_static()
    geo = {"generatedAt": NOW_ISO, "cities": {}}
    # 停車場
    for city, meta in GEO_CITIES.items():
        c = {"parking": [], "bikes": [], "speed": [], "freeway": []}
        try:
            for r in tdx(f"v1:Parking/OffStreet/ParkingAvailability/City/{city}").get("ParkingAvailabilities", []):
                pos = st["carparks"].get(city, {}).get(r.get("CarParkID"))
                if not pos:
                    continue
                total, avail = r.get("TotalSpaces"), r.get("AvailableSpaces")
                car = next((a for a in r.get("Availabilities") or [] if a.get("SpaceType") == 1), None)
                if car and car.get("NumberOfSpaces"):
                    total, avail = car["NumberOfSpaces"], car.get("AvailableSpaces")
                if not total or avail is None or avail < 0 or total < 20:
                    continue
                c["parking"].append([pos[0], pos[1], int(avail), int(total), pos[2][:18]])
        except Exception as e:  # noqa: BLE001
            log("geo parking", city, e); GEO_ERRS.append(f"geo parking {city}: " + safe_err(e))
        try:
            for r in tdx(f"Bike/Availability/City/{city}"):
                pos = st["bikes"].get(city, {}).get(r.get("StationUID"))
                if pos and r.get("ServiceStatus", 1) == 1:
                    c["bikes"].append([pos[0], pos[1], int(r.get("AvailableRentBikes") or 0), int(pos[3] or 0), pos[2][:14]])
        except Exception as e:  # noqa: BLE001
            log("geo bikes", city, e); GEO_ERRS.append(f"geo bikes {city}: " + safe_err(e))
        geo["cities"][city] = c
    # 台北市區 VD 車速
    try:
        for v in tdx("Road/Traffic/Live/VD/City/Taipei").get("VDLives", []):
            pos = st["vd"].get("Taipei", {}).get(v.get("VDID"))
            if not pos:
                continue
            sp = [ln.get("Speed") for lf in v.get("LinkFlows") or [] for ln in lf.get("Lanes") or [] if (ln.get("Speed") or 0) > 0]
            if sp:
                geo["cities"]["Taipei"]["speed"].append([pos[0], pos[1], round(sum(sp) / len(sp)), pos[2][:10]])
    except Exception as e:  # noqa: BLE001
        log("geo vd live", e); GEO_ERRS.append("geo vd live: " + safe_err(e))
    # 國道 ETag 路段車速（畫線）
    try:
        live = {pr["ETagPairID"]: next((f["SpaceMeanSpeed"] for f in pr.get("Flows", []) if f.get("VehicleType") == 31 and (f.get("SpaceMeanSpeed") or 0) > 0), None)
                for pr in tdx("Road/Traffic/Live/ETag/Freeway").get("ETagPairLives", [])}
        for pid, desc, pts in st.get("etag", []):
            spd = live.get(pid)
            if spd is None:
                continue
            for city, meta in GEO_CITIES.items():
                if any(_in_bbox(x, y, meta["bbox"]) for x, y in pts):
                    geo["cities"][city]["freeway"].append([pts, round(spd), desc[:16]])
    except Exception as e:  # noqa: BLE001
        log("geo etag live", e); GEO_ERRS.append("geo etag live: " + safe_err(e))
    write_json(GEO_PATH, geo, separators=(",", ":"))
    summary = {city: {k: len(v) for k, v in c.items()} for city, c in geo["cities"].items()}
    if not any(sum(v.values()) for v in summary.values()):
        raise RuntimeError(f"geo: nothing errs={GEO_ERRS[:6]} (static: carparks={ {k: len(v) for k, v in st.get('carparks', {}).items()} } bikes={ {k: len(v) for k, v in st.get('bikes', {}).items()} } vd={len(st.get('vd', {}).get('Taipei', {}))} etag={len(st.get('etag', []))})")
    return {"label": "TDX", "counts": summary, "errs": GEO_ERRS[:12]}

# ---------- run ----------
run("pulse", p_pulse)
run("taiex", p_taiex)
run("tw_market", p_tw_market, keep_if_fresh_hours=0.5)
run("tw_stocks", p_tw_stocks)
run("fx", p_fx_any)
run("poly", p_poly)
run("tech", p_tech)
run("trends", p_trends)
run("luxury", p_luxury, keep_if_fresh_hours=3)
run("commodities", p_commodities, keep_if_fresh_hours=3)
run("revenue", p_revenue, keep_if_fresh_hours=20)
run("media", p_media, keep_if_fresh_hours=6)
# run("reddit", p_reddit, keep_if_fresh_hours=1)  # 改用 PTT；有金鑰再開
run("lyst", p_lyst, keep_if_fresh_hours=24 * 6)
run("macro", p_macro, keep_if_fresh_hours=6)
run("weather", p_weather)
run("tw_pulse", p_tw_pulse)
run("geo", p_geo)
run("ptt", p_ptt, keep_if_fresh_hours=0.5)
run("tiktok", p_tiktok, keep_if_fresh_hours=20)

DATA.mkdir(exist_ok=True)
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
