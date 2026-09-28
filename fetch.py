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
    """Append (date, value) to a series; replace if same date; cap 400."""
    if value is None or date is None:
        return
    series = HISTORY.setdefault(group, {}).setdefault(key, [])
    if series and series[-1][0] == date:
        series[-1][1] = value
    else:
        series.append([date, value])
        if len(series) > 400:
            del series[: len(series) - 400]


def run(pid: str, fn, keep_if_fresh_hours: float = 0):
    """Run one panel fetcher. keep_if_fresh_hours>0 skips re-fetch when the
    previous file is newer than that (for daily/weekly sources)."""
    prev = load_prev(pid)
    if keep_if_fresh_hours and prev and prev.get("updatedAt") and not prev.get("error"):
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
        (PANELS / f"{pid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"[{pid}] ok {time.time() - t0:.1f}s")
    except Exception as e:  # noqa: BLE001
        log(f"[{pid}] FAIL {type(e).__name__}: {e}")
        if prev:
            prev["error"] = f"{NOW_ISO} {type(e).__name__}: {str(e)[:120]}"
            RESULTS[pid] = prev
            (PANELS / f"{pid}.json").write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            RESULTS[pid] = {"updatedAt": None, "error": f"{NOW_ISO} {type(e).__name__}: {str(e)[:120]}", "items": []}


# ---------- Yahoo Finance (batch quotes + 1 month series) ----------
_yahoo_cache: dict[str, dict] = {}


def yahoo_chart(sym: str, rng="1mo", interval="1d"):
    if sym in _yahoo_cache:
        return _yahoo_cache[sym]
    last_err = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            j = gjson(f"https://{host}/v8/finance/chart/{sym}", params={"range": rng, "interval": interval, "includePrePost": "false"})
            res = j["chart"]["result"][0]
            meta = res["meta"]
            closes = res["indicators"]["quote"][0].get("close") or []
            ts = res.get("timestamp") or []
            series = [(datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), c) for t, c in zip(ts, closes) if c is not None]
            price = meta.get("regularMarketPrice")
            prev = None
            if series:
                if price is None:
                    price = series[-1][1]
                # 前收：若最新價就是最後一根收盤，前收是倒數第二根；否則最後一根就是前收
                if len(series) >= 2 and abs(series[-1][1] - price) / max(abs(price), 1e-9) < 1e-4:
                    prev = series[-2][1]
                else:
                    prev = series[-1][1]
            else:
                prev = meta.get("previousClose")
            chg_pct = (price - prev) / prev * 100 if price is not None and prev else None
            out = {"price": price, "chg_pct": chg_pct, "ccy": meta.get("currency"), "series": series,
                   "asOf": series[-1][0] if series else None}
            _yahoo_cache[sym] = out
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"yahoo {sym}: {last_err}")


# ---------- panels ----------
def p_taiex():
    rows = gjson("https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK")
    if not rows:
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
        "history": HISTORY["taiex"]["TAIEX"][-60:],
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
                      "spark": [v for _, v in HISTORY["tw_stocks"][code][-30:]]})
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
                          "spark": [v for _, v in HISTORY["fx"][code][-30:]]})
    order = ["USD", "EUR", "JPY", "CNY"]
    if items:
        items.sort(key=lambda x: order.index(x["code"]))
        return {"label": "台銀即期", "items": items}
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
            hist_put("fx", code, d, v)
        items.append({"code": code, "name": name, "buy": q["price"], "sell": None, "chg_pct": q["chg_pct"],
                      "spark": [v for _, v in q["series"][-30:]]})
    if not items:
        raise RuntimeError("yahoo fx failed")
    return {"label": "Yahoo 中價（台銀被擋時）", "items": items}


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
       ("HG=F", "銅", "USD/lb"), ("ALI=F", "鋁", "USD/t"), ("GC=F", "黃金", "USD/oz")]
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
                         "ccy": "USD", "series": obs, "asOf": obs[-1][0]}
                except Exception as e2:  # noqa: BLE001
                    log("cmdty fred", sym, e2)
        if not q:
            continue
        as_of = max(as_of or "", q["asOf"] or "")
        for d, v in q["series"]:
            hist_put("commodities", sym, d, v)
        items.append({"sym": sym, "name": name, "unit": unit, "price": q["price"], "chg_pct": q["chg_pct"],
                      "spark": [v for _, v in q["series"][-30:]]})
    shipping = []
    try:
        html = get("https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry").text
        m = re.search(r"\$([\d,]{4,6})\s*per\s*40ft", html)
        pct = re.search(r"(decreased|increased|fell|rose|down|up)\s+(?:by\s+)?(\d+(?:\.\d+)?)%", html, re.I)
        dt = re.search(r"(\d{1,2}\s+\w+\s+20\d\d)", html)
        if m:
            val = num(m.group(1))
            chg = None
            if pct:
                chg = num(pct.group(2)) * (-1 if pct.group(1).lower() in ("decreased", "fell", "down") else 1)
            hist_put("shipping", "WCI", TODAY_TPE.isoformat(), val)
            shipping.append({"name": "Drewry WCI", "value": val, "unit": "USD/40ft", "date": dt.group(1) if dt else "",
                             "chg_pct": chg, "spark": [v for _, v in HISTORY["shipping"]["WCI"][-20:]]})
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
                           "mom": (last["revenue"] - prevm["revenue"]) / prevm["revenue"] * 100,
                           "yoy": (last["revenue"] - yoy["revenue"]) / yoy["revenue"] * 100 if yoy else None,
                           "period": f"{last['revenue_year']}/{last['revenue_month']:02d}",
                           "spark": [r["revenue"] / 1000 for r in rows[-13:]]}
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
    prev_brands = [b.get("brand") for b in prev.get("brands", [])] if prev.get("quarter") != quarter else None
    out_b = []
    for i, b in enumerate(brands):
        move = 0
        if prev_brands and b in prev_brands:
            move = prev_brands.index(b) - i
        out_b.append({"brand": b, "move": move})
    return {"quarter": quarter, "brands": out_b, "products": [{"name": p, "move": 0} for p in products]}


def p_macro():
    """主計總處 SDMX；失敗就保留手動維護的 data/panels/macro.json。"""
    prev = load_prev("macro") or {"items": []}
    items = {it["label"]: it for it in prev.get("items", [])}
    try:
        # CPI 總指數年增率（A030101015：消費者物價基本分類指數）
        url = ("https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sdmx/A030101015/1.1.M"
               f"&startTime={TODAY_TPE.year - 1}-M01&endTime={TODAY_TPE.year}-M12")
        j = gjson(url, headers={"Accept": "application/json"})
        # 結構依主計總處 SDMX-JSON；解析失敗即拋出，保留舊值
        obs = j["data"]["dataSets"][0]["series"]
        first = next(iter(obs.values()))["observations"]
        vals = [v[0] for _, v in sorted(first.items(), key=lambda kv: int(kv[0]))]
        if len(vals) >= 13:
            cur, last = vals[-1], vals[-13]
            yoy = (cur - last) / last * 100
            items["CPI 年增"] = {"label": "CPI 年增", "value": f"{yoy:.2f}%", "period": "最新月", "prev": items.get("CPI 年增", {}).get("value"), "tone": ""}
    except Exception as e:  # noqa: BLE001
        log("dgbas sdmx", e)
    if not items:
        raise RuntimeError("no macro items; edit data/panels/macro.json by hand")
    return {"items": list(items.values()), "note": prev.get("note", "")}



# ---------- pulse: 24 小時會動的東西（盤中 5 分鐘線） ----------
PULSE = [("^TWII", "台股加權", "TWD"), ("BTC-USD", "Bitcoin", "USD"), ("ETH-USD", "Ethereum", "USD"),
         ("ES=F", "S&P 500 期貨", "USD"), ("NQ=F", "Nasdaq 期貨", "USD"), ("DX-Y.NYB", "美元指數", "")]


def yahoo_intraday(sym):
    last_err = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            j = gjson(f"https://{host}/v8/finance/chart/{sym}", params={"range": "1d", "interval": "5m", "includePrePost": "false"})
            res = j["chart"]["result"][0]
            meta = res["meta"]
            closes = res["indicators"]["quote"][0].get("close") or []
            ts = res.get("timestamp") or []
            series = [(t, c) for t, c in zip(ts, closes) if c is not None]
            price = meta.get("regularMarketPrice") or (series[-1][1] if series else None)
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            return {"price": price, "prev": prev, "chg_pct": (price - prev) / prev * 100 if price and prev else None,
                    "series": [c for _, c in series][-80:], "asOf": series[-1][0] if series else meta.get("regularMarketTime"),
                    "state": meta.get("marketState")}
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"yahoo intraday {sym}: {last_err}")


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

# ---------- run ----------
run("pulse", p_pulse)
run("taiex", p_taiex)
run("tw_stocks", p_tw_stocks)
run("fx", p_fx_any)
run("poly", p_poly)
run("tech", p_tech)
run("trends", p_trends)
run("luxury", p_luxury, keep_if_fresh_hours=3)
run("commodities", p_commodities, keep_if_fresh_hours=3)
run("revenue", p_revenue, keep_if_fresh_hours=20)
run("media", p_media, keep_if_fresh_hours=6)
run("reddit", p_reddit, keep_if_fresh_hours=1)
run("lyst", p_lyst, keep_if_fresh_hours=24 * 6)
run("macro", p_macro, keep_if_fresh_hours=20)

DATA.mkdir(exist_ok=True)
HIST_PATH.write_text(json.dumps(HISTORY, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(DATA / "all.json").write_text(json.dumps({"generatedAt": NOW_ISO, "panels": RESULTS}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
ok = [k for k, v in RESULTS.items() if not v.get("error")]
bad = [k for k, v in RESULTS.items() if v.get("error")]
log(f"done ok={ok} failed={bad}")
