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
import zipfile
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
PANEL_CAP = {"voice": 280, "pop": 150, "house": 290, "jobs": 150, "mops": 120, "geo": 420, "news": 300, "aiwire": 120, "devpulse": 200, "social": 150, "radar": 150, "cofacts": 90, "threads_g": 300, "mood": 200, "macro": 200, "supply": 200, "tw_pulse": 150, "revenue": 200}
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


TW_WATCH = [("2912", "統一超", "通路"), ("1216", "統一", "食品"), ("2903", "遠百", "百貨"), ("2727", "王品", "餐飲"),
            ("2723", "美食-KY", "餐飲"), ("2707", "晶華", "飯店"), ("1476", "儒鴻", "機能服飾"), ("1477", "聚陽", "機能服飾")]
# 觀察清單：(區塊, 代號, 名稱, 小分類)；債券 ETF 在櫃買
TW_LIST = [("權值", c, n, "") for c, n in [("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"), ("2382", "廣達"), ("2308", "台達電"), ("3711", "日月光投控"),
                                          ("2881", "富邦金"), ("2882", "國泰金"), ("2412", "中華電"), ("2603", "長榮")]] + \
          [("ETF", "0050", "元大台灣50", "市值型"), ("ETF", "006208", "富邦台50", "市值型"), ("ETF", "0056", "元大高股息", "高股息"), ("ETF", "00878", "國泰永續高股息", "高股息"),
           ("ETF", "00919", "群益台灣精選高息", "高股息"), ("ETF", "00929", "復華台灣科技優息", "高股息"), ("ETF", "00940", "元大台灣價值高息", "高股息"),
           ("ETF", "00631L", "元大台灣50正2", "槓桿反向"), ("ETF", "00675L", "富邦臺灣加權正2", "槓桿反向"), ("ETF", "00632R", "元大台灣50反1", "槓桿反向"),
           ("ETF", "00679B", "元大美債20年", "債券"), ("ETF", "00687B", "國泰20年美債", "債券"), ("ETF", "00937B", "群益ESG投等債20+", "債券")] + \
          [("消費", c, n, g) for c, n, g in TW_WATCH]
TPEX_DAILY = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def _tpex_rows():
    for k in range(3):  # 櫃買偶爾傳到一半斷線
        try:
            return gjson(TPEX_DAILY, timeout=60)
        except Exception as e:  # noqa: BLE001
            log("tpex daily", k, e); time.sleep(2)
    return []


def p_tw_stocks():
    rows = gjson("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    by = {r["Code"]: ("tse", r) for r in rows}
    trows = _tpex_rows()
    for r in trows:
        c = str(r.get("SecuritiesCompanyCode") or "").strip()
        if c and c not in by:
            by[c] = ("otc", r)
    items, date, otc = [], None, set()
    for sec, code, name, sub in TW_LIST:
        mk, r = by.get(code, (None, None))
        if not r:
            continue
        if mk == "tse":
            d, px, ch, val = roc_to_iso(r["Date"]), num(r["ClosingPrice"]), num(r["Change"]), num(r.get("TradeValue"))
        else:
            otc.add(code)
            d, px, ch, val = roc_to_iso(r.get("Date")), num(r.get("Close")), num(r.get("Change")), num(r.get("TransactionAmount"))
        date = max(date or d, d)
        hist_put("tw_stocks", code, d, px)
        items.append({"code": code, "name": name, "group": sub, "sec": sec, "price": px, "chg": ch, "value": val, "date": d,
                      "spark": hist_get("tw_stocks", code)})
    if not items:
        raise RuntimeError("no watch rows")
    # 主動式 ETF（代號結尾 A）：成交值前 10
    act = []
    for c, (mk, r) in by.items():
        if not re.match(r"^\d{5}A$", c):
            continue
        if mk == "tse":
            px, ch, val, nm = num(r["ClosingPrice"]), num(r["Change"]), num(r.get("TradeValue")), r.get("Name")
        else:
            px, ch, val, nm = num(r.get("Close")), num(r.get("Change")), num(r.get("TransactionAmount")), r.get("CompanyName")
        if px:
            act.append({"code": c, "name": (nm or "")[:12], "price": px, "chg": ch, "value": val, "mk": mk})
    act.sort(key=lambda x: -(x["value"] or 0))
    MIS_DIAG.clear()
    try:
        qs = twse_mis_quotes([it["code"] for it in items], otc=otc)
        live = [it for it in items if _mis_override(it, qs.get(it["code"]), date)]
        if live:
            date = max(it["date"] for it in live)
    except Exception as e:  # noqa: BLE001
        log("tw_stocks mis", e); MIS_DIAG.append("err " + safe_err(e)[:80])
    return {"date": date, "items": items, "active": act[:12], "activeN": len(act), "mis": MIS_DIAG[:6]}


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


POLY_TOPICS = [("Fed／利率", "fed-rates", 3), ("經濟／通膨", "economy", 2), ("經濟／通膨", "inflation", 2), ("台海／中國", "china", 3),
               ("台灣選舉", "taiwan", 3), ("地緣政治", "geopolitics", 3), ("地緣政治", "middle-east", 2), ("地緣政治", "ukraine", 2),
               ("AI／科技", "ai", 3), ("AI／科技", "big-tech", 2), ("美國期中選舉", "midterms", 3), ("加密貨幣", "crypto", 2)]
POLY_NOISE = re.compile(r"\bon (January|February|March|April|May|June|July|August|September|October|November|December) \d|\d+\s*-\s*(January|February|March|April|May|June|July|August|September|October|November|December)? ?\d+\?|bankruptcy|aliens|Millennium Prize", re.I)


# ---------- 2026 五都選戰：Polymarket 機率（只看不押；台灣下注選舉違法）＋ 新聞聲量 ＋ 手動民調 ----------
ELECT_DAY = "2026-11-28"
ELECT_CITIES = [("台北", "taipei-mayor-election-winner-20260813125857100"), ("新北", "new-taipei-mayor-election-winner-20260813125857200"),
                ("台中", "taichung-mayor-election-winner-20260813125857400"), ("台南", "tainan-mayor-election-winner-20260813125857500"),
                ("高雄", "kaohsiung-mayor-election-winner-20260813125857600")]
ELECT_NAMES = {"Chiang Wan-an": ("蔣萬安", "國民黨"), "Puma Shen": ("沈伯洋", "民進黨"), "Lee Shu-chuan": ("李四川", "國民黨"),
               "Su Chiao-hui": ("蘇巧慧", "民進黨"), "Johnny Chiang": ("江啟臣", "國民黨"), "Ho Hsin-chun": ("何欣純", "民進黨"),
               "Hsieh Lung-chieh": ("謝龍介", "國民黨"), "Chen Ting-fei": ("陳亭妃", "民進黨"), "Lin Yi-feng": ("林義豐", ""),
               "Ko Chih-en": ("柯志恩", "國民黨"), "Lai Jui-lung": ("賴瑞隆", "民進黨"), "Huang Kuo-chang": ("黃國昌", "民眾黨")}
ELECT_MENTIONS = DATA / "elect_mentions.json"
# 政見主題：看候選人在哪些議題上被報導，再用勝率加權，推估接下來四年政策和預算的方向
ELECT_TOPICS = [("居住／社宅", r"社宅|社會住宅|住宅|租金|房價|囤房|都更|危老|打房"), ("托育／生育", r"托育|育兒|生育|少子|幼兒園|托嬰|育嬰|產後|兒童"),
                ("長照／高齡", r"長照|高齡|銀髮|老人|失智|敬老|照顧"), ("交通建設", r"捷運|輕軌|交通|公車|道路|鐵路|停車|機場|高鐵|塞車"),
                ("觀光／城市活動", r"觀光|旅遊|旅宿|城市行銷|演唱會|大型活動|夜市|跨年|燈會"), ("產業／AI 科技", r"產業|AI|人工智慧|半導體|科技|招商|園區|新創|台積電"),
                ("能源／環境", r"淨零|減碳|能源|電力|綠能|空污|空氣|環保|垃圾|缺水|水情|核電"), ("治安／防詐", r"治安|詐騙|防詐|毒品|警察|酒駕"),
                ("教育／青年", r"教育|學校|青年|學生|營養午餐|課後|租屋補貼"), ("運動／文化", r"運動|體育|巨蛋|球場|文化|藝文|博物館"),
                ("醫療／健康", r"醫療|醫院|健保|健康|急診"), ("補助／發錢", r"普發|補助|津貼|發現金|減稅|退稅|紅包")]


def p_elect():
    errs, today = [], TODAY_TPE.isoformat()
    # 1) 新聞聲量：每輪把看到的標題記下來（依日期去重），算每位候選人每天被提到幾次
    titles = []
    nw = RESULTS.get("news") or {}
    titles += [x.get("title") or "" for x in (nw.get("tw") or [])]
    for v in ((RESULTS.get("localnews") or {}).get("counties") or {}).values():
        titles += [x.get("title") or "" for x in (v if isinstance(v, list) else [])]
    titles += [x.get("title") or "" for x in ((RESULTS.get("ptt") or {}).get("items") or [])]
    try:
        store = json.loads(ELECT_MENTIONS.read_text(encoding="utf-8")) if ELECT_MENTIONS.exists() else {}
    except Exception:  # noqa: BLE001
        store = {}
    zh_names = [v[0] for v in ELECT_NAMES.values()]
    def add(d, nm, t):
        lst = store.setdefault(d, {}).setdefault(nm, [])
        h = t[:80]
        if h not in lst:
            lst.append(h)
    for t in set(titles):
        for nm in zh_names:
            if nm in t:
                add(today, nm, t)
    # 每 3 小時用 Google News 搜一次每位候選人，補足情報站本身沒收到的報導（依刊出日期歸檔）
    last = store.get("_gn_at") or ""
    if not last or (NOW - datetime.fromisoformat(last)).total_seconds() > 3 * 3600:
        for nm in zh_names:
            try:
                for it in _gnews_full(f'"{nm}"') or []:
                    d = datetime.fromisoformat(it["at"].replace("Z", "+00:00")).astimezone(TPE).date().isoformat()
                    if nm in it["title"] and d >= (TODAY_TPE - timedelta(days=20)).isoformat():
                        add(d, nm, it["title"])
                time.sleep(1)
            except Exception as e:  # noqa: BLE001
                errs.append(f"新聞 {nm}: {safe_err(e)}")
        store["_gn_at"] = NOW.isoformat()
    cut = (TODAY_TPE - timedelta(days=21)).isoformat()
    store = {d: v for d, v in store.items() if d.startswith("_") or d >= cut}
    write_json(ELECT_MENTIONS, store, separators=(",", ":"))
    days7 = [(TODAY_TPE - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    days14 = [(TODAY_TPE - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    # 2) 手動民調（ops/polls.json，說「更新民調」時由 Claude 填，附出處）
    try:
        polls = json.loads((ROOT / "ops" / "polls.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        polls = {}
    # 3) 預測市場
    cities = []
    for city, slug in ELECT_CITIES:
        try:
            evs = gjson("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=30)
            ev = evs[0] if isinstance(evs, list) and evs else {}
            cands = []
            for m in ev.get("markets") or []:
                en = m.get("groupItemTitle") or ""
                if en not in ELECT_NAMES:
                    continue
                try:
                    p = float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100
                except Exception:  # noqa: BLE001
                    continue
                if p < 1.5:
                    continue
                zh, party = ELECT_NAMES[en]
                key = f"{city}:{zh}"
                hist = HISTORY.get("elect", {}).get(key) or []
                if len(hist) < 5:  # 第一次：用 Polymarket 公開歷史價格回補開盤以來的日線
                    try:
                        tok = json.loads(m.get("clobTokenIds") or "[]")[0]
                        ph = gjson("https://clob.polymarket.com/prices-history", params={"market": tok, "interval": "max", "fidelity": "1440"}, timeout=30)
                        for pt in ph.get("history") or []:
                            d = datetime.fromtimestamp(int(pt["t"]), TPE).date().isoformat()
                            hist_put("elect", key, d, round(float(pt["p"]) * 100, 1))
                        time.sleep(0.3)
                    except Exception as e:  # noqa: BLE001
                        errs.append(f"{city} 回補: {safe_err(e)}")
                hist_put("elect", key, today, round(p, 1))
                h = HISTORY.get("elect", {}).get(key) or []
                prev7 = next((v for d, v in reversed(h) if d <= (TODAY_TPE - timedelta(days=7)).isoformat()), None)
                tc = {}
                for d in days14:
                    for t in store.get(d, {}).get(zh, []):
                        for tn, pat in ELECT_TOPICS:
                            if re.search(pat, t):
                                tc[tn] = tc.get(tn, 0) + 1
                cands.append({"name": zh, "party": party, "p": round(p, 1), "d7": round(p - prev7, 1) if prev7 is not None else None,
                              "spark": [v for _, v in h[-45:]], "news": [len(store.get(d, {}).get(zh, [])) for d in days7],
                              "n14": sum(len(store.get(d, {}).get(zh, [])) for d in days14),
                              "topics": sorted(tc.items(), key=lambda kv: -kv[1])[:4]})
            cands.sort(key=lambda c: -c["p"])
            vol, v24 = float(ev.get("volume") or 0), float(ev.get("volume24hr") or 0)
            rel = "可信" if vol >= 300000 else "普通" if vol >= 50000 and v24 >= 1000 else "偏弱" if vol >= 10000 else "幾乎沒交易"
            cities.append({"city": city, "cands": cands[:3], "vol": round(vol), "vol24": round(v24), "rel": rel,
                           "url": f"https://polymarket.com/event/{slug}", "polls": (polls.get(city) or [])[:3]})
            time.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{city}: {safe_err(e)}")
    if not cities:
        raise RuntimeError(f"elect: nothing {errs[:2]}")
    # 政策風向：每位候選人的議題占比 × 勝率，五都加總；兩大陣營都在講的議題另外標出（不管誰贏都會推）
    wind = {}
    for c in cities:
        for x in c["cands"]:
            tot = sum(v for _, v in x["topics"]) or 0
            for tn, v in x["topics"]:
                w = wind.setdefault(tn, {"score": 0.0, "cities": set(), "both": set(), "_side": {}})
                w["score"] += (x["p"] / 100) * (v / tot)
                w["cities"].add(c["city"])
                w["_side"].setdefault(c["city"], set()).add(x["party"] or x["name"])
    out_wind = []
    for tn, w in wind.items():
        both = sorted(ci for ci, sides in w["_side"].items() if len(sides) >= 2)
        out_wind.append({"topic": tn, "score": round(w["score"], 2), "cities": sorted(w["cities"]), "both": both})
    out_wind.sort(key=lambda r: -r["score"])
    return {"day": ELECT_DAY, "cities": cities, "wind": out_wind[:8], "days": days7, "pollsAt": polls.get("_updated"), "errs": errs[:5],
            "src": "Polymarket 公開報價（只看不押）＋ 情報站收進來的新聞與 PTT 標題 ＋ 手動整理民調"}


def p_poly():
    groups, seen, flat = {}, set(), []
    for label, tag, k in POLY_TOPICS:
        try:
            evs = gjson("https://gamma-api.polymarket.com/events", params={"tag_slug": tag, "active": "true", "closed": "false",
                                                                          "order": "volume24hr", "ascending": "false", "limit": 12}, timeout=30)
        except Exception as e:  # noqa: BLE001
            log("poly", tag, e); continue
        got = 0
        for ev in evs:
            title = ev.get("title") or ""
            if ev.get("id") in seen or SPORTY.search(title) or POLY_NOISE.search(title):
                continue
            outs = []
            for m in ev.get("markets") or []:
                if m.get("closed") or m.get("active") is False:
                    continue
                try:
                    yes = float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100
                except Exception:  # noqa: BLE001
                    continue
                if yes < 0.5 or yes > 99.5:
                    continue
                d1 = m.get("oneDayPriceChange")
                outs.append({"name": (m.get("groupItemTitle") or ("Yes" if len(ev.get("markets") or []) == 1 else m.get("question") or ""))[:40],
                             "yes": round(yes, 1), "d1": round(d1 * 100, 1) if isinstance(d1, (int, float)) else None})
            if not outs:
                continue
            outs.sort(key=lambda o: -o["yes"])
            seen.add(ev.get("id"))
            e = {"title": title[:110], "slug": ev.get("slug") or "", "vol24h": round(ev.get("volume24hr") or 0), "end": (ev.get("endDate") or "")[:10],
                 "multi": len(ev.get("markets") or []) > 1, "outs": outs[:3]}
            groups.setdefault(label, []).append(e)
            top = outs[0]
            flat.append({"question": title + (f" — {top['name']}" if e["multi"] else ""), "slug": e["slug"], "yes": top["yes"], "d1": top["d1"],
                         "vol24h": e["vol24h"], "end": e["end"], "topic": label})
            got += 1
            if got >= k:
                break
        time.sleep(0.3)
    if not flat:
        raise RuntimeError("poly: nothing")
    order = []
    for label, _, _ in POLY_TOPICS:
        if label in groups and label not in order:
            order.append(label)
    return {"groups": [{"topic": t, "events": groups[t]} for t in order], "items": sorted(flat, key=lambda x: -(x["vol24h"] or 0))}


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


# ---------- OSS 雷達：GitHub Trending（舊 repo 突然爆紅）＋ Simon Willison ＋ HF 熱門 Spaces ＋ 盯梢 repo 新版本 ----------
OSS_WATCH = [  # (owner/repo, 顯示名) — 名單 2026-10-09 定
    ("Comfy-Org/ComfyUI", "ComfyUI"),
    ("nexu-io/open-design", "Open Design"),
    ("remotion-dev/remotion", "Remotion"),
    ("gitroomhq/postiz-app", "Postiz"),
    ("storytold/photocraft", "PhotoCraft"),
]
OSS_SPACE_SKIP = re.compile(r"uncensored|nsfw|nude|porn|hentai", re.I)


def _strip_tags(s: str) -> str:
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def _gh_trending(since="daily", limit=10):
    page = get("https://github.com/trending", params={"since": since}, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"}).text
    out = []
    for blk in re.findall(r"<article[^>]*Box-row[^>]*>(.*?)</article>", page, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"/]+/[^"/]+)"', blk, re.S)
        if not m:
            continue
        name = m.group(1).strip()
        desc = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S)
        lang = re.search(r'itemprop="programmingLanguage"[^>]*>(.*?)<', blk, re.S)
        stars = re.search(r'href="/' + re.escape(name) + r'/stargazers"[^>]*>(.*?)</a>', blk, re.S)
        today = re.search(r'([\d,]+)\s+stars?\s+(today|this week|this month)', _strip_tags(blk))
        out.append({"name": name, "url": "https://github.com/" + name,
                    "desc": _strip_tags(desc.group(1))[:110] if desc else "",
                    "lang": _strip_tags(lang.group(1)) if lang else None,
                    "stars": num(_strip_tags(stars.group(1)).replace(",", "")) if stars else None,
                    "today": num(today.group(1).replace(",", "")) if today else None})
        if len(out) >= limit:
            break
    if not out:
        raise RuntimeError("trending: 頁面結構變了，沒解析到 repo")
    return out


def _atom(url, source, limit=8):
    raw = get(url, headers={"User-Agent": "Mozilla/5.0"}).content
    root = ET.fromstring(raw.lstrip(b"\xef\xbb\xbf \r\n\t"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = ""
        for l in e.findall("a:link", ns):
            if l.get("rel") in (None, "alternate"):
                link = l.get("href") or ""; break
        at = (e.findtext("a:published", default="", namespaces=ns) or e.findtext("a:updated", default="", namespaces=ns) or "").strip()
        if title:
            out.append({"source": source, "title": title[:100], "url": link, "at": at[:19] + "Z" if len(at) >= 19 else at})
        if len(out) >= limit:
            break
    return out


def p_oss():
    errs, out = [], {}
    gh_hdr = {"Accept": "application/vnd.github+json", **({"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]} if os.environ.get("GITHUB_TOKEN") else {})}
    try:
        out["trending"] = _gh_trending("daily", 10)
    except Exception as e:  # noqa: BLE001
        errs.append("GitHub Trending: " + safe_err(e))
    # Gemini 一句話：只替「沒看過的 repo」補，一輪最多一次呼叫；看過的從上一輪快取帶出，不重複花額度
    # ZH_VER 改版時舊快取作廢、全部重寫；寫得爛的（套話、重複詞）不進快取，下一輪再試一次，第二次就收
    ZH_VER = "v2"
    prev = load_prev("oss") or {}
    same = prev.get("zh_ver") == ZH_VER
    cache = dict(prev.get("zh_cache") or {}) if same else {}
    tries = dict(prev.get("zh_tries") or {}) if same else {}
    todo = [r for r in out.get("trending") or [] if r["name"] not in cache]
    if todo and GEMINI_KEY:
        lines = "\n".join(f"- {r['name']}｜{r.get('lang') or '—'}｜{r.get('desc') or '（沒有描述）'}" for r in todo)
        prompt = f"""下面是今天 GitHub Trending 上的 repo（名稱｜語言｜英文描述）。替每一個寫一句繁體中文、台灣用語的說明，讓不寫程式的設計師一看就懂它是什麼、能拿來幹嘛。

寫法：
- 15 到 25 字，直接講它做什麼，動詞開頭或直接講它是什麼
- 有知名產品可以比，就說「像 Photoshop 的開源版」這種講法，比抽象描述好懂
- 同一個詞在一句裡只能出現一次
- 不要用：「專為…設計」「一款」「打造」「賦能」「極致」「實用的」「強大的」，也不要每句都用「工具」結尾
- 描述太少看不出用途，就寫「描述太少，看不出用途」，不要猜

好的寫法：
- 把 PS5 遊戲搬到電腦上跑
- 讓 AI 寫程式助手畫出好看的架構圖
- 像 Photoshop 的開源版，用 Rust 從零重寫
- 讓 Claude 跨對話記住你講過的事

不要這樣寫：
- 專為藝術家設計的創作引擎（套話，沒講它做什麼）
- 有圖形介面的除錯與除錯輔助軟體（同一個詞重複）
- 分享給 AI 助理使用的實用工作技能（空泛）

輸出 JSON：{{"items": [{{"name": "owner/repo", "zh": "一句話"}}]}}

{lines}"""
        bad = re.compile(r"專為|一款|打造|賦能|極致|實用的|強大的")
        try:
            js, _model = _gemini_json(prompt)
            for it in (js.get("items") or []):
                nm, zh = (it.get("name") or "").strip(), (it.get("zh") or "").strip().rstrip("。")
                if not (nm and zh):
                    continue
                poor = bool(bad.search(zh) or re.search(r"([\u4e00-\u9fff]{2,}).*\1", zh))
                if poor and tries.get(nm, 0) < 1:
                    tries[nm] = tries.get(nm, 0) + 1  # 這輪先不收，下一輪重寫
                    continue
                cache[nm] = "" if poor else zh[:40]  # 重寫還是爛就放棄，頁面改顯示英文描述，也不再花額度重試
                tries.pop(nm, None)
        except Exception as e:  # noqa: BLE001
            errs.append("Gemini 摘要: " + safe_err(e))
    for r in out.get("trending") or []:
        if cache.get(r["name"]):
            r["zh"] = cache[r["name"]]
    out["zh_ver"] = ZH_VER
    out["zh_tries"] = dict(list(tries.items())[-100:])
    out["zh_cache"] = dict(list(cache.items())[-300:])
    try:
        out["simonw"] = _atom("https://simonwillison.net/atom/everything/", "Simon Willison", 8)
    except Exception as e:  # noqa: BLE001
        errs.append("Simon Willison: " + safe_err(e))
    try:
        sp = gjson("https://huggingface.co/api/spaces", params={"sort": "trendingScore", "limit": 20})
        out["spaces"] = [{"id": s.get("id"), "likes": s.get("likes"), "sdk": s.get("sdk"), "url": "https://huggingface.co/spaces/" + (s.get("id") or "")}
                         for s in sp if s.get("id") and not OSS_SPACE_SKIP.search(s["id"])][:8]
    except Exception as e:  # noqa: BLE001
        errs.append("HF Spaces: " + safe_err(e))
    rel = []
    for repo, label in OSS_WATCH:
        try:
            rs = gjson(f"https://api.github.com/repos/{repo}/releases", params={"per_page": 1}, headers=gh_hdr)
            if rs:
                r = rs[0]
                rel.append({"repo": repo, "label": label, "tag": (r.get("tag_name") or "")[:40], "title": (r.get("name") or r.get("tag_name") or "")[:90],
                            "url": r.get("html_url"), "at": r.get("published_at") or ""})
            else:  # 沒發 Release 的專案退回看最新 tag
                ts = gjson(f"https://api.github.com/repos/{repo}/tags", params={"per_page": 1}, headers=gh_hdr)
                if ts:
                    rel.append({"repo": repo, "label": label, "tag": ts[0].get("name", "")[:40], "title": ts[0].get("name", "")[:90],
                                "url": f"https://github.com/{repo}/releases/tag/{ts[0].get('name', '')}", "at": ""})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{label}: " + safe_err(e))
    rel.sort(key=lambda x: x.get("at") or "", reverse=True)
    out["releases"] = rel
    if not any(out.get(k) for k in ("trending", "simonw", "spaces", "releases")):
        raise RuntimeError(f"oss: nothing {errs[:3]}")
    out["errs"] = errs[:6]
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
    # 3) 全體上市櫃月營收依產業加總：哪個產業的營收在長
    agg, period, errs = {}, None, []
    for mk, url in (("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"), ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O")):
        try:
            for r in gjson(url):
                ind = (r.get("產業別") or "").strip() or "其他"
                cur, ly, pm = num(r.get("營業收入-當月營收")), num(r.get("營業收入-去年當月營收")), num(r.get("營業收入-上月營收"))
                if not cur or cur <= 0 or not ly or ly <= 0 or re.search(r"金融|保險|證券", ind):  # 金融業營收含投資損益、會出現負值，不適合比
                    continue
                period = period or roc_ym(r.get("資料年月"))
                a = agg.setdefault(ind, {"name": ind, "cur": 0.0, "ly": 0.0, "pm": 0.0, "n": 0, "top": []})
                a["cur"] += cur; a["ly"] += ly; a["n"] += 1
                if pm and pm > 0:
                    a["pm"] += pm; a["cur_pm"] = a.get("cur_pm", 0) + cur
                if True:
                    a["top"].append((cur - ly, r.get("公司名稱") or r.get("公司簡稱") or r.get("公司代號"), round((cur - ly) / ly * 100, 1)))
        except Exception as e:  # noqa: BLE001
            errs.append(f"{mk}全體營收: {safe_err(e)}")
    inds = []
    for a in agg.values():
        if a["n"] < 3 or not a["ly"]:
            continue
        a["top"].sort(key=lambda t: -t[0])
        inds.append({"name": a["name"], "n": a["n"], "rev": round(a["cur"]), "yoy": round((a["cur"] - a["ly"]) / a["ly"] * 100, 1),
                     "mom": round((a.get("cur_pm", 0) - a["pm"]) / a["pm"] * 100, 1) if a["pm"] else None,
                     "lead": [{"name": str(t[1])[:10], "yoy": t[2]} for t in a["top"][:2]]})
    inds.sort(key=lambda x: -x["yoy"])
    if not items and not inds:
        raise RuntimeError("no revenue rows")
    order = list(REV_WATCH)
    return {"items": sorted(items.values(), key=lambda x: order.index(x["code"])), "inds": inds, "ind_period": period, "errs": errs}


# ---------- ETF 存股族：集保戶股權分散表（每週）裡 ETF 的持有人數 ----------
def p_etfholders():
    import csv, io
    raw = get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=90).content.decode("utf-8-sig", "replace")
    rows = list(csv.reader(io.StringIO(raw)))
    if len(rows) < 100:
        raise RuntimeError("tdcc 1-5: too few rows")
    hdr = rows[0]
    ci = {k: i for i, k in enumerate(hdr)}
    i_d, i_c, i_l, i_n = (ci.get("資料日期", 0), ci.get("證券代號", 1), ci.get("持股分級", 2), ci.get("人數", 3))
    date, etf, allh = None, {}, 0
    for r in rows[1:]:
        if len(r) <= i_n or r[i_l].strip() != "17":  # 17 = 合計
            continue
        date = date or r[i_d].strip()
        code, n = r[i_c].strip(), num(r[i_n]) or 0
        allh += n
        if code.startswith("00"):
            etf[code] = n
    if not etf:
        raise RuntimeError("tdcc 1-5: no ETF rows")
    d = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if date and len(date) == 8 else TODAY_TPE.isoformat()
    names = {}
    for url, kc, kn in (("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", "Name"),
                        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "SecuritiesCompanyCode", "CompanyName")):
        try:
            for x in gjson(url):
                if str(x.get(kc, "")).startswith("00"):
                    names[x[kc]] = (x.get(kn) or "").strip()
        except Exception as e:  # noqa: BLE001
            log("etf names", url, e)
    total = sum(etf.values())
    prev_total = next((v for dd, v in reversed(HISTORY.get("etf", {}).get("holders_total", [])) if dd < d), None)
    hist_put("etf", "holders_total", d, total)
    hist_put("etf", "share_pct", d, round(total / allh * 100, 2) if allh else None)
    top = sorted(etf.items(), key=lambda kv: -kv[1])[:40]
    items = []
    for code, n in top:
        pv = next((v for dd, v in reversed(HISTORY.get("etf", {}).get("h:" + code, [])) if dd < d), None)
        hist_put("etf", "h:" + code, d, n)
        items.append({"code": code, "name": names.get(code, code)[:14], "n": n, "chg": (n - pv) if pv else None,
                      "chg_pct": round((n - pv) / pv * 100, 2) if pv else None})
    return {"date": d, "total": total, "chg": (total - prev_total) if prev_total else None, "n_etf": len(etf),
            "share_pct": round(total / allh * 100, 2) if allh else None, "spark": hist_get("etf", "holders_total", 26),
            "items": items, "src": "集保結算所 集保戶股權分散表（每週）；人數為各 ETF 持有人數加總（同一人持有多檔會重複計算）"}


# ---------- 稅籍新開家數：財政部全國營業（稅籍）登記，細類行業代碼（每天更新，只含營業中） ----------
TAXREG_CODES = DATA / "taxreg_codes.json"
# 消費與生活服務類（行業代碼前兩碼）：零售、電商、住宿餐飲、廣告設計攝影、教育、照顧、藝文運動娛樂、個人服務
TAXREG_CONSUMER = {"47", "48", "55", "56", "73", "74", "76", "85", "87", "88", "90", "91", "93", "96"}


def p_taxreg():
    """各細類行業近 6 個月新設家數年增。資料只含營業中的店、最近 1–2 個月登錄還沒補齊，
    兩者都會讓原始年增偏低，所以每個行業都除以「全體」的比值，看的是相對全體的成長。"""
    import zipfile, io, csv as _csv
    from collections import defaultdict
    raw = get("https://eip.fia.gov.tw/data/BGMOPEN1.zip", timeout=300).content
    z = zipfile.ZipFile(io.BytesIO(raw))
    m0 = TODAY_TPE.replace(day=1)
    def mback(k):
        y, m = m0.year, m0.month - k
        while m <= 0:
            y, m = y - 1, m + 12
        return f"{y}-{m:02d}"
    w6, w3 = [mback(k) for k in range(6, 0, -1)], [mback(k) for k in range(3, 0, -1)]
    l6, l3 = [mback(k + 12) for k in range(6, 0, -1)], [mback(k + 12) for k in range(3, 0, -1)]
    keep = set(mback(k) for k in range(1, 26))
    cnt = defaultdict(lambda: defaultdict(int))  # code -> ym -> n（主＋副行業都算，同一家同一碼只算一次）
    names, total, asof, rows = {}, defaultdict(int), "", 0
    with z.open(z.infolist()[0]) as fh:
        rd = _csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
        hdr = next(rd)
        ci = {h.strip(): i for i, h in enumerate(hdr)}
        idate = ci["設立日期"]
        pairs = [(ci[c], ci[n]) for c, n in (("行業代號", "名稱"), ("行業代號1", "名稱1"), ("行業代號2", "名稱2"), ("行業代號3", "名稱3")) if c in ci and n in ci]
        for row in rd:
            if len(row) <= idate:
                continue
            d = row[idate].strip()
            if not rows and not d.isdigit():  # 第二行是資料日期，例如 07-OCT-26
                asof = row[0].strip()
                continue
            rows += 1
            if len(d) < 6 or not d.isdigit():
                continue
            ym = f"{int(d[:-4]) + 1911}-{d[-4:-2]}"
            if ym not in keep:
                continue
            total[ym] += 1
            seen = set()
            for ic, inn in pairs:
                if ic < len(row):
                    c = row[ic].strip()
                    if c and c not in seen:
                        seen.add(c)
                        cnt[c][ym] += 1
                        if c not in names and inn < len(row):
                            names[c] = row[inn].strip()
    if rows < 500000:
        raise RuntimeError(f"taxreg: only {rows} rows")
    s = lambda dct, ms: sum(dct.get(m, 0) for m in ms)  # noqa: E731
    N6, L6, N3, L3 = s(total, w6), s(total, l6), s(total, w3), s(total, l3)
    base6, base3 = (N6 / L6 if L6 else 1), (N3 / L3 if L3 else 1)
    codes, items = {}, []
    for c, dct in cnt.items():
        n6, ly6, n3, ly3 = s(dct, w6), s(dct, l6), s(dct, w3), s(dct, l3)
        codes[c] = [names.get(c, ""), n6, ly6, n3, ly3]
        if n6 < 30:
            continue
        it = {"code": c, "name": names.get(c, "")[:16], "n6": n6, "ly6": ly6, "n3": n3,
              "spark": [dct.get(mback(k), 0) for k in range(13, 0, -1)]}
        cons = c[:2] in TAXREG_CONSUMER
        if cons:
            it["cons"] = True
        if ly6 < max(8, n6 * 0.15):  # 去年同期幾乎沒有：多半是新設的行業代碼，年增沒有意義
            it["new"] = True
        else:
            it["yoy"] = round(((n6 / ly6) / base6 - 1) * 100)
        items.append(it)
    write_json(TAXREG_CODES, {"at": NOW_ISO, "asof": asof, "w6": [w6[0], w6[-1]], "base6": round(base6, 3), "codes": codes}, separators=(",", ":"))
    grown = sorted([x for x in items if "yoy" in x and x["ly6"] >= 15 and x.get("cons")], key=lambda x: -x["yoy"])
    hist_put("taxreg", "n6", TODAY_TPE.isoformat(), N6)
    me = taxreg_supply(r"視覺傳達|專門設計|廣告服務|廣告代理|室內設計")  # 同業：廣告、設計
    return {"asof": asof, "rows": rows, "win": [w6[0], w6[-1]], "n6": N6, "ly6": L6, "raw_yoy": round((base6 - 1) * 100, 1),
            "monthly": [[mback(k), total.get(mback(k), 0)] for k in range(25, 0, -1)],
            "up": grown[:15], "down": grown[::-1][:10], "new": sorted([x for x in items if x.get("new") and x.get("cons")], key=lambda x: -x["n6"])[:8],
            "big": sorted(items, key=lambda x: -x["n6"])[:12], "me": me,
            "src": "財政部 全國營業（稅籍）登記資料集（只含營業中）；年增已除以全體比值，校正倒店與登錄延遲；排行只列消費與生活服務類"}


def taxreg_supply(pattern, codes=None):
    """把趨勢關鍵字對應到稅籍細類（用行業名稱比對），回傳供給面的新開家數與相對年增。"""
    if not pattern:
        return None
    try:
        if codes is None:
            codes = json.loads(TAXREG_CODES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    base, cs = codes.get("base6") or 1, codes.get("codes") or {}
    hit = [(c, v) for c, v in cs.items() if re.search(pattern, v[0])]
    if not hit:
        return None
    n6 = sum(v[1] for _, v in hit)
    old = [(c, v) for c, v in hit if v[2] >= max(8, v[1] * 0.15)]  # 年增只用去年就有的代碼，新代碼會灌水
    n6o, ly6 = sum(v[1] for _, v in old), sum(v[2] for _, v in old)
    out = {"n6": n6, "ly6": ly6, "codes": [v[0][:14] for _, v in sorted(hit, key=lambda kv: -kv[1][1])[:3]], "n_codes": len(hit),
           "win": codes.get("w6")}
    if ly6 >= 10:
        out["yoy"] = round(((n6o / ly6) / base - 1) * 100)
    return out

# ---------- 政策與民意：行政院公報「法規草案預告」＋ JOIN「提點子」連署（政府開放資料，授權可再利用） ----------
POL_TOPICS = [
    ("消費與食品", r"食品|飲料|餐飲|零售|消費|化粧品|化妝品|標示|廣告|電商|網購|網路購物|菸|酒|商品|價格|外送"),
    ("健康與照護", r"醫療|藥|健康|長照|長期照顧|照護|醫美|保健|健保|醫院|護理|心理|身心|失智"),
    ("寵物與動物", r"寵物|動物|犬|貓|動保|飼主"),
    ("居住與不動產", r"住宅|房屋|租賃|建築|社宅|社會住宅|都市|不動產|房價|包租|代管"),
    ("數位與 AI", r"數位|資訊|個資|個人資料|資安|網路|人工智慧|\bAI\b|電信|平臺|平台|演算法|電子"),
    ("金融與支付", r"金融|銀行|保險|支付|證券|虛擬資產|電子票證|信用|投資"),
    ("交通與移動", r"交通|車輛|汽車|機車|道路|捷運|鐵路|航空|停車|自行車|駕駛"),
    ("觀光與文化", r"觀光|旅館|民宿|旅行|文化|藝文|運動|體育|展演|博物館"),
    ("教育與勞動", r"教育|學校|補習|學生|勞工|勞動|工時|薪資|就業|托育|育兒|兒少|幼兒"),
    ("能源與環境", r"能源|電力|環境|減碳|碳|回收|廢棄物|空氣|水資源|再生能源|氣候|污染|汙染|塑膠|容器|包材|消防|原子能|核"),
    ("稅務與財政", r"稅|預算|財政|特別條例|補助|國債|公債"),
    ("司法與治安", r"法院|刑法|刑事|檢察|治安|詐欺|詐騙|毒品|監獄|犯罪|警察|槍砲"),
]
POL_CONSUMER = {"消費與食品", "健康與照護", "寵物與動物", "居住與不動產", "數位與 AI", "觀光與文化"}
GAZ_DRAFTS = DATA / "gazette_drafts.json"


def _pol_topic(text):
    for nm, pat in POL_TOPICS:
        if re.search(pat, text or ""):
            return nm
    return "其他"


def _roc_cn_date(s):
    m = re.search(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", s or "")
    return f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def p_policy():
    import xml.etree.ElementTree as ET
    errs, today = [], TODAY_TPE.isoformat()
    # 1) 公報：每天只給「最新一期」，所以每輪都把草案預告存起來，累積成清單
    try:
        store = json.loads(GAZ_DRAFTS.read_text(encoding="utf-8")) if GAZ_DRAFTS.exists() else {}
    except Exception:  # noqa: BLE001
        store = {}
    try:
        root = ET.fromstring(get("https://gazette.nat.gov.tw/egFront/OpenData/downloadXML.jsp", timeout=90).content)
        for rec in root.findall("Record"):
            g = lambda k: (rec.findtext(k) or "").strip()  # noqa: E731
            if "草案" not in g("Doc_Style_SName") or "預告" not in g("Doc_Style_SName"):
                continue
            mid = g("MetaId")
            title = re.sub(r"^.{0,20}?公告：", "", g("Title"))
            txt = " ".join([title, g("ThemeSubject")])
            store[mid] = {"title": title[:90], "gov": g("PubGovName") or g("PubGov"), "under": g("UndertakeGov"),
                          "pub": _roc_cn_date(g("Date_Published")), "due": _roc_cn_date(g("Comment_Deadline")),
                          "kw": g("Keyword")[:60], "topic": _pol_topic(txt), "url": g("GazetteHTML")}
    except Exception as e:  # noqa: BLE001
        errs.append(f"公報: {safe_err(e)}")
    cut = (TODAY_TPE - timedelta(days=120)).isoformat()
    store = {k: v for k, v in store.items() if (v.get("pub") or today) >= cut}
    write_json(GAZ_DRAFTS, store, separators=(",", ":"))
    drafts = sorted(store.values(), key=lambda x: x.get("pub") or "", reverse=True)
    open_ = [d for d in drafts if (d.get("due") or "") >= today]
    d30 = [d for d in drafts if (d.get("pub") or "") >= (TODAY_TPE - timedelta(days=30)).isoformat()]
    tcount = {}
    for d in d30:
        tcount[d["topic"]] = tcount.get(d["topic"], 0) + 1
    # 2) JOIN 提點子：今年的提議與附議數；存每天附議數，算 7 天增加
    ideas = []
    try:
        arr = gjson(f"https://join.gov.tw/toOpenData/v2/ey/idea?year={TODAY_TPE.year}", timeout=180)
        if TODAY_TPE.month <= 2:  # 年初也看去年底的
            try:
                arr += gjson(f"https://join.gov.tw/toOpenData/v2/ey/idea?year={TODAY_TPE.year - 1}", timeout=180)
            except Exception:  # noqa: BLE001
                pass
        for x in arr:
            sup, th = int(num(x.get("附議數量")) or 0), int(num(x.get("附議門檻")) or 0)
            pub = (x.get("publishDate") or "")[:10]
            if not pub:
                continue
            url = x.get("網址") or ""
            key = url.rsplit("/", 1)[-1][:12]
            ideas.append({"k": key, "title": (x.get("標題") or "")[:70], "sup": sup, "th": th, "pub": pub, "url": url,
                          "topic": _pol_topic((x.get("標題") or "") + " " + (x.get("提議內容") or "")[:300])})
    except Exception as e:  # noqa: BLE001
        errs.append(f"提點子: {safe_err(e)}")
    hot = []
    if ideas:
        d60 = (TODAY_TPE - timedelta(days=60)).isoformat()
        live = [i for i in ideas if i["pub"] >= d60 and i["sup"] > 0]
        for i in sorted(live, key=lambda i: -i["sup"])[:40]:
            old = next((v for d, v in reversed(HISTORY.get("join", {}).get(i["k"], [])) if d <= (TODAY_TPE - timedelta(days=7)).isoformat()), None)
            hist_put("join", i["k"], today, i["sup"])
            i["chg7"] = (i["sup"] - old) if old is not None else None
        passed = [i for i in ideas if i["th"] and i["sup"] >= i["th"] and i["pub"] >= (TODAY_TPE - timedelta(days=120)).isoformat()]
        hot = sorted(live, key=lambda i: -(i.get("chg7") if i.get("chg7") is not None else i["sup"]))[:10]
    else:
        passed = []
    n30 = sum(1 for i in ideas if i["pub"] >= (TODAY_TPE - timedelta(days=30)).isoformat())
    itopic = {}
    for i in ideas:
        if i["pub"] >= (TODAY_TPE - timedelta(days=30)).isoformat():
            itopic[i["topic"]] = itopic.get(i["topic"], 0) + 1
    # 3) 立法院法律案（OpenFun LYAPI，資料 CC-BY-4.0）：依「最新進度日期」排序，抓近 45 天有動的
    bills = []
    try:
        c45 = (TODAY_TPE - timedelta(days=75)).isoformat()
        for page in range(1, 25):
            js = gjson("https://ly.govapi.tw/v2/bills", params={"議案類別": "法律案", "limit": "100", "page": str(page)}, timeout=60)
            got = js.get("bills") or []
            for b in got:
                d = b.get("最新進度日期") or ""
                if d < c45:
                    continue
                nm = re.sub(r"[，,]?請審議案。?$|案。$", "", b.get("議案名稱") or "").strip("「」 ")
                laws = " ".join(b.get("法律編號:str") or [])
                who = (b.get("提案單位/提案委員") or "").replace("本院委員", "")
                bills.append({"id": b.get("議案編號"), "title": nm[:80], "who": who[:24], "src": b.get("提案來源") or "",
                              "st": b.get("議案狀態") or "", "d": d, "topic": _pol_topic(nm + " " + laws),
                              "new": "草案" in nm and not re.search(r"修正|增訂|廢止|刪除|條文|併案|^報告", nm),
                              "url": b.get("url") or f"https://ppg.ly.gov.tw/ppg/bills/{b.get('議案編號')}/details"})
            if not got or (got[-1].get("最新進度日期") or "") < c45:
                break
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        errs.append(f"立法院: {safe_err(e)}")
    c30 = (TODAY_TPE - timedelta(days=60)).isoformat()  # 立法院有休會期，用 60 天才不會整段空掉
    b30 = [b for b in bills if b["d"] >= c30]
    btopic = {}
    for b in b30:
        btopic[b["topic"]] = btopic.get(b["topic"], 0) + 1
    third, seen3 = [], set()
    for b in sorted(bills, key=lambda b: b["d"], reverse=True):
        if "三讀" in b["st"] and b["title"] not in seen3:
            seen3.add(b["title"]); third.append(b)
    newlaw, seenn = [], set()
    for b in sorted(b30, key=lambda b: b["d"], reverse=True):  # 同一部新法常有好幾位委員各提一版，只留最新一筆
        if b["new"] and b["title"] not in seenn and b["title"] not in seen3:
            seenn.add(b["title"]); newlaw.append(b)
    bpick = sorted(sorted(newlaw, key=lambda b: b["d"], reverse=True), key=lambda b: b["topic"] not in POL_CONSUMER)[:8]
    if not drafts and not ideas and not bills:
        raise RuntimeError(f"policy: nothing {errs[:2]}")
    return {"drafts": drafts[:40], "open_n": len(open_), "d30_n": len(d30), "d_topics": sorted(tcount.items(), key=lambda kv: -kv[1]),
            "since": min((d.get("pub") for d in drafts if d.get("pub")), default=""),
            "ideas_hot": hot, "ideas_passed": sorted(passed, key=lambda i: i["pub"], reverse=True)[:8], "ideas_n30": n30,
            "i_topics": sorted(itopic.items(), key=lambda kv: -kv[1]), "consumer": sorted(POL_CONSUMER),
            "bills_n30": len(b30), "b_topics": sorted(btopic.items(), key=lambda kv: -kv[1]), "b_new": bpick,
            "b_newn": len(newlaw), "b_third": sorted(third, key=lambda b: b["d"], reverse=True)[:6],
            "src": "行政院公報資訊網 Open Data（法規命令草案預告）＋ 公共政策網路參與平臺「提點子」開放資料 ＋ 立法院議案（OpenFun LYAPI，CC-BY-4.0）", "errs": errs[:4]}


# ---------- 品牌與專利：智慧局商標申請、發明公開（政府開放資料 API） ----------
TIPO_TK = "43b47d07-4795-45d9-819a-9c71c72e4105"  # 智慧局在政府資料開放平臺公開的 API 金鑰
NICE = {3: "美妝保養", 5: "藥品保健", 9: "科技軟體", 10: "醫療器材", 14: "珠寶鐘錶", 16: "文具印刷", 18: "皮件包袋", 20: "家具",
        21: "居家廚具", 24: "寢具布品", 25: "服飾鞋帽", 28: "玩具運動", 29: "肉蛋乳品", 30: "烘焙咖啡茶", 31: "農產寵食", 32: "飲料",
        33: "酒", 35: "廣告零售", 36: "金融不動產", 41: "教育娛樂", 42: "科技服務", 43: "餐飲住宿", 44: "醫療美容"}
IPC_THEMES = [("AI", r"^G06N"), ("電商與商業模式", r"^G06Q"), ("醫療資訊", r"^G16H"), ("美妝保養", r"^A61Q|^A61K8"),
              ("保健食品與藥", r"^A61K(?!8)|^A61P|^A23L33"), ("食品飲料", r"^A23|^C12G|^A21"), ("醫療器材", r"^A61[BCFGHJMN]"),
              ("居家與家具", r"^A47"), ("個人用品", r"^A4[1-5]"), ("寵物與農業", r"^A01K|^A01"), ("運動與遊戲", r"^A63"),
              ("車輛與移動", r"^B60|^B62|^B64"), ("電池與能源", r"^H01M|^H02J|^Y02"), ("半導體", r"^H01L|^H10"), ("通訊", r"^H04")]
IPR_CONSUMER = {"美妝保養", "保健食品與藥", "食品飲料", "居家與家具", "個人用品", "寵物與農業", "運動與遊戲", "電商與商業模式", "AI", "醫療資訊"}


def _tipo(ep, **p):
    return gjson("https://cloud.tipo.gov.tw/S220/opdataapi/api/" + ep, params={"tk": TIPO_TK, "format": "json", **p}, timeout=180)


def _is_co(name):
    return bool(re.search(r"公司|有限|股份|集團|企業|商行|工作室|Inc|Ltd|LLC|Corp|GmbH|AG$|S\.A\.", name or ""))


def p_ipr():
    errs, out = [], {}
    # 商標：依申請號由新往回抓，用申請日期分桶；智慧局每月更新
    try:
        total = int(_tipo("TmarkAppl", top=1)["total-count"])
        recs, skip = [], total
        stop = (TODAY_TPE - timedelta(days=150)).strftime("%Y/%m/%d")
        for _ in range(10):  # 最多 5 萬筆；申請號大致照收件順序，整頁中位日期早於比較窗口就停
            skip = max(0, skip - 5000)
            page = _tipo("TmarkAppl", top=5000, skip=skip)["tmarkappl"]["tmarkcontent"]
            recs += page
            pd_ = sorted(r.get("appl-date") or "" for r in page if (r.get("appl-date") or "") >= "2000")
            if skip == 0 or (pd_ and pd_[len(pd_) // 2] < stop):
                break
            time.sleep(1)
        ds = sorted({(r.get("appl-date") or "")[:10] for r in recs if (r.get("appl-date") or "") >= "2020"})
        latest = ds[-1] if ds else ""
        # 最後一天可能還沒補齊：以「最新日期的前一個月底」為窗口終點，比較近 60 天與前 60 天
        end = datetime.strptime(latest, "%Y/%m/%d").date() if latest else TODAY_TPE
        w1 = (end - timedelta(days=59)).strftime("%Y/%m/%d"); w0 = (end - timedelta(days=119)).strftime("%Y/%m/%d")
        cur, prv, newest, seen = {}, {}, [], set()
        for r in recs:
            d = (r.get("appl-date") or "")[:10]
            if d < w0:
                continue
            cls = sorted({int(g.get("goodsclass-code") or 0) for g in (r.get("goodsclasses") or []) if str(g.get("goodsclass-code") or "").isdigit() and int(g.get("goodsclass-code")) <= 45})
            tgt = cur if d >= w1 else prv
            for c in cls:
                tgt[c] = tgt.get(c, 0) + 1
            apps = [a.get("chinese-name") or a.get("english-name") or "" for a in ((r.get("parties") or {}).get("applicants") or [])]
            co = next((a for a in apps if _is_co(a)), "")
            nm = (r.get("tmark-name") or "").strip()
            if d >= w1 and co and nm and not re.search(r"公司|標章", nm) and any(c in NICE for c in cls) and (nm, co) not in seen:
                seen.add((nm, co))
                newest.append({"name": nm[:30], "co": re.sub(r"\s+", "", co)[:24], "date": d.replace("/", "-"), "cls": [c for c in cls if c in NICE][:3]})
        rows = []
        for c, lab in NICE.items():
            a, b = cur.get(c, 0), prv.get(c, 0)
            rows.append({"cls": c, "name": lab, "n": a, "prev": b, "chg": round((a / b - 1) * 100) if b >= 20 else None})
        newest.sort(key=lambda x: x["date"], reverse=True)
        out["tm"] = {"latest": latest.replace("/", "-"), "win": [w1.replace("/", "-"), end.isoformat()], "rows": rows,
                     "total": sum(cur.values()), "new": newest[:60]}
    except Exception as e:  # noqa: BLE001
        errs.append(f"商標: {safe_err(e)}")
    # 發明公開：依申請號由新往回抓，用公開日分桶
    try:
        total = int(_tipo("PatentPub", top=1)["total-count"])
        recs, skip = [], total
        stop = (TODAY_TPE - timedelta(days=95)).strftime("%Y/%m/%d")
        for _ in range(12):  # 申請號順序和公開日不完全一致，整頁中位公開日早於比較窗口一段時間才停
            skip = max(0, skip - 5000)
            page = _tipo("PatentPub", top=5000, skip=skip)["tw-patent-pub"]["patentcontent"]
            recs += page
            nd = sorted(((r.get("publication-reference") or {}).get("notice-date") or "") for r in page)
            nd = [x for x in nd if x]
            if skip == 0 or (nd and nd[len(nd) // 2] < stop):
                break
            time.sleep(1)
        nds = sorted({((r.get("publication-reference") or {}).get("notice-date") or "") for r in recs} - {""})
        end = datetime.strptime(nds[-1], "%Y/%m/%d").date() if nds else TODAY_TPE
        w1 = (end - timedelta(days=29)).strftime("%Y/%m/%d"); w0 = (end - timedelta(days=59)).strftime("%Y/%m/%d")
        cur, prv, who = {}, {}, {}
        for r in recs:
            d = (r.get("publication-reference") or {}).get("notice-date") or ""
            if d < w0:
                continue
            ipcs = [(c.get("ipc-full") or "").replace(" ", "") for c in (r.get("classification-ipc") or [])]
            themes = {nm for nm, pat in IPC_THEMES if any(re.match(pat, i) for i in ipcs)}
            tgt = cur if d >= w1 else prv
            for t in themes:
                tgt[t] = tgt.get(t, 0) + 1
            if d >= w1:
                apps = [a.get("chinese-name") or a.get("english-name") or "" for a in ((r.get("parties") or {}).get("applicants") or [])]
                co = next((a for a in apps if _is_co(a)), "")
                for t in themes:
                    if co:
                        who.setdefault(t, {})
                        who[t][co] = who[t].get(co, 0) + 1
        rows = []
        for nm, _ in IPC_THEMES:
            a, b = cur.get(nm, 0), prv.get(nm, 0)
            top = sorted((who.get(nm) or {}).items(), key=lambda kv: -kv[1])[:3]
            rows.append({"name": nm, "n": a, "prev": b, "chg": round((a / b - 1) * 100) if b >= 15 else None,
                         "cons": nm in IPR_CONSUMER, "top": [[re.sub(r"\s+", "", k)[:20], v] for k, v in top]})
        out["pat"] = {"latest": nds[-1].replace("/", "-") if nds else "", "win": [w1.replace("/", "-"), end.isoformat()], "rows": rows,
                      "n": sum(1 for r in recs if ((r.get("publication-reference") or {}).get("notice-date") or "") >= w1)}
    except Exception as e:  # noqa: BLE001
        errs.append(f"專利: {safe_err(e)}")
    if not out:
        raise RuntimeError(f"ipr: nothing {errs[:2]}")
    return {**out, "src": "經濟部智慧財產局開放資料 API（商標註冊申請案、發明公開）", "errs": errs[:4]}

# ---------- 企業動向：誰要上市、誰易主、誰換跑道、誰要開法說會（證交所／櫃買／公開資訊觀測站，全部官方免費） ----------
CONSUMER_IND = r"食品|紡織|觀光|餐旅|貿易百貨|居家生活|生技醫療|文化創意|運動休閒|數位雲端|電子商務"


def _clean(s, n=120):
    import html as _h
    s = _h.unescape(str(s or "")).replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


IND_CODE = {"01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維", "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷",
            "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造", "15": "航運業", "16": "觀光餐旅",
            "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
            "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
            "30": "資訊服務業", "31": "其他電子業", "32": "文化創意業", "33": "農業科技業", "34": "電子商務", "35": "綠能環保",
            "36": "數位雲端", "37": "運動休閒", "38": "居家生活"}


def p_corp():
    errs, ind = [], {}
    for url in ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
                "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"):  # 上市、上櫃、興櫃基本資料（新股多半從興櫃來）
        for _att in range(2):  # 櫃買的大檔偶爾傳到一半斷線，重試一次
            try:
                for r in gjson(url, timeout=90):
                    c = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
                    k = str(r.get("產業別") or r.get("SecuritiesIndustryCode") or "").strip()
                    if c and k:
                        ind[c] = IND_CODE.get(k.zfill(2), "")
                break
            except Exception as e:  # noqa: BLE001
                if _att:
                    errs.append(f"產業對照: {safe_err(e)}")
    for url in ("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"):
        try:  # 基本資料沒抓到的，用月營收表的產業別補
            for r in gjson(url, timeout=60):
                c = str(r.get("公司代號") or "").strip()
                if c and not ind.get(c):
                    ind[c] = (r.get("產業別") or "").strip()
        except Exception as e:  # noqa: BLE001
            log("corp ind fill", e)
    today = TODAY_TPE.isoformat()
    ago = lambda d: (TODAY_TPE - timedelta(days=d)).isoformat()  # noqa: E731
    ahead = lambda d: (TODAY_TPE + timedelta(days=d)).isoformat()  # noqa: E731
    # 1) 公開申購（新股掛牌前的抽籤）：只留初上市／初上櫃，掛牌日在過去 45 天到未來
    ipo = []
    try:
        j = gjson("https://www.twse.com.tw/rwd/zh/announcement/publicForm?response=json", timeout=60)
        fi = {f.strip(): i for i, f in enumerate(j.get("fields") or [])}
        g = lambda row, k: str(row[fi[k]]).strip() if k in fi and fi[k] < len(row) else ""  # noqa: E731
        for row in j.get("data") or []:
            mk = g(row, "發行市場")
            if not re.search(r"初上市|初上櫃", mk):
                continue
            lst = roc_to_iso(g(row, "撥券日期(上市、上櫃日期)"))
            if not re.match(r"\d{4}-", lst) or lst < ago(45):
                continue
            code = g(row, "證券代號")
            price = num(g(row, "實際承銷價(元)")) or num(g(row, "承銷價(元)"))
            ipo.append({"code": code, "name": g(row, "證券名稱")[:8], "mk": "上市" if "上市" in mk else "上櫃",
                        "start": roc_to_iso(g(row, "申購開始日")), "end": roc_to_iso(g(row, "申購結束日")),
                        "draw": roc_to_iso(g(row, "抽籤日期")), "list": lst, "price": price,
                        "rate": num(g(row, "中籤率(%)")), "ind": ind.get(code, "")})
        ipo.sort(key=lambda x: x["list"])
    except Exception as e:  # noqa: BLE001
        errs.append(f"公開申購: {safe_err(e)}")
    # 2) 排隊申請上市／上櫃：近 120 天送件的
    queue = []
    try:  # 證交所這支的欄位名稱錯位一格，照位置讀：序號、代號、名稱、申請日、董事長、資本額、審議會、董事會、核准、上市日…
        for r in gjson("https://openapi.twse.com.tw/v1/company/applylistingLocal", timeout=60):
            v = [str(x or "").strip() for x in r.values()]
            if len(v) < 6 or not re.match(r"^\d{4}[A-Z]?$", v[1]):
                continue
            ad = roc_to_iso(v[3])
            if not re.match(r"\d{4}-", ad) or ad < ago(120):
                continue
            steps = sum(1 for x in v[6:10] if re.match(r"^\d{7}$", x))
            queue.append({"code": v[1], "name": v[2][:8], "mk": "上市", "apply": ad, "steps": steps,
                          "cap": num(v[5]), "uw": v[10][:6] if len(v) > 10 else "", "note": _clean(v[-1], 12), "ind": ind.get(v[1], "")})
    except Exception as e:  # noqa: BLE001
        errs.append(f"申請上市: {safe_err(e)}")
    try:
        for r in gjson("https://www.tpex.org.tw/openapi/v1/tpex_esb_applicant_companies", timeout=60):
            ad = str(r.get("Date") or "")
            ad = f"{ad[:4]}-{ad[4:6]}-{ad[6:8]}" if re.match(r"^\d{8}$", ad) else ""
            if not ad or ad < ago(120):
                continue
            code = str(r.get("SecuritiesCompanyCode") or "").strip()
            steps = sum(1 for k in ("TPExListingScreeningCommitteeDate", "TPExSanctionedDate", "TPExApprovedTradingDate", "ListingDate") if str(r.get(k) or "").strip())
            cap = num(r.get("CapitalWhileApplying"))
            queue.append({"code": code, "name": str(r.get("CompanyName") or "")[:8], "mk": "上櫃", "apply": ad, "steps": steps,
                          "cap": round(cap / 1000) if cap else None, "uw": str(r.get("LeadUnderwriter") or "")[:6], "note": "", "ind": ind.get(code, "")})
    except Exception as e:  # noqa: BLE001
        errs.append(f"申請上櫃: {safe_err(e)}")
    queue.sort(key=lambda x: x["apply"], reverse=True)
    # 3) 經營權異動（近一年）＋ 4) 營業範圍重大變更（最新一季）
    control, pivot = [], []
    for mk, url in (("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap24_L"), ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap24_O")):
        try:
            for r in gjson(url, timeout=60):
                code = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
                d = roc_to_iso(r.get("經營權異動日期"))
                if not re.match(r"\d{4}-", d) or d < ago(365):
                    continue
                desc = _clean(r.get("經營權異動說明"), 400)
                ent = r"[^，。、；「」（()\s]{2,24}?(?:集團|有限公司|株式會社|Ltd\.?|Inc\.?)"
                who = None
                for pat in (rf"予({ent})", rf"最大股東({ent})", rf"由({ent})", rf"({ent})(?:及[^，。]{{0,40}}?)?(?:等[^，。]{{0,6}}?)?公開收購",
                            r"^([A-Za-z][A-Za-z0-9&.,\s]{2,40}?(?:Ltd\.?|Inc\.?))"):
                    who = re.search(pat, desc)
                    if who:
                        break
                who = re.sub(r"(股份)?有限公司$", "", who.group(1)).strip() if who else ""
                how = "公開收購" if "公開收購" in desc else "股權轉讓" if re.search(r"轉讓|股權交割|取得.{0,10}股權|納入合併", desc) else \
                      "合併" if "合併" in desc and "合併財務" not in desc else "董事會改組" if re.search(r"改選|改派|解任|補選", desc) else ""
                control.append({"code": code, "name": str(r.get("公司名稱") or r.get("CompanyName") or "")[:8], "mk": mk, "date": d,
                                "who": who, "how": how, "desc": _clean(desc, 160), "ind": ind.get(code, "")})
        except Exception as e:  # noqa: BLE001
            errs.append(f"經營權{mk}: {safe_err(e)}")
    control.sort(key=lambda x: x["date"], reverse=True)
    for mk, url in (("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap25_L"), ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap25_O")):
        try:
            for r in gjson(url, timeout=60):
                code = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
                t = str(r.get("營業範圍重大變更說明") or "")
                tags = [lbl for pat, lbl in ((r"新增主要經營業務", "新業務過半"), (r"經營業務變更", "舊本業縮到兩成以下"),
                                             (r"處分不動產、廠房", "處分廠房"), (r"營建", "轉做營建"), (r"轉投資|金融資產", "轉投資")) if re.search(pat, t)]
                pivot.append({"code": code, "name": str(r.get("公司名稱") or r.get("CompanyName") or "")[:8], "mk": mk,
                              "q": f"{r.get('年度', '')}Q{r.get('季別', '')}", "tags": tags or [_clean(t, 30)], "ind": ind.get(code, "")})
        except Exception as e:  # noqa: BLE001
            errs.append(f"營業範圍{mk}: {safe_err(e)}")
    pivot.sort(key=lambda x: (x["q"], "新業務過半" in x["tags"]), reverse=True)
    # 5) 法說會：公開資訊觀測站 法人說明會一覽表（本月＋下月），留今天起 21 天內
    conf, seen = [], set()
    months = [TODAY_TPE.replace(day=1)]
    nm = (TODAY_TPE.replace(day=28) + timedelta(days=5)).replace(day=1)
    if TODAY_TPE.day >= 10:
        months.append(nm)
    import csv as _csv, io as _io
    for typek, mk in (("sii", "上市"), ("otc", "上櫃")):
        for m0 in months:
            try:
                r = S.get("https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1", timeout=60,
                          params={"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": typek,
                                  "year": str(m0.year - 1911), "month": f"{m0.month:02d}"})
                r.encoding = "utf-8"
                fn = re.search(r"name='filename' value='([^']+)'", r.text)
                if not fn:
                    if "查無" not in r.text:
                        errs.append(f"法說會{mk}{m0.month}月: 沒有下載檔名")
                    continue
                c = S.post("https://mopsov.twse.com.tw/server-java/t105sb02", timeout=60, data={"firstin": "true", "step": "10", "filename": fn.group(1)})
                raw = c.content
                try:
                    txt = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    txt = raw.decode("big5", errors="ignore")
                for row in _csv.DictReader(_io.StringIO(txt)):
                    row = {(k or "").strip(): v for k, v in row.items()}
                    code = str(row.get("公司代號") or "").strip()
                    dm = re.findall(r"\d{3}/\d{2}/\d{2}", str(row.get("召開法人說明會日期") or ""))
                    if not code or not dm:
                        continue
                    d0, d1 = roc_to_iso(dm[0]), roc_to_iso(dm[-1])
                    if d1 < today or d0 > ahead(21) or (code, d0) in seen:
                        continue
                    seen.add((code, d0))
                    summ = _clean(row.get("法人說明會擇要訊息"), 160)
                    routine = bool(re.search(r"受邀|邀請|參加.{0,20}(論壇|研討會|投資人會議|座談)", summ)) and len(summ) < 90
                    i_ = ind.get(code, "")
                    conf.append({"code": code, "name": _clean(row.get("公司名稱"), 8), "mk": mk, "date": max(d0, today) if d0 < today <= d1 else d0,
                                 "time": _clean(row.get("召開法人說明會時間"), 8), "place": _clean(row.get("召開法人說明會地點"), 24),
                                 "summary": summ, "ind": i_, "cons": bool(i_ and re.search(CONSUMER_IND, i_)), "routine": routine})
            except Exception as e:  # noqa: BLE001
                errs.append(f"法說會{mk}{m0.month}月: {safe_err(e)}")
    conf.sort(key=lambda x: (x["date"], not x["cons"]))
    if not (ipo or queue or control or conf):
        raise RuntimeError(f"corp: nothing {errs[:3]}")
    hist_put("corp", "queue", today, len(queue))
    return {"ipo": ipo[:20], "queue": queue[:40], "queue_n": len(queue), "control": control[:30], "control_n": len(control),
            "pivot": pivot[:20], "pivot_n": len(pivot), "conf": conf[:120], "conf_n": len(conf),
            "src": "證交所／櫃買中心 OpenAPI（公開申購、申請上市櫃、經營權及營業範圍異動專區）＋ 公開資訊觀測站 法人說明會一覽表",
            "errs": errs[:6]}


FASHION_TW = {  # 台灣時尚媒體官方來源（都經過實測：網站規則允許、從 GitHub 連得到）
    "美麗佳人": ("gnews", "https://www.marieclaire.com.tw/google-news.xml"),
    "VOGUE": ("rss", "https://www.vogue.com.tw/feed/rss"),
    "ELLE": ("rss", "https://www.elle.com/tw/rss/all.xml"),
    "BAZAAR": ("rss", "https://www.harpersbazaar.com/tw/rss/all.xml"),
    "COSMO": ("rss", "https://www.cosmopolitan.com/tw/rss/all.xml"),
    "Women's Health": ("rss", "https://www.womenshealthmag.com/tw/rss/all.xml"),
    "美人圈": ("rss", "https://www.beauty321.com/rss"),
    # GQ 官網擋機房主機（Cloudflare，台灣機房也一樣），改用 Google 新聞收錄的 GQ Taiwan 文章（標題、日期、連結）
    "GQ": ("rss", "https://news.google.com/rss/search?q=site:gq.com.tw&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
}
FASHION_RELAY: dict = {}
# 國際版（官方 RSS，GitHub 連得到）：只拿來算分類比例，不進「本週同框」熱詞
FASHION_INTL = {
    "VOGUE US": "https://www.vogue.com/feed/rss", "ELLE US": "https://www.elle.com/rss/all.xml",
    "BAZAAR US": "https://www.harpersbazaar.com/rss/all.xml", "COSMO US": "https://www.cosmopolitan.com/rss/all.xml",
    "Marie Claire US": "https://www.marieclaire.com/feeds/all", "GQ US": "https://www.gq.com/feed/rss",
    "Women's Health US": "https://www.womenshealthmag.com/rss/all.xml",
    "VOGUE UK": "https://www.vogue.co.uk/feed/rss", "Marie Claire UK": "https://www.marieclaire.co.uk/feeds/all",
}
FASHION_HEADS_INTL = DATA / "fashion_heads_intl.json"
# 統一分類：先看網址路徑／RSS 分類（各家編輯自己分的），都沒有才用標題關鍵字
FASHION_CATS = ["時尚", "美容", "生活", "娛樂", "感情", "星座", "文化", "健康"]
_FC_PATH = [("星座", r"astrolog|horoscope|zodiac|星座"), ("美容", r"beauty|hair|skin|makeup|fragrance|nail|body-care|groom|美容|保養|彩妝"),
            ("時尚", r"fashion|(?<!life)style|watch|jewel|\bbags?\b|shoe|runway|時尚|穿搭"), ("感情", r"love|relationship|sex|secret-talk|pleasure|dating|兩性|感情"),
            ("娛樂", r"entertain|celebrit|tvshow|movie|music|star|royal|名人|娛樂"), ("文化", r"culture|\barts?\b|exhibit|\bbooks?\b|文化|藝術"),
            ("健康", r"fitness|health|wellness|wellbeing|nutrition|weight|sport|健康|健身"), ("生活", r"life|living|travel|taste|food|home|design|whats-hot|event|shop|business|wedding|生活|旅遊|美食")]
_FC_KW = [("星座", r"星座|運勢|塔羅|水逆|上升|太陽星座"), ("美容", r"保養|彩妝|香水|香氛|髮|美甲|肌膚|皮膚|防曬|口紅|唇|粉底|醫美|妝|精華|乳液|面膜|抗老|毛孔"),
          ("時尚", r"穿搭|秀場|時裝|包款|包包|鞋|精品|聯名|腕錶|手錶|錶款|西裝|潮流|珠寶|大衣|洋裝|牛仔|單品|設計師|Chanel|Dior|Gucci|Prada|LV|Hermès|愛馬仕"),
          ("感情", r"戀愛|感情|分手|約會|婚姻|另一半|男友|女友|曖昧|渣|伴侶|老公|老婆|兩性"), ("娛樂", r"韓劇|日劇|電影|影集|演唱會|女星|男星|偶像|Netflix|劇|專輯|MV|綜藝|金鐘|金馬|女團|男團"),
          ("文化", r"展覽|藝術|美術館|博物館|書|作家|攝影展|建築"), ("健康", r"運動|健身|減重|減肥|睡眠|醫師|健康|飲食|瘦|脂肪|血糖|蛋白質|跑步")]


def _fashion_cat(url: str, rcats=(), title: str = "") -> str:
    from urllib.parse import urlparse, unquote
    path = unquote(urlparse(url or "").path.lower())
    segs = [x for x in path.strip("/").split("/") if x not in ("tw", "article", "")][:2]
    for txt in [" ".join(rcats or []), " ".join(segs)]:
        if not txt.strip():
            continue
        for cat, rx in _FC_PATH:
            if re.search(rx, txt, re.I):
                return cat
    for cat, rx in _FC_KW:
        if re.search(rx, title or "", re.I):
            return cat
    return "生活"
FASHION_HEADS = DATA / "fashion_heads.json"  # 標題語感庫：滾動 60 天，寫文案時拿來校準語感
FASHION_AD = re.compile(r"星座|運勢|塔羅|開箱|懶人包|贈票|優惠|折扣|週年慶|會員日|抽獎|團購|特價|限時|報名|滿額|贈品|試用|好禮|下殺|即日起|快閃店|聯名款開賣")
FASHION_STOP = {"vogue", "elle", "bazaar", "cosmo", "cosmopolitan", "marie claire", "hot spot", "the", "and", "of", "with", "for", "in", "to", "a",
                "ig", "netflix", "youtube", "tw", "taiwan", "new", "mv", "vs", "ft", "x", "diy", "ai", "app", "led", "spa", "ok", "nt", "top"}
FASHION_GENERIC = re.compile(r"[的了是在也和與及就都很最更再又還被把讓為對從到這那個些麼何月日年天款位種件大小新上下中前後一二三四五六七八九十多]"
                             r"|打造|推出|開幕|登場|進駐|曝光|回歸|首度|限定|必看|推薦|分享|揭曉|公開|看懂|入手|教學|整理|盤點|攻略|秘密|關鍵|方法|技巧|原因|亮點|一次|懶人|穿搭|造型|單品|系列|新品|全新|最新|正式|品牌|設計|女星|男星|明星|網友|今年|秋冬|春夏|台灣|台北|臺北|臺灣|時尚|美麗|質感|靈感|風格|話題|朋友|日常|生活")


def _unesc(t: str) -> str:
    for _ in range(3):  # 來源有重複編碼（&amp;amp;）的情況
        u = html_mod.unescape(t)
        if u == t:
            break
        t = u
    return t


def _fashion_feed(kind, url):
    root = ET.fromstring(get(url).content.lstrip(b"\xef\xbb\xbf \r\n\t"))
    out = []
    if kind == "gnews":
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "n": "http://www.google.com/schemas/sitemap-news/0.9"}
        for u in root.findall("s:url", ns):
            t = _unesc((u.findtext("n:news/n:title", "", ns) or "").strip())
            if t:
                out.append({"title": t, "url": (u.findtext("s:loc", "", ns) or "").strip(), "at": _rss_date(u.findtext("n:news/n:publication_date", "", ns) or "")})
    else:
        for it in root.iter("item"):
            t = _unesc((it.findtext("title") or "").strip())
            if t:
                rc = [(c.text or "").strip().split("/")[0].strip() for c in it.findall("category") if (c.text or "").strip()]
                out.append({"title": t, "url": (it.findtext("link") or "").strip(), "at": _rss_date(it.findtext("pubDate") or ""), "rc": rc[:3]})
    return out


def _fashion_terms(title: str) -> set:
    """詞彙來源只取三種比較不會是虛詞的：拉丁字（品牌、人名）、引號書名號內的詞、3–4 字中文片段。"""
    terms = set()
    for m in re.findall(r"[「『《〈]([^」』》〉]{2,16})[」』》〉]", title):
        w = m.strip().lower()
        if w and not FASHION_GENERIC.fullmatch(w):
            terms.add(w)
    t = re.sub(r"[「」『』《》【】〈〉（）()｜|：:！!？?，,。、．…\"'“”‘’#＃＋+~～/]", " ", title)
    for m in re.findall(r"[A-Za-z][A-Za-z0-9&'.\-]+(?:\s+[A-Za-z][A-Za-z0-9&'.\-]+){0,2}", t):
        w = m.strip(" .-'").lower()
        if len(w) >= 2 and w not in FASHION_STOP:
            terms.add(w)
    for seg in re.findall(r"[\u4e00-\u9fff]{3,}", t):
        for L in (3, 4):
            for i in range(len(seg) - L + 1):
                g = seg[i:i + L]
                if not FASHION_GENERIC.search(g):
                    terms.add(g)
    return terms


def p_media():
    errs, latest = [], []
    try:
        heads = json.loads(FASHION_HEADS.read_text(encoding="utf-8")) if FASHION_HEADS.exists() else {}
    except Exception:  # noqa: BLE001
        heads = {}
    srcs = list(FASHION_TW.items()) + [(s_, ("relay", k_)) for s_, k_ in FASHION_RELAY.items()]
    for src, (kind, url) in srcs:
        try:
            if kind == "relay":
                got = []
                for r in relay_rows(relay_get(f"latest/{url}", 120)):
                    t = _unesc(str(r.get("title") or "").strip())
                    if t:
                        got.append({"title": t, "url": str(r.get("link") or ""), "at": _rss_date(str(r.get("pubDate") or "")),
                                    "rc": [str(r.get("category") or "").split("/")[0].strip()] if r.get("category") else []})
            else:
                got = _fashion_feed(kind, url)
                for it in got:  # Google 新聞的標題尾巴帶「 - GQ Taiwan」
                    it["title"] = re.sub(r"\s+-\s+GQ Taiwan\s*$", "", it["title"])
        except Exception as e:  # noqa: BLE001
            log("fashion", src, e); errs.append(f"{src}: {safe_err(e)}"); continue
        got.sort(key=lambda x: x.get("at") or "", reverse=True)
        got = got[:80]  # 美人圈的 RSS 一次給上千篇，只取最新的
        for it in got:
            it["source"] = src
            it["cat"] = _fashion_cat(it["url"], it.get("rc"), it["title"])
            k = it["url"] or (src + it["title"])
            if k not in heads:
                heads[k] = {"s": src, "t": it["title"][:120], "at": it["at"] or NOW_ISO, "c": it["cat"]}
            else:
                heads[k]["t"] = it["title"][:120]
                heads[k]["c"] = it["cat"]
        latest += [x for x in got if not FASHION_AD.search(x["title"])][:6]
    cut60 = (NOW - timedelta(days=60)).isoformat().replace("+00:00", "Z")
    heads = {k: v for k, v in heads.items() if v.get("at", "") >= cut60}
    for k, v in heads.items():
        if not v.get("c"):
            v["c"] = _fashion_cat(k if k.startswith("http") else "", (), v.get("t", ""))
    write_json(FASHION_HEADS, heads, separators=(",", ":"))
    # 分類統計：近 7 天／30 天各類篇數、各家 30 天分類組成、上一個 7 天（比較用）
    def _cnt(rows):
        c = {k: 0 for k in FASHION_CATS}
        for v in rows:
            c[v.get("c") or "生活"] = c.get(v.get("c") or "生活", 0) + 1
        return c
    cut30 = (NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    cut7_ = (NOW - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    cut14 = (NOW - timedelta(days=14)).isoformat().replace("+00:00", "Z")
    h30 = [v for v in heads.values() if v.get("at", "") >= cut30]
    h7 = [v for v in h30 if v.get("at", "") >= cut7_]
    hp7 = [v for v in heads.values() if cut14 <= v.get("at", "") < cut7_]
    src30: dict = {}
    for v in h30:
        src30.setdefault(v["s"], []).append(v)
    ex7 = {}
    for v in sorted(h7, key=lambda v: v.get("at", ""), reverse=True):
        if not FASHION_AD.search(v["t"]) or v.get("c") == "星座":
            ex7.setdefault(v.get("c") or "生活", v["t"])
    sp = {v["s"] for v in hp7}  # 跟上週比只算兩週都有資料的雜誌，避免新加入的來源灌水
    cats = {"order": FASHION_CATS, "w7": _cnt(h7), "p7": _cnt(hp7), "w7cmp": _cnt([v for v in h7 if v["s"] in sp]), "d30": _cnt(h30), "n7": len(h7), "n30": len(h30),
            "src30": {s_: _cnt(rows) for s_, rows in sorted(src30.items(), key=lambda kv: -len(kv[1]))}, "ex7": ex7,
            "span_days": round((NOW - min((datetime.fromisoformat(v["at"].replace("Z", "+00:00")) for v in heads.values() if v.get("at")), default=NOW)).total_seconds() / 86400, 1)}
    # 本週同框：近 7 天、排除業配與星座專欄，同一個詞在 2 家以上台灣媒體出現（家數多的排前面）
    cut7 = (NOW - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    week = [v for v in heads.values() if v.get("at", "") >= cut7 and not FASHION_AD.search(v["t"])]
    by_term: dict = {}
    for idx, v in enumerate(week):
        for term in _fashion_terms(v["t"]):
            d = by_term.setdefault(term, {"src": set(), "ids": set(), "ex": {}})
            d["src"].add(v["s"]); d["ids"].add(idx)
            d["ex"].setdefault(v["s"], v["t"])
    cand = {t: d for t, d in by_term.items() if len(d["src"]) >= 2}
    # 同一批標題裡的重疊片段（皮膚科／膚科醫／科醫師）拼回完整詞（皮膚科醫師）
    groups: dict = {}
    for t, d in cand.items():
        groups.setdefault(frozenset(d["ids"]), []).append(t)
    merged = {}
    for ids, terms in groups.items():
        terms = sorted(set(terms), key=len, reverse=True)
        changed = True
        while changed:
            changed = False
            for x in terms:
                for y in terms:
                    if x == y:
                        continue
                    for ov in range(min(len(x), len(y)) - 1, 1, -1):
                        if x.endswith(y[:ov]):
                            z = x + y[ov:]
                            if all(z in week[i]["t"].lower() for i in ids):
                                terms = [w for w in terms if w not in (x, y)] + [z]
                                changed = True
                            break
                    if changed:
                        break
                if changed:
                    break
        terms = [w for w in terms if not any(w != o and w in o for o in terms)]
        d0 = cand[next(iter(t for t in cand if frozenset(cand[t]["ids"]) == ids))]
        for w in terms:
            merged[w] = {"src": d0["src"], "n": len(ids), "ex": d0["ex"]}
    keep = []
    for t, d in sorted(merged.items(), key=lambda kv: (-len(kv[1]["src"]), -kv[1]["n"], not re.match(r"[a-z]", kv[0]), -len(kv[0]))):
        if any(t in k and t != k and len(merged[k]["src"]) >= len(d["src"]) for k in merged):
            continue
        keep.append({"term": t, "sources": sorted(d["src"]), "n": d["n"], "examples": list(d["ex"].items())[:3]})
    together = keep[:12]
    # 國際：WWD（官方 RSS）
    intl = []
    try:
        for it in _fashion_feed("rss", "https://wwd.com/feed/")[:6]:
            it["source"] = "WWD"; intl.append(it)
    except Exception as e:  # noqa: BLE001
        errs.append(f"WWD: {safe_err(e)}")
    latest.sort(key=lambda x: x.get("at") or "", reverse=True)
    if not latest and not intl:
        raise RuntimeError("no media items " + "; ".join(errs)[:160])
    per = {}
    for v in heads.values():
        per[v["s"]] = per.get(v["s"], 0) + 1
    # 國際版分類比例
    try:
        ih = json.loads(FASHION_HEADS_INTL.read_text(encoding="utf-8")) if FASHION_HEADS_INTL.exists() else {}
    except Exception:  # noqa: BLE001
        ih = {}
    for src, url in FASHION_INTL.items():
        try:
            for it in _fashion_feed("rss", url)[:80]:
                k = it["url"] or (src + it["title"])
                ih[k] = {"s": src, "t": it["title"][:120], "at": it["at"] or (ih.get(k) or {}).get("at") or NOW_ISO,
                         "c": _fashion_cat(it["url"], it.get("rc"), it["title"])}
        except Exception as e:  # noqa: BLE001
            errs.append(f"{src}: {safe_err(e)}")
    ih = {k: v for k, v in ih.items() if v.get("at", "") >= cut30}
    write_json(FASHION_HEADS_INTL, ih, separators=(",", ":"))
    i30 = list(ih.values())
    i7 = [v for v in i30 if v.get("at", "") >= cut7_]
    isrc: dict = {}
    for v in i30:
        isrc.setdefault(v["s"], []).append(v)
    cats["intl"] = {"w7": _cnt(i7), "d30": _cnt(i30), "n7": len(i7), "n30": len(i30),
                    "src30": {s_: _cnt(rows) for s_, rows in sorted(isrc.items(), key=lambda kv: -len(kv[1]))}}
    return {"items": latest[:16], "intl": intl, "together": together, "cats": cats, "week_n": len(week), "lexicon": len(heads), "per_source": per, "errs": errs}


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
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "\n", html, flags=re.S)  # 先拿掉 script：meta 和 JSON 裡也有 hottest brands
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    page_move = {}  # 新版面每個品牌下面直接寫名次變動（+2、-1、-）

    def grab(anchor):
        best = []
        for i in [k for k, l in enumerate(lines) if anchor.lower() in l.lower()]:  # 每個出現位置都試，取抓到最多的
            got = _lyst_list(lines[i + 1:i + 80])
            if len(got) > len(best):
                best = got
        return best

    def _lyst_list(seg):
        out = []
        for k, l in enumerate(seg):
            m = re.match(r"^(\d{1,2})\.?\s*(.*)$", l)
            if not m or int(m.group(1)) != len(out) + 1:
                continue
            name = m.group(2).strip()
            if not name and k + 1 < len(seg):  # 2026 起新版面：「01」一行、品牌名下一行、名次變動再下一行
                name = seg[k + 1].strip()
            if name and not re.match(r"^[+\-–]?\d*$", name):
                nm = name.title() if name.isupper() else name
                mv = seg[k + 2].strip() if not m.group(2).strip() and k + 2 < len(seg) else ""
                if re.match(r"^([+\-–]\d+|[-–])$", mv):
                    page_move[nm] = 0 if mv in ("-", "–") else int(mv.replace("–", "-"))
                out.append(nm)
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
        move = page_move[b] if b in page_move else ((prev_brands.index(b) - i) if b in prev_brands else 0)
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


MIS_DIAG: list = []


def twse_mis_quotes(codes, otc=()):
    """證交所官方即時（個股批次）：回 {code: {price, prev, chg, pct, day, time}}；未成交（z='-'）就略過該檔。"""
    ex = "|".join(f"{'otc' if c in otc else 'tse'}_{c}.tw" for c in codes)
    r = S.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp", params={"ex_ch": ex, "json": "1", "delay": "0", "_": int(time.time() * 1000)},
              headers={"Referer": "https://mis.twse.com.tw/stock/index.jsp", "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = {}
    arr = r.json().get("msgArray") or []
    MIS_DIAG.append(f"msgArray={len(arr)}")
    for m in arr:
        c = m.get("c"); z = num(m.get("z")); y = num(m.get("y"))
        if not z:  # 兩次撮合之間沒有成交價：用最佳一檔買賣價中間值，再不行用開盤價
            bid = num((m.get("b") or "").split("_")[0]); ask = num((m.get("a") or "").split("_")[0])
            z = (bid + ask) / 2 if bid and ask else (bid or ask or num(m.get("o")))
        if not c or not z or not y:
            MIS_DIAG.append(f"{c}: z={m.get('z')} b={str(m.get('b'))[:12]} y={m.get('y')}")
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


WX_CITIES = [  # (顯示名, 預報縣市名, 觀測站候選：有人站優先、自動站備援)
    ("基隆", "基隆市", ["基隆"]), ("台北", "臺北市", ["臺北"]), ("新北", "新北市", ["板橋", "新北"]), ("桃園", "桃園市", ["桃園", "新屋", "中壢"]),
    ("新竹", "新竹市", ["新竹", "新竹市東區"]), ("台中", "臺中市", ["臺中"]), ("彰化", "彰化縣", ["彰化", "田中", "彰師大"]), ("嘉義", "嘉義市", ["嘉義"]),
    ("台南", "臺南市", ["臺南"]), ("高雄", "高雄市", ["高雄"]), ("屏東", "屏東縣", ["屏東", "恆春"]), ("宜蘭", "宜蘭縣", ["宜蘭"]),
    ("花蓮", "花蓮縣", ["花蓮"]), ("台東", "臺東縣", ["臺東"]),
]


def p_weather():
    out = []
    manned = {st["StationName"]: st for st in cwa("O-A0003-001").get("Station", [])}
    auto = {}
    try:
        auto = {st["StationName"]: st for st in cwa("O-A0001-001").get("Station", [])}
    except Exception as e:  # noqa: BLE001
        log("cwa auto", e)
    rain = {st["StationName"]: st for st in cwa("O-A0002-001").get("Station", [])}
    fc = {loc["locationName"]: loc for loc in cwa("F-C0032-001").get("location", [])}
    for label, county, cands in WX_CITIES:
        o = next((manned[c] for c in cands if c in manned), None) or next((auto[c] for c in cands if c in auto), {})
        st_name = o.get("StationName", cands[0])
        we = o.get("WeatherElement", {})
        r = next((rain[c] for c in cands if c in rain), {}).get("RainfallElement", {})
        f = fc.get(county, {})
        els = {e["elementName"]: e["time"] for e in f.get("weatherElement", [])}

        def fparam(name, i=0):
            try:
                return els[name][i]["parameter"]["parameterName"]
            except Exception:  # noqa: BLE001
                return None
        temp = _cwa_num(we.get("AirTemperature"))
        out.append({
            "city": label, "station": st_name,
            "temp": temp, "rh": _cwa_num(we.get("RelativeHumidity")),
            "weather": we.get("Weather"), "wind": _cwa_num(we.get("WindSpeed")),
            "rain10": _cwa_num((r.get("Past10Min") or {}).get("Precipitation")),
            "rain1h": _cwa_num((r.get("Past1hr") or {}).get("Precipitation")),
            "rain24h": _cwa_num((r.get("Past24hr") or {}).get("Precipitation")),
            "obsTime": (o.get("ObsTime") or {}).get("DateTime"),
            "forecast": [{"start": els.get("Wx", [{}])[i].get("startTime", "")[5:16] if els.get("Wx") and len(els["Wx"]) > i else "",
                          "wx": fparam("Wx", i), "pop": fparam("PoP", i), "minT": fparam("MinT", i), "maxT": fparam("MaxT", i)}
                         for i in range(3)],
        })
        if temp is not None and temp > -50:
            hist_put("weather", label + "_temp", NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M"), temp)
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
    if not any(c["temp"] is not None for c in out):
        raise RuntimeError("cwa: no observations")
    # 雨量站：全台正在下雨的站（過去 1 小時 ≥0.5mm 或 10 分鐘內有雨），地圖畫點；同一筆資料不多打 API
    rainmap, county_rain = [], {}
    for st in rain.values():
        lon, lat = _cwa_ll(st)
        re_ = st.get("RainfallElement") or {}
        r1 = _cwa_num((re_.get("Past1hr") or {}).get("Precipitation"))
        r10 = _cwa_num((re_.get("Past10Min") or {}).get("Precipitation"))
        if lon is None or lat is None or not ((r1 or 0) >= 0.5 or (r10 or 0) > 0):
            continue
        cty = (st.get("GeoInfo") or {}).get("CountyName") or ""
        rainmap.append([round(lon, 3), round(lat, 3), r1 or 0, r10 or 0, st.get("StationName", ""), cty])
        if cty:
            county_rain[cty] = max(county_rain.get(cty, 0), r1 or 0)
    rainmap.sort(key=lambda x: -x[2])
    # 紫外線：當日最大值，對應到各城市選用的有人站
    uv = {}
    try:
        for sid, v in _cwa_uv().items():
            uv[sid] = v
        id_of = {name: st.get("StationId") for name, st in manned.items()}
        for c in out:
            sid = id_of.get(c["station"])
            if sid and sid in uv:
                c["uv"] = uv[sid]
    except Exception as e:  # noqa: BLE001
        log("cwa uv", e)
    tempmap = []
    for st in list(manned.values()) + list(auto.values()):
        lon, lat = _cwa_ll(st)
        t = _cwa_num((st.get("WeatherElement") or {}).get("AirTemperature"))
        if lon is not None and t is not None and -20 < t < 45:
            tempmap.append([round(lon, 3), round(lat, 3), t, st.get("StationName", ""), ((st.get("GeoInfo") or {}).get("CountyName") or "")])
    return {"label": "氣象署", "items": out, "warnings": warns[:12], "rainmap": rainmap[:700], "rainN": len(rainmap), "tempmap": tempmap[:900],
            "countyRain": county_rain, "rainStations": len(rain)}


def _cwa_ll(st):
    cs = (st.get("GeoInfo") or {}).get("Coordinates") or []
    pick = next((c for c in cs if "WGS" in str(c.get("CoordinateName", "")).upper()), cs[-1] if cs else {})
    lon, lat = num(pick.get("StationLongitude")), num(pick.get("StationLatitude"))
    if lon is None or not (118 < lon < 123 and 21 < (lat or 0) < 27):
        return None, None
    return lon, lat


def _walk_dicts(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_dicts(v)


def _cwa_uv():
    """O-A0005-001 每日紫外線最大值：回傳 {測站代號: 指數}（欄位名稱各版本不同，用掃的）。"""
    out = {}
    for d in _walk_dicts(cwa("O-A0005-001")):
        sid = next((d[k] for k in d if k.lower() in ("stationid", "locationcode")), None)
        val = next((d[k] for k in d if "uv" in k.lower() and not isinstance(d[k], (dict, list))), None)
        if sid and num(val) is not None:
            out[str(sid)] = num(val)
    return out


def _tree(o, d=0):
    if d > 6:
        return "…"
    if isinstance(o, dict):
        return {k: _tree(v, d + 1) for k, v in list(o.items())[:30]}
    if isinstance(o, list):
        return [len(o), _tree(o[0], d + 1)] if o else [0]
    return str(o)[:40]


# ---------- 颱風動態（W-C0034-005，沒有颱風時是空的） ----------
def _ll_pair(s):
    try:
        a, b = [float(x) for x in str(s).replace(" ", "").split(",")[:2]]
        return [a, b] if a > b else [b, a]  # [經度, 緯度]
    except Exception:  # noqa: BLE001
        return None


def _ci(d, *keys):
    """不分大小寫取欄位（氣象署新舊版本命名不同）。"""
    if not isinstance(d, dict):
        return None
    low = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None


def _radius(v):
    if isinstance(v, dict):
        v = _ci(v, "Radius", "radius", "value")
    return num(v)


def p_typhoon():
    rec = cwa("W-C0034-005")
    tcs = []
    for d in _walk_dicts(rec):
        if _ci(d, "analysisData") is None and _ci(d, "forecastData") is None:
            continue
        def fixes(part):
            fx = _ci(_ci(d, part) or {}, "fix") or []
            out = []
            for f in fx if isinstance(fx, list) else [fx]:
                lon, lat = num(_ci(f, "CoordinateLongitude")), num(_ci(f, "CoordinateLatitude"))
                ll = [lon, lat] if lon is not None and lat is not None else _ll_pair(_ci(f, "coordinate"))
                if not ll:
                    continue
                out.append({"t": _ci(f, "DateTime", "fixTime", "InitialTime", "initTime") or "", "tau": num(_ci(f, "ForecastHour", "tau")), "ll": ll,
                            "wind": num(_ci(f, "MaxWindSpeed")), "gust": num(_ci(f, "MaxGustSpeed")), "p": num(_ci(f, "Pressure")),
                            "mv": num(_ci(f, "MovingSpeed")), "dir": _ci(f, "MovingDirection") or "",
                            "r15": _radius(_ci(f, "Circle15ms", "circleOf15Ms")), "r25": _radius(_ci(f, "Circle25ms", "circleOf25Ms")),
                            "r70": _radius(_ci(f, "Radius70PercentProbability", "radiusOf70PercentProbability"))})
            return out
        name = _ci(d, "CwaTyphoonName") or _ci(d, "TyphoonName") or ""
        tcs.append({"name": name, "en": _ci(d, "TyphoonName") or "", "td": _ci(d, "CwaTyNo", "CwaTdNo") or "",
                    "past": fixes("analysisData")[-24:], "fc": fixes("forecastData")})
    return {"items": tcs, "diag": None if tcs else _tree(rec)}


# ---------- 雷達回波（O-A0059-001 格點 → 自己畫成透明 PNG，地圖疊圖） ----------
CWA_FILE = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/"
RADAR_COLORS = [(15, (60, 170, 255, 120)), (20, (0, 200, 200, 140)), (25, (0, 200, 90, 155)), (30, (180, 230, 0, 170)), (35, (255, 220, 0, 185)),
                (40, (255, 150, 0, 200)), (45, (255, 60, 30, 210)), (50, (225, 0, 90, 220)), (55, (190, 0, 200, 230))]


def _png_rgba(w, h, rows):
    import struct
    import zlib
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def p_radar_wx():
    import math
    j = gjson(CWA_FILE + "O-A0059-001", params={"Authorization": CWA_KEY, "downloadType": "WEB", "format": "JSON"})
    ds = (j.get("cwaopendata") or j).get("dataset") or {}
    content, params = "", {}
    for d in _walk_dicts(ds):
        for k, v in d.items():
            if isinstance(v, str) and len(v) > len(content) and v.count(",") > 1000:
                content = v
            elif isinstance(v, (str, int, float)) and len(str(v)) < 40:
                params.setdefault(k, v)
        if "parameterName" in d and "parameterValue" in d:
            params.setdefault(str(d["parameterName"]), d["parameterValue"])
    def pv(*keys, default=None):
        for k, v in params.items():
            if any(x.lower() in k.lower().replace(" ", "") for x in keys) and num(v) is not None:
                return num(v)
        return default
    lon0 = pv("StartPointLongitude", "經度", default=118.0)
    lat0 = pv("StartPointLatitude", "緯度", default=20.0)
    res = pv("GridResolution", "Resolution", "解析度", default=0.0125)
    nx = int(pv("GridDimensionX", "DimensionX", default=441))
    ny = int(pv("GridDimensionY", "DimensionY", default=561))
    vals = [num(x) for x in content.split(",")] if content else []
    if len(vals) != nx * ny:
        return {"error_detail": f"grid {len(vals)} != {nx}x{ny}", "diag": _tree(ds), "params": {k: str(v)[:30] for k, v in list(params.items())[:40]}}
    when = next((params[k] for k in params if "datetime" in k.lower() or "obstime" in k.lower()), "")
    def color(v):
        if v is None or v < RADAR_COLORS[0][0]:
            return b"\x00\x00\x00\x00"
        c = RADAR_COLORS[0][1]
        for th, cc in RADAR_COLORS:
            if v >= th:
                c = cc
        return bytes(c)
    # 重新取樣成麥卡托等距的列，疊到地圖上不會南北偏移
    merc = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
    south, north = lat0 - res / 2, lat0 + (ny - 1) * res + res / 2
    west, east = lon0 - res / 2, lon0 + (nx - 1) * res + res / 2
    ys, yn = merc(south), merc(north)
    H = ny
    rows, strong = [], 0
    for r in range(H):
        y = yn - (r + 0.5) * (yn - ys) / H
        la = math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)
        sr = min(ny - 1, max(0, int(round((la - lat0) / res))))
        line = vals[sr * nx:(sr + 1) * nx]
        rows.append(b"".join(color(v) for v in line))
        strong += sum(1 for v in line if v is not None and v >= 40)
    png = _png_rgba(nx, H, rows)
    (DATA / "radar.png").write_bytes(png)
    echo = sum(1 for v in vals if v is not None and v >= 15)
    return {"time": str(when), "bounds": [[west, north], [east, north], [east, south], [west, south]], "img": "radar.png",
            "echoPct": round(100 * echo / len(vals), 1), "strongPct": round(100 * strong / len(vals), 2),
            "maxDbz": max((v for v in vals if v is not None), default=None), "bytes": len(png)}


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
    _t = NOW.astimezone(TPE)
    today_md = f"{_t.month}/{_t.day:02d}"  # PTT 列表日期：月不補零、日補零（9/05、10/01）
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


# ---------- 台灣現場：YouBike／停車場／市區車速／桃機（全部免金鑰的原始單位開放資料） ----------
# 2026-10 起不用 TDX（免費額度每月約 4,500 次，地圖一天就用完、帳號被停權）。
# GitHub 主機連得到的來源只有：台北市資料大平臺（YouBike、停車場、VD 路段）、新北市開放資料（YouBike）、桃園機場航班檔。
# 國道（高公局 tisvcloud）、台中／高雄等 YouBike 來源擋海外 IP，所以沒有。
GEO_PATH = DATA / "geo.json"
GEO_STATIC_PATH = DATA / "geo_static.json"
GEO_ERRS: list = []
TPE_YB_URL = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
NTPC_YB_URL = "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json"
TPE_PARK_DESC = "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json"
TPE_PARK_AV = "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json"
TPE_VD_URL = "https://tcgbusfs.blob.core.windows.net/blobtisv/GetVD.xml.gz"
TPE_AIR_URL = "https://www.taoyuan-airport.com/uploads/flightx/a_flight_v4.txt"
LIVE_CITIES = {
    "Taipei": {"label": "台北市", "center": [121.54, 25.05], "zoom": 11.3},
    "NewTaipei": {"label": "新北市", "center": [121.50, 25.02], "zoom": 10.2},
}
_live_cache: dict = {}

# ---------- 台灣抓取站（Google Cloud 彰化機房，ops/tw_relay.py）：每 5 分鐘把全台 YouBike、國道、省道存到 bucket 的 relay/ ----------
YB_AREAS = {"00": ("Taipei", "台北市"), "05": ("NewTaipei", "新北市"), "07": ("Taoyuan", "桃園市"), "09": ("Hsinchu", "新竹市"),
            "0B": ("HsinchuCounty", "新竹縣"), "10": ("HSP", "新竹科學園區"), "0A": ("Miaoli", "苗栗縣"), "01": ("Taichung", "台中市"),
            "08": ("Chiayi", "嘉義市"), "11": ("ChiayiCounty", "嘉義縣"), "13": ("Tainan", "台南市"), "12": ("Kaohsiung", "高雄市"),
            "14": ("Pingtung", "屏東縣"), "15": ("Taitung", "台東縣")}
_relay_cache: dict = {}


def relay_get(name: str, max_age_min: float = 0):
    """讀 gs://<bucket>/relay/<name>.json.gz（latest/xxx 或 static/xxx）。max_age_min>0 時太舊就丟錯。"""
    if name not in _relay_cache:
        bucket, project = os.environ.get("GCP_BUCKET"), os.environ.get("GCP_PROJECT")
        if not bucket or not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            raise RuntimeError("沒有 Google Cloud 憑證")
        import gzip
        from google.cloud import storage
        raw = storage.Client(project=project).bucket(bucket).blob(f"relay/{name}.json.gz").download_as_bytes(timeout=60)
        _relay_cache[name] = json.loads(gzip.decompress(raw))
    d = _relay_cache[name]
    if max_age_min:
        try:
            age = (NOW - datetime.fromisoformat(d["at"])).total_seconds() / 60
        except Exception:  # noqa: BLE001
            age = 1e9
        if age > max_age_min:
            raise RuntimeError(f"relay {name} 太舊（{age:.0f} 分鐘）")
    return d


def relay_rows(d) -> list:
    cols = d.get("cols") or []
    return [dict(zip(cols, r)) for r in d.get("rows") or []]


def _yb_relay() -> dict:
    """全台 YouBike（彰化機房抓的）→ {city_key: [[lon, lat, 可借, 總車位, 站名, 可還]]}。"""
    if "yb_relay" in _live_cache:
        return _live_cache["yb_relay"]
    meta = {r[0]: r for r in relay_get("static/yb_meta")["rows"]}
    out: dict = {}
    for no, area, bikes, _eb, empty, cap, status, _upd in relay_get("latest/yb", 30)["rows"]:
        m = meta.get(no)
        a = YB_AREAS.get(area)
        if not m or not a or str(status) != "1" or not m[4] or not m[5]:
            continue
        out.setdefault(a[0], []).append([round(float(m[5]), 5), round(float(m[4]), 5), int(num(bikes) or 0), int(num(cap) or 0),
                                         str(m[3] or "").replace("YouBike2.0_", "")[:14], int(num(empty) or 0)])
    if not out:
        raise RuntimeError("relay youbike empty")
    _live_cache["yb_relay"] = out
    return out


def live_cities() -> dict:
    """地圖與脈搏表要列的城市：雙北固定，其他縣市看彰化機房有沒有抓到。"""
    out = dict(LIVE_CITIES)
    try:
        yb = _yb_relay()
    except Exception as e:  # noqa: BLE001
        log("relay yb", safe_err(e))
        return out
    for code, (k, label) in YB_AREAS.items():
        st = yb.get(k)
        if k in out or not st:
            continue
        xs, ys = [r[0] for r in st], [r[1] for r in st]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 0.02)
        import math
        out[k] = {"label": label, "center": [round((min(xs) + max(xs)) / 2, 4), round((min(ys) + max(ys)) / 2, 4)],
                  "zoom": round(min(12.5, max(9.3, math.log2(1.6 / span) + 8.5)), 2)}
    return out


def _gz_text(r) -> str:
    raw = r.content
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


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


def _yb_stations(city: str) -> list:
    """回 [[lon, lat, 可借, 總車位, 站名, 可還]]（只含營運中的站）。同一輪只抓一次。"""
    if city in _live_cache:
        return _live_cache[city]
    try:
        rows = _yb_relay().get(city)
        if rows:
            _live_cache[city] = rows
            return rows
    except Exception as e:  # noqa: BLE001
        log("yb relay", city, safe_err(e))  # 彰化機房沒資料：雙北退回市府來源
    out = []
    if city == "Taipei":
        for s in gjson(TPE_YB_URL):
            if str(s.get("act")) != "1" or not s.get("latitude"):
                continue
            out.append([round(float(s["longitude"]), 5), round(float(s["latitude"]), 5), int(s.get("available_rent_bikes") or 0),
                        int(s.get("Quantity") or 0), (s.get("sna") or "").replace("YouBike2.0_", "")[:14], int(s.get("available_return_bikes") or 0)])
    elif city == "NewTaipei":
        rows, page = [], 0
        while page < 5:  # 新北約 1,800 站：一頁 3,000 通常一次拿完
            batch = gjson(NTPC_YB_URL, params={"page": page, "size": 3000})
            rows += batch
            if len(batch) < 3000:
                break
            page += 1
        for s in rows:
            if str(s.get("act")) != "1" or not s.get("lat"):
                continue
            out.append([round(float(s["lng"]), 5), round(float(s["lat"]), 5), int(num(s.get("sbi_quantity")) or 0),
                        int(num(s.get("tot_quantity")) or 0), (s.get("sna") or "").replace("YouBike2.0_", "")[:14], int(num(s.get("bemp")) or 0)])
    _live_cache[city] = out
    return out


def _tpe_parking() -> list:
    """台北市停車場：[[lon, lat, 剩餘汽車位, 汽車位, 名稱]]。座標表一天更新一次（2.8MB），剩餘每輪抓。"""
    if "parking" in _live_cache:
        return _live_cache["parking"]
    st = {}
    if GEO_STATIC_PATH.exists():
        try:
            st = json.loads(GEO_STATIC_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
    pos = st.get("tpe_park") if st.get("v") == 2 else None
    fresh = pos and st.get("fetchedAt", "") >= (NOW - timedelta(hours=24)).isoformat()
    if not fresh:
        try:
            desc = json.loads(_gz_text(get(TPE_PARK_DESC)))["data"]["park"]
            pos = {}
            for p in desc:
                try:
                    tot = int(p.get("totalcar") or 0)
                    if tot >= 20 and p.get("tw97x"):
                        lon, lat = _twd97_to_wgs84(float(p["tw97x"]), float(p["tw97y"]))
                        pos[p["id"]] = [lon, lat, tot, (p.get("name") or "")[:18]]
                except Exception:  # noqa: BLE001
                    continue
            write_json(GEO_STATIC_PATH, {"v": 2, "fetchedAt": NOW_ISO, "tpe_park": pos}, separators=(",", ":"))
        except Exception as e:  # noqa: BLE001
            if not pos:
                raise
            log("tpe parking desc", e)  # 座標表抓不到：沿用舊表
    out = []
    for p in json.loads(_gz_text(get(TPE_PARK_AV)))["data"]["park"]:
        meta = pos.get(p.get("id"))
        av = p.get("availablecar")
        if meta and isinstance(av, (int, float)) and av >= 0:
            out.append([meta[0], meta[1], int(min(av, meta[2])), meta[2], meta[3]])
    _live_cache["parking"] = out
    return out


def _tpe_vd() -> list:
    """台北市 VD 路段：[{name, road, spd, vol, a:[lon,lat], b:[lon,lat]}]。"""
    if "vd" in _live_cache:
        return _live_cache["vd"]
    t = _gz_text(get(TPE_VD_URL))
    out = []
    for s in re.findall(r"<vd:SectionData>(.*?)</vd:SectionData>", t, re.S):
        g = lambda tag: (re.search(rf"<vd:{tag}>(.*?)</vd:{tag}>", s) or [None, ""])[1]
        spd, vol = num(g("AvgSpd")), num(g("TotalVol"))
        ax, ay, bx, by = num(g("StartWgsX")), num(g("StartWgsY")), num(g("EndWgsX")), num(g("EndWgsY"))
        if not spd or spd <= 0 or None in (ax, ay, bx, by):
            continue
        if not all(121.40 <= x <= 121.70 for x in (ax, bx)) or not all(24.90 <= y <= 25.25 for y in (ay, by)) \
                or abs(ax - bx) + abs(ay - by) > 0.05:  # 座標錯置的路段（會拉出一條橫跨地圖的線）不畫
            continue
        name = re.sub(r"\s+", " ", g("SectionName")).strip()
        out.append({"name": name, "road": name.split(" ")[0], "spd": spd, "vol": vol or 0,
                    "a": [round(ax, 5), round(ay, 5)], "b": [round(bx, 5), round(by, 5)]})
    _live_cache["vd"] = out
    return out


def p_tw_pulse():
    """全台脈搏：雙北 YouBike、台北停車場剩餘率、台北主要道路均速與最塞路段。"""
    key = NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M")
    bikes, errs = [], []
    park_pct = None
    try:
        pk = _tpe_parking()
        tot = sum(p[3] for p in pk)
        park_pct = round(sum(p[2] for p in pk) / tot * 100, 1) if tot else None
    except Exception as e:  # noqa: BLE001
        log("tw_pulse parking", e); errs.append("台北停車場: " + safe_err(e))
    for city, meta in live_cities().items():
        try:
            rows = _yb_stations(city)
        except Exception as e:  # noqa: BLE001
            log("tw_pulse bikes", city, e); errs.append(f"YouBike {meta['label']}: " + safe_err(e)); continue
        if not rows:
            continue
        rent = sum(r[2] for r in rows)
        label = meta["label"]
        hist_put("youbike", label, key, rent)
        bikes.append({"city": label, "stations": len(rows), "rent": rent, "empty": sum(1 for r in rows if r[2] == 0),
                      "full": sum(1 for r in rows if r[5] == 0), "park_pct": park_pct if city == "Taipei" else None,
                      "spark": hist_get("youbike", label, 48)})
    roads, jams = [], []
    try:
        secs = _tpe_vd()
        agg = {}
        for s in secs:
            a = agg.setdefault(s["road"], [0.0, 0.0, 0])
            w = max(s["vol"], 1)
            a[0] += s["spd"] * w; a[1] += w; a[2] += 1
        top = sorted(((r, v) for r, v in agg.items() if v[2] >= 4), key=lambda x: -x[1][1])[:8]
        for road, (w, c, nsec) in top:
            spd = round(w / c, 1)
            hist_put("tpe_road", road, key, spd)
            roads.append({"road": road, "dir": "", "speed": spd, "count": int(c), "spark": hist_get("tpe_road", road, 48)})
        slow = sorted((s for s in secs if s["spd"] < 15 and s["vol"] >= 20), key=lambda s: s["spd"])[:6]
        jams = [{"section": s["name"][:22], "speed": round(s["spd"])} for s in slow]
    except Exception as e:  # noqa: BLE001
        log("tw_pulse vd", e); errs.append("台北 VD: " + safe_err(e))
    if not bikes and not roads:
        raise RuntimeError("tw_pulse: nothing " + "; ".join(errs)[:200])
    bikes.sort(key=lambda b: -b["stations"])
    return {"label": "全台 YouBike（彰化機房）・台北市資料大平臺", "bikes": bikes, "roads": roads, "roadKind": "city", "jams": jams, "errs": errs}


def p_geo():
    """地圖：雙北 YouBike、台北停車場、台北市區路段車速（全台概覽畫路段線）。"""
    GEO_ERRS.clear()
    prev = {}
    if GEO_PATH.exists():
        try:
            prev = json.loads(GEO_PATH.read_text(encoding="utf-8")).get("cities", {})
        except Exception:  # noqa: BLE001
            prev = {}
    cities = live_cities()
    geo = {"generatedAt": NOW_ISO, "labels": {k: v["label"] for k, v in cities.items()},
           "views": {k: [v["center"], v["zoom"]] for k, v in cities.items()}, "avail": {}, "cities": {}, "freeway": [],
           "lineLabel": "台北市區路段"}
    for city in cities:
        c = {"parking": [], "bikes": [], "speed": []}
        try:
            c["bikes"] = [r[:5] for r in _yb_stations(city)]
        except Exception as e:  # noqa: BLE001
            GEO_ERRS.append(f"bikes {city}: " + safe_err(e)); c["bikes"] = (prev.get(city) or {}).get("bikes", [])
        if city == "Taipei":
            try:
                c["parking"] = _tpe_parking()
            except Exception as e:  # noqa: BLE001
                GEO_ERRS.append("parking Taipei: " + safe_err(e)); c["parking"] = (prev.get(city) or {}).get("parking", [])
            try:
                secs = _tpe_vd()
                c["speed"] = [[round((s["a"][0] + s["b"][0]) / 2, 5), round((s["a"][1] + s["b"][1]) / 2, 5), round(s["spd"]), s["name"][:16]] for s in secs]
                geo["freeway"] = [[[s["a"], s["b"]], round(s["spd"]), s["name"][:16]] for s in secs]
            except Exception as e:  # noqa: BLE001
                GEO_ERRS.append("vd Taipei: " + safe_err(e)); c["speed"] = (prev.get(city) or {}).get("speed", [])
        geo["cities"][city] = c
        geo["avail"][city] = {"parking": bool(c["parking"]), "bikes": bool(c["bikes"]), "vd": bool(c["speed"])}
    write_json(GEO_PATH, geo, separators=(",", ":"))
    summary = {city: {k: len(v) for k, v in c.items() if v} for city, c in geo["cities"].items()}
    if not any(summary.values()):
        raise RuntimeError(f"geo: nothing errs={GEO_ERRS[:4]}")
    return {"label": "台北市資料大平臺・新北市開放資料", "cities_with_data": sum(1 for v in summary.values() if v), "freeway": len(geo["freeway"]),
            "totals": {k: sum(v.get(k, 0) for v in summary.values()) for k in ("parking", "bikes", "speed")}, "errs": GEO_ERRS[:12]}


# ---------- 智庫觀點：McKinsey Insights（RSS 有標題、摘要、分類；全文在官網，擋機房主機所以只存摘要＋連結） ----------
THINK_RSS = "https://www.mckinsey.com/insights/rss"
THINK_POD = "https://www.omnycontent.com/d/playlist/708664bd-6843-4623-8066-aede00ce0c8a/3f6f52af-fba1-496d-b11b-af040139456a/bfe0b44a-082f-495a-952a-af0401394590/podcast.rss"
THINK_GROUPS = [
    ("tech", "科技與 AI", re.compile(r"\bAI\b|Artificial|Generative|Technolog|Digital|Cloud|Cyber|Semiconductor|High Tech|Software|Data|Analytics|Disruptive|Automation|Robot|Quantum|Telecom", re.I)),
    ("consumer", "消費與行銷", re.compile(r"Consumer|Retail|Marketing|Sales|Luxury|Fashion|Brand|Customer|Travel|Media|Entertainment|Apparel|Beauty|Food|Hospitality", re.I)),
]


def _rss_items(text):
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    out = []
    for it in root.iter("item"):
        g = lambda t: html_mod.unescape((it.findtext(t) or "").strip())
        at = ""
        try:
            at = parsedate_to_datetime(g("pubDate")).astimezone(TPE).isoformat()
        except Exception:  # noqa: BLE001
            try:  # McKinsey 只給日期（Fri, 02 Oct 2026）
                at = datetime.strptime(g("pubDate")[:16].strip(), "%a, %d %b %Y").replace(hour=12, tzinfo=TPE).isoformat()
            except Exception:  # noqa: BLE001
                at = ""
        cats = [html_mod.unescape(html_mod.unescape((c.text or "").strip())) for c in it.findall("category") if (c.text or "").strip()]
        out.append({"title": g("title"), "desc": re.sub(r"<[^>]+>", "", g("description"))[:400], "url": g("link"), "at": at, "cats": cats[:8]})
    return out


def p_think():
    """McKinsey 最新文章，依分類拆成科技與 AI／消費與行銷／總經與產業；保留 120 天。"""
    prev = []
    try:
        old = json.loads((PANELS / "think.json").read_text(encoding="utf-8"))
        prev = [x for g_ in old.get("groups", []) for x in g_.get("items", [])]
    except Exception:  # noqa: BLE001
        pass
    fresh = _rss_items(get(THINK_RSS).text)
    if not fresh:
        raise RuntimeError("mckinsey rss empty")
    by_url = {x["url"]: x for x in prev if x.get("url")}
    for x in fresh:
        by_url[x["url"]] = {**by_url.get(x["url"], {}), **x}
    cutoff = (NOW.astimezone(TPE) - timedelta(days=120)).isoformat()
    items = sorted((x for x in by_url.values() if x.get("at", "") >= cutoff), key=lambda x: x.get("at", ""), reverse=True)
    groups = {k: {"key": k, "name": nm, "items": []} for k, nm, _ in THINK_GROUPS}
    groups["macro"] = {"key": "macro", "name": "總經與產業", "items": []}
    for x in items:
        blob = " ".join(x.get("cats") or []) + " " + x.get("title", "")
        score = {k: len(rx.findall(blob)) for k, _, rx in THINK_GROUPS}
        best = max(score, key=lambda k: score[k])
        k = best if score[best] > 0 else "macro"
        x["src"] = "McKinsey"
        if len(groups[k]["items"]) < 60:
            groups[k]["items"].append(x)
    pod = []
    try:
        pod = [{"title": x["title"], "url": x["url"], "at": x["at"]} for x in _rss_items(get(THINK_POD).text)[:6]]
    except Exception as e:  # noqa: BLE001
        log("think podcast", safe_err(e))
    week = (NOW.astimezone(TPE) - timedelta(days=7)).isoformat()
    return {"label": "McKinsey Insights", "groups": list(groups.values()), "podcast": pod,
            "week": sum(1 for x in items if x.get("at", "") >= week), "total": len(items)}


# ---------- 聲量雷達：關鍵字的搜尋熱度（Google 趨勢，台灣機房抓）、討論量（Google 收錄的 Dcard／PTT／Mobile01／痞客邦）、新聞量 ----------
VOICE_KW_PATH = ROOT / "ops" / "voice_keywords.json"
VOICE_SITES = [("Dcard", "dcard.tw"), ("PTT", "ptt.cc"), ("Mobile01", "mobile01.com"), ("痞客邦", "pixnet.net")]
GNEWS = "https://news.google.com/rss/search"


def _gnews_full(q):
    from email.utils import parsedate_to_datetime
    r = get(GNEWS, params={"q": q, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"})
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        try:
            at = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        t = html_mod.unescape((it.findtext("title") or "").strip())
        src = (it.find("source").text if it.find("source") is not None else "") or ""
        t = re.sub(r"\s+-\s+" + re.escape(src) + r"\s*$", "", t) if src else t
        out.append({"title": t[:120], "url": (it.findtext("link") or "").strip(), "at": at.isoformat().replace("+00:00", "Z"), "source": src[:30]})
    return out


def p_voice():
    """每個關鍵字三種訊號：搜尋熱度、討論量（依平台）、新聞量；附 30 天每日新聞量與自動判讀。"""
    cfg = json.loads(VOICE_KW_PATH.read_text(encoding="utf-8"))
    kws, groups = cfg["keywords"], cfg.get("groups") or {}
    try:
        gt = relay_get("latest/gtrends", 60 * 24)
    except Exception as e:  # noqa: BLE001
        gt = {"kw": {}, "errs": {"_": safe_err(e)}}
    now = NOW.astimezone(timezone.utc)
    d30 = now - timedelta(days=30)
    d7 = now - timedelta(days=7)
    days = [(now - timedelta(days=29 - i)).astimezone(TPE).strftime("%Y-%m-%d") for i in range(30)]
    out, errs = [], []
    for kw in kws:
        q = kw["q"]
        row = {"k": kw["k"], "q": q, "group": kw.get("group", ""), **({"ref": True} if kw.get("ref") else {})}
        try:
            news = [x for x in _gnews_full(" ".join(f'"{w}"' for w in q.split()) + " when:30d") if datetime.fromisoformat(x["at"].replace("Z", "+00:00")) >= d30]
            row["news30"] = len(news)
            row["news7"] = sum(1 for x in news if datetime.fromisoformat(x["at"].replace("Z", "+00:00")) >= d7)
            cnt = {d: 0 for d in days}
            for x in news:
                dd = datetime.fromisoformat(x["at"].replace("Z", "+00:00")).astimezone(TPE).strftime("%Y-%m-%d")
                if dd in cnt:
                    cnt[dd] += 1
            row["news_daily"] = [cnt[d] for d in days]
            row["news_top"] = news[:3]
        except Exception as e:  # noqa: BLE001
            errs.append(f"{kw['k']} 新聞: {safe_err(e)}")
        try:  # 媒體年增：近 7 天 vs 去年同 7 天（Google 新聞 after:/before:，一次最多回 100 則）
            qq = " ".join(f'"{w}"' for w in q.split())
            t1 = NOW.astimezone(TPE).date() + timedelta(days=1)
            t0 = t1 - timedelta(days=7)
            def _win(a, b):
                lo, hi = datetime(a.year, a.month, a.day, tzinfo=TPE), datetime(b.year, b.month, b.day, tzinfo=TPE)
                return [x for x in _gnews_full(f"{qq} after:{a.isoformat()} before:{b.isoformat()}")
                        if lo <= datetime.fromisoformat(x["at"].replace("Z", "+00:00")) < hi]
            cur = _win(t0, t1)
            time.sleep(0.4)
            ly = _win(t0 - timedelta(days=364), t1 - timedelta(days=364))
            row["media7"], row["media7_ly"] = len(cur), len(ly)
            row["media_capped"] = len(cur) >= 90
            if not row["media_capped"]:
                row["_mratio"] = max(len(cur), 1) / max(len(ly), 3)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{kw['k']} 媒體年增: {safe_err(e)}")
        disc, ditems = {}, []
        for nm, site in VOICE_SITES:
            try:
                got = [x for x in _gnews_full(" ".join(f'"{w}"' for w in q.split()) + f" site:{site}")]
                recent = [x for x in got if datetime.fromisoformat(x["at"].replace("Z", "+00:00")) >= now - timedelta(days=90)]
                disc[nm] = len(recent)
                ditems += [{**x, "src": nm} for x in recent[:3]]
            except Exception as e:  # noqa: BLE001
                errs.append(f"{kw['k']} {nm}: {safe_err(e)}")
            time.sleep(0.4)
        row["disc90"] = disc
        row["disc_total"] = sum(disc.values())
        row["disc_top"] = sorted(ditems, key=lambda x: x["at"], reverse=True)[:4]
        tr = (gt.get("kw") or {}).get(kw["k"]) or []
        vals = [v for _, v in tr]
        row["trend"] = vals[-260:]  # 5 年每週
        if len(vals) >= 60:
            zeros = sum(1 for v in vals[-104:] if not v)
            mean = lambda a: sum(a) / len(a) if a else 0  # noqa: E731
            last4, prev12, ly4 = vals[-4:], vals[-16:-4], vals[-56:-52]
            row["trend_level"] = round(mean(last4))
            if zeros > 20 or not mean(prev12):  # 近兩年有 20 週以上是 0：量太低
                row["trend_sparse"] = True
            else:
                row["trend_chg"] = round((mean(last4) - mean(prev12)) / mean(prev12) * 100)  # 近一月 vs 前三個月
                if mean(ly4):
                    row["trend_yoy"] = round((mean(last4) - mean(ly4)) / mean(ly4) * 100)  # 年增（同期比，扣掉季節性）
            pk = max(range(len(vals)), key=lambda i: vals[i])
            row["trend_peak"] = tr[pk][0][:7]
        # 自動判讀（找機會用）：新聞與討論的來源最多回 100 則，大字會頂到上限，所以主訊號看搜尋變化
        hist_put("voice_news", kw["k"], NOW.astimezone(TPE).strftime("%Y-%m-%d"), row.get("news7", 0))
        out.append(row)
    # Google 新聞的舊文章會慢慢掉出索引，去年同期一定比較少；用全部關鍵字的中位數當基準校正
    rs = sorted(r["_mratio"] for r in out if "_mratio" in r)
    base = rs[len(rs) // 2] if rs else 1
    sup_pat = {kw["k"]: kw.get("supply") for kw in kws}
    try:
        tcodes = json.loads(TAXREG_CODES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        tcodes = None
    for row in out:
        sp = taxreg_supply(sup_pat.get(row["k"]), tcodes) if tcodes else None
        if sp:
            row["supply"] = sp
        mr = row.pop("_mratio", None)
        if mr is not None:
            row["media_yoy"] = round((mr / base - 1) * 100)
        kw = {"k": row["k"], "ref": row.get("ref")}
        c, y = row.get("trend_chg"), row.get("trend_yoy")
        my, capped = row.get("media_yoy"), row.get("media_capped")
        g = y if y is not None else c  # 主看搜尋年增（扣季節性），沒有就看近一月
        if kw.get("ref"):
            tag = "對照組：" + ("在降溫" if g is not None and g <= -15 else "回溫中" if g is not None and g >= 15 else "持平")
        elif kw["k"] not in (gt.get("kw") or {}):
            tag = "搜尋趨勢抓取中"
        elif g is None:
            tag = "搜尋量太低，數字不穩"
        elif g >= 20 and (c or 0) >= -10 and not capped and my is not None and my <= g / 2 and (sy := (row.get("supply") or {}).get("yoy")) is not None and sy <= g / 2:
            tag = "機會窗口：需求在長，媒體和新店都還沒跟上"
        elif g >= 20 and (c or 0) >= -10 and (sy := (row.get("supply") or {}).get("yoy")) is not None and sy >= 15:
            tag = "需求在長，新店也在湧入：競爭變多"
        elif g >= 20 and (c or 0) >= -10 and not capped and my is not None and my <= g / 2:
            tag = "搜尋長得比媒體快（供給面沒有對應資料）" if not row.get("supply") else "搜尋長得比媒體快"
        elif g >= 15 and capped:
            tag = "正在發燒：媒體已經全面跟上"
        elif g >= 15 and (c or 0) >= -10:
            tag = "還在升溫：媒體也在跟"
        elif g >= 15:
            tag = "一年來在升、最近一個月放緩"
        elif g <= -15 and ((my or 0) >= 15 or capped):
            tag = "搜尋在降、媒體還在炒：小心追高"
        elif g <= -15:
            tag = "在降溫"
        elif (c or 0) >= 20:
            tag = "最近一個月突然升溫：觀察是不是新趨勢"
        else:
            tag = "平穩"
        row["tag"] = tag
    for k, e in (gt.get("errs") or {}).items():
        if k == "_cookies" or (k.startswith("_") and gt.get("kw")):
            continue
        errs.append(f"搜尋趨勢 {k}: {e}"[:160])
    return {"label": "Google 趨勢・Google 新聞收錄", "kw": out, "media_base": round(base, 2), "groups": groups, "gt_at": gt.get("at"), "errs": errs[:12]}


# ---------- 流行排行：Spotify、Netflix、Apple Podcast、KKBOX、LINE TODAY（台灣） ----------
def p_pop():
    out, errs = {}, []
    try:  # Spotify 台灣每日（kworb 整理官方排行）
        r = get("https://kworb.net/spotify/country/tw_daily.html")
        txt = r.content.decode("utf-8", "replace")
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", txt, re.S)[1:21]:
            cells = [html_mod.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) >= 7 and cells[0].isdigit():
                at = cells[2].split(" - ", 1)
                rows.append({"rank": int(cells[0]), "move": cells[1], "artist": at[0], "title": at[1] if len(at) > 1 else "", "days": num(cells[3]), "streams": num(cells[6])})
        out["spotify"] = rows
    except Exception as e:  # noqa: BLE001
        errs.append("Spotify: " + safe_err(e))
    try:  # Netflix 官方每週前十（全球檔，只取台灣最新一週）
        r = get("https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv", timeout=90)
        lines = [l.split("\t") for l in r.content.decode("utf-8", "replace").splitlines() if "\tTW\t" in l]
        wk = max(l[2] for l in lines)
        nf = {"week": wk, "films": [], "tv": []}
        for l in lines:
            if l[2] != wk:
                continue
            item = {"rank": int(l[4]), "title": l[6] if l[6] not in ("N/A", "") else l[5], "show": l[5], "weeks": int(num(l[7]) or 1)}
            (nf["films"] if l[3] == "Films" else nf["tv"]).append(item)
        nf["films"].sort(key=lambda x: x["rank"]); nf["tv"].sort(key=lambda x: x["rank"])
        out["netflix"] = nf
    except Exception as e:  # noqa: BLE001
        errs.append("Netflix: " + safe_err(e))
    try:  # Apple Podcast 台灣熱門
        j = gjson("https://rss.applemarketingtools.com/api/v2/tw/podcasts/top/25/podcasts.json")
        out["podcast"] = [{"rank": i + 1, "title": x.get("name", ""), "artist": x.get("artistName", ""), "url": x.get("url", ""),
                           "genre": ((x.get("genres") or [{}])[0] or {}).get("name", "")} for i, x in enumerate(j["feed"]["results"][:20])]
    except Exception as e:  # noqa: BLE001
        errs.append("Podcast: " + safe_err(e))
    try:  # KKBOX 每日單曲（華語）
        j = gjson("https://kma.kkbox.com/charts/api/v1/daily", params={"category": "297", "lang": "tc", "limit": "20", "terr": "tw", "type": "song"})
        songs = (((j.get("data") or {}).get("charts") or {}).get("song") or [])
        out["kkbox"] = [{"rank": x["rankings"]["this_period"], "last": x["rankings"].get("last_period"), "title": x.get("song_name", ""),
                         "artist": x.get("artist_name", ""), "url": x.get("song_url", "")} for x in songs[:20]]
    except Exception as e:  # noqa: BLE001
        errs.append("KKBOX: " + safe_err(e))
    try:  # LINE TODAY 即時熱門
        r = get("https://today.line.me/tw/v2/tab/top")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        fb = json.loads(m.group(1))["props"]["pageProps"]["fallback"]
        best = []
        for k, v in fb.items():
            arts = v if isinstance(v, list) else (v.get("items") or v.get("articles") or []) if isinstance(v, dict) else []
            arts = [a for a in arts if isinstance(a, dict) and a.get("title")]
            if len(arts) > len(best):
                best = arts
        out["line"] = [{"rank": i + 1, "title": a["title"], "source": a.get("publisher", ""), "cat": a.get("categoryName", ""),
                        "url": ("https://today.line.me/tw/v2/article/" + a["url"]["hash"]) if isinstance(a.get("url"), dict) and a["url"].get("hash") else ""}
                       for i, a in enumerate(best[:15])]
    except Exception as e:  # noqa: BLE001
        errs.append("LINE TODAY: " + safe_err(e))
    if not out:
        raise RuntimeError("pop: nothing " + "; ".join(errs)[:160])
    return {"label": "Spotify・Netflix・Apple Podcast・KKBOX・LINE TODAY", **out, "errs": errs}


# ---------- 國道・省道即時路況（彰化機房抓的高公局、公路局資料） ----------
ROADS_GEO_PATH = DATA / "roads_geo.json"
ROADS_LIVE_PATH = DATA / "roads_live.json"
DIR_ZH = {"N": "北", "S": "南", "E": "東", "W": "西", "B": "雙向"}
_dz = lambda x: f"{DIR_ZH[x]}向" if x in DIR_ZH else ""
CMS_KW = re.compile(r"施工|事故|封閉|封\(|封）|管制|壅塞|回堵|故障|注意|颱風|豪雨|大雨|濃霧|霧|落石|坍方|車禍|散落|改道|地震|強風|拋錨|火警|路面")


def _wkt_line(t):
    m = re.search(r"\(([^()]*)\)", str(t or ""))
    if not m:
        return []
    out = []
    for pt in m.group(1).split(","):
        xy = pt.split()
        if len(xy) >= 2:
            try:
                out.append((float(xy[0]), float(xy[1])))
            except ValueError:
                pass
    return out


def _dp(pts, tol):
    """Douglas-Peucker 簡化（度）。"""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        L = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / L
            if d > best:
                best, bi = d, i
        if best > tol and bi > 0:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [q for q, k in zip(pts, keep) if k]


# eTag 常用路段旅行時間：門架編號本身帶路線與里程（01F0017N＝國1 1.7K 北向）
ETAG_CORR = [("台北→新竹", "01F", "S", 23, 95), ("新竹→台北", "01F", "N", 23, 95),
             ("新竹→台中", "01F", "S", 95, 178), ("台中→新竹", "01F", "N", 95, 178),
             ("南港→頭城（雪隧）", "05F", "S", 0, 30), ("頭城→南港（雪隧）", "05F", "N", 0, 30)]


def _gid(g):
    m = re.match(r"(\d\d[A-Z])(\d{4})([NSEW])", str(g or ""))
    return (m.group(1), int(m.group(2)) / 10, m.group(3)) if m else None


def _etag_corridors(key):
    live = relay_rows(relay_get("latest/fw_etag", 30))
    pairs = {r["ETagPairID"]: r for r in relay_rows(relay_get("static/fw_etagpair"))}
    out = []
    for label, road, d, lo, hi in ETAG_CORR:
        tt = dist = 0.0
        n_ = 0
        for r in live:
            p_ = pairs.get(r.get("ETagPairID")) or {}
            a, b = _gid(p_.get("StartETagGantryID")), _gid(p_.get("EndETagGantryID"))
            if not a or not b or a[0] != road or a[2] != d or b[0] != road:
                continue
            if not (lo <= min(a[1], b[1]) and max(a[1], b[1]) <= hi):
                continue
            car = next((f for f in (r.get("Flows") or []) if isinstance(f, dict) and str(f.get("VehicleType")) == "31"
                        and (num(f.get("TravelTime")) or 0) > 0), None)
            if not car:
                continue
            tt += num(car["TravelTime"]); dist += num(p_.get("Distance")) or abs(b[1] - a[1]); n_ += 1
        L = hi - lo
        if not n_ or dist < L * 0.6:
            continue
        mins = tt / 60 * L / dist  # 少數門架沒資料時按里程補齊
        ideal = L / 90 * 60
        hist_put("etag", label, key, round(mins, 1))
        out.append({"label": label, "min": round(mins), "ideal": round(ideal), "delay": round(mins - ideal), "km": L,
                    "cover": round(dist / L * 100), "spark": hist_get("etag", label, 48)})
    return out


def _roads_geo():
    """路段形狀（一天換一次）：{v, fw:{ids, n, c}, thb:{ids, n, c}}；c 是 [經度*1e4, 緯度*1e4, ...]。"""
    fs, fg = relay_get("static/fw_section"), relay_get("static/fw_shape")
    ts, tg = relay_get("static/thb_section"), relay_get("static/thb_shape")
    v = f'{fg.get("at")}|{tg.get("at")}|{fs.get("at")}|{ts.get("at")}'
    if ROADS_GEO_PATH.exists():
        try:
            old = json.loads(ROADS_GEO_PATH.read_text(encoding="utf-8"))
            if old.get("v") == v:
                return old
        except Exception:  # noqa: BLE001
            pass
    out = {"v": v}
    for key, sec, shp, tol in (("fw", fs, fg, 0.00025), ("thb", ts, tg, 0.0004)):
        names = {}
        for r in relay_rows(sec):
            if key == "fw":
                names[r["SectionID"]] = f'{r.get("RoadName", "")}{_dz(r.get("RoadDirection"))} {r.get("RoadSection.Start", "")}→{r.get("RoadSection.End", "")}'
            else:
                names[r["SectionID"]] = f'{r.get("RoadName", "")}{_dz(r.get("RoadDirection"))} {r.get("SectionMile.StartKM", "")}～{r.get("SectionMile.EndKM", "")}'
        ids, nm, cs = [], [], []
        for sid, wkt in shp["rows"]:
            pts = _dp(_wkt_line(wkt), tol)
            if len(pts) < 2 or not all(118 < x < 123 and 21 < y < 27 for x, y in pts):
                continue
            flat = []
            for x, y in pts:
                flat += [round(x * 1e4), round(y * 1e4)]
            ids.append(sid); nm.append(names.get(sid, "")); cs.append(flat)
        out[key] = {"ids": ids, "n": nm, "c": cs}
    write_json(ROADS_GEO_PATH, out, separators=(",", ":"))
    return out


def p_roads():
    """全台國道與省道即時路況：各國道均速、最塞區間、省道壅塞路段、即時事件、看板訊息、路況新聞。"""
    key = NOW.astimezone(TPE).strftime("%Y-%m-%dT%H:%M")
    errs = []
    fl = relay_get("latest/fw_live", 30)
    sec = {r["SectionID"]: r for r in relay_rows(relay_get("static/fw_section"))}
    fw = []
    for r in relay_rows(fl):
        s_ = sec.get(r.get("SectionID"))
        spd = num(r.get("TravelSpeed"))
        if not s_ or not spd or spd <= 0:
            continue
        fw.append({"id": r["SectionID"], "road": s_.get("RoadName", ""), "dir": DIR_ZH.get(s_.get("RoadDirection"), ""),
                   "from": s_.get("RoadSection.Start", ""), "to": s_.get("RoadSection.End", ""), "km": s_.get("SectionMile.StartKM", ""),
                   "len": num(s_.get("SectionLength")) or 0, "spd": spd})
    agg: dict = {}
    for x in fw:
        a = agg.setdefault((x["road"], x["dir"]), [0.0, 0.0, 0.0])
        a[0] += x["spd"] * x["len"]; a[1] += x["len"]; a[2] += x["len"] if x["spd"] < 60 else 0
    roads = []
    rk = lambda t: (int(re.search(r"\d+", t[0]).group()) if re.search(r"\d+", t[0]) else 99, t[0], t[1])
    for (road, d), (w, L, slow) in sorted(agg.items(), key=lambda kv: rk(kv[0])):
        if L < 8:
            continue
        avg = round(w / L, 1)
        hist_put("fw_road", road + d, key, avg)
        roads.append({"road": road, "dir": d, "speed": avg, "km": round(L, 1), "slow_km": round(slow, 1), "spark": hist_get("fw_road", road + d, 48)})
    # 國道色帶：國 1／3／5 主線依里程排好的 [起 km, 迄 km, 車速, 名稱]
    def _km(v):
        m = re.match(r"\s*(\d+)\s*[kK]\s*\+?\s*(\d*)", str(v or ""))
        return round(int(m.group(1)) + int(m.group(2) or 0) / 1000, 2) if m else None
    strips: dict = {}
    for x in fw:
        if x["road"] not in ("國道1號", "國道3號", "國道5號"):
            continue
        s_ = sec.get(x["id"]) or {}
        a, b = _km(s_.get("SectionMile.StartKM")), _km(s_.get("SectionMile.EndKM"))
        if a is None or b is None:
            continue
        strips.setdefault(x["road"], {}).setdefault(x["dir"], []).append([min(a, b), max(a, b), round(x["spd"]), f'{x["from"]}→{x["to"]}'])
    for r_ in strips.values():
        for d_ in r_:
            r_[d_].sort()
    jams = [{"title": f'{x["road"]}{x["dir"]}向 {x["from"]}→{x["to"]}', "road": x["road"], "dir": x["dir"], "km": x["km"], "speed": round(x["spd"])}
            for x in sorted((x for x in fw if x["spd"] < 50), key=lambda x: x["spd"])[:12]]
    slow_km = round(sum(x["len"] for x in fw if x["spd"] < 60), 1)
    hist_put("fw_road", "_slow_km", key, slow_km)

    thb = {"levels": {}, "jams": [], "roads": []}
    tl_rows = []
    try:
        tsec = {r["SectionID"]: r for r in relay_rows(relay_get("static/thb_section"))}
        tl_rows = relay_rows(relay_get("latest/thb_live", 30))
        lv: dict = {}
        per: dict = {}
        tj = []
        for r in tl_rows:
            lvl = int(num(r.get("CongestionLevel")) or 0)
            lv[lvl] = lv.get(lvl, 0) + 1
            s_ = tsec.get(r.get("SectionID")) or {}
            road = s_.get("RoadName") or ""
            spd = num(r.get("TravelSpeed"))
            if road:
                pr = per.setdefault(road, [0, 0])
                pr[0] += 1; pr[1] += 1 if lvl == 3 else 0
            if lvl in (2, 3) and spd and spd > 0 and road:
                tj.append({"title": f'{road}{_dz(s_.get("RoadDirection"))} {s_.get("SectionMile.StartKM", "")}～{s_.get("SectionMile.EndKM", "")}',
                           "road": road, "speed": round(spd), "lvl": lvl})
        names = {-1: "封閉", 0: "資料不足", -99: "資料不足", 1: "順暢", 2: "車多", 3: "壅塞"}
        for k_, v_ in sorted(lv.items()):
            nm_ = names.get(k_, str(k_))
            thb["levels"][nm_] = thb["levels"].get(nm_, 0) + v_
        thb["jams"] = sorted(tj, key=lambda x: (-x["lvl"], x["speed"]))[:12]
        thb["roads"] = [{"road": r, "n": n_, "jam": j} for r, (n_, j) in sorted(per.items(), key=lambda kv: -kv[1][1]) if j][:10]
        hist_put("thb", "_jam", key, lv.get(3, 0))
    except Exception as e:  # noqa: BLE001
        errs.append("省道: " + safe_err(e))

    etag = []
    try:
        etag = _etag_corridors(key)
    except Exception as e:  # noqa: BLE001
        errs.append("eTag: " + safe_err(e))

    events = []
    try:
        for r in relay_rows(relay_get("latest/fw_events", 30)):
            m = re.search(r"POINT\s*\(\s*([\d.]+)\s+([\d.]+)", str(r.get("Positions") or ""))
            events.append({"title": str(r.get("Description") or r.get("EventTitle") or "")[:160], "kind": str(r.get("EventTitle") or "").replace("事件", ""),
                           "road": r.get("Location.FreeExpressHighway.Road") or "", "dir": r.get("Location.FreeExpressHighway.Direction") or "",
                           "km": r.get("Location.FreeExpressHighway.StartKM") or "", "at": r.get("EffectiveTime") or r.get("PublishTime") or "",
                           "impact": r.get("Impact.Description") or "", "block": num(r.get("Impact.BlockedLanes")),
                           "ll": [float(m.group(1)), float(m.group(2))] if m else None})
        events.sort(key=lambda x: str(x["at"]), reverse=True)
    except Exception as e:  # noqa: BLE001
        errs.append("國道事件: " + safe_err(e))
    kinds: dict = {}
    for x in events:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1

    cms: dict = {}
    for k in ("fw_cms", "thb_cms"):
        try:
            for r in relay_rows(relay_get(f"latest/{k}", 30)):
                texts = [r.get("Messages.Message.Text")]
                for m_ in r.get("Messages") or []:
                    if isinstance(m_, dict):
                        texts.append(m_.get("Text") or m_.get("Message.Text"))
                for t in texts:
                    t = re.sub(r"\s+", " ", str(t or "")).strip()
                    if len(t) >= 4 and CMS_KW.search(t):
                        c = cms.setdefault(t, {"title": t[:80], "n": 0, "src": "國道" if k == "fw_cms" else "省道"})
                        c["n"] += 1
        except Exception as e:  # noqa: BLE001
            errs.append(f"{k}: " + safe_err(e))
    cutoff = (NOW.astimezone(TPE) - timedelta(days=3)).isoformat()
    news = []
    for k, src in (("thb_news", "公路局"), ("fw_news", "高公局")):
        try:
            for r in relay_rows(relay_get(f"latest/{k}", 60)):
                at = str(r.get("PublishTime") or r.get("UpdateTime") or "")
                if at and at.replace(" ", "T") < cutoff:
                    continue
                if k == "fw_news" and len(str(r.get("Title") or "")) < 8:  # 高公局只有「出口壅塞」這種分類標題的，事件區已經有
                    continue
                news.append({"title": str(r.get("Title") or "")[:120], "desc": str(r.get("Description") or "")[:200],
                             "url": r.get("NewsURL") or "", "source": src, "at": at})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{k}: " + safe_err(e))
    news.sort(key=lambda x: x["at"], reverse=True)

    # 地圖用：路段形狀（一天換一次）＋這輪的車速／壅塞等級
    try:
        g = _roads_geo()
        fs = {x["id"]: round(x["spd"]) for x in fw}
        tl = {r.get("SectionID"): (int(num(r.get("CongestionLevel")) or 0), round(num(r.get("TravelSpeed")) or 0)) for r in tl_rows}
        write_json(ROADS_LIVE_PATH, {"at": fl.get("at"), "v": g["v"], "fw": [fs.get(i, -1) for i in g["fw"]["ids"]],
                                     "thbL": [tl.get(i, (0, 0))[0] for i in g["thb"]["ids"]], "thbS": [tl.get(i, (0, 0))[1] for i in g["thb"]["ids"]]},
                   separators=(",", ":"))
    except Exception as e:  # noqa: BLE001
        errs.append("地圖路段: " + safe_err(e))

    return {"label": "高公局・公路局（彰化機房每 5 分鐘）", "asOf": (fl.get("meta") or {}).get("UpdateTime") or fl.get("at"),
            "fw": {"strips": strips, "roads": roads, "jams": jams, "slow_km": slow_km, "slow_spark": hist_get("fw_road", "_slow_km", 48), "n": len(fw)},
            "thb": {**thb, "n": len(tl_rows), "jam_spark": hist_get("thb", "_jam", 48)},
            "etag": etag, "events": events[:80], "kinds": kinds, "cms": sorted(cms.values(), key=lambda c: -c["n"])[:30], "news": news[:30], "errs": errs}


def p_airport():
    """桃機今日出發／抵達：班次、延誤、取消，與接下來 8 班出發（桃園機場官網航班檔）。"""
    r = get(TPE_AIR_URL, headers={"Referer": "https://www.taoyuan-airport.com/"})
    txt = r.content.decode("cp950", errors="replace")
    now_tpe = NOW.astimezone(TPE)
    today = now_tpe.strftime("%Y/%m/%d")
    out = {k: {"total": 0, "delayed": 0, "cancelled": 0, "upcoming": []} for k in ("dep", "arr")}
    seen = set()
    for line in txt.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 14 or f[1] not in ("A", "D"):
            continue
        kind = "dep" if f[1] == "D" else "arr"
        try:
            sched = datetime.strptime(f"{f[6]} {f[7]}", "%Y/%m/%d %H:%M:%S").replace(tzinfo=TPE)
            est = datetime.strptime(f"{f[8]} {f[9]}", "%Y/%m/%d %H:%M:%S").replace(tzinfo=TPE) if f[8] and f[9] else None
        except ValueError:
            continue
        k = (kind, f[6], f[7], f[10], f[5] or f[0])  # 共掛班號（同時間、同航點、同登機門）只算一次
        if k in seen:
            continue
        seen.add(k)
        status = f[13].upper()
        zh = re.sub(r"[A-Za-z ]+", "", f[13])
        late = est is not None and (est - sched) >= timedelta(minutes=30)
        if f[6] == today:
            o = out[kind]
            o["total"] += 1
            if "CANCEL" in status:
                o["cancelled"] += 1
            elif "DELAY" in status or late:
                o["delayed"] += 1
        if (kind == "dep" and sched >= now_tpe - timedelta(minutes=5) and sched <= now_tpe + timedelta(hours=12)
                and not any(w in status for w in ("CANCEL", "DEPARTED"))):
            out["dep"]["upcoming"].append({"flight": f"{f[2]}{f[4].lstrip()}", "to": f[10], "sched": sched.strftime("%H:%M"),
                                           "est": est.strftime("%H:%M") if est else "", "remark": zh[:4], "gate": f[5][:4], "_t": sched})
    up = sorted(out["dep"]["upcoming"], key=lambda x: x["_t"])[:8]
    for u in up:
        u.pop("_t", None)
    out["dep"]["upcoming"] = up
    if not out["dep"]["total"] and not out["arr"]["total"]:
        raise RuntimeError("airport: empty")
    out["label"] = "桃園機場"
    return out


# ---------- 台灣現場：各縣市現況（災害示警、停班停課、各地新聞）與油價 ----------
# 國家災防中心 CAP 示警（全台、不用金鑰；同一來源 3 秒內不能重打）、人事總處停班停課、中油牌價、Google News 依縣市。
TW_COUNTIES = {  # 名稱：(經度, 緯度, 標題裡會出現的寫法)
    "臺北市": (121.56, 25.05, ("臺北市", "台北市", "北市")), "新北市": (121.47, 25.01, ("新北",)), "基隆市": (121.74, 25.13, ("基隆",)),
    "桃園市": (121.22, 24.93, ("桃園", "桃市")), "新竹市": (120.97, 24.80, ("新竹市", "竹市")), "新竹縣": (121.12, 24.70, ("新竹縣", "竹縣", "竹北")),
    "苗栗縣": (120.87, 24.49, ("苗栗",)), "臺中市": (120.68, 24.16, ("臺中", "台中", "中市")), "彰化縣": (120.50, 24.00, ("彰化",)),
    "南投縣": (120.90, 23.85, ("南投",)), "雲林縣": (120.39, 23.70, ("雲林",)), "嘉義市": (120.45, 23.48, ("嘉義市", "嘉市")),
    "嘉義縣": (120.40, 23.43, ("嘉義縣", "嘉縣")), "臺南市": (120.22, 23.00, ("臺南", "台南", "南市")), "高雄市": (120.31, 22.63, ("高雄", "高市")),
    "屏東縣": (120.55, 22.55, ("屏東",)), "宜蘭縣": (121.75, 24.70, ("宜蘭",)), "花蓮縣": (121.55, 23.90, ("花蓮",)),
    "臺東縣": (121.10, 22.80, ("臺東", "台東")), "澎湖縣": (119.58, 23.57, ("澎湖",)), "金門縣": (118.35, 24.45, ("金門",)),
    "連江縣": (119.95, 26.15, ("連江", "馬祖")),
}
# 鄉鎮市區 → 縣市（只收全台唯一的名稱；東區、中正區這類多縣市都有的不收）
TW_AREAS = {"臺北市": "內湖區 北投區 南港區 士林區 大同區 文山區 松山區 萬華區", "基隆市": "七堵區 仁愛區 安樂區 暖暖區", "新北市": "三峽區 三芝區 三重區 中和區 五股區 八里區 土城區 坪林區 平溪區 新店區 新莊區 板橋區 林口區 樹林區 永和區 汐止區 泰山區 淡水區 深坑區 烏來區 瑞芳區 石碇區 石門區 萬里區 蘆洲區 貢寮區 金山區 雙溪區 鶯歌區", "連江縣": "北竿鄉 南竿鄉 東引鄉 莒光鄉", "宜蘭縣": "三星鄉 五結鄉 冬山鄉 南澳鄉 員山鄉 壯圍鄉 大同鄉 宜蘭市 礁溪鄉 羅東鎮 蘇澳鎮 釣魚臺 頭城鎮", "新竹市": "香山區", "新竹縣": "五峰鄉 北埔鄉 寶山鄉 尖石鄉 峨眉鄉 新埔鎮 新豐鄉 橫山鄉 湖口鄉 竹北市 竹東鎮 芎林鄉 關西鎮", "桃園市": "中壢區 八德區 大園區 大溪區 平鎮區 復興區 新屋區 桃園區 楊梅區 蘆竹區 觀音區 龍潭區 龜山區", "苗栗縣": "三灣鄉 三義鄉 公館鄉 卓蘭鎮 南庄鄉 大湖鄉 後龍鎮 泰安鄉 獅潭鄉 竹南鎮 苑裡鎮 苗栗市 西湖鄉 通霄鎮 造橋鄉 銅鑼鄉 頭份市 頭屋鄉", "臺中市": "中區 北屯區 南屯區 后里區 和平區 外埔區 大甲區 大肚區 大里區 大雅區 太平區 新社區 東勢區 梧棲區 沙鹿區 清水區 潭子區 烏日區 石岡區 神岡區 西屯區 豐原區 霧峰區 龍井區", "彰化縣": "二林鎮 二水鄉 伸港鄉 北斗鎮 和美鎮 員林市 埔心鄉 埔鹽鄉 埤頭鄉 大城鄉 大村鄉 彰化市 永靖鄉 溪州鄉 溪湖鎮 田中鎮 田尾鄉 社頭鄉 福興鄉 秀水鄉 竹塘鄉 線西鄉 芬園鄉 花壇鄉 芳苑鄉 鹿港鎮", "南投縣": "中寮鄉 仁愛鄉 信義鄉 南投市 名間鄉 國姓鄉 埔里鎮 水里鄉 竹山鎮 草屯鎮 集集鎮 魚池鄉 鹿谷鄉", "嘉義縣": "中埔鄉 六腳鄉 大埔鄉 大林鎮 太保市 布袋鎮 新港鄉 朴子市 東石鄉 梅山鄉 民雄鄉 水上鄉 溪口鄉 番路鄉 竹崎鄉 義竹鄉 阿里山鄉 鹿草鄉", "雲林縣": "二崙鄉 元長鄉 北港鎮 口湖鄉 古坑鄉 四湖鄉 土庫鎮 大埤鄉 崙背鄉 斗六市 斗南鎮 東勢鄉 林內鄉 水林鄉 臺西鄉 莿桐鄉 虎尾鎮 褒忠鄉 西螺鎮 麥寮鄉", "臺南市": "七股區 下營區 中西區 仁德區 佳里區 六甲區 北門區 南化區 善化區 大內區 學甲區 安南區 安定區 安平區 官田區 將軍區 山上區 左鎮區 後壁區 新化區 新市區 新營區 東山區 柳營區 楠西區 歸仁區 永康區 玉井區 白河區 西港區 關廟區 鹽水區 麻豆區 龍崎區", "高雄市": "三民區 仁武區 內門區 六龜區 前金區 前鎮區 南沙群島 大寮區 大樹區 大社區 小港區 岡山區 左營區 彌陀區 新興區 旗山區 旗津區 杉林區 東沙群島 林園區 桃源區 梓官區 楠梓區 橋頭區 永安區 湖內區 燕巢區 田寮區 甲仙區 美濃區 苓雅區 茂林區 茄萣區 路竹區 那瑪夏區 阿蓮區 鳥松區 鳳山區 鹽埕區 鼓山區", "澎湖縣": "七美鄉 望安鄉 湖西鄉 白沙鄉 西嶼鄉 馬公市", "金門縣": "烈嶼鄉 烏坵鄉 金城鎮 金寧鄉 金沙鎮 金湖鎮", "屏東縣": "三地門鄉 九如鄉 佳冬鄉 來義鄉 內埔鄉 南州鄉 屏東市 崁頂鄉 恆春鎮 新園鄉 新埤鄉 春日鄉 東港鎮 枋寮鄉 枋山鄉 林邊鄉 泰武鄉 滿州鄉 潮州鎮 牡丹鄉 獅子鄉 琉球鄉 瑪家鄉 竹田鄉 萬丹鄉 萬巒鄉 車城鄉 里港鄉 長治鄉 霧臺鄉 高樹鄉 鹽埔鄉 麟洛鄉", "臺東縣": "卑南鄉 大武鄉 太麻里鄉 延平鄉 成功鎮 東河鄉 池上鄉 海端鄉 綠島鄉 臺東市 蘭嶼鄉 達仁鄉 金峰鄉 長濱鄉 關山鎮 鹿野鄉", "花蓮縣": "光復鄉 卓溪鄉 吉安鄉 壽豐鄉 富里鄉 新城鄉 玉里鎮 瑞穗鄉 秀林鄉 花蓮市 萬榮鄉 豐濱鄉 鳳林鎮"}
AREA_TO_COUNTY = {a: c for c, v in TW_AREAS.items() for a in v.split()}
NCDR_FEED = "https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx"
DGPA_URL = "https://www.dgpa.gov.tw/typh/daily/nds.html"
CPC_URL = "https://vipmbr.cpc.com.tw/cpcstn/ListPriceWebService.asmx/getCPCMainProdListPrice_XML"
# 類別嚴重度：3＝可能危及安全、2＝需要注意、1＝生活影響（停水只算數量，不上地圖色）
ALERT_LEVEL = {"颱風": 3, "地震": 3, "土石流": 3, "淹水": 3, "疏散避難": 3, "海嘯": 3, "降雨": 2, "雷雨": 2, "強風": 2, "高溫": 2, "低溫": 2,
               "濃霧": 2, "道路封閉": 2, "鐵路事故": 2, "水庫放流": 2, "停電": 2, "火災": 1, "停水": 1, "空氣品質": 1}


def _cap_time(s: str):
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*(上午|下午)?\s*(\d{1,2}):(\d{2}):(\d{2})", (s or "").strip())
    if not m:
        return None
    y, mo, d, ap, hh, mi, ss = m.groups()
    hh = int(hh) % 12 + (12 if ap == "下午" else 0) if ap else int(hh)
    return datetime(int(y), int(mo), int(d), hh, int(mi), int(ss), tzinfo=TPE)


def _counties_in(text: str) -> list:
    out = []
    for name, (_, _, keys) in TW_COUNTIES.items():
        if any(k in text for k in keys):
            out.append(name)
    if not out:  # 只寫了區名（觀音區、龜山區…）：用鄉鎮表反查縣市
        for a, c in AREA_TO_COUNTY.items():
            if a in text and c not in out:
                out.append(c)
    return out


def p_alerts():
    """災害示警（現在仍有效的）＋ 停班停課。"""
    errs, alerts = [], []
    try:
        root = ET.fromstring(get(NCDR_FEED).content)
        ns = {"a": "http://www.w3.org/2005/Atom", "cap": "urn:oasis:names:tc:emergency:cap:1.1"}
        now_tpe = NOW.astimezone(TPE)
        for e in root.findall("a:entry", ns):
            cat = (e.findtext("a:title", "", ns) or "").strip()
            lvl = ALERT_LEVEL.get(cat)
            if not lvl or (e.findtext("cap:msgType", "", ns) or "") == "Cancel":
                continue
            exp = _cap_time(e.findtext("cap:expires", "", ns))
            if exp and exp < now_tpe:
                continue
            text = re.sub(r"<[^>]+>|\s+", " ", html_mod.unescape(e.findtext("a:summary", "", ns) or "")).strip()
            if re.search(r"已結案|已無警戒|解除|恢復供水|已恢復", text):
                continue
            area = _counties_in(text)
            link = e.find("a:link", ns)
            alerts.append({"id": e.findtext("a:id", "", ns), "cat": cat, "lvl": lvl, "area": area, "text": text[:160],
                           "src": (e.findtext("a:author/a:name", "", ns) or "")[:12], "at": _rss_date(e.findtext("a:updated", "", ns) or ""),
                           "exp": exp.isoformat() if exp else "", "url": link.get("href") if link is not None else ""})
    except Exception as e:  # noqa: BLE001
        log("ncdr", e); errs.append("災害示警: " + safe_err(e))
    # 同一類別、同一組縣市只留最新一則（水利署會對同一站連發好幾則）
    seen, uniq = set(), []
    for a in sorted(alerts, key=lambda x: x["at"], reverse=True):
        k = (a["cat"], tuple(a["area"]), a["text"][:24])
        if k in seen:
            continue
        seen.add(k); uniq.append(a)
    stop = {"items": [], "none": None, "updated": ""}
    try:
        t = get(DGPA_URL).content.decode("utf-8", errors="replace")
        m = re.search(r"更新時間：\s*([\d/: ]+)", t)
        stop["updated"] = (m.group(1).strip() if m else "")
        body = t[t.find("Table_Body"):] if "Table_Body" in t else ""
        if "無停班停課訊息" in body[:3000]:
            stop["none"] = True
        else:
            for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", body, re.S | re.I)[:30]:
                cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<TD[^>]*>(.*?)</TD>", tr, re.S | re.I)]
                cells = [c for c in cells if c]
                if len(cells) >= 2 and _counties_in(cells[0]):
                    stop["items"].append({"area": cells[0][:12], "text": cells[1][:120]})
            stop["none"] = not stop["items"]
    except Exception as e:  # noqa: BLE001
        log("dgpa", e); errs.append("停班停課: " + safe_err(e))
    if not uniq and stop["none"] is None:
        raise RuntimeError("alerts: nothing " + "; ".join(errs)[:160])
    return {"alerts": uniq[:80], "n_total": len(uniq), "stopwork": stop, "errs": errs}


def p_oil():
    root = ET.fromstring(get(CPC_URL).content)
    want = {"98無鉛汽油": "98", "95無鉛汽油": "95", "92無鉛汽油": "92", "超級柴油": "柴油"}
    out, eff = [], ""
    for tb in root.iter("Table"):
        name = (tb.findtext("產品名稱") or "").strip()
        if name not in want or "自營站" not in (tb.findtext("交貨地點") or ""):
            continue
        price = num(tb.findtext("參考牌價_金額"))
        d = (tb.findtext("牌價生效日期") or "").strip()
        if len(d) == 7:
            d = f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:7]}"
        eff = eff or d
        hist_put("oil", want[name], d, price)
        hist = hist_get("oil", want[name], 10)  # 依生效日排序；同一天只會有一筆
        chg = round(hist[-1] - hist[-2], 2) if len(hist) >= 2 else None
        out.append({"name": want[name], "price": price, "chg": chg})
    if not out:
        raise RuntimeError("oil: no rows")
    order = ["92", "95", "98", "柴油"]
    out.sort(key=lambda x: order.index(x["name"]))
    return {"items": out, "effective": eff, "label": "中油"}


def p_localnews():
    """各縣市近 24 小時新聞（Google News；標題要真的提到該縣市）。"""
    out, errs = {}, []
    for name, (_, _, keys) in TW_COUNTIES.items():
        try:
            got = _gnews(f"{keys[0]} when:1d", limit=15)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {safe_err(e)}"); continue
        items = []
        for it in got:
            if not any(k in it["title"] for k in keys) or WATCH_SRC_BLOCK.search(it.get("source", "")) or CROWD_SRC_BLOCK.search(it.get("source", "")):
                continue
            items.append({"title": it["title"][:70], "url": it["url"], "source": it["source"], "at": it["at"]})
        items.sort(key=lambda x: x.get("at") or "", reverse=True)
        out[name] = items[:8]
        time.sleep(0.3)
    if not any(out.values()):
        raise RuntimeError("localnews: nothing " + "; ".join(errs)[:160])
    return {"counties": out, "errs": errs[:6]}


# ---------- 藝文活動（文化部藝文資訊平台，不用金鑰）：地圖點位、各縣市、本週值得看 ----------
CULTURE_URL = "https://cloud.culture.tw/frontsite/trans/SearchShowAction.do"
CULTURE_CATS = {"6": "展覽", "1": "音樂", "2": "戲劇", "17": "演唱會", "7": "講座", "3": "舞蹈"}
CULTURE_SKIP = re.compile(r"加購|升級|套票|停售|取消|延期|常設展|導覽服務|團體預約")


def _cul_dt(s):
    try:
        return datetime.strptime(str(s).strip()[:16], "%Y/%m/%d %H:%M").replace(tzinfo=TPE)
    except Exception:  # noqa: BLE001
        try:
            return datetime.strptime(str(s).strip()[:10], "%Y/%m/%d").replace(tzinfo=TPE)
        except Exception:  # noqa: BLE001
            return None


def p_culture():
    now = NOW.astimezone(TPE)
    soon = now + timedelta(days=7)
    events, errs = [], []
    for cat, cname in CULTURE_CATS.items():
        try:
            rows = gjson(CULTURE_URL, params={"method": "doFindTypeJ", "category": cat}, timeout=60)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{cname}: {safe_err(e)}"); continue
        for ev in rows:
            title = re.sub(r"\s+", " ", ev.get("title") or "").strip()
            if not title or CULTURE_SKIP.search(title):
                continue
            sd, ed = _cul_dt(ev.get("startDate")), _cul_dt(ev.get("endDate"))
            if ed and ed.date() < now.date():
                continue
            long_run = bool(sd and ed and (ed - sd).days > 400)  # 跨好幾年的多半是常設展
            if cat == "6" and long_run:
                continue
            # 找本週內（現在～7 天後）還有的場次；展覽只要展期涵蓋本週就算
            sess = []
            for si in ev.get("showInfo") or []:
                if not isinstance(si, dict):
                    continue
                t, te = _cul_dt(si.get("time")), _cul_dt(si.get("endTime"))
                if cat == "6":
                    ok = (t is None or t <= soon) and (te is None or te >= now)
                else:
                    ok = t is not None and now - timedelta(hours=3) <= t <= soon
                if ok:
                    sess.append((t or now, si))
            if not sess:
                continue
            sess.sort(key=lambda x: x[0])
            t, si = sess[0]
            loc = (si.get("location") or "").strip()
            county = (_counties_in(loc) or _counties_in(si.get("locationName") or "") or [""])[0]
            lat, lon = num(si.get("latitude")), num(si.get("longitude"))
            if not (lat and lon and 21 < lat < 27 and 118 < lon < 123):
                lat = lon = None
            closing = bool(cat == "6" and ed and (ed.date() - now.date()).days <= 7)
            events.append({"t": title[:60], "c": cname, "county": county, "venue": ((si.get("locationName") or "") or loc)[:24],
                           "at": t.strftime("%m/%d %H:%M") if cat != "6" else "", "end": ed.strftime("%m/%d") if ed else "",
                           "n": len(sess), "price": re.sub(r"\s+", " ", si.get("price") or "")[:30], "unit": (ev.get("showUnit") or "")[:20],
                           "url": ev.get("webSales") or ev.get("sourceWebPromote") or "", "hit": int(num(ev.get("hitRate")) or 0),
                           "ll": [round(lon, 4), round(lat, 4)] if lat else None, "closing": closing})
        time.sleep(0.3)
    if not events:
        raise RuntimeError("culture: nothing " + "; ".join(errs)[:160])
    # 同名同場地去重
    seen, uniq = set(), []
    for e in sorted(events, key=lambda x: -x["hit"]):
        k = (e["t"][:24], e["venue"][:10])
        if k not in seen:
            seen.add(k); uniq.append(e)
    by_county = {}
    for e in uniq:
        if e["county"]:
            by_county.setdefault(e["county"], []).append(e)
    counts = {k: len(v) for k, v in by_county.items()}
    top = {k: v[:4] for k, v in by_county.items()}
    exhib = [e for e in uniq if e["c"] == "展覽"]
    picks = {"closing": [e for e in exhib if e["closing"]][:6], "exhib": exhib[:8],
             "stage": [e for e in uniq if e["c"] in ("演唱會", "戲劇", "舞蹈", "音樂")][:8]}
    points = [[e["ll"][0], e["ll"][1], e["t"], e["c"], e["venue"], e["at"] or ("至 " + e["end"]), e["url"], e["price"]] for e in uniq if e["ll"]][:900]
    cat_n = {c: sum(1 for e in uniq if e["c"] == c) for c in CULTURE_CATS.values()}
    return {"counts": counts, "top": top, "picks": picks, "points": points, "catN": cat_n, "n": len(uniq), "errs": errs}


# ---------- 菜價（農業部批發市場，台北一為基準；颱風前後會跳） ----------
MOA_VEG = "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx"
VEG_BASKET = [("甘藍", "高麗菜"), ("包心白", "大白菜"), ("小白菜", "小白菜"), ("青江白菜", "青江菜"), ("蕹菜", "空心菜"), ("菠菜", "菠菜"),
              ("萵苣菜", "萵苣"), ("青蔥", "青蔥"), ("花椰菜", "花椰菜"), ("胡瓜", "小黃瓜"), ("絲瓜", "絲瓜"), ("茄子", "茄子"),
              ("番茄", "番茄"), ("胡蘿蔔", "胡蘿蔔"), ("蘿蔔", "白蘿蔔"), ("辣椒", "辣椒")]


def p_veg():
    today = NOW.astimezone(TPE).date()
    roc = lambda d: f"{d.year - 1911}.{d.month:02d}.{d.day:02d}"
    have = HISTORY.get("veg", {}).get("高麗菜") or []
    since = today - timedelta(days=4 if len(have) >= 10 else 30)  # 第一次回補一個月
    rows, skip = [], 0
    while skip < 30000:
        got = gjson(MOA_VEG, params={"StartDate": roc(since), "EndDate": roc(today), "Market": "台北一", "$top": "3000", "$skip": str(skip)}, timeout=60)
        rows += got
        if len(got) < 3000:
            break
        skip += 3000
    agg = {}  # (日期, 品名) -> [金額, 量]
    for r in rows:
        if r.get("市場名稱") != "台北一":
            continue
        name = (r.get("作物名稱") or "").split("-")[0]
        p, v = num(r.get("平均價")), num(r.get("交易量"))
        if not p or not v:
            continue
        for key, label in VEG_BASKET:
            if name == key:
                d = r.get("交易日期") or ""
                m = re.match(r"(\d+)\.(\d+)\.(\d+)", d)
                if not m:
                    continue
                iso = f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
                a = agg.setdefault((iso, label), [0.0, 0.0])
                a[0] += p * v; a[1] += v
    for (iso, label), (amt, vol) in agg.items():
        hist_put("veg", label, iso, round(amt / vol, 1))
        hist_put("veg_vol", label, iso, round(vol))
    items, ratios = [], []
    for _, label in VEG_BASKET:
        h = HISTORY.get("veg", {}).get(label) or []
        if not h:
            continue
        vals = [v for _, v in h[-15:]]
        cur = vals[-1]
        base = sum(vals[:-1]) / len(vals[:-1]) if len(vals) > 1 else None
        chg = round(100 * (cur / base - 1), 1) if base else None
        if chg is not None:
            ratios.append(chg)
        items.append({"name": label, "price": cur, "date": h[-1][0], "prev": vals[-2] if len(vals) > 1 else None, "chg14": chg, "spark": vals})
    if not items:
        raise RuntimeError(f"veg: no basket rows ({len(rows)} rows)")
    idx = round(sum(ratios) / len(ratios), 1) if ratios else None
    if idx is not None:
        hist_put("veg_idx", "basket", max(i["date"] for i in items), idx)
    items.sort(key=lambda x: -(x["chg14"] or 0))
    return {"market": "台北一", "date": max(i["date"] for i in items), "index": idx, "items": items, "rows": len(rows)}


# ---------- 魚價（農業部漁產品交易行情：全台魚市場，近十個交易日） ----------
MOA_FISH = "https://data.moa.gov.tw/Service/OpenData/FromM/AquaticTransData.aspx"


def p_fish():
    rows = gjson(MOA_FISH, params={"IsTransData": "1", "UnitId": "039"}, timeout=120)
    agg, vol10 = {}, {}  # (日期, 魚) -> [金額, 量]；魚 -> 十日量
    for r in rows:
        name = (r.get("魚貨名稱") or "").strip()
        p, v = num(r.get("平均價")), num(r.get("交易量"))
        m = re.match(r"(\d{3})(\d{2})(\d{2})$", str(r.get("交易日期") or ""))
        # 冷凍大宗（鮪、鯊、下雜魚）多在漁港拍賣，跟餐桌價格無關，排除
        if not name or name.startswith("其他") or "凍" in name or "雜" in name or not p or not v or not m:
            continue
        iso = f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
        a = agg.setdefault((iso, name), [0.0, 0.0])
        a[0] += p * v; a[1] += v
        vol10[name] = vol10.get(name, 0) + v
    if not agg:
        raise RuntimeError(f"fish: no rows ({len(rows)})")
    top = [k for k, _ in sorted(vol10.items(), key=lambda kv: -kv[1])[:40]]  # 只存量大的，歷史檔才不會膨脹
    for (iso, name), (amt, vol) in agg.items():
        if name in top:
            hist_put("fish", name, iso, round(amt / vol, 1))
    basket = top[:16]
    items, ratios = [], []
    for name in basket:
        h = HISTORY.get("fish", {}).get(name) or []
        vals = [v for _, v in h[-15:]]
        if not vals:
            continue
        cur = vals[-1]
        base = sum(vals[:-1]) / len(vals[:-1]) if len(vals) > 1 else None
        chg = round(100 * (cur / base - 1), 1) if base else None
        if chg is not None:
            ratios.append(chg)
        items.append({"name": name, "price": cur, "date": h[-1][0], "prev": vals[-2] if len(vals) > 1 else None, "chg14": chg,
                      "spark": vals, "vol": round(vol10[name] / 1000, 1)})
    idx = round(sorted(ratios)[len(ratios) // 2], 1) if ratios else None  # 中位數：單一魚種暴漲暴跌不會拉歪
    date = max(i["date"] for i in items)
    if idx is not None:
        hist_put("fish_idx", "basket", date, idx)
    items.sort(key=lambda x: -(x["chg14"] or 0))
    return {"date": date, "index": idx, "items": items, "rows": len(rows), "src": "農業部資料開放平臺 · 漁產品交易行情"}


# ---------- 水果（同一個果菜批發資料源，台北一，量最大的 16 種） ----------
def p_fruit():
    today = NOW.astimezone(TPE).date()
    roc = lambda d: f"{d.year - 1911}.{d.month:02d}.{d.day:02d}"  # noqa: E731
    have = HISTORY.get("fruit", {}).get("香蕉") or []
    since = today - timedelta(days=4 if len(have) >= 10 else 30)
    rows, skip = [], 0
    while skip < 30000:
        got = gjson(MOA_VEG, params={"StartDate": roc(since), "EndDate": roc(today), "Market": "台北一", "$top": "3000", "$skip": str(skip)}, timeout=60)
        rows += got
        if len(got) < 3000:
            break
        skip += 3000
    agg, vol = {}, {}
    for r in rows:
        if r.get("種類代碼") != "N05" or r.get("市場名稱") != "台北一":
            continue
        name = (r.get("作物名稱") or "").split("-")[0]
        p, v = num(r.get("平均價")), num(r.get("交易量"))
        m = re.match(r"(\d+)\.(\d+)\.(\d+)", r.get("交易日期") or "")
        if not name or name == "其他" or not p or not v or not m:
            continue
        iso = f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
        a = agg.setdefault((iso, name), [0.0, 0.0]); a[0] += p * v; a[1] += v
        vol[name] = vol.get(name, 0) + v
    top = [k for k, _ in sorted(vol.items(), key=lambda kv: -kv[1])[:30]]
    for (iso, name), (amt, v) in agg.items():
        if name in top:
            hist_put("fruit", name, iso, round(amt / v, 1))
    items, ratios = [], []
    for name in top[:16]:
        h = HISTORY.get("fruit", {}).get(name) or []
        vals = [v for _, v in h[-15:]]
        if not vals:
            continue
        cur, base = vals[-1], (sum(vals[:-1]) / len(vals[:-1]) if len(vals) > 1 else None)
        chg = round(100 * (cur / base - 1), 1) if base else None
        if chg is not None:
            ratios.append(chg)
        items.append({"name": name, "price": cur, "date": h[-1][0], "prev": vals[-2] if len(vals) > 1 else None, "chg14": chg, "spark": vals})
    if not items:
        raise RuntimeError(f"fruit: no rows ({len(rows)})")
    idx = round(sorted(ratios)[len(ratios) // 2], 1) if ratios else None
    items.sort(key=lambda x: -(x["chg14"] or 0))
    return {"date": max(i["date"] for i in items), "index": idx, "items": items, "market": "台北一"}


# ---------- 肉蛋（農業部毛豬交易行情、家禽交易行情） ----------
def p_meat():
    out = []
    try:  # 毛豬：各市場依成交頭數加權
        rows = gjson("https://data.moa.gov.tw/Service/OpenData/FromM/AnimalTransData.aspx", params={"IsTransData": "1", "UnitId": "026"}, timeout=120)
        agg = {}
        for r in rows:
            m = re.match(r"(\d{3})(\d{2})(\d{2})$", str(r.get("交易日期") or ""))
            n_, p = num(r.get("成交頭數-總數")), num(r.get("成交頭數-平均價格"))
            if not m or not n_ or not p:
                continue
            iso = f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}"
            a = agg.setdefault(iso, [0.0, 0.0]); a[0] += p * n_; a[1] += n_
        for iso, (amt, n_) in agg.items():
            hist_put("meat", "毛豬", iso, round(amt / n_, 1))
    except Exception as e:  # noqa: BLE001
        log("pig", e)
    try:  # 白肉雞、雞蛋（元／台斤）
        rows = gjson("https://data.moa.gov.tw/Service/OpenData/FromM/PoultryTransBoiledChickenData.aspx", params={"IsTransData": "1", "UnitId": "056"}, timeout=120)
        for r in rows:
            d = (r.get("日期") or "").replace("/", "-")
            if not re.match(r"\d{4}-\d{2}-\d{2}$", d):
                continue
            for k, label in (("白肉雞(2.0Kg以上)", "白肉雞"), ("雞蛋(產地價)", "雞蛋產地價"), ("雞蛋(大運輸價)", "雞蛋批發價")):
                v = num(r.get(k))
                if v:
                    hist_put("meat", label, d, v)
    except Exception as e:  # noqa: BLE001
        log("poultry", e)
    units = {"毛豬": "元/公斤", "白肉雞": "元/台斤", "雞蛋產地價": "元/台斤", "雞蛋批發價": "元/台斤"}
    for label, unit in units.items():
        h = HISTORY.get("meat", {}).get(label) or []
        vals = [v for _, v in h[-15:]]
        if not vals:
            continue
        cur, base = vals[-1], (sum(vals[:-1]) / len(vals[:-1]) if len(vals) > 1 else None)
        out.append({"name": label, "unit": unit, "price": cur, "date": h[-1][0], "prev": vals[-2] if len(vals) > 1 else None,
                    "chg14": round(100 * (cur / base - 1), 1) if base else None, "spark": vals,
                    "yoy": next((round(100 * (cur / v - 1), 1) for d, v in reversed(h) if d <= (date_from(h[-1][0]) - timedelta(days=365)).isoformat()), None)})
    if not out:
        raise RuntimeError("meat: nothing")
    return {"date": max(i["date"] for i in out), "items": out}


def date_from(iso):
    return datetime.strptime(iso[:10], "%Y-%m-%d").date()


# ---------- 信用卡各類簽帳（聯合信用卡處理中心，金管會開放資料，2014 起每月） ----------
def p_cards():
    txt = get("https://www.nccc.com.tw/dataDownload/Gender/BANK_TWN_ALL_GD.CSV", timeout=90).content.decode("utf-8-sig", "ignore")
    agg = {}
    for row in csv.reader(io.StringIO(txt)):
        if len(row) < 6 or not row[0].isdigit():
            continue
        ym, cat, amt = row[0], row[2], num(row[5])
        if amt:
            agg.setdefault(cat, {}); agg[cat][ym] = agg[cat].get(ym, 0) + amt
    tot = {}
    for cat, s in agg.items():
        for ym, v in s.items():
            tot[ym] = tot.get(ym, 0) + v
    agg["總計"] = tot
    last = max(tot)
    def yoy(s, ym):
        p = f"{int(ym[:4]) - 1}{ym[4:]}"
        return round(100 * (s[ym] / s[p] - 1), 1) if s.get(ym) and s.get(p) else None
    yms = sorted(tot)[-24:]
    rows = []
    for cat in ["總計", "食", "衣", "住", "行", "文教康樂", "百貨", "其他"]:
        s = agg.get(cat) or {}
        if last not in s:
            continue
        y3 = [yoy(s, m) for m in sorted(s)[-3:]]
        y3 = [v for v in y3 if v is not None]
        rows.append({"cat": cat, "amt": round(s[last] / 1e8, 1), "yoy": yoy(s, last), "yoy3": round(sum(y3) / len(y3), 1) if y3 else None,
                     "spark": [yoy(s, m) for m in yms if yoy(s, m) is not None]})
    return {"month": f"{last[:4]}-{last[4:]}", "rows": rows, "src": "聯合信用卡處理中心（金管會銀行局開放資料）"}


# ---------- 景氣轉向：國發會領先指標、經濟部外銷訂單 ----------
def p_lead():
    out, errs = {}, []
    try:
        meta = gjson("https://data.gov.tw/api/v2/rest/dataset/6099", timeout=60)["result"]
        u = next(d["resourceDownloadUrl"] for d in meta["distribution"] if d.get("resourceDownloadUrl"))
        z = zipfile.ZipFile(io.BytesIO(get(u, timeout=90).content))
        name = next(n for n in z.namelist() if n.startswith("景氣指標與燈號"))
        rows = list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "ignore"))))
        rows = [r for r in rows if re.match(r"\d{6}$", r.get("Date") or "")]
        lead = [(r["Date"], num(r.get("領先指標不含趨勢指數"))) for r in rows if num(r.get("領先指標不含趨勢指數"))]
        coin = [(r["Date"], num(r.get("同時指標不含趨勢指數"))) for r in rows if num(r.get("同時指標不含趨勢指數"))]
        sig = [(r["Date"], r.get("景氣對策信號"), num(r.get("景氣對策信號綜合分數"))) for r in rows if num(r.get("景氣對策信號綜合分數"))]
        streak = 0
        for i in range(len(lead) - 1, 0, -1):
            d = lead[i][1] - lead[i - 1][1]
            if streak == 0:
                streak = 1 if d > 0 else -1
            elif (d > 0) == (streak > 0):
                streak += 1 if streak > 0 else -1
            else:
                break
        out["lead"] = {"month": lead[-1][0], "value": round(lead[-1][1], 2), "chg": round(lead[-1][1] - lead[-2][1], 2), "streak": streak,
                       "spark": [round(v, 2) for _, v in lead[-36:]], "coin": [round(v, 2) for _, v in coin[-36:]],
                       "signal": sig[-1][1] if sig else None, "score": sig[-1][2] if sig else None, "scores": [s for _, _, s in sig[-24:]]}
    except Exception as e:  # noqa: BLE001
        errs.append(f"領先指標: {safe_err(e)}")
    try:
        txt = get("https://service.moea.gov.tw/EE520/opendata/b.csv", timeout=60).content.decode("utf-8-sig", "ignore")
        s = {}
        for row in csv.reader(io.StringIO(txt)):
            if len(row) >= 3 and row[0] == "外銷訂單金額" and re.match(r"\d{5}$", row[1]):
                s[row[1]] = num(row[2])
        ks = sorted(s)
        def yoy(k):
            p = f"{int(k[:3]) - 1:03d}{k[3:]}"
            return round(100 * (s[k] / s[p] - 1), 1) if s.get(p) else None
        out["orders"] = {"month": f"{int(ks[-1][:3]) + 1911}-{ks[-1][3:]}", "value": s[ks[-1]], "yoy": yoy(ks[-1]),
                         "spark": [yoy(k) for k in ks[-24:] if yoy(k) is not None]}
    except Exception as e:  # noqa: BLE001
        errs.append(f"外銷訂單: {safe_err(e)}")
    if not out:
        raise RuntimeError(f"lead: nothing {errs}")
    out["errs"] = errs
    return out


# ---------- 台北捷運各站進站人次（逐月 OD 檔，約 300MB／月，只在新月份出現時抓） ----------
METRO_STORE = DATA / "metro_months.json"


def _metro_month(url):
    tot = {}
    with S.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        first = True
        for raw in r.iter_lines():
            if first:
                first = False; continue
            parts = raw.decode("utf-8", "ignore").split(",")
            if len(parts) < 5:
                continue
            try:
                v = int(parts[4])
            except ValueError:
                continue
            if v:
                st = re.sub(r"^[A-Z]+", "", parts[2])
                tot[st] = tot.get(st, 0) + v
    return tot


def p_metro():
    try:
        store = json.loads(METRO_STORE.read_text(encoding="utf-8")) if METRO_STORE.exists() else {}
    except Exception:  # noqa: BLE001
        store = {}
    idx = get("https://data.taipei/api/dataset/63f31c7e-7fc3-418b-bd82-b95158755b4d/resource/eb481f58-1238-4cff-8caa-fa7bb20cb4f4/download", timeout=60)
    months = {}
    for row in csv.reader(io.StringIO(idx.content.decode("utf-8-sig", "ignore"))):
        if len(row) >= 4 and row[1].isdigit() and row[2].isdigit():
            months[f"{row[1]}-{int(row[2]):02d}"] = row[3]
    latest = max(months)
    ly = f"{int(latest[:4]) - 1}{latest[4:]}"
    fetched = 0
    for m in (latest, ly):
        if m not in store and m in months and fetched < 2:
            store[m] = _metro_month(months[m]); fetched += 1
            write_json(METRO_STORE, store, separators=(",", ":"))
    if latest not in store or ly not in store:
        raise RuntimeError("metro: months missing")
    cur, prev = store[latest], store[ly]
    rows = []
    for st, v in cur.items():
        p = prev.get(st)
        if p and p >= 150000:
            rows.append({"st": st, "n": v, "prev": p, "chg": round(100 * (v / p - 1), 1)})
    tc, tp = sum(cur.values()), sum(prev.values())
    rows.sort(key=lambda r: -r["chg"])
    newst = [st for st, v in cur.items() if st not in prev and v >= 50000]
    return {"month": latest, "total": tc, "total_chg": round(100 * (tc / tp - 1), 1) if tp else None,
            "up": rows[:10], "down": rows[-6:][::-1], "new": newst[:6], "n": len(rows)}


# ---------- 主題溫度計（維基百科逐月瀏覽量，2016 起；中文 vs 英文、日文看誰先動） ----------
WIKI_MAP = DATA / "wiki_map.json"
WIKI_SERIES = DATA / "wiki_series.json"


def _wiki_pv(lang, title, end):
    t = requests.utils.quote(title.replace(" ", "_"), safe="")
    r = S.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{t}/monthly/20160101/{end}", timeout=40)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return [[i["timestamp"][:6], i["views"]] for i in r.json().get("items", [])]


def _corr(a, b):
    n = len(a)
    if n < 12:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a) ** .5
    vb = sum((y - mb) ** 2 for y in b) ** .5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) if va and vb else None


def p_wiki():
    cfg = json.loads((ROOT / "ops" / "wiki_topics.json").read_text(encoding="utf-8"))["topics"]
    try:
        mp = json.loads(WIKI_MAP.read_text(encoding="utf-8")) if WIKI_MAP.exists() else {}
    except Exception:  # noqa: BLE001
        mp = {}
    errs = []
    for q, _ in cfg:
        if q in mp and mp[q].get("at", "") >= (TODAY_TPE - timedelta(days=30)).isoformat():
            continue
        try:
            j = gjson("https://zh.wikipedia.org/w/api.php", params={"action": "query", "titles": q, "prop": "langlinks", "lllimit": "500",
                                                                  "redirects": "1", "converttitles": "1", "format": "json"}, timeout=40)
            pg = list(j["query"]["pages"].values())[0]
            if "missing" in pg:
                mp[q] = {"zh": None, "at": TODAY_TPE.isoformat()}; continue
            ll = {x["lang"]: x["*"] for x in pg.get("langlinks", [])}
            mp[q] = {"zh": pg["title"], "en": ll.get("en"), "ja": ll.get("ja"), "at": TODAY_TPE.isoformat()}
            time.sleep(0.2)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{q}: {safe_err(e)}")
    write_json(WIKI_MAP, mp)
    end = (TODAY_TPE.replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
    series = {}
    for q, grp in cfg:
        m = mp.get(q) or {}
        if not m.get("zh"):
            continue
        s = {}
        for lang in ("zh", "en", "ja"):
            if m.get(lang):
                try:
                    s[lang] = _wiki_pv(lang, m[lang], end); time.sleep(0.15)
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{q}/{lang}: {safe_err(e)}")
        series[q] = s
    write_json(WIKI_SERIES, series, separators=(",", ":"))
    rows = []
    for q, grp in cfg:
        s = series.get(q) or {}
        zh = s.get("zh") or []
        if len(zh) < 27:
            continue
        v = [x[1] for x in zh]
        def yoy3(vals):
            return round(100 * (sum(vals[-3:]) / sum(vals[-15:-12]) - 1)) if len(vals) >= 15 and sum(vals[-15:-12]) > 0 else None
        g12 = round(100 * (sum(v[-12:]) / sum(v[-24:-12]) - 1)) if sum(v[-24:-12]) else None
        g12p = round(100 * (sum(v[-24:-12]) / sum(v[-36:-24]) - 1)) if len(v) >= 36 and sum(v[-36:-24]) else None
        now = sum(v[-3:]) / 3
        pk = max(range(len(v)), key=lambda i: v[i])
        ratio = now / v[pk] if v[pk] else 0
        y3 = yoy3(v)
        if y3 is not None and y3 >= 50 and ratio >= .7:
            kind = "新興加速"
        elif ratio < .5 and pk >= len(v) - 60 and v[pk] > 2 * (sum(v[max(0, pk - 36):max(1, pk - 24)]) / 12 or 1):
            kind = "熱潮已退"
        elif g12 is not None and g12 >= 15 and (g12p is None or g12p > 0):
            kind = "長期上升"
        elif g12 is not None and g12 <= -15:
            kind = "退燒中"
        else:
            kind = "穩定"
        foreign, lead = [], None
        for lang in ("en", "ja"):
            fv = [x[1] for x in (s.get(lang) or [])]
            if len(fv) < 27:
                continue
            fy = yoy3(fv)
            foreign.append({"lang": lang, "yoy3": fy})
            # 時間差：用年增率序列找「國外領先幾個月」相關最高
            zmap = dict(zh); fmap = {k: x for k, x in s[lang]}
            keys = sorted(set(zmap) & set(fmap))
            zy = {k: zmap[k] / zmap[p] - 1 for k in keys for p in [f"{int(k[:4]) - 1}{k[4:]}"] if zmap.get(p)}
            fyy = {k: fmap[k] / fmap[p] - 1 for k in keys for p in [f"{int(k[:4]) - 1}{k[4:]}"] if fmap.get(p)}
            kk = sorted(set(zy) & set(fyy))[-72:]
            best = None
            for L in range(1, 13):
                a = [fyy[kk[i - L]] for i in range(L, len(kk))]
                b = [zy[kk[i]] for i in range(L, len(kk))]
                r = _corr(a, b)
                if r is not None and r >= .5 and (best is None or r > best[1]):
                    best = (L, round(r, 2))
            if best and (lead is None or best[1] > lead["r"]):
                lead = {"lang": lang, "lag": best[0], "r": best[1]}
        abroad = any((f["yoy3"] or 0) >= 30 for f in foreign) and (y3 is None or y3 < 10)
        rows.append({"q": q, "title": mp[q]["zh"], "grp": grp, "kind": kind, "yoy3": y3, "g12": g12,
                     "peak": zh[pk][0], "ratio": round(ratio, 2), "spark": v[-60:], "foreign": foreign, "lead": lead, "abroad": abroad,
                     "last": zh[-1][0]})
    if not rows:
        raise RuntimeError(f"wiki: nothing {errs[:3]}")
    order = {"新興加速": 0, "長期上升": 1, "穩定": 3, "退燒中": 4, "熱潮已退": 5}
    rows.sort(key=lambda r: (order[r["kind"]] - (1 if r["abroad"] else 0) * .5, -(r["yoy3"] or 0)))
    return {"rows": rows, "month": rows[0]["last"], "errs": errs[:5],
            "src": "維基百科逐月瀏覽量（Wikimedia Pageviews API，2016 起；中文維基＝全球中文讀者，台灣占大宗）"}


# ---------- 美國企業在談什麼（SEC EDGAR 全文檢索：10-K / 10-Q / 8-K 提到的次數，比去年同期） ----------
# SEC 存取規範：每秒不超過 10 次、User-Agent 要寫聯絡信箱。信箱放在 GitHub secret（SEC_CONTACT），不寫進公開程式碼。
SEC_WORDS = [("GLP-1", "GLP-1"), ("tariffs", "關稅"), ("agentic", "AI 代理"), ("generative AI", "生成式 AI"),
             ("data center", "資料中心"), ("humanoid", "人形機器人"), ("small modular reactor", "小型核電"), ("stablecoin", "穩定幣"),
             ("Taiwan", "台灣"), ("private label", "自有品牌"), ("trade down", "消費降級"), ("Gen Z", "Z 世代"),
             ("loyalty program", "會員經濟"), ("resale", "二手轉售"), ("influencer", "網紅行銷"), ("pet food", "寵物食品"),
             ("non-alcoholic", "無酒精"), ("longevity", "長壽經濟")]
SIC2 = {"01": "農業", "13": "油氣", "20": "食品飲料", "23": "服飾", "28": "製藥化學", "35": "電腦機械", "36": "電子半導體", "37": "汽車運輸",
        "38": "醫材儀器", "48": "電信", "49": "公用事業", "50": "批發", "51": "批發", "53": "百貨量販", "54": "食品零售", "56": "服飾零售",
        "58": "餐飲", "59": "零售", "60": "銀行", "61": "金融", "62": "證券", "63": "保險", "67": "投資控股", "70": "旅館", "73": "軟體服務",
        "78": "影視", "79": "娛樂", "80": "醫療服務", "87": "工程顧問"}


def p_secwords():
    contact = os.environ.get("SEC_CONTACT", "").strip()
    if "@" not in contact:
        raise RuntimeError("SEC_CONTACT secret 還沒設定")
    hdr = {"User-Agent": f"intel-terminal {contact}", "Accept": "application/json"}
    end = TODAY_TPE - timedelta(days=1)
    start = end - timedelta(days=89)
    ly = lambda d: d.replace(year=d.year - 1)  # noqa: E731
    def q(word, a, b):
        for k in range(3):  # 全文檢索偶爾回 500，稍等重試
            r = S.get("https://efts.sec.gov/LATEST/search-index", headers=hdr, timeout=40,
                      params={"q": f'"{word}"', "dateRange": "custom", "startdt": a.isoformat(), "enddt": b.isoformat(), "forms": "10-K,10-Q,8-K"})
            time.sleep(0.4)
            if r.status_code < 500 or k == 2:
                r.raise_for_status()
                return r.json()
            time.sleep(3 * (k + 1))
    rows, errs = [], []
    for word, label in SEC_WORDS:
        try:
            cur = q(word, start, end)
            prev = q(word, ly(start), ly(end))
            n_cur = int(((cur.get("hits") or {}).get("total") or {}).get("value") or 0)
            n_prev = int(((prev.get("hits") or {}).get("total") or {}).get("value") or 0)
            ag = cur.get("aggregations") or {}
            ent = [re.sub(r"\s*\(CIK \d+\)", "", b.get("key") or "").strip() for b in (ag.get("entity_filter") or {}).get("buckets", [])[:3]]
            sic = [(b.get("key") or "")[:2] for b in (ag.get("sic_filter") or {}).get("buckets", [])[:3]]
            rows.append({"w": word, "label": label, "n": n_cur, "prev": n_prev,
                         "chg": round(100 * (n_cur / n_prev - 1)) if n_prev >= 20 else None,
                         "co": [re.sub(r"\s{2,}", " ", e) for e in ent if e][:3], "ind": [SIC2[s] for s in dict.fromkeys(sic) if s in SIC2][:2]})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{word}: {safe_err(e)}")
    if not rows:
        raise RuntimeError(f"sec: nothing {errs[:2]}")
    for r in rows:
        hist_put("secwords", r["w"], end.isoformat(), r["n"])
    rows.sort(key=lambda r: -(r["chg"] if r["chg"] is not None else -999))
    return {"win": [start.isoformat(), end.isoformat()], "rows": rows, "errs": errs[:4],
            "src": "SEC EDGAR 全文檢索（10-K、10-Q、8-K 含附件，計文件數）"}



# ---------- 地圖：新聞定位到鄉鎮、新公司點位、航班、閃電、實價登錄 ----------
try:
    TOWNS = json.loads((ROOT / "tw_towns.json").read_text(encoding="utf-8"))  # 縣市+鄉鎮 -> [經度, 緯度, 縣市, 鄉鎮]
except Exception:  # noqa: BLE001
    TOWNS = {}
_TOWN_BY_NAME: dict = {}
for _k, (_lo, _la, _c, _t) in TOWNS.items():
    _TOWN_BY_NAME.setdefault(_t, []).append((_c, _lo, _la, _t))
    if _t.startswith("臺"):
        _TOWN_BY_NAME.setdefault("台" + _t[1:], []).append((_c, _lo, _la, _t))
# 簡稱（竹北、員林、羅東、板橋…）：只收全台唯一、不是常見詞的
_TOWN_STOP = {"中正", "中山", "信義", "仁愛", "大同", "光復", "和平", "復興", "太平", "永安", "東山", "新城", "新市", "成功", "和美", "安定", "福興",
              "大城", "大村", "新興", "三民", "前金", "中西", "長治", "民生", "大安", "東區", "西區", "南區", "北區", "中區", "安南", "大雅", "大樹",
              "大社", "五結", "三星", "大園", "八德", "平鎮", "前鎮", "新園", "萬丹", "竹田", "內埔", "里港", "東勢", "水上", "中和", "大里", "清水", "新化", "南化"}
_stems: dict = {}
for _name, _lst in list(_TOWN_BY_NAME.items()):
    if len(_lst) == 1 and len(_name) >= 3 and _name[-1] in "市鎮區鄉":
        _stems.setdefault(_name[:-1], []).append(_lst[0])
for _st, _lst in _stems.items():
    if len(_lst) == 1 and len(_st) >= 2 and _st not in _TOWN_STOP and _st not in _TOWN_BY_NAME and not any(_st in a or a.startswith(_st) for _v in TW_COUNTIES.values() for a in _v[2]) \
            and not any(c.startswith(_st) or c.startswith(_st.replace("台", "臺")) for c in TW_COUNTIES):
        _TOWN_BY_NAME[_st] = _lst


def _jitter(key: str, r: float = 0.05):
    import hashlib
    h = hashlib.md5(key.encode("utf-8")).digest()
    return (h[0] / 255 - 0.5) * 2 * r, (h[1] / 255 - 0.5) * 2 * r


def _place(text: str, county: str = ""):
    """標題裡的地名 → (經度, 緯度, 地名, 層級)。鄉鎮優先；同名鄉鎮要靠縣市判斷。"""
    best = None
    counties = set(_counties_in(text)) | ({county} if county else set())
    for name, lst in _TOWN_BY_NAME.items():
        if name not in text:
            continue
        cands = [x for x in lst if x[0] in counties] if counties else (lst if len(lst) == 1 else [])
        if cands and (best is None or len(name) > len(best[1])):
            best = (cands[0], name)
    if best:
        (c, lo, la, t), _ = best
        dx, dy = _jitter(text, 0.012)
        return [round(lo + dx, 4), round(la + dy, 4), c.replace("臺", "台") + t, "town"]
    c = county or next(iter(_counties_in(text)), "")
    if c in TW_COUNTIES:
        lo, la, _ = TW_COUNTIES[c]
        dx, dy = _jitter(text, 0.07)
        return [round(lo + dx, 4), round(la + dy, 4), c.replace("臺", "台"), "county"]
    return None


def p_mapfeed():
    """把已抓到的新聞、示警、新公司放上地圖（不打外部 API）。"""
    pts, seen = [], set()
    def add(title, url, source, at, kind, county=""):
        if not title or title in seen:
            return
        pl = _place(title, county)
        if not pl:
            return
        seen.add(title)
        pts.append({"ll": pl[:2], "place": pl[2], "lvl": pl[3], "t": title[:80], "u": url or "", "s": (source or "")[:12], "at": at or "", "k": kind})
    for c, items in ((RESULTS.get("localnews") or {}).get("counties") or {}).items():
        for it in items:
            add(it.get("title"), it.get("url"), it.get("source"), it.get("at"), "local", c)
    for it in (RESULTS.get("news") or {}).get("tw") or []:
        add(it.get("title"), it.get("url"), it.get("source"), it.get("at"), "news")
    for g in (RESULTS.get("news") or {}).get("groups") or []:
        for it in (g.get("items") or []) if isinstance(g, dict) else []:
            add(it.get("title"), it.get("url"), it.get("source"), it.get("at"), "news")
    alerts = []
    for a in (RESULTS.get("alerts") or {}).get("alerts") or []:
        pl = _place(a.get("text", ""), (a.get("area") or [""])[0])
        if pl and a.get("lvl", 0) >= 1:
            alerts.append({"ll": pl[:2], "place": pl[2], "lvl": a.get("lvl"), "cat": a.get("cat"), "t": a.get("text", "")[:120], "u": a.get("url", ""), "at": a.get("at", "")})
    brands = []
    B = RESULTS.get("brands") or {}
    bl = (B.get("peers") or []) + (B.get("big") or [])
    try:
        gc = _gcis_enrich([it.get("name", "") for it in bl])
    except Exception as e:  # noqa: BLE001
        log("gcis enrich", e); gc = {}
    for it in bl:
        c = it.get("city") or ""
        g = gc.get(it.get("name", "")) or {}
        pl = _place(g["addr"], c) if g.get("addr") else None
        if pl and pl[3] == "town":
            ll, place = pl[:2], pl[2]
        elif c in TW_COUNTIES:
            lo, la, _ = TW_COUNTIES[c]
            dx, dy = _jitter(it.get("name", ""), 0.08)
            ll, place = [round(lo + dx, 4), round(la + dy, 4)], c.replace("臺", "台")
        else:
            continue
        brands.append({"ll": ll, "place": place, "t": it.get("name"), "cat": it.get("cat"), "cap": it.get("cap"), "date": it.get("date"), "city": c,
                       "addr": re.sub(r"\d+樓.*$", "", g.get("addr", "")), "boss": g.get("boss", ""), "ban": g.get("ban", "")})
    return {"news": pts, "alerts": alerts, "brands": brands, "n_town": sum(1 for p in pts if p["lvl"] == "town"), "n": len(pts)}


ADSB_URL = "https://api.adsb.lol/v2/point/23.7/121/250"


def p_flights():
    j = gjson(ADSB_URL, timeout=20)
    out = []
    for a in j.get("ac") or []:
        lat, lon = num(a.get("lat")), num(a.get("lon"))
        alt = a.get("alt_baro")
        if lat is None or lon is None or alt == "ground":
            continue
        out.append([round(lon, 3), round(lat, 3), num(a.get("track")) or 0, num(alt) or 0, (a.get("flight") or "").strip(), a.get("t") or "", a.get("r") or "", num(a.get("gs")) or 0])
    if not out:
        raise RuntimeError("adsb: no aircraft")
    return {"items": out, "src": "adsb.lol（ODbL）"}


def p_lightning():
    """氣象署閃電落雷即時觀測（O-A0039-001，平臺只給 KMZ／XML）：抓經緯度與時間。"""
    import zipfile
    last, pts, diag = None, [], None
    for fmt in ("KMZ", "XML", "JSON"):
        try:
            r = get(CWA_FILE + "O-A0039-001", params={"Authorization": CWA_KEY, "downloadType": "WEB", "format": fmt}, timeout=60)
        except Exception as e:  # noqa: BLE001
            last = e; continue
        raw = r.content
        if raw[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(raw))
            raw = b"".join(zf.read(n) for n in zf.namelist() if n.lower().endswith((".kml", ".xml")))
        txt = raw.decode("utf-8", errors="replace")
        # KML：<Placemark> 內有 <coordinates>經度,緯度</coordinates>；時間可能在 <name>、<when> 或描述裡
        for pm in re.findall(r"<Placemark\b.*?</Placemark>", txt, re.S):
            m = re.search(r"<coordinates>\s*([\d.]+)\s*,\s*([\d.]+)", pm)
            if not m:
                continue
            lon, lat = float(m.group(1)), float(m.group(2))
            tm = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)", pm)
            amp = re.search(r"(-?\d+(?:\.\d+)?)\s*kA", pm)
            if 115 < lon < 127 and 18 < lat < 29:
                pts.append([round(lon, 3), round(lat, 3), tm.group(1) if tm else "", float(amp.group(1)) if amp else None])
        if not pts:  # XML／JSON：掃有經緯度的節點
            try:
                rec = json.loads(txt) if fmt == "JSON" else None
            except Exception:  # noqa: BLE001
                rec = None
            if rec is None:
                for m in re.finditer(r"<(?:\w+:)?(?:lon|longitude)>([\d.]+)</.*?<(?:\w+:)?(?:lat|latitude)>([\d.]+)<", txt, re.S | re.I):
                    lon, lat = float(m.group(1)), float(m.group(2))
                    if 115 < lon < 127 and 18 < lat < 29:
                        pts.append([round(lon, 3), round(lat, 3), "", None])
            else:
                for d in _walk_dicts(rec):
                    lon = next((num(d[k]) for k in d if k.lower() in ("longitude", "lon") and num(d[k]) is not None), None)
                    lat = next((num(d[k]) for k in d if k.lower() in ("latitude", "lat") and num(d[k]) is not None), None)
                    if lon and lat and 115 < lon < 127 and 18 < lat < 29:
                        pts.append([round(lon, 3), round(lat, 3), "", None])
        diag = {"fmt": fmt, "bytes": len(r.content), "head": re.sub(r"\s+", " ", txt[:600])}
        break
    if diag is None:
        raise RuntimeError(f"lightning: {safe_err(last)}")
    return {"items": pts[-2000:], "n": len(pts), "diag": None if pts else diag}


PLVR_SEASON = "https://plvr.land.moi.gov.tw/DownloadSeason"
PLVR_CITY = {"a": "臺北市", "b": "臺中市", "c": "基隆市", "d": "臺南市", "e": "高雄市", "f": "新北市", "g": "宜蘭縣", "h": "桃園市", "i": "嘉義市", "j": "新竹縣",
             "k": "苗栗縣", "m": "南投縣", "n": "彰化縣", "o": "新竹市", "p": "雲林縣", "q": "嘉義縣", "t": "屏東縣", "u": "花蓮縣", "v": "臺東縣", "w": "金門縣",
             "x": "澎湖縣", "z": "連江縣"}


_FW = str.maketrans("０１２３４５６７８９", "0123456789")


def _plvr_rows(season):
    """一季的買賣明細（a 檔），每列回傳 dict。"""
    import zipfile
    raw = get(PLVR_SEASON, params={"season": season, "type": "zip", "fileName": "lvr_landcsv.zip"}, timeout=150).content
    zf = zipfile.ZipFile(io.BytesIO(raw))
    rows = []
    want = ("鄉鎮市區", "交易標的", "土地位置建物門牌", "交易年月日", "移轉層次", "總樓層數", "建物型態", "主要用途", "建築完成年月", "建物移轉總面積平方公尺",
            "建物現況格局-房", "建物現況格局-廳", "總價元", "單價元平方公尺", "車位移轉總面積平方公尺", "車位總價元", "備註", "電梯")
    for name in zf.namelist():
        m = re.match(r"^([a-z])_lvr_land_a\.csv$", name.lower())
        if not m or m.group(1) not in PLVR_CITY:
            continue
        txt = zf.read(name).decode("utf-8-sig", errors="replace")
        rd = list(csv.reader(io.StringIO(txt)))
        if len(rd) < 3:
            continue
        hd = [h.strip() for h in rd[0]]
        ix = {k: hd.index(k) for k in want if k in hd}
        for r in rd[2:]:
            d = {k: (r[i].strip() if i < len(r) else "") for k, i in ix.items()}
            d["city"] = PLVR_CITY[m.group(1)]
            rows.append(d)
    return rows


def _plvr_seasons():
    today = NOW.astimezone(TPE).date()
    y, q = today.year - 1911, (today.month - 1) // 3 + 1
    out = []
    for _ in range(4):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append(f"{y}S{q}")
    return out


_ROAD_RE = re.compile(r"([^\d\s]{1,12}?(?:大道|路|街)(?:[一二三四五六七八九十]+段)?)")


def _plvr_clean(rows):
    """只留住宅、去掉親友／特殊交易；算出扣掉車位的每坪單價。"""
    out = []
    for d in rows:
        if "建物" not in d.get("交易標的", "") or "住" not in d.get("主要用途", "") or re.search(r"親友|特殊|關係|瑕疵|債權|法拍|增建|毛胚|含增建|地上權", d.get("備註", "")):
            continue
        total, area = num(d.get("總價元")), num(d.get("建物移轉總面積平方公尺"))
        pk_p, pk_a = num(d.get("車位總價元")) or 0, num(d.get("車位移轉總面積平方公尺")) or 0
        if not total or not area or area <= pk_a:
            continue
        ping = (area - pk_a) * 0.3025
        unit = (total - pk_p) / ping / 10000 if ping > 3 else None
        if not unit or not (3 < unit < 500):
            continue
        addr = d.get("土地位置建物門牌", "").translate(_FW)
        town = d.get("鄉鎮市區", "")
        rest = addr.split(town, 1)[-1] if town and town in addr else addr
        m = _ROAD_RE.search(rest)
        road = m.group(1) if m else ""
        road = re.sub(r"^.*?(里|村|鄰)", "", road) or road
        dt = d.get("交易年月日", "")
        built = d.get("建築完成年月", "")
        age = None
        if len(built) >= 5 and built[:-4].isdigit():
            age = NOW.astimezone(TPE).year - (int(built[:-4]) + 1911)
        num_m = re.search(re.escape(road) + r"(.{0,14}?號)", rest) if road else None
        out.append({"city": d["city"], "town": town, "road": road, "unit": round(unit, 1), "total": round(total / 10000), "ping": round(ping, 1),
                    "date": f"{dt[:-4]}/{dt[-4:-2]}/{dt[-2:]}" if len(dt) >= 7 else dt, "type": re.sub(r"\(.*?\)", "", d.get("建物型態", ""))[:6],
                    "floor": (d.get("移轉層次", "")[:8] + "/" + d.get("總樓層數", "")[:6]).strip("/"), "age": age,
                    "room": d.get("建物現況格局-房", ""), "no": num_m.group(1) if num_m else "", "car": bool(pk_p)})
    return out


def _med(v):
    v = sorted(v)
    return round(v[len(v) // 2], 1) if v else None


def p_house():
    """實價登錄：最近一季住宅買賣。全台各鄉鎮中位數（上地圖）＋各縣市明細檔（區→路段→成交，分頁面板用）。"""
    seasons = _plvr_seasons()
    rows, used = [], ""
    for ssn in seasons[:3]:
        try:
            rows = _plvr_rows(ssn)
        except Exception as e:  # noqa: BLE001
            log("plvr", ssn, e); rows = []
        if len(rows) >= 20000:
            used = ssn
            break
    if not rows:
        raise RuntimeError("plvr: no rows")
    used = used or seasons[2]
    deals = _plvr_clean(rows)
    # 前一季的各區中位數（算季變化）；歷史裡沒有才多抓一次
    prev_ssn = seasons[seasons.index(used) + 1] if used in seasons and seasons.index(used) + 1 < len(seasons) else None
    if prev_ssn and not any(prev_ssn == r[0] for r in HISTORY.get("house_town", {}).get("臺北市大安區", [])):
        try:
            pv: dict = {}
            for d in _plvr_clean(_plvr_rows(prev_ssn)):
                pv.setdefault(d["city"] + d["town"], []).append(d["unit"])
            for k, v in pv.items():
                if len(v) >= 5:
                    hist_put("house_town", k, prev_ssn, _med(v))
        except Exception as e:  # noqa: BLE001
            log("plvr prev", e)
    by_town: dict = {}
    for d in deals:
        by_town.setdefault((d["city"], d["town"]), []).append(d)
    towns, by_city, detail = [], {}, {}
    for (city, town), lst in by_town.items():
        units = [d["unit"] for d in lst]
        by_city.setdefault(city, []).extend(units)
        if len(lst) < 3:
            continue
        med = _med(units)
        hist_put("house_town", city + town, used, med)
        h = HISTORY.get("house_town", {}).get(city + town, [])
        prev = next((v for s_, v in reversed(h) if s_ < used), None)
        chg = round(100 * (med / prev - 1), 1) if prev else None
        t = TOWNS.get(city + town) or TOWNS.get(city.replace("臺", "台") + town)
        if t and len(lst) >= 5:
            towns.append([t[0], t[1], city, town, med, len(lst)])
        roads: dict = {}
        for d in lst:
            roads.setdefault(d["road"] or "（未載路名）", []).append(d)
        road_rows = []
        for rd, rl in roads.items():
            rl.sort(key=lambda x: x["date"], reverse=True)
            types: dict = {}
            for d in rl:
                types[d["type"]] = types.get(d["type"], 0) + 1
            road_rows.append({"road": rd, "n": len(rl), "med": _med([d["unit"] for d in rl]), "tot": _med([d["total"] for d in rl]),
                              "ping": _med([d["ping"] for d in rl]), "type": max(types, key=types.get) if types else "",
                              "deals": [{k: d[k] for k in ("date", "no", "floor", "ping", "total", "unit", "type", "age", "room", "car")} for d in rl[:8]]})
        road_rows.sort(key=lambda x: -x["n"])
        us = sorted(units)
        types: dict = {}
        for d in lst:
            types[d["type"]] = types.get(d["type"], 0) + 1
        detail.setdefault(city, []).append({"town": town, "n": len(lst), "med": med, "p25": us[len(us) // 4], "p75": us[3 * len(us) // 4], "chg": chg,
                                            "tot": _med([d["total"] for d in lst]), "types": sorted(types.items(), key=lambda x: -x[1])[:4], "roads": road_rows[:60]})
    hd = DATA / "house"
    hd.mkdir(exist_ok=True)
    for city, lst in detail.items():
        lst.sort(key=lambda x: -x["med"])
        write_json(hd / f"{city}.json", {"season": used, "city": city, "towns": lst, "n": sum(x["n"] for x in lst)}, separators=(",", ":"))
    city_med = {c: _med(v) for c, v in by_city.items()}
    for c, v in city_med.items():
        hist_put("house", c, used, v)
    towns.sort(key=lambda x: -x[4])
    return {"season": used, "towns": towns, "city": city_med, "cityN": {c: len(v) for c, v in by_city.items()}, "rows": len(rows), "deals": len(deals),
            "files": sorted(detail)}


# ---------- 104 職缺：不限產業，依職類、縣市、產業分類 ----------
J104 = "https://www.104.com.tw/jobs/search/api/jobs"
J104_H = {"Referer": "https://www.104.com.tw/jobs/search/", "Accept": "application/json"}
J104_CAT = [("2001000000", "經營／人資"), ("2002000000", "行政／總務／法務"), ("2003000000", "財會／金融"), ("2004000000", "行銷／企劃／專案"),
            ("2005000000", "客服／門市／業務／貿易"), ("2006000000", "餐飲／旅遊／美容美髮"), ("2007000000", "資訊軟體"), ("2008000000", "研發"),
            ("2009000000", "生產製造／品管"), ("2010000000", "操作／技術／維修"), ("2011000000", "物流／運輸"), ("2012000000", "營建／製圖"),
            ("2013000000", "傳播藝術／設計"), ("2014000000", "文字／傳媒"), ("2015000000", "醫療／保健"), ("2016000000", "教育／輔導"),
            ("2017000000", "軍警消／保全"), ("2018000000", "其他")]
J104_AREA = [("6001001000", "台北市", ["臺北市"]), ("6001002000", "新北市", ["新北市"]), ("6001005000", "桃園市", ["桃園市"]), ("6001006000", "新竹縣市", ["新竹市", "新竹縣"]),
             ("6001008000", "台中市", ["臺中市"]), ("6001014000", "台南市", ["臺南市"]), ("6001016000", "高雄市", ["高雄市"]), ("6001004000", "基隆市", ["基隆市"]),
             ("6001003000", "宜蘭縣", ["宜蘭縣"]), ("6001007000", "苗栗縣", ["苗栗縣"]), ("6001010000", "彰化縣", ["彰化縣"]), ("6001011000", "南投縣", ["南投縣"]),
             ("6001012000", "雲林縣", ["雲林縣"]), ("6001013000", "嘉義縣市", ["嘉義市", "嘉義縣"]), ("6001018000", "屏東縣", ["屏東縣"]), ("6001020000", "花蓮縣", ["花蓮縣"]),
             ("6001019000", "台東縣", ["臺東縣"]), ("6001021000", "澎湖縣", ["澎湖縣"]), ("6001022000", "金門縣", ["金門縣"]), ("6001023000", "連江縣", ["連江縣"])]
J104_IND = {"1001": "電子資訊／半導體", "1002": "一般製造", "1003": "批發零售", "1004": "金融保險", "1005": "文教", "1006": "大眾傳播", "1007": "旅遊休閒運動",
            "1008": "法律會計顧問設計", "1009": "一般服務", "1010": "運輸物流", "1011": "營建不動產", "1012": "醫療保健", "1013": "政治宗教社福", "1014": "農林漁牧水電",
            "1015": "礦業", "1016": "住宿餐飲"}


def _j104(**params):
    j = gjson(J104, params={"page": 1, "pagesize": 30, **params}, headers=J104_H, timeout=30)
    return j, int(((j.get("metadata") or {}).get("pagination") or {}).get("total") or 0)


def p_jobs():
    today = NOW.astimezone(TPE).date().isoformat()
    j, total = _j104()
    if not total:
        raise RuntimeError("104: no total")
    hist_put("jobs", "total", today, total)
    def chg(key, v):
        h = HISTORY.get("jobs", {}).get(key, [])
        old = next((x for d, x in reversed(h) if d <= (NOW.astimezone(TPE).date() - timedelta(days=7)).isoformat()), None)
        return round(100 * (v / old - 1), 1) if old else None
    cats = []
    for code, name in J104_CAT:
        try:
            _, n = _j104(jobcat=code)
            hist_put("jobs", "cat:" + name, today, n)
            cats.append({"name": name, "n": n, "chg7": chg("cat:" + name, n), "spark": hist_get("jobs", "cat:" + name, 30)})
        except Exception as e:  # noqa: BLE001
            log("104 cat", name, e)
        time.sleep(0.6)
    areas = []
    for code, name, counties in J104_AREA:
        try:
            _, n = _j104(area=code)
            hist_put("jobs", "area:" + name, today, n)
            areas.append({"name": name, "counties": counties, "n": n, "chg7": chg("area:" + name, n)})
        except Exception as e:  # noqa: BLE001
            log("104 area", name, e)
        time.sleep(0.6)
    inds = []  # 各產業刊登中職缺（看哪個產業在搶人）
    for code, name in J104_IND.items():
        if name == "礦業":
            continue
        try:
            _, n = _j104(indcat=code + "000000")
            if not n or n >= total:  # 參數沒生效會回全站總數
                continue
            hist_put("jobs", "ind:" + name, today, n)
            inds.append({"name": name, "n": n, "chg7": chg("ind:" + name, n), "spark": hist_get("jobs", "ind:" + name, 30)})
        except Exception as e:  # noqa: BLE001
            log("104 ind", name, e)
        time.sleep(0.6)
    inds.sort(key=lambda x: -x["n"])
    latest, seen = [], set()
    for page in (1, 2, 3):
        try:
            jj = j if page == 1 else gjson(J104, params={"page": page, "pagesize": 30}, headers=J104_H, timeout=30)
        except Exception as e:  # noqa: BLE001
            log("104 page", e); break
        for x in jj.get("data") or []:
            no = x.get("jobNo")
            if not no or no in seen:
                continue
            seen.add(no)
            lat, lon = num(x.get("lat")), num(x.get("lon"))
            link = x.get("link") or {}
            if isinstance(link, str):
                m = re.search(r"'job':\s*'([^']+)'", link); link = {"job": m.group(1) if m else ""}
            lo, hi = num(x.get("salaryLow")) or 0, num(x.get("salaryHigh")) or 0
            latest.append({"t": (x.get("jobName") or "")[:60], "co": (x.get("custName") or "")[:30], "ind": J104_IND.get(str(x.get("coIndustry") or "")[:4], "其他"),
                           "indd": (x.get("coIndustryDesc") or "")[:16], "place": (x.get("jobAddrNoDesc") or "")[:10], "date": x.get("appearDate") or "",
                           "sal": [lo, hi if hi < 9999999 else 0], "u": link.get("job") or "",
                           "ll": [round(lon, 4), round(lat, 4)] if lat and lon and 118 < lon < 123 and 21 < lat < 27 else None})
        time.sleep(0.6)
    latest.sort(key=lambda x: x["date"], reverse=True)
    ind_mix: dict = {}
    for x in latest:
        ind_mix[x["ind"]] = ind_mix.get(x["ind"], 0) + 1
    cats.sort(key=lambda x: -x["n"])
    return {"total": total, "chg7": chg("total", total), "spark": hist_get("jobs", "total", 60), "cats": cats, "inds": inds, "areas": areas, "latest": latest[:90],
            "indMix": sorted(ind_mix.items(), key=lambda x: -x[1]), "src": "104 人力銀行"}


# ---------- 上市櫃重大訊息（證交所、櫃買中心）：分類、依公司地址上地圖 ----------
MOPS_SRC = [("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
            ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O")]
MOPS_CAT = [("澄清", r"澄清|媒體報導|報載"), ("事故", r"火災|爆炸|事故|停工|停產|災害|資安|網路攻擊|駭客|勒索"),
            ("更名／面額", r"更名|名稱變更|變更名稱|面額"),
            ("人事", r"董事長|總經理|發言人|財務主管|會計主管|稽核主管|研發主管|董事(?!會)|監察人|經理人|獨立董事|委員|辭任|解任|異動"),
            ("營運", r"臨床|新藥|IND|藥證|許可證|訂單|合約|簽約|專利|認證|新產品|量產|得標|授權|投產|擴廠|產能"),
            ("法律", r"訴訟|判決|裁罰|罰鍰|檢調|搜索|起訴|仲裁|裁定"),
            ("財務", r"營收|財報|財務報告|盈餘|股利|配息|背書保證|資金貸與|借款|公司債|庫藏股|減資|自結|限制員工|員工認股|基準日|現金增資|發行新股"),
            ("併購投資", r"合併|收購|併購|公開收購|股權|轉投資|合資|策略聯盟|設立.*子公司|子公司.*設立|分割|增資"),
            ("資產交易", r"取得|處分|不動產|使用權資產|設備|土地|廠房|有價證券"),
            ("會議", r"董事會|股東會|法人說明會|業績發表|說明會"), ("主管機關", r"證券交易所|櫃買中心|證期局|金管會|函辦理")]


def _roc8(s):
    s = str(s).strip()
    return f"{int(s[:-4]) + 1911}-{s[-4:-2]}-{s[-2:]}" if len(s) >= 6 and s[:-4].isdigit() else s


def p_mops():
    prev = load_prev("mops") or {}
    cache_p = DATA / "listed_basic.json"
    basic = {}
    try:
        c = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
        if c.get("at", "") > (NOW - timedelta(days=7)).isoformat():
            basic = c.get("map") or {}
    except Exception:  # noqa: BLE001
        basic = {}
    errs = []
    if not basic:
        for mk, _, bu in MOPS_SRC:
            try:
                for r in gjson(bu, timeout=60):
                    r = {k.strip(): v for k, v in r.items()}
                    code = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
                    if code:
                        basic[code] = [str(r.get("住址") or r.get("Address") or "")[:40], str(r.get("公司簡稱") or r.get("CompanyAbbreviation") or "")[:10], str(r.get("產業別") or "")[:4], mk]
            except Exception as e:  # noqa: BLE001
                errs.append(f"{mk}基本資料: {safe_err(e)}")
        if basic:
            write_json(cache_p, {"at": NOW_ISO, "map": basic}, separators=(",", ":"))
    items = []
    for mk, u, _ in MOPS_SRC:
        try:
            for r in gjson(u, timeout=60):
                r = {k.strip(): v for k, v in r.items()}
                code = str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
                subj = re.sub(r"\s+", " ", str(r.get("主旨") or r.get("Subject") or "")).strip()
                if not code or not subj:
                    continue
                cat = next((c for c, rx in MOPS_CAT if re.search(rx, subj)), "其他")
                b = basic.get(code) or ["", "", "", mk]
                pl = _place(b[0]) if b[0] else None
                items.append({"d": _roc8(r.get("發言日期") or r.get("Date") or ""), "tm": str(r.get("發言時間") or "").zfill(6)[:4], "code": code,
                              "name": str(r.get("公司名稱") or r.get("CompanyName") or b[1])[:16], "short": b[1], "mk": mk, "cat": cat, "t": subj[:120],
                              "desc": re.sub(r"\s+", " ", str(r.get("說明") or ""))[:300], "addr": b[0], "ll": pl[:2] if pl else None,
                              "place": pl[2] if pl else "", "u": f"https://mops.twse.com.tw/mops/#/web/t05st01?companyId={code}"})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{mk}重大訊息: {safe_err(e)}")
    # 開放資料只給最新一天：跟上一輪合併，留 14 天
    cutoff = (NOW.astimezone(TPE).date() - timedelta(days=14)).isoformat()
    keyset, merged = set(), []
    for it in items + (prev.get("items") or []):
        k = (it.get("code"), it.get("d"), it.get("t", "")[:40])
        if k in keyset or (it.get("d") or "") < cutoff:
            continue
        keyset.add(k); merged.append(it)
    if not merged:
        raise RuntimeError("mops: nothing " + "; ".join(errs)[:150])
    merged.sort(key=lambda x: (x.get("d", ""), x.get("tm", "")), reverse=True)
    for it in merged:  # 類別規則改了也套到舊資料
        it["cat"] = next((c for c, rx in MOPS_CAT if re.search(rx, it.get("t", ""))), "其他")
    cats: dict = {}
    for it in merged:
        cats[it["cat"]] = cats.get(it["cat"], 0) + 1
    return {"items": merged[:400], "cats": sorted(cats.items(), key=lambda x: -x[1]), "today": len(items), "errs": errs}


# ---------- 新公司：用經濟部商工登記查地址、負責人、資本額（結果快取，不重查） ----------
GCIS_CO = "https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C"


def _gcis_enrich(names, budget=40):
    cp = DATA / "gcis_cache.json"
    try:
        cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    except Exception:  # noqa: BLE001
        cache = {}
    n = 0
    for nm in names:
        if nm in cache or n >= budget or not nm.endswith("公司"):
            continue
        n += 1
        try:
            rows = gjson(GCIS_CO, params={"$format": "json", "$filter": f"Company_Name like {nm} and Company_Status eq 01", "$skip": 0, "$top": 5}, timeout=20) or []
            r = next((x for x in rows if x.get("Company_Name") == nm), rows[0] if rows else None)
            cache[nm] = {"addr": (r or {}).get("Company_Location", "")[:60], "boss": (r or {}).get("Responsible_Name", "")[:12],
                         "ban": (r or {}).get("Business_Accounting_NO", ""), "paid": num((r or {}).get("Paid_In_Capital_Amount"))} if r else {}
        except Exception as e:  # noqa: BLE001
            log("gcis", nm, e); break
        time.sleep(0.4)
    if n:
        write_json(cp, cache, separators=(",", ":"))
    return cache


# ---------- 台指期籌碼（期交所開放資料）----------
TAIFEX = "https://openapi.taifex.com.tw/v1/"


def p_taifex():
    rows = gjson(TAIFEX + "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate", timeout=40)
    want = {"臺股期貨": "台指期", "小型臺指期貨": "小台", "微型臺指期貨": "微台"}
    out, date = {}, ""
    for r in rows:
        name = want.get(str(r.get("ContractCode") or "").strip())
        if not name:
            continue
        who = str(r.get("Item") or "")
        who = "外資" if "外資" in who else "投信" if "投信" in who else "自營商" if "自營" in who else who
        rd = str(r.get("Date") or "")
        date = date or (roc_to_iso(rd) if len(rd) == 7 else f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}")
        oi = num(r.get("OpenInterest(Net)"))
        out.setdefault(name, {})[who] = {"oi": oi, "vol": num(r.get("TradingVolume(Net)")), "val": round((num(r.get("ContractValueofOpenInterest(Net)(Thousands)")) or 0) / 100000, 1)}
        hist_put("taifex", f"{name}:{who}", date, oi)
    if not out:
        raise RuntimeError("taifex: no rows")
    for name, d in out.items():
        for who, v in d.items():
            h = hist_get("taifex", f"{name}:{who}", 20)
            v["chg"] = (h[-1] - h[-2]) if len(h) >= 2 else None
            v["spark"] = h
    pcr = []
    try:
        for r in gjson(TAIFEX + "PutCallRatio", timeout=40)[:10]:
            pcr.append({"d": str(r.get("Date")), "vol": num(r.get("PutCallVolumeRatio%")), "oi": num(r.get("PutCallOIRatio%"))})
    except Exception as e:  # noqa: BLE001
        log("pcr", e)
    return {"date": date, "fut": out, "pcr": pcr}


# ---------- 美股巨頭、期貨與美債（Yahoo）----------
US_BIG = [("NVDA", "Nvidia"), ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta"),
          ("TSLA", "Tesla"), ("AVGO", "Broadcom"), ("TSM", "台積電 ADR")]
US_FUT = [("ES=F", "S&P 500 期", "idx"), ("NQ=F", "Nasdaq 期", "idx"), ("YM=F", "道瓊期", "idx"), ("RTY=F", "羅素 2000 期", "idx"), ("NIY=F", "日經期", "idx"),
          ("^IRX", "美債 3 個月", "y"), ("^TNX", "美債 10 年", "y"), ("^TYX", "美債 30 年", "y")]


def p_usbig():
    big, fut, errs = [], [], []
    for sym, name in US_BIG:
        try:
            q = yahoo_daily(sym, "2mo")
            big.append({"sym": sym, "name": name, "price": q["price"], "chg_pct": q["chg_pct"], "chg5_pct": q["chg5_pct"], "open": q["open"], "spark": q["closes"][-30:]})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{sym}: {safe_err(e)}")
    for sym, name, kind in US_FUT:
        try:
            q = yahoo_daily(sym, "2mo")
            cl = q["closes"]
            bp = round((cl[-1] - cl[-2]) * 100, 1) if kind == "y" and len(cl) >= 2 else None
            fut.append({"sym": sym, "name": name, "kind": kind, "price": q["price"], "chg_pct": q["chg_pct"], "bp": bp, "spark": cl[-30:]})
        except Exception as e:  # noqa: BLE001
            errs.append(f"{sym}: {safe_err(e)}")
    adr = None
    try:
        tsm = next(x for x in big if x["sym"] == "TSM")["price"]
        twd = yahoo_daily("TWD=X", "1mo")["price"]
        tw = next((it["price"] for it in (RESULTS.get("tw_stocks") or {}).get("items", []) if it["code"] == "2330"), None) or ((RESULTS.get("tw_market") or {}).get("tsmc") or {}).get("price")
        if tsm and twd and tw:
            adr = {"premium": round(100 * (tsm * twd / 5 / tw - 1), 1), "tsm": tsm, "twd": twd, "tw": tw}
    except Exception as e:  # noqa: BLE001
        errs.append(f"ADR: {safe_err(e)}")
    if not big and not fut:
        raise RuntimeError("usbig: nothing " + "; ".join(errs)[:150])
    return {"big": big, "fut": fut, "adr": adr, "errs": errs[:4]}

# ---------- 時事：台灣 / 國際 / 關鍵字 / 訊號 ----------
# Vin 的關注領域（Google News 繁中）：每組顯示最新 3 則。帶引號＝精準比對。改這裡。
NEWS_GROUPS = [
    ("廣告與代理商", ['"廣告代理商"', '"比稿" 廣告 OR 行銷 OR 品牌', "廣告不實 OR 誇大不實 開罰", '"數位廣告" OR "廣告量" 台灣', "坎城創意節 OR 時報廣告金像獎 OR 4A創意獎 OR 龍璽"]),
    ("品牌與設計", ['"品牌重塑" OR "品牌升級"', "台灣設計展 OR 文博會 OR 金點設計獎", '"視覺識別" OR "包裝設計"', "家具展 OR 室內設計 OR 設計師品牌"]),
    ("AI 大廠與模型", ["OpenAI OR Anthropic OR DeepMind 發布 OR 推出", "ChatGPT OR Claude OR Gemini 新功能 OR 新模型", "AI agent OR AI 代理人 OR 智慧代理",
                  "en:OpenAI OR Anthropic OR \"Google DeepMind\" launches OR announces OR releases", "en:\"AI agent\" OR agentic launch"]),
    ("AI 與製作工具", ["Sora OR Runway OR Kling 影片", "生成式AI 廣告 OR 生成式AI 版權", "Figma OR Canva 新功能", "開源模型 OR Ollama OR 本地部署"]),
    ("市場與投資", ["槓桿ETF OR 00631L OR 00675L", "聯準會 利率 OR FOMC", "台積電 法說 OR 台積電 ADR"]),
    ("地緣與科技政策", ["台海 OR 共機 OR 軍演", "關稅 台灣 OR 232條款", "半導體 出口管制 OR 晶片法案"]),
    ("時尚與奢華", ["LVMH OR Kering OR Hermès OR 愛馬仕", '"quiet luxury" OR 老錢風 穿搭', "時裝週 OR 創意總監 上任", "精品 台灣 OR 精品 業績"]),
    ("資訊安全", ["資安 OR 駭客 OR 勒索軟體 OR 個資外洩", "資安署 OR 數位發展部 資安 OR 資安法", "資安 新創 OR 資安 募資 OR 資安 併購",
              "en:cybersecurity breach OR ransomware OR \"zero-day\"", "en:\"AI security\" OR \"agent security\" startup"]),
    ("生物科技", ["生技 新藥 OR 生技 募資 OR 生技 授權", "細胞治療 OR 基因治療 OR 再生醫療 OR 外泌體", "FDA 核准 OR 食藥署 核准 新藥",
              "en:biotech raises OR \"drug discovery\" AI", "en:\"AI biology\" OR \"protein design\" OR \"gene editing\""]),
    ("文化與生活", ["廟宇 OR 媽祖 OR 民間信仰", "紀念幣 OR 錢幣 拍賣", "獨立書店 OR 誠品", "灣區 OR 舊金山 OR 加州 台灣人", "潭子 OR 台中 北屯"]),
]
# Google News 是全文比對，標題常跟關鍵字無關；以下查詢要求標題本身要命中這些字才收
WATCH_MUST = {
    '"比稿" 廣告 OR 行銷 OR 品牌': r"比稿|提案|標案|代理",
    "廣告不實 OR 誇大不實 開罰": r"廣告|誇大|不實",
    '"數位廣告" OR "廣告量" 台灣': r"廣告|行銷|媒體",
    "坎城創意節 OR 時報廣告金像獎 OR 4A創意獎 OR 龍璽": r"坎城|金像|4A|龍璽|創意獎|廣告獎",
    '"品牌重塑" OR "品牌升級"': r"品牌",
    "生成式AI 廣告 OR 生成式AI 版權": r"廣告|版權|著作|行銷|品牌|創作",
    '"quiet luxury" OR 老錢風 穿搭': r"老錢|quiet luxury|靜奢|穿搭|時尚",
    "生技 新藥 OR 生技 募資 OR 生技 授權": r"新藥|募資|臨床|授權|併購|FDA|核准|試驗",
    "家具展 OR 室內設計 OR 設計師品牌": r"家具|室內|設計",
}
# 中港官媒、轉載站與明顯不相干的標題
WATCH_SRC_BLOCK = re.compile(r"大公|文匯|新華|人民網|中新|環球網|央視|觀察者|新浪|搜狐|網易|鳳凰|IndexBox|tkww|takungpao|wenweipo|chinanews|xinhua|people\.com|cctv|huanqiu|guancha|sina|sohu|163\.com|ifeng", re.I)
WATCH_NOISE = re.compile(r"抓去關|處置股|試駕|開箱|星座|運勢|今彩|威力彩|大樂透|發票中獎")
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


# 開獎、樂透這類每天固定發的稿件不是新聞訊號，會擠掉真的頭條
NEWS_NOISE = re.compile(r"今彩\s*539|威力彩|大樂透|雙贏彩|3星彩|4星彩|賓果賓果|樂透|統一發票.*(?:中獎號碼|開獎)|頭獎.*(?:槓龜|中獎)")


def p_news():
    NEWS_ERRS.clear(); HOT_POOL.clear()
    tw = []
    for feed in ("politics", "finance", "technology"):
        tw += _try("cna " + feed, _rss, f"https://feeds.feedburner.com/rsscna/{feed}", "中央社", 6)
    if not tw:
        tw += _try("cna gnews", _gnews, "site:cna.com.tw", "中央社", 8)
    pts = _try("pts", _rss, "https://news.pts.org.tw/xml/newsfeed.xml", "公視", 6) or _try("pts gnews", _gnews, "site:news.pts.org.tw", "公視", 5)
    tw = [n for n in tw + pts if not NEWS_NOISE.search(n.get("title") or "")]
    pts = [n for n in tw if n.get("source") == "公視"]; tw = [n for n in tw if n.get("source") != "公視"]
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
        got, all7 = [], []
        for q in qs:
            lang = "en" if q.startswith("en:") else "zh"
            must = WATCH_MUST.get(q)
            lim = 8 if must else 4
            full = _try("kw " + q, _gnews, q[3:] if lang == "en" else q, "", 100, lang)
            for i, it in enumerate(full):
                if WATCH_SRC_BLOCK.search(it.get("source") or "") or WATCH_NOISE.search(it.get("title") or ""):
                    continue
                if must and not re.search(must, it.get("title") or "", re.I):
                    continue
                it["kw"] = q; all7.append(it)
                if i < lim:
                    got.append(it)
            time.sleep(0.8)
        # 每組 4 則：關鍵字輪流各出一則（避免單一話題洗版），標題前 14 字相同視為同一則
        fresh_cut = (NOW - timedelta(days=21)).isoformat()
        got = [g for g in got if (g.get("at") or "") >= fresh_cut]  # 三週以上的舊聞不進 Watchlist
        HOT_POOL.extend(got)  # 熱詞引擎看全部命中，不只面板挑出的 3 則
        by_kw = {q: _dedupe_sort([g for g in got if g["kw"] == q], 4) for q in qs}
        picked, seen = [], set()
        for rnd in range(4):
            for q in qs:
                if len(picked) >= 4:
                    break
                for it in by_kw[q][rnd:rnd + 1]:
                    k = re.sub(r"\W+", "", it["title"])[:14]
                    if k not in seen:
                        seen.add(k); picked.append(it)
        # 近 7 天每天幾則（用全部命中、去重後算，不是只看挑出來的 4 則）
        d7, seen7 = {}, set()
        for it in all7:
            k7 = re.sub(r"\W+", "", it.get("title") or "")[:14]
            if not it.get("at") or k7 in seen7:
                continue
            seen7.add(k7)
            dd = datetime.fromisoformat(it["at"].replace("Z", "+00:00")).astimezone(TPE).date().isoformat()
            d7[dd] = d7.get(dd, 0) + 1
        days7 = [(TODAY_TPE - timedelta(days=6 - i)).isoformat() for i in range(7)]
        groups.append({"name": name, "items": picked, "daily7": [d7.get(d, 0) for d in days7], "days7": days7})

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
        ("deepseek", lambda: [{**c, "source": "DeepSeek"} for c in _changelog("https://api-docs.deepseek.com/updates/", "DeepSeek", "deepseek", 4)], (), "DeepSeek", "deepseek"),
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
            for r in gjson(f"https://api.github.com/orgs/{org}/repos", params={"sort": "created", "per_page": 8}, headers=gh_hdr):
                # 內部元件、fork、封存的 repo 不是發布訊號（例如 DeepSeek Harness 的 dsh-* 元件）
                if r.get("fork") or r.get("archived") or re.search(r"internal|component used by|test|demo|template|mirror", r.get("description") or "", re.I):
                    continue
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
HOT_STOP_ZH = set("推出 發布 上線 代理 宣布 公布 曝光 揭曉 亮相 登場 開賣 開放 更新 升級 首度 首次 正式 全新 最新 安全 大安 中正 信義 台灣 台北 台中 高雄 新北 桃園 台南 中國 美國 日本 韓國 香港 全球 國際 國內 總統 政府 國會 立法院 立委 民眾 網友 記者 新聞 報導 影片 直播 專家 分析 表示 指出 認為 今天 今日 明天 昨天 上午 下午 晚間 凌晨 目前 最新 快訊 獨家 焦點 專題 系列 問題 情況 市場 公司 企業 產業 業者 消費者 用戶 台股 股市 大盤 個股 早盤 盤中 收盤 開盤 新台幣 美元 億元 萬元 億 萬 人 年 月 日 時 分 點 元 台 家 名 位 次 種 項 條 件 個 ETF 基金 投資人 股價 新功能 功能 模型 工具 服務 平台 系統 技術 應用 發展 影響 未來 時代 世界 生活 文化 設計 品牌 廣告 行銷 網路 社群 粉絲 議題 話題 討論 聲明 回應 消息 傳出 曝光 揭露 現場 畫面 一次 全部 這樣 這個 那個 什麼 怎麼 為何 為什麼 竟然 卻 竟 恐 將 再 也 都 又 就 才 最 更 很 太 還 已 已經 沒有 不是 就是 可以 可能 需要 應該 因為 所以 如果 但是 然而 以及 或者 之後 之前 之間 以上 以下 對於 關於 根據 透過 針對 包括 除了 另外 其中 其他 此外 關鍵 交流 論壇 合作 金融 經濟 合作 活動 計畫 計劃 成果 成功 重要 持續 加強 推動 提升 強化 支持 呼籲 啟動 舉辦 參與 發表 出席 會議 座談 研討 簽署 協議 方案 政策 措施 機制 挑戰 機會 風險 趨勢 布局 佈局 轉型 創新 升溫 降溫 大增 大減 不只 第一 首位 唯一 恐怕 背後 真相 原因 關係 狀況 結果 方式 方向 角色 價值 意義 重點 亮點 焦點".split())
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
        h = hits.setdefault(k, {"term": w, "n": 0, "sources": set(), "titles": set(), "sample": {"title": (it.get("title") or "")[:60], "url": it.get("url")}})
        h["n"] += 1; h["sources"].add(src)
        h["titles"].add(re.sub(r"\W+", "", it.get("title") or "")[:18])  # 同一篇稿被多家轉載只算一次

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
    for h in hits.values():
        h["eff"] = min(len(h["sources"]), len(h["titles"]))  # 有效來源數：不同來源且不同標題
    cands = [h for h in hits.values() if h["eff"] >= 2]
    # 同一組標題裡的中文碎片（國軍嚴密／嚴密監控／密監控應）只留最長的一個
    by_titles: dict = {}
    for h in cands:
        if re.search(r"[\u4e00-\u9fff]", h["term"]):
            key = frozenset(h["titles"])
            if key not in by_titles or len(h["term"]) > len(by_titles[key]["term"]):
                by_titles[key] = h
    cjk_keep = {id(h) for h in by_titles.values()}
    cands = [h for h in cands if not re.search(r"[\u4e00-\u9fff]", h["term"]) or id(h) in cjk_keep]
    # 最長匹配：短段若被某個更長的段涵蓋且來源集合相同 → 丟
    keep = []
    for h in cands:
        dominated = any(o is not h and h["term"] in o["term"] and len(o["term"]) > len(h["term"]) and o["sources"] >= h["sources"] for o in cands)
        if not dominated:
            keep.append(h)
    out = [{"term": h["term"], "n": h["n"], "src": h["eff"], "sources": sorted(h["sources"])[:6], "sample": h["sample"], "hot": h["eff"] >= 3} for h in keep]
    out.sort(key=lambda x: (-x["src"], -x["n"], -len(x["term"])))
    return out[:10]


def _hot_terms(news):
    pool = list(news.get("tw") or []) + list(news.get("intl") or []) + list(HOT_POOL)
    for pid in ("aiwire", "design"):
        pool += (load_prev(pid) or {}).get("items") or []
    for r in ((load_prev("ptt") or {}).get("items") or [])[:40]:
        pool.append({"title": r.get("title"), "source": "PTT", "url": r.get("url"), "at": NOW_ISO})
    rd = load_prev("radar") or {}
    for f in (rd.get("funding") or []):
        pool.append({"title": f.get("title"), "source": f.get("source") or "funding", "url": f.get("url"), "at": f.get("at") or NOW_ISO})
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
        if len(seeds) >= 4:  # grounding 每次要打 Gemini，關鍵字壓到 4 個省額度
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
        time.sleep(8)  # 免費層每分鐘請求數很低，慢慢打
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


def _gemini_call(prompt, model, json_mode=True, tools=None, max_tokens=6000):
    # maxOutputTokens 含「思考」token：預設思考會把輸出吃光而截斷 JSON，所以關掉思考、放大上限
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}}}
    if json_mode and not tools:  # 開了搜尋工具就不能強制 JSON，改由 prompt 要求
        body["generationConfig"]["responseMimeType"] = "application/json"
    if tools:
        body["tools"] = tools
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = S.post(url, params={"key": GEMINI_KEY}, json=body, timeout=90)
    if r.status_code == 400 and "thinking" in r.text.lower():  # 這個模型不接受 thinkingBudget（例如只支援 thinkingLevel）
        body["generationConfig"].pop("thinkingConfig", None)
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "LOW"}
        r = S.post(url, params={"key": GEMINI_KEY}, json=body, timeout=90)
        if r.status_code == 400:
            body["generationConfig"].pop("thinkingConfig", None)
            r = S.post(url, params={"key": GEMINI_KEY}, json=body, timeout=90)
    return r


def _gemini_json(prompt, schema_hint=None, tools=None):
    last = None
    for model in (_gemini_models() or GEMINI_MODELS):
        try:
            r = _gemini_call(prompt, model, tools=tools)
            if r.status_code in (429, 503):  # 每分鐘額度或過載：等 20 秒再試同一個模型一次
                time.sleep(20)
                r = _gemini_call(prompt, model, tools=tools)
            if r.status_code in (404, 429, 503):  # 還是不行 → 換下一個模型
                try:
                    msg = (r.json().get("error") or {}).get("message", "")[:90]
                except ValueError:
                    msg = ""
                last = RuntimeError(f"{model} {r.status_code} {msg}"); continue
            if r.status_code >= 400:
                raise RuntimeError(f"gemini {r.status_code} {r.text[:120]}")
            js = r.json()
            cand = js["candidates"][0]
            txt = "".join(p_.get("text", "") for p_ in cand["content"]["parts"] if not p_.get("thought"))  # 略過思考段
            txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())
            try:
                data = json.loads(txt)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", txt, re.S)
                if not m:
                    raise
                data = json.loads(m.group(0))
            if isinstance(data, dict):
                data["_grounding"] = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
            return data, model
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
            raw = ""
            try:
                raw = json.dumps(r.json(), ensure_ascii=False)[:260]
            except Exception:  # noqa: BLE001
                raw = r.text[:260]
            last = RuntimeError(f"{model} parse: {str(e)[:60]} raw={raw!r}")
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
    prompt = f"""你是台灣的輿情分析師。下面是今天從三個來源抓到的原文（PTT 熱文標題、LINE 群組正在轉傳並被拿去查證的訊息、Bluesky 英文貼文）。
請只根據這些文字判斷「大眾情緒」，不要加入你自己的時事知識。用繁體中文、台灣用語，不要用「不是…而是…」句型，不要空泛。

輸出 JSON，格式：
{{
  "taiwan": {{"score": -1到1的小數（-1 極負面、0 中性、1 極正面）, "label": "兩到四個字的情緒標籤，例如 焦慮、亢奮、無感、憤怒", "themes": ["最多三個正在燒的主題，各 2-6 字"], "line": "一句 40 字內的判讀：台灣人今天在意什麼、語氣如何"}},
  "overseas": {{"score": 同上, "label": 同上, "themes": [...], "line": "一句 40 字內的判讀（英文貼文的情緒）"}},
  "sources": {{"PTT": {{"score": 小數, "note": "15 字內"}}, "LINE": {{"score": 小數, "note": "15 字內"}}}},
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



# ---------- 公司雷達：盯梢層（固定 5 家）＋ 雷達層（自動發現新募資、Show HN、Product Hunt） ----------
RADAR_WATCH = [  # (名稱, 一句定位, Google News 英文查詢, HN 查詢, Bluesky 查詢)
    ("Instinct", "傳簡訊辦事的 AI 助理", '"Instinct" ("Noah Shinn" OR "AI assistant")', "Instinct Shinn", '"Instinct AI"'),
    ("Moda", "品牌簡報設計代理", '"Moda" AI ("design agent" OR presentations OR "brand")', "Moda design agent", '"Moda" AI design'),
    ("Flora", "節點式創意畫布", '"Flora" AI (canvas OR creative OR Redpoint)', "Flora creative canvas", '"Flora" AI canvas'),
    ("Flick", "AI 拍片工作台", '"Flick" AI (filmmaking OR film OR video)', "Flick AI filmmaking", '"Flick" AI film'),
    ("Fish Audio", "聲音複製與配音", '"Fish Audio"', '"Fish Audio"', '"Fish Audio"'),
]
RADAR_TOPIC = re.compile(r"\b(design|designer|video|film|image|photo|creative|brand|branding|marketing|advert|ads?\b|voice|audio|music|presentation|slides?|deck|content|avatar|animation|3D|motion|font|typograph|assistant|agent|ugc|influencer|commerce|fashion|retail)", re.I)
RADAR_RAISE = re.compile(r"^(?P<co>[A-Z][\w.&'’\- ]{1,40}?)(?:,.{0,60}?,)?\s+(?:raises|lands|secures|closes|nabs|bags|gets|snags|picks up|announces)\s+(?:a\s+)?\$?(?P<amt>[\d.]+)\s*(?P<unit>[MB]|million|billion)", re.I)
RADAR_HIST = "radar"
RADAR_SKIP = re.compile(r"fintech|bank|payment|compliance|legal|insur|crypto|blockchain|logistics|supply chain|devops|database|infra", re.I)
RADAR_CATS = [  # 標籤 → 判斷規則（依序比對，第一個命中的為準）
    ("資安", re.compile(r"secur|cyber|threat|identity|zero.trust|fraud|breach|vulnerab|pentest|soc\b", re.I)),
    ("生技", re.compile(r"biotech|\bbio\b|pharma|\bdrugs?\b|therapeut|\bgenes?\b|genetic|genom|protein|antibod|\bcells?\b|molecul|clinical|diagnos|life science", re.I)),
    ("創意", re.compile(r"design|video|\bfilm|image|photo|creative|\bbrand(?:s|ing|ed)?\b|marketing|advert|voice|audio|music|presentation|slides?|deck|content|avatar|animation|3D|motion|font|ugc|influencer|fashion|retail|commerce", re.I)),
    ("AI 助理", re.compile(r"assistant|agent|copilot", re.I)),
]


def _radar_cat(t):
    return next((c for c, rx in RADAR_CATS if rx.search(t)), None)


def _hn_search(q, days=7, tags="story", min_points=0, by_date=True, hits=20):
    since = int((NOW - timedelta(days=days)).timestamp())
    js = gjson("https://hn.algolia.com/api/v1/" + ("search_by_date" if by_date else "search"),
               params={"query": q, "tags": tags, "numericFilters": f"created_at_i>{since},points>={min_points}", "hitsPerPage": hits})
    out = []
    for h in js.get("hits") or []:
        out.append({"title": h.get("title") or "", "points": h.get("points") or 0, "comments": h.get("num_comments") or 0,
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "hn": f"https://news.ycombinator.com/item?id={h.get('objectID')}", "at": (h.get("created_at") or "")[:19] + "Z"})
    return out


def _radar_amount(m):
    v = float(m.group("amt")); u = m.group("unit").lower()
    return v * 1000 if u in ("b", "billion") else v


def p_radar():
    errs, watch, funding, showhn, ph = [], [], [], [], []
    cut7 = (NOW - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    cut1 = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    # 盯梢層
    for name, desc, gq, hq, bq in RADAR_WATCH:
        rec = {"name": name, "desc": desc, "news": [], "n_news7": 0, "n_hn7": 0, "n_bsky1": 0, "hn_top": None}
        news = _try("radar news " + name, _gnews, gq, "", 10, "en")
        news = [n_ for n_ in news if (n_.get("at") or "") >= cut7 and name.split()[0].lower() in (n_.get("title") or "").lower()]
        rec["news"] = news[:3]; rec["n_news7"] = len(news)
        try:
            hn = [h for h in _hn_search(hq, 7) if name.split()[0].lower() in h["title"].lower()]
            rec["n_hn7"] = len(hn)
            if hn:
                rec["hn_top"] = max(hn, key=lambda h: h["points"])
        except Exception as e:  # noqa: BLE001
            errs.append(f"hn {name}: {safe_err(e)[:60]}")
        try:
            b = _bsky_search(bq, 25)
            rec["n_bsky1"] = sum(1 for x in b if (x.get("at") or "") >= cut1)
        except Exception as e:  # noqa: BLE001
            errs.append(f"bsky {name}: {safe_err(e)[:60]}")
        score = rec["n_news7"] * 3 + rec["n_hn7"] * 2 + rec["n_bsky1"]
        hist_put(RADAR_HIST, name, TODAY_TPE.isoformat(), score)
        hs = hist_get(RADAR_HIST, name, 30)
        base = sorted(hs[:-1])[len(hs[:-1]) // 2] if len(hs) > 3 else None  # 過去中位數
        rec["score"] = score; rec["spark"] = hs
        rec["spike"] = bool(base is not None and score >= max(6, base * 2))
        watch.append(rec)
        time.sleep(0.6)
    # 雷達層 1：新募資（英文新聞，只留小額、主題相關）
    seen = set()
    for q in ('AI ("raises" OR "lands" OR "secures") ("seed" OR "Series A") (design OR video OR creative OR marketing OR brand)',
              'startup raises seed round AI (video OR image OR voice OR assistant OR agent OR presentations)',
              '("raises" OR "secures") ("seed" OR "Series A") (cybersecurity OR "security startup" OR "AI security")',
              '("raises" OR "secures") ("seed" OR "Series A") (biotech OR "drug discovery" OR "AI biology" OR therapeutics)'):
        for n_ in _try("radar funding", _gnews, q, "", 20, "en"):
            t = n_.get("title") or ""
            m = RADAR_RAISE.search(t)
            cat = _radar_cat(t)
            if not m or (n_.get("at") or "") < cut7 or not cat or RADAR_SKIP.search(t):
                continue
            co = m.group("co").strip(" ,")
            mm = re.search(r"rebrands as ([A-Z][\w.\-]+)", t)
            if mm:
                co = mm.group(1)
            co = re.sub(r"^.*?-based\s+(?:[a-z][\w\-]*\s+)*", "", co)  # Milan-based biotech Aptadir → Aptadir
            co = re.sub(r"^(?:AI|startup|biotech|cybersecurity|security)\s+(?:startup\s+)?", "", co, flags=re.I).strip()
            amt = _radar_amount(m)
            if amt > 150 or co.lower() in seen:  # 1.5 億美元以上就不是「小」了
                continue
            seen.add(co.lower())
            stage = "種子" if re.search(r"seed|pre-seed", t, re.I) else "A 輪" if re.search(r"series a\b", t, re.I) else "B 輪" if re.search(r"series b\b", t, re.I) else ""
            funding.append({"company": co, "amount": amt, "stage": stage, "cat": cat, "title": t[:110], "url": n_.get("url"), "at": n_.get("at"), "source": n_.get("source")})
        time.sleep(0.8)
    funding.sort(key=lambda x: x.get("at") or "", reverse=True)
    # 雷達層 2：Show HN（兩天內、≥20 分、主題相關）
    try:
        for h in _hn_search("", 2, tags="show_hn", min_points=20, hits=60):
            cat = _radar_cat(h["title"])
            if cat and not RADAR_SKIP.search(h["title"]):
                showhn.append({**h, "cat": cat})
        showhn.sort(key=lambda h: -h["points"])
    except Exception as e:  # noqa: BLE001
        errs.append("show hn: " + safe_err(e)[:80])
    # 雷達層 3：Product Hunt 精選（RSS，抓不到就略過）
    try:
        for it in _rss("https://www.producthunt.com/feed", "Product Hunt", 40):
            cat = _radar_cat(it["title"])
            if cat:
                ph.append({**it, "cat": cat})
    except Exception as e:  # noqa: BLE001
        errs.append("product hunt: " + safe_err(e)[:60])
    if not watch and not funding and not showhn:
        raise RuntimeError(f"radar: nothing {errs[:3]}")
    # 每類最多 4 筆，避免單一類洗版
    per, fsel = {}, []
    for f in funding:
        if per.get(f["cat"], 0) < 4:
            per[f["cat"]] = per.get(f["cat"], 0) + 1; fsel.append(f)
    return {"watch": watch, "funding": fsel[:14], "showhn": showhn[:8], "ph": ph[:8], "errs": errs[:6]}


# ---------- 第三批（免新金鑰）：標案 / 設計廣告媒體 / 地震 / 台電 / 桃機 ----------
# 看政府把錢花在哪些產業方向（不是找案子）：關鍵字數量維持 5 個，不增加抓取次數
PCC_KW = ["人工智慧", "長照", "淨零", "觀光", "運動"]
PCC_EXCLUDE = ("拆除", "租賃", "印刷", "清潔", "保全")
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
                (("https://www.itsnicethat.com/rss", "https://www.itsnicethat.com/feed", "https://www.itsnicethat.com/articles.rss"), "INT", "site:itsnicethat.com"),
                ("https://campaignbriefasia.com/feed/", "CB Asia", "site:campaignbriefasia.com"),
                ("https://www.creativereview.co.uk/feed/", "CR", "site:creativereview.co.uk")]


def p_design():
    items, errs = [], []
    for url, src, q in DESIGN_FEEDS:
        got, last_e = [], None
        for u in (url if isinstance(url, tuple) else (url,)):
            try:
                got = _rss(u, src, 5)
                if got:
                    break
            except Exception as e:  # noqa: BLE001
                last_e = e
        if not got:
            log("design rss", src, last_e); errs.append(f"{src}: 官方 RSS 抓不到，改用 Google News")
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
                    "lat": num(epi.get("EpicenterLatitude")), "lon": num(epi.get("EpicenterLongitude")),
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
            if sid == "A191RL1Q225SBEA" or sid.endswith("Q"):
                per = f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"
            elif sid in ("ICSA", "DFF") or "DGS" in sid or sid.startswith("T10Y"):
                per = d[:10]
            else:
                per = d[:7]
            items.append({"group": group, "label": label, "value": txt, "raw": round(v, 3), "prev": ptxt, "period": per,
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
                if datetime.fromisoformat(d).weekday() < 5:  # 週末本來就不開盤，不列
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
    """決標公告：產業方向關鍵字（AI、長照、淨零、觀光、運動）誰得標、決標金額。"""
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
        pat = r"擴張（Expansion）(?:\s*\d+\s*)*?(\d+\.\d+)\s*%"  # 刻度是整數、數值帶小數，不綁刻度數量
        txt, inds = "", []
        for _load in range(2):  # 圖表是 JS 晚畫的：每次載入最多等 4×2.5 秒，還沒有就整頁重載一次
            pg = b.new_page(user_agent=UA, locale="zh-TW")
            try:
                pg.goto(f"https://index.ndc.gov.tw/n/zh_tw/{page}", wait_until="networkidle", timeout=60000)
            except Exception:  # noqa: BLE001
                pass
            for _ in range(4):
                pg.wait_for_timeout(2500)
                txt = pg.inner_text("body")
                if re.search(pat, txt):
                    break
            if re.search(pat, txt) and not inds:  # 各產業：同一頁的 JSON 介面（要帶頁面上的 csrf token）；data[0]＝產業指數、data[1]＝新增訂單
                try:
                    raw = pg.evaluate(_NDC_JS, f"/n/json/data/{page}/industry")
                    for ln in (json.loads(raw).get("line") or {}).values():
                        ser = (ln.get("data") or [[]])[0] or []
                        od = (ln.get("data") or [[], []])[1] if len(ln.get("data") or []) > 1 else []
                        if len(ser) < 2:
                            continue
                        nm = str(ln.get("name") or "")
                        nm = nm[:-1] if nm.endswith("不動產業") else nm[:-2] if nm.endswith("產業") else nm[:-1] if nm.endswith("業") else nm
                        inds.append({"name": nm, "value": ser[-1].get("y"), "prev": ser[-2].get("y"), "period": str(ser[-1].get("x") or ""),
                                     "orders": od[-1].get("y") if od else None, "spark": [x.get("y") for x in ser[-13:]]})
                except Exception as e:  # noqa: BLE001
                    log("ndc industry", page, e)
            pg.close()
            if re.search(pat, txt):
                break
        b.close()
    head = re.search(pat, txt)
    orders = re.search(r"新增訂單[^\n]*\n(?:\s*\d+\s*\n){4}\s*(\d+\.?\d*)\s*%", txt)
    ym = re.search(r"(20\d\d)\n(\d{1,2})月", txt)
    chg = re.search(r"較上月變化\s*([+-]?\d+(?:\.\d+)?)\s*百分點", txt)
    nxt = re.search(r"下次發布日期\s*:\s*(\d{4}-\d{2}-\d{2})", txt)
    if not head:
        npct = len(re.findall(r"\d+\.\d+\s*%", txt))
        raise RuntimeError(f"ndc {page} parse (len={len(txt)}, axis={'擴張（Expansion）' in txt}, pct={npct})")
    return {"value": float(head.group(1)), "orders": float(orders.group(1)) if orders else None,
            "period": f"{ym.group(1)}-{int(ym.group(2)):02d}" if ym else "", "chg": float(chg.group(1)) if chg else None,
            "next": nxt.group(1) if nxt else "", "inds": inds}


_NDC_JS = """async (u) => { const t=(document.querySelector('meta[name=csrf-token]')||{}).content||'';
  const r=await fetch(u,{method:'POST',headers:{'X-CSRF-TOKEN':t,'X-Requested-With':'XMLHttpRequest'}}); return await r.text(); }"""


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
            prev = (load_prev("supply") or {}).get(key)
            if not prev:  # 上一輪也沒有：從歷史序列補最後一個值
                sp = hist_get("supply", key, 24)
                if sp:
                    prev = {"value": sp[-1], "orders": None, "period": "", "chg": round(sp[-1] - sp[-2], 1) if len(sp) > 1 else None,
                            "next": "", "spark": sp}
            if prev:  # 抓不到就沿用上一次的值，標成舊值，不讓數字消失
                out[key] = {**prev, "stale": True}
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
        if out["retail"]:
            last = max(r_["period"] for r_ in out["retail"])
            expect = (TODAY_TPE.replace(day=1) - timedelta(days=1)).replace(day=1)  # 上個月
            if TODAY_TPE.day >= 25:
                expect = TODAY_TPE.replace(day=1)
            expect_p = (expect.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")  # 經濟部約每月 23 日公布「上上個月」
            if last < expect_p:
                out["retail_lag"] = {"have": last, "expect": expect_p}
                news = _try("retail news", _gnews, "零售業營業額 年增 經濟部統計處", "", 6)
                news = [n_ for n_ in news if (n_.get("at") or "") >= (NOW - timedelta(days=20)).isoformat() and re.search(r"零售|營業額", n_.get("title") or "")]
                if news:
                    out["retail_news"] = news[0]
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

# ---------- 新品牌雷達：每月新設立公司／商業登記、同業新設、得標排行 ----------
BRAND_CATS = [
    ("外商在台", r"^(香港商|新加坡商|美商|日商|英商|德商|法商|韓商|澳商|英屬|開曼|薩摩亞|塞席爾|馬來西亞商|越南商|荷蘭商|瑞士商)"),
    ("設計創意", r"設計|創意|影像|影音|影視|品牌|行銷|廣告|文創|傳播|傳媒|媒體|製作|攝影|藝術|視覺|動畫|內容|策展|整合行銷|創藝|彩藝|花藝|手作"),
    ("科技 AI", r"科技|資訊|智能|智慧|數位|軟體|網路|雲端|資安|電子|AI|人工智慧|機器人|半導體|系統|算力|通訊"),
    ("生技健康", r"生技|生醫|醫療|健康|藥|保健|醫學|診所|長照|照護|婦幼"),
    ("美容養生", r"美容|美學|美甲|美睫|化粧|化妝|保養|醫美|髮|美妝|紋繡|SPA|養生|推拿|整復|按摩|足體|美研"),
    ("餐飲", r"餐飲|咖啡|茶|烘焙|料理|小吃|飲|麵|甜點|酒|餐|食堂|廚房|便當|酥雞|滷味|肉飯|鍋物|火鍋|牛排|蔬食|冰品|豆花|餃子|炸雞|雞排|美食|食坊|小館|飯館|河粉|湯包|魚焿|蛋糕|食品|膳"),
    ("農漁食材", r"農產|水產|蔬果|果園|農場|漁業|水果|果行|鮮魚|苗園|草本|茶園"),
    ("零售選物", r"選物|選品|嚴選|生活館|小舖|本舖|販賣|專賣|百貨|用品|禮品|玩具|娃娃|商店|雜貨|貿易|進出口|商貿|電商|網購|物流"),
    ("時尚服飾", r"服飾|時尚|成衣|鞋|皮件|珠寶|精品|服裝|織|衣"),
    ("不動產營建", r"建設|營造|不動產|開發|地產|室內裝修|裝潢|工程|建築|物業|租賃住宅|包租|代管|租管|建材|五金|住宅|家居|冷氣|軟裝|水電|消防|機電|空調|耐火"),
    ("工業製造", r"工業|精密|機械|金屬|材料|鋼鐵|電機|自動化|動力|製造|製所|包裝|供應鏈|塑膠|化工|模具"),
    ("汽車交通", r"車業|汽車|車體|車修|車行|輪胎|通運|停車|機車|運輸|貨運|交通"),
    ("能源綠色", r"能源|綠能|太陽能|光電|儲能|電力|環保|回收|碳|永續|水務"),
    ("教育文化", r"教育|文教|補習|才藝|藝文|文化|音樂|歌唱|書院|學苑|語言"),
    ("休閒旅宿", r"旅行|旅遊|民宿|旅館|酒店|觀光|露營|渡假|運動|健身|瑜珈|休閒|娛樂|遊戲|高爾夫|匹克|體能|體育|育樂"),
    ("生活服務", r"人力|派遣|保全|清潔|禮儀|生命|病媒|洗衣|搬家|寵物|毛孩|照相|維修"),
    ("顧問服務", r"顧問|諮詢|管理|財務|會計|法律|專利|策略"),
    ("投資控股", r"投資|資產|控股|創投|資本"),
]


def _brand_cat(name):
    if re.search(r"消防|機電|水電|空調|冷凍|結構|土木|測量|環境工程", name or ""):
        return "不動產營建"
    if re.search(r"生命禮儀|禮儀", name or ""):
        return "生活服務"
    for c, pat in BRAND_CATS:
        if re.search(pat, name or ""):
            return c
    return "名稱看不出產業"


def _roc_date(s):
    s = str(s or "").strip()
    m = re.match(r"^(\d{2,3})(\d{2})(\d{2})$", s)
    return f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}" if m else ""


def _gov_dists(ds):
    """data.gov.tw 資料集的各月份下載連結，回傳 [(說明, url)]，新的在後。"""
    j = gjson(f"https://data.gov.tw/api/v2/rest/dataset/{ds}", timeout=40)
    out = []
    for d in (j.get("result") or {}).get("distribution") or []:
        u = d.get("resourceDownloadUrl") or d.get("downloadURL")
        if u:
            out.append((d.get("resourceDescription") or "", u))
    def ym(desc):
        m = re.search(r"(\d{4})年(\d{1,2})月", desc)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    out.sort(key=lambda x: ym(x[0]))
    return out


def _csv_rows(url, timeout=120):
    import csv, io
    b = get(url, timeout=timeout).content
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            t = b.decode(enc); break
        except Exception:
            t = None
    return list(csv.DictReader(io.StringIO(t or b.decode("utf-8", "ignore"))))


AW_LOG = DATA / "awards_log.json"


def p_brands():
    errs = []
    months = {}
    for ds, kind, name_k, date_k, addr_k in ((6047, "公司", "公司名稱", "核准設立日期", "公司所在地"), (6668, "商業", "商業名稱", "設立日期", "商業所在地")):
        try:
            dists = _gov_dists(ds)[-2:]
            for desc, u in dists:
                m = re.search(r"(\d{4})年(\d{1,2})月", desc)
                key = f"{m.group(1)}-{int(m.group(2)):02d}" if m else desc
                rows = _csv_rows(u)
                for r in rows:
                    nm = (r.get(name_k) or "").strip()
                    if not nm:
                        continue
                    months.setdefault(key, []).append({"name": nm, "kind": kind, "cap": num(r.get("資本額")), "date": _roc_date(r.get(date_k)),
                                                       "city": ((r.get("縣市名稱") or r.get(addr_k) or "")[:3]).replace("台", "臺"), "cat": _brand_cat(nm)})
                time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{kind}: {safe_err(e)}")
    if not months:
        raise RuntimeError("; ".join(errs) or "no data")
    keys = sorted(months)
    cur_k = keys[-1]; prv_k = keys[-2] if len(keys) > 1 else None
    cur, prv = months[cur_k], months.get(prv_k, [])
    def cnt(lst):
        c = {}
        for x in lst:
            c[x["cat"]] = c.get(x["cat"], 0) + 1
        return c
    cc, pc = cnt(cur), cnt(prv)
    cats = []
    for c, _ in BRAND_CATS + [("名稱看不出產業", "")]:
        n_, p_ = cc.get(c, 0), pc.get(c, 0)
        hist_put("brands", c, cur_k, n_)
        if prv_k:
            hist_put("brands", c, prv_k, p_)
        cats.append({"cat": c, "n": n_, "prev": p_, "chg": round((n_ - p_) / p_ * 100, 1) if p_ else None, "spark": hist_get("brands", c, 12)})
    peers = sorted([x for x in cur if x["cat"] == "設計創意"], key=lambda x: (-(x["cap"] or 0), x["date"]))[:30]
    big = sorted([x for x in cur if x["kind"] == "公司" and (x["cap"] or 0) >= 5e7], key=lambda x: -(x["cap"] or 0))[:12]
    # 得標排行：累積決標紀錄（滾動 180 天）＋ 決標金額快取
    log_ = {}
    if AW_LOG.exists():
        try:
            log_ = json.loads(AW_LOG.read_text(encoding="utf-8"))
        except Exception:
            log_ = {}
    for it in (RESULTS.get("awards") or {}).get("items", []):
        if it.get("key") and it.get("winner"):
            log_[it["key"]] = {"d": it.get("date"), "w": it.get("winner"), "a": it.get("amount"), "t": it.get("title")}
    cut = (TODAY_TPE - timedelta(days=180)).strftime("%Y%m%d")
    log_ = {k: v for k, v in log_.items() if (v.get("d") or "99999999") >= cut}
    write_json(AW_LOG, log_, separators=(",", ":"))
    try:
        cache = json.loads(AWARD_CACHE.read_text(encoding="utf-8")) if AWARD_CACHE.exists() else {}
    except Exception:
        cache = {}
    board = {}
    for k in set(log_) | set(cache):
        v = log_.get(k) or {}
        c = cache.get(k) or {}
        w = v.get("w") or c.get("winner") or ""
        a = v.get("a") if v.get("a") is not None else c.get("amount")
        for nm in [x.strip() for x in re.split(r"[、,，]", w) if x.strip()]:
            b = board.setdefault(nm, {"name": nm, "n": 0, "amt": 0})
            b["n"] += 1
            b["amt"] += num(a) or 0
    top = sorted(board.values(), key=lambda b: (-b["n"], -b["amt"]))[:10]
    return {"month": cur_k, "prev_month": prv_k, "total": len(cur), "total_prev": len(prv),
            "companies": sum(1 for x in cur if x["kind"] == "公司"), "businesses": sum(1 for x in cur if x["kind"] == "商業"),
            "cats": cats, "peers": peers, "big": big, "board": top, "board_n": len(set(log_) | set(cache)), "errs": errs}


# ---------- 集資雷達：嘖嘖等平台擋爬，改看新聞（爆案）與操盤代理商動態 ----------
CROWD_Q = ['嘖嘖 集資', '嘖嘖 募資', '集資 破百萬 OR 破千萬', '募資 天破百萬 OR 小時破百萬', '群眾募資 突破 OR 達標', '集資 達標',
           'Kickstarter 台灣 募資', 'Kickstarter 台灣團隊 OR 台灣品牌', 'flyingV 募資', '貝殼放大', '挖貝 集資', '群眾集資 趨勢 OR 報告 OR 年報']
CROWD_MUST = re.compile(r"集資|群募|群眾募資|嘖嘖|flyingV|貝殼放大|Kickstarter|挖貝|募資平台|募資計畫|募資專案"
                        r"|募資.{0,8}(破|達標|首日|突破)", re.I)
CROWD_NOISE = re.compile(r"港股|IPO|新股|招股|上市|ETF|彩券|樂透|創投|估值|融資|人民幣|基金|詐|股價|億美元|香港|拉皮|都更|勸募|侵占|不起訴", re.I)
CROWD_SRC_BLOCK = re.compile(r"香港|HKET|on\.cc|東網|文匯|信報|TVB|Now |電台|大公|新華|人民網|中新|環球|央視|觀察者|新浪|搜狐|網易|鳳凰", re.I)
CROWD_PRO = re.compile(r"貝殼放大|挖貝|年報|報告|數據|趨勢|產業|併購|海外|攻略|心法|操盤|排行|總額|累積")


def _crowd_amt(t: str):
    m = re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:億|千萬|百萬|萬)(?:美元|日圓|港元)?", t)
    return m.group(0).replace(" ", "") if m else None


KS_PWL_FEED = "https://www.kickstarter.com/projects/feed.atom"  # 官方 Atom：Projects We Love 新案
KICKTRAQ_HOT = "https://www.kicktraq.com/hot/"  # robots 允許、Crawl-Delay 6；每 3 小時只讀這一頁


def _ks_hot():
    t = get(KICKTRAQ_HOT, headers={"Referer": "https://www.kicktraq.com/"}).text
    out = []
    for blk in re.findall(r'<div class="listentry-mini(?: dark)?"><div class="listentry-mini rank">(.*?)<div class="clear">', t, re.S):
        rank = re.match(r"(\d+)", blk)
        a = re.search(r'<a href="/projects/([^"]+?)/?" title="([^"]+)"', blk)
        if not rank or not a:
            continue
        mv = re.search(r"\(([+-]\d+)\)", blk)
        cat = re.search(r'class="listentry-mini cat">(.*?)</div>', blk)
        out.append({"rank": int(rank.group(1)), "title": html_mod.unescape(a.group(2))[:70],
                    "url": "https://www.kickstarter.com/projects/" + a.group(1).strip("/"),
                    "move": int(mv.group(1)) if mv else None, "new": "title=\"new\"" in blk and not mv,
                    "cat": html_mod.unescape(cat.group(1)).replace(" > ", "／") if cat else ""})
    return out[:10]


def _ks_pwl():
    root = ET.fromstring(get(KS_PWL_FEED).content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", "", ns) or "").strip()
        title = re.split(r" by ", title)[0][:70]
        link = e.find("a:link", ns)
        body = html_mod.unescape(e.findtext("a:content", "", ns) or "")
        blurb = re.sub(r"<[^>]+>", " ", body.split("<br />")[-1] if "<br />" in body else body)
        out.append({"title": title, "url": link.get("href") if link is not None else "", "blurb": re.sub(r"\s+", " ", blurb).strip()[:110],
                    "at": _rss_date(e.findtext("a:published", "", ns) or "")})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:8]


def p_crowd():
    """集資雷達：嘖嘖等平台擋程式讀取，改看近 60 天報導。專案爆案 vs 平台／操盤方動態依標題分流。"""
    cut = (NOW - timedelta(days=60)).isoformat().replace("+00:00", "Z")
    seen, hot, pro, errs = set(), [], [], []
    for q in CROWD_Q:
        try:
            got = _gnews(q + " when:60d", limit=15)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{q[:12]}: {safe_err(e)}"); continue
        for it in got:
            t = it["title"]
            if not CROWD_MUST.search(t) or CROWD_NOISE.search(t) or CROWD_SRC_BLOCK.search(it.get("source", "")):
                continue
            if it.get("at") and it["at"] < cut:
                continue
            k = re.sub(r"\W", "", t)[:20]
            if k in seen:
                continue
            seen.add(k)
            it["amt"] = _crowd_amt(t)
            project = it["amt"] and re.search(r"破|達標|突破|紀錄|首日|小時|天", t)
            (hot if project or not CROWD_PRO.search(t) else pro).append(it)
        time.sleep(0.4)
    hot.sort(key=lambda x: x.get("at") or "", reverse=True)
    pro.sort(key=lambda x: x.get("at") or "", reverse=True)
    ks_hot, ks_pwl = [], []
    for name, fn in (("Kicktraq", _ks_hot), ("Kickstarter feed", _ks_pwl)):
        try:
            got = fn()
            if name == "Kicktraq":
                ks_hot = got
            else:
                ks_pwl = got
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {safe_err(e)}")
    if not hot and not pro and not ks_hot and not ks_pwl:
        raise RuntimeError("crowd: nothing " + "; ".join(errs)[:160])
    cats = {}
    for x in ks_hot:
        c = x["cat"].split("／")[0] if x["cat"] else "其他"
        cats[c] = cats.get(c, 0) + 1
    return {"hot": hot[:14], "pro": pro[:10], "ks_hot": ks_hot, "ks_cats": sorted(cats.items(), key=lambda kv: -kv[1]),
            "ks_pwl": ks_pwl, "errs": errs}


# ---------- 注意力流向：電影票房、App Store 台灣免費榜（YouTube／趨勢／維基沿用既有面板） ----------
BOX_CACHE = DATA / "box_cache.json"


def p_attention():
    errs, out = [], {}
    try:
        j = gjson("https://boxofficetw.tfai.org.tw/OpenData/statistic/since2016", timeout=90)
        end = (j.get("End") or "")[:10]
        cut = (datetime.fromisoformat(end) - timedelta(days=70)).date().isoformat() if end else ""
        films = [f for f in j.get("List") or [] if (f.get("ReleaseDate") or "")[:10] >= cut and (f.get("TotalAmounts") or 0) > 0]
        cache = json.loads(BOX_CACHE.read_text(encoding="utf-8")) if BOX_CACHE.exists() else {}
        cache[end] = {f["Name"]: f.get("TotalAmounts") or 0 for f in films}
        keep = sorted(cache)[-6:]
        cache = {k: cache[k] for k in keep}
        write_json(BOX_CACHE, cache, separators=(",", ":"))
        prev = cache.get(keep[-2]) if len(keep) > 1 else None
        rows = []
        for f in films:
            tot = f.get("TotalAmounts") or 0
            gain = (tot - prev[f["Name"]]) if prev and f["Name"] in prev else (tot if prev is not None else None)
            rows.append({"name": f["Name"], "country": f.get("Country"), "release": (f.get("ReleaseDate") or "")[:10], "total": tot,
                         "tickets": f.get("TotalTickets"), "theaters": f.get("TheaterCount"), "week": gain})
        rows.sort(key=lambda r: -(r["week"] if r["week"] is not None else r["total"]))
        out["box"] = {"asOf": end, "weekly": prev is not None, "items": rows[:10]}
    except Exception as e:  # noqa: BLE001
        errs.append(f"票房: {safe_err(e)}")
    try:
        try:
            j = gjson("https://rss.marketingtools.apple.com/api/v2/tw/apps/top-free/25/apps.json", timeout=45)
        except Exception:  # 這個端點偶爾逾時或 502，等一下再試一次
            time.sleep(3)
            j = gjson("https://rss.marketingtools.apple.com/api/v2/tw/apps/top-free/25/apps.json", timeout=45)
        prev = {a["id"]: a["rank"] for a in ((load_prev("attention") or {}).get("apps") or {}).get("items", [])}
        apps = []
        for i, a in enumerate(j["feed"]["results"], 1):
            apps.append({"id": a["id"], "rank": i, "name": a["name"], "dev": a.get("artistName"), "url": a.get("url"),
                         "prev": prev.get(a["id"]), "new": bool(prev) and a["id"] not in prev})
        out["apps"] = {"asOf": j["feed"].get("updated"), "items": apps}
    except Exception as e:  # noqa: BLE001
        errs.append(f"App Store: {safe_err(e)}")
        old = (load_prev("attention") or {}).get("apps")
        if old:
            out["apps"] = old
    if not out:
        raise RuntimeError("; ".join(errs))
    out["errs"] = errs
    return out


# ---------- 消費溫度計：電子發票各行業金額（月）、零售業態客單價 ----------
CONSUME_FOCUS = ["零售業", "餐飲業", "住宿業", "旅行及相關服務業", "運動、娛樂及休閒服務業", "創作及藝術表演業", "個人及家庭用品維修業",
                 "醫療保健業", "教育業", "電信業", "航空運輸業", "陸上運輸業", "不動產經營及相關服務業", "專門設計業", "廣告業及市場研究業", "資訊服務業"]


def _ym_shift(ym, k):
    y, m = int(ym[:4]), int(ym[4:])
    m += k
    while m <= 0:
        m += 12; y -= 1
    while m > 12:
        m -= 12; y += 1
    return f"{y}{m:02d}"


def p_consume():
    rows = _csv_rows("https://dataset.einvoice.nat.gov.tw/ods/portal/ODS303W/download/0DBDAF6E-5E44-49A8-8528-E22648B2F32E/17/4A1A0DA1-9C2B-4871-9B49-B742136B052D/0/?fileType=csv", timeout=180)
    agg = {}
    for r in rows:
        k = (r.get("行業別") or "").strip()
        ym = (r.get("發票年月") or "").strip()
        a = num(r.get("電子發票金額"))
        if not k or not ym or a is None:
            continue
        agg.setdefault(k, {}).setdefault(ym, 0.0)
        agg[k][ym] += a
    months = sorted({ym for v in agg.values() for ym in v})
    if not months:
        raise RuntimeError("電子發票資料空白")
    last = months[-1]
    def item(k):
        s = agg.get(k) or {}
        cur, yo, mo = s.get(last), s.get(_ym_shift(last, -12)), s.get(_ym_shift(last, -1))
        spark = [round(s.get(_ym_shift(last, -i), 0) / 1e8, 2) for i in range(12, -1, -1)]
        return {"name": k, "amt": cur, "yoy": round((cur / yo - 1) * 100, 1) if cur and yo else None,
                "mom": round((cur / mo - 1) * 100, 1) if cur and mo else None, "spark": spark}
    focus = [item(k) for k in CONSUME_FOCUS if k in agg]
    allind = sorted([item(k) for k in agg], key=lambda x: -(x["yoy"] if x["yoy"] is not None else -999))
    # 製造、批發、工程等 B2B 行業的發票受大單影響大，年增常是幾倍，不適合當消費訊號
    movers = [x for x in allind if x["yoy"] is not None and (x["amt"] or 0) > 1e9 and not re.search(r"製造|批發|工程|礦|金融|證券|保險|電力|燃氣|用水|廢棄物|污染|公共行政|機械|維修及安裝|企業總管理|倉儲|未分類", x["name"])]
    retail = []
    try:
        rr = _csv_rows("https://dataset.einvoice.nat.gov.tw/ods/portal/ODS303W/download/3886F055-EB77-4DF9-98E2-F3F49A7D3434/1/6E5DA78C-2586-4CBE-B73D-65B80F67AE2A/0/?fileType=csv", timeout=120)
        tk = {}
        for r in rr:
            k, ym = r.get("行業名稱"), r.get("發票年月")
            c, a = num(r.get("平均開立張數")), num(r.get("平均開立金額"))
            if k and ym and c and a:
                t = tk.setdefault(k, {}).setdefault(ym, [0.0, 0.0])
                t[0] += a; t[1] += c
        lm = max(ym for v in tk.values() for ym in v)
        for k, v in tk.items():
            cur = v.get(lm); yo = v.get(_ym_shift(lm, -12))
            ct = cur[0] / cur[1] if cur and cur[1] else None
            cy = yo[0] / yo[1] if yo and yo[1] else None
            retail.append({"name": k, "ticket": round(ct) if ct else None, "yoy": round((ct / cy - 1) * 100, 1) if ct and cy else None,
                           "spark": [round(v[_ym_shift(lm, -i)][0] / v[_ym_shift(lm, -i)][1]) if v.get(_ym_shift(lm, -i)) and v[_ym_shift(lm, -i)][1] else None for i in range(12, -1, -1)]})
        retail.sort(key=lambda x: -(x["ticket"] or 0))
        retail_m = lm
    except Exception as e:  # noqa: BLE001
        retail_m = None; log("consume retail", e)
    return {"month": f"{last[:4]}-{last[4:]}", "focus": focus, "up": movers[:6], "down": movers[-6:][::-1],
            "retail": retail, "retail_month": f"{retail_m[:4]}-{retail_m[4:]}" if retail_m else None}


run("pulse", p_pulse)
run("taiex", p_taiex)
run("tw_market", p_tw_market, keep_if_fresh_hours=0.5)
run("tw_stocks", p_tw_stocks)
run("fx", p_fx_any)
run("poly", p_poly, keep_if_fresh_hours=0.5)
run("tech", p_tech)
run("oss", p_oss, keep_if_fresh_hours=1)
run("trends", p_trends)
run("youtube", p_youtube, keep_if_fresh_hours=0.5)
run("attention", p_attention, keep_if_fresh_hours=3)
run("consume", p_consume, keep_if_fresh_hours=24)
run("luxury", p_luxury, keep_if_fresh_hours=3)
run("world", p_world, keep_if_fresh_hours=0.25)
run("usbig", p_usbig, keep_if_fresh_hours=0.25)
run("taifex", p_taifex, keep_if_fresh_hours=1)
run("sectors", p_sectors, keep_if_fresh_hours=0.5)
run("fear", p_fear, keep_if_fresh_hours=0.5)
run("commodities", p_commodities, keep_if_fresh_hours=3)
run("revenue", p_revenue, keep_if_fresh_hours=20)
run("etfholders", p_etfholders, keep_if_fresh_hours=12)
run("corp", p_corp, keep_if_fresh_hours=6)
run("policy", p_policy, keep_if_fresh_hours=6)
run("ipr", p_ipr, keep_if_fresh_hours=72)
run("media", p_media, keep_if_fresh_hours=2)
# run("reddit", p_reddit, keep_if_fresh_hours=1)  # 改用 PTT；有金鑰再開
run("lyst", p_lyst, keep_if_fresh_hours=24 * 6)
run("macro", p_macro, keep_if_fresh_hours=6)
run("gmacro", p_gmacro, keep_if_fresh_hours=6)
run("liquidity", p_liquidity, keep_if_fresh_hours=3)
run("calendar", p_calendar, keep_if_fresh_hours=6)
run("awards", p_awards, keep_if_fresh_hours=1)
run("brands", p_brands, keep_if_fresh_hours=12)
run("taxreg", p_taxreg, keep_if_fresh_hours=72)
run("crowd", p_crowd, keep_if_fresh_hours=3)
_sp = load_prev("supply") or {}
_sp_next = min([x.get("next") for x in (_sp.get("pmi") or {}, _sp.get("nmi") or {}) if x.get("next")] or ["9999"])
run("supply", p_supply, keep_if_fresh_hours=1 if TODAY_TPE.isoformat() >= _sp_next else 6)  # 發布日起每小時重抓，抓到新月份 next 會往後推
run("weather", p_weather)
run("radar_wx", p_radar_wx, keep_if_fresh_hours=0.15)
run("typhoon", p_typhoon, keep_if_fresh_hours=0.5)
run("ptt", p_ptt, keep_if_fresh_hours=0.5)
run("aiwire", p_aiwire, keep_if_fresh_hours=0.25)
run("devpulse", p_devpulse, keep_if_fresh_hours=1)
run("news", p_news, keep_if_fresh_hours=0.25)
run("social", p_social, keep_if_fresh_hours=0.5)
run("radar", p_radar, keep_if_fresh_hours=2)
run("cofacts", p_cofacts, keep_if_fresh_hours=0.5)
# run("threads_g", p_threads_g, keep_if_fresh_hours=3)  # Custom Search JSON API 不收新客戶、Gemini grounding 免費層無額度（429）；Threads 暫無免費路徑
run("mood", p_mood, keep_if_fresh_hours=1)
run("tenders", p_tenders, keep_if_fresh_hours=0.5)
run("design", p_design, keep_if_fresh_hours=1)
run("quake", p_quake)
run("flights", p_flights)
run("lightning", p_lightning, keep_if_fresh_hours=0.15)
run("house", p_house, keep_if_fresh_hours=24 * 5)
run("jobs", p_jobs, keep_if_fresh_hours=6)
run("mops", p_mops, keep_if_fresh_hours=0.5)
run("power", p_power, keep_if_fresh_hours=0.25)
run("airport", p_airport, keep_if_fresh_hours=0.25)
run("alerts", p_alerts, keep_if_fresh_hours=0.15)
run("oil", p_oil, keep_if_fresh_hours=12)
run("localnews", p_localnews, keep_if_fresh_hours=1)
run("elect", p_elect, keep_if_fresh_hours=0.5)  # 要在新聞、地方新聞、PTT 之後
run("culture", p_culture, keep_if_fresh_hours=6)
run("veg", p_veg, keep_if_fresh_hours=6)
run("fish", p_fish, keep_if_fresh_hours=6)
run("fruit", p_fruit, keep_if_fresh_hours=6)
run("meat", p_meat, keep_if_fresh_hours=6)
run("cards", p_cards, keep_if_fresh_hours=24)
run("lead", p_lead, keep_if_fresh_hours=24)
run("wiki", p_wiki, keep_if_fresh_hours=72)
run("metro", p_metro, keep_if_fresh_hours=72)
run("secwords", p_secwords, keep_if_fresh_hours=24)
# run("tiktok", p_tiktok, keep_if_fresh_hours=20)  # Creative Center 擋資料中心 IP，每輪白耗 60 秒，先停

DATA.mkdir(exist_ok=True)
run("think", p_think, keep_if_fresh_hours=2)
run("voice", p_voice, keep_if_fresh_hours=6)
run("pop", p_pop, keep_if_fresh_hours=3)
run("roads", p_roads)
run("mapfeed", p_mapfeed)  # 吃本輪其他面板的結果，不打外部 API
run("geo", p_geo, keep_if_fresh_hours=0.15)  # 最重，放最後；超過軟性期限就沿用上一輪
run("tw_pulse", p_tw_pulse)  # 吃地圖那輪的快取，幾乎不多打 API
FINISHED_ISO = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
try:
    write_json(HIST_PATH, HISTORY, separators=(",", ":"))
    write_json(DATA / "all.json", {"generatedAt": NOW_ISO, "finishedAt": FINISHED_ISO, "panels": RESULTS}, separators=(",", ":"))
except ValueError as e:
    log("NaN in output, not writing:", e)
    sys.exit(1)
# 每日存檔：把當天出現過的頭條、熱詞、榜單累積起來，之後可以回查「那天發生什麼」
def archive_day():
    day = datetime.now(TPE).strftime("%Y-%m-%d")
    p = DATA / "archive" / f"{day}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        cur = {}
    def merge(key, items, idf, cap=300):
        seen = {idf(x) for x in cur.get(key, [])}
        lst = cur.get(key, [])
        for x in items or []:
            k = idf(x)
            if k and k not in seen:
                seen.add(k); lst.append(x)
        cur[key] = lst[-cap:]
    R = RESULTS
    pick = lambda it, *ks: {k: it.get(k) for k in ks if it.get(k) is not None}
    news = (R.get("news") or {})
    merge("news", [pick(x, "source", "title", "url", "at") for x in (news.get("tw") or []) + (news.get("intl") or [])], lambda x: x.get("title"))
    merge("ai", [pick(x, "source", "title", "url", "at", "vendor") for x in (R.get("aiwire") or {}).get("items", [])], lambda x: x.get("title"))
    merge("hot", [{"term": h.get("term"), "src": h.get("src"), "at": NOW_ISO} for h in ((news.get("signals") or {}).get("hot") or [])], lambda x: x.get("term"), 200)
    merge("ptt", [pick(x, "board", "title", "push", "url") for x in (R.get("ptt") or {}).get("items", [])], lambda x: x.get("title"))
    merge("trends", [pick(x, "title", "traffic") for x in (R.get("trends") or {}).get("items", [])], lambda x: x.get("title"), 200)
    merge("cofacts", [pick(x, "text", "verdict", "requests", "url") for x in (R.get("cofacts") or {}).get("hot", [])], lambda x: (x.get("text") or "")[:60], 100)
    merge("oss", [pick(x, "name", "desc", "zh", "stars", "today", "url") for x in (R.get("oss") or {}).get("trending", [])], lambda x: x.get("name"), 300)
    merge("radar", [pick(x, "company", "amount", "stage", "cat", "title", "url") for x in (R.get("radar") or {}).get("funding", [])], lambda x: x.get("company"), 100)
    merge("brands", [pick(x, "name", "date", "city", "cap", "cat") for x in (R.get("brands") or {}).get("peers", []) + (R.get("brands") or {}).get("big", [])], lambda x: x.get("name"), 400)
    md = R.get("mood") or {}
    cur["mood"] = {k: (md.get(k) or {}).get("score") for k in ("taiwan", "overseas")}
    tx = (R.get("taiex") or {})
    cur["close"] = {"taiex": tx.get("index"), "vix": next((f.get("value") for f in (R.get("fear") or {}).get("items", []) if f.get("sym") == "^VIX"), None)}
    cur["updatedAt"] = NOW_ISO
    write_json(p, cur, separators=(",", ":"))

try:
    archive_day()
except Exception as e:  # noqa: BLE001
    log("archive failed:", safe_err(e))

# ---------- 歷史資料庫：每輪把「這輪有更新、內容有變」的面板完整存到 Google Cloud ----------
# 存法：gs://<bucket>/raw/dt=YYYY-MM-DD/HHMMSS.ndjson.gz，每行 {ts, panel, doc}；BigQuery 外部表 intel.snapshots 直接查這些檔
# 新增的面板不用改這裡：只要進了 RESULTS 就會自動存。地圖、雷達圖、實價登錄明細也一起存。
_ITEM_TITLE = ("title", "t", "question", "headline", "jobName", "subject", "term", "text", "name")
_ITEM_URL = ("url", "u", "link", "href", "slug")
_ITEM_SRC = ("source", "s", "src", "co", "short", "unit", "venue", "place", "cat", "group", "board")


def _vault_items(pid, doc):
    """把面板裡「有標題的條目」攤平成一筆一筆（新聞、職缺、重訊、藝文、Polymarket…），給全文搜尋用。"""
    out = []

    def walk(o, path, depth):
        if depth > 6 or len(out) > 3000:
            return
        if isinstance(o, dict):
            tk = next((k for k in _ITEM_TITLE if isinstance(o.get(k), str) and len(o[k].strip()) >= 2 and not re.match(r"^\d{4}-\d\d-\d\d|^[\d\s:./-]+$", o[k].strip())), None)
            if tk:
                url = next((str(o[k]) for k in _ITEM_URL if isinstance(o.get(k), str) and o[k]), "")
                src = next((str(o[k]) for k in _ITEM_SRC if isinstance(o.get(k), (str, int, float)) and str(o[k]) and k != tk), "")
                extra = {k: v for k, v in o.items() if k not in (tk,) and isinstance(v, (str, int, float, bool)) and len(str(v)) < 300}
                out.append({"panel": pid, "path": path[:60], "title": o[tk].strip()[:300], "url": url[:500], "source": src[:60],
                            "extra": json.dumps(extra, ensure_ascii=False)[:1500]})
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v, f"{path}.{k}" if path else k, depth + 1)
        elif isinstance(o, list):
            for v in o[:500]:
                if isinstance(v, (dict, list)):
                    walk(v, path, depth + 1)
    walk(doc, "", 0)
    return out


def vault_push():
    bucket, project = os.environ.get("GCP_BUCKET"), os.environ.get("GCP_PROJECT")
    if not bucket or not project or not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return "skip: no gcp"
    import base64
    import gzip
    import hashlib
    st_p = DATA / "vault_state.json"
    try:
        state = json.loads(st_p.read_text(encoding="utf-8")) if st_p.exists() else {}
    except Exception:  # noqa: BLE001
        state = {}
    hashes = state.setdefault("h", {})
    lines, pending = [], {}

    kf = state.setdefault("kf", {})  # 每個面板上次整份寫入的時間（epoch）

    def add(name, doc_text, force=False):
        h = hashlib.sha1(doc_text.encode("utf-8")).hexdigest()
        if hashes.get(name) == h and not force:
            return
        pending[name] = h  # 上傳成功才記下，失敗下一輪會重存
        lines.append(json.dumps({"ts": NOW_ISO, "panel": name, "doc": doc_text}, ensure_ascii=False))

    items = []
    seen_p = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "vault_items_seen.txt"  # 同一條迴圈內去重（跨迴圈重複無妨，查詢時會合併）
    try:
        seen = set(seen_p.read_text(encoding="utf-8").split()) if seen_p.exists() else set()
    except Exception:  # noqa: BLE001
        seen = set()
    new_seen = []
    for pid, doc in RESULTS.items():
        if doc.get("updatedAt") != NOW_ISO:  # 這輪沒重抓（沿用舊值或失敗）就不存
            continue
        body = {k: v for k, v in doc.items() if k != "updatedAt"}
        add(pid, json.dumps(body, ensure_ascii=False, sort_keys=True))
        try:
            for it in _vault_items(pid, body):
                k = hashlib.sha1(f"{pid}|{it['title']}|{it['url']}".encode("utf-8")).hexdigest()[:16]
                if k in seen:
                    continue
                seen.add(k); new_seen.append(k)
                items.append(json.dumps({"ts": NOW_ISO, **it}, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            log("vault items", pid, safe_err(e))
    extras = []
    if (RESULTS.get("geo") or {}).get("updatedAt") == NOW_ISO and (DATA / "geo.json").exists():
        extras.append(("geo_map", (DATA / "geo.json").read_text(encoding="utf-8")))
    if (RESULTS.get("radar_wx") or {}).get("updatedAt") == NOW_ISO and (DATA / "radar.png").exists():
        extras.append(("radar_png", json.dumps({"png_base64": base64.b64encode((DATA / "radar.png").read_bytes()).decode()})))
    if (RESULTS.get("house") or {}).get("updatedAt") == NOW_ISO and (DATA / "house").exists():
        for f in sorted((DATA / "house").glob("*.json")):
            extras.append((f"house_detail:{f.stem}", f.read_text(encoding="utf-8")))
    for name, text in extras:
        add(name, text)
    # 每日關鍵影格：沒變的面板也至少每 20 小時整份存一次，時光機只要掃前一天的檔就找得到每個面板
    for pid, doc in RESULTS.items():
        if pid in pending or time.time() - float(kf.get(pid) or 0) < 20 * 3600:
            continue
        body = {k: v for k, v in doc.items() if k != "updatedAt"}
        add(pid, json.dumps(body, ensure_ascii=False, sort_keys=True), force=True)
    if not lines:
        return "nothing changed"
    from google.cloud import storage
    tpe = NOW.astimezone(TPE)
    obj = f"raw/dt={tpe.strftime('%Y-%m-%d')}/{tpe.strftime('%H%M%S')}.ndjson.gz"
    data = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), 9)
    storage.Client(project=project).bucket(bucket).blob(obj).upload_from_string(data, content_type="application/gzip")
    hashes.update(pending)
    for name in pending:
        kf[name] = time.time()
    if items:
        try:
            iobj = obj.replace("raw/", "items/", 1)
            storage.Client(project=project).bucket(bucket).blob(iobj).upload_from_string(gzip.compress(("\n".join(items) + "\n").encode("utf-8"), 9), content_type="application/gzip")
            with open(seen_p, "a", encoding="utf-8") as f:
                f.write("\n".join(new_seen) + "\n")
        except Exception as e:  # noqa: BLE001
            log("vault items upload", safe_err(e))
    if not state.get("bq_items"):
        try:
            from google.cloud import bigquery
            bq = bigquery.Client(project=project)
            tid = f"{project}.intel.items"
            try:
                bq.get_table(tid)
            except Exception:  # noqa: BLE001
                ext = bigquery.ExternalConfig("NEWLINE_DELIMITED_JSON")
                ext.source_uris = [f"gs://{bucket}/items/*"]
                ext.compression = "GZIP"
                hp = bigquery.HivePartitioningOptions()
                hp.mode = "AUTO"
                hp.source_uri_prefix = f"gs://{bucket}/items/"
                ext.hive_partitioning = hp
                t = bigquery.Table(tid, schema=[bigquery.SchemaField(n, "TIMESTAMP" if n == "ts" else "STRING")
                                                for n in ("ts", "panel", "path", "title", "url", "source", "extra")])
                t.external_data_configuration = ext
                bq.create_table(t)
            state["bq_items"] = 1
        except Exception as e:  # noqa: BLE001
            log("vault bq items", safe_err(e))
    if not state.get("bq_relay"):  # 彰化機房的明細（每站、每路段）另外一張表，避免主表越掃越大
        try:
            from google.cloud import bigquery
            bq = bigquery.Client(project=project)
            tid = f"{project}.intel.tw_detail"
            try:
                bq.get_table(tid)
            except Exception:  # noqa: BLE001
                ext = bigquery.ExternalConfig("NEWLINE_DELIMITED_JSON")
                ext.source_uris = [f"gs://{bucket}/relay/raw/*"]
                ext.compression = "GZIP"
                hp = bigquery.HivePartitioningOptions()
                hp.mode = "AUTO"
                hp.source_uri_prefix = f"gs://{bucket}/relay/raw/"
                ext.hive_partitioning = hp
                t = bigquery.Table(tid, schema=[bigquery.SchemaField("ts", "TIMESTAMP"), bigquery.SchemaField("src", "STRING"),
                                                bigquery.SchemaField("doc", "STRING")])
                t.external_data_configuration = ext
                bq.create_table(t)
            state["bq_relay"] = 1
        except Exception as e:  # noqa: BLE001
            log("vault bq relay", safe_err(e))
    if not state.get("bq_table"):
        try:
            from google.cloud import bigquery
            bq = bigquery.Client(project=project)
            tid = f"{project}.intel.snapshots"
            try:
                bq.get_table(tid)
            except Exception:  # noqa: BLE001
                ext = bigquery.ExternalConfig("NEWLINE_DELIMITED_JSON")
                ext.source_uris = [f"gs://{bucket}/raw/*"]
                ext.compression = "GZIP"
                hp = bigquery.HivePartitioningOptions()
                hp.mode = "AUTO"
                hp.source_uri_prefix = f"gs://{bucket}/raw/"
                ext.hive_partitioning = hp
                t = bigquery.Table(tid, schema=[bigquery.SchemaField("ts", "TIMESTAMP"), bigquery.SchemaField("panel", "STRING"),
                                                bigquery.SchemaField("doc", "STRING")])
                t.external_data_configuration = ext
                bq.create_table(t)
            state["bq_table"] = 1
        except Exception as e:  # noqa: BLE001
            log("vault bq", safe_err(e))
    state["last"] = {"at": NOW_ISO, "obj": obj, "n": len(lines), "bytes": len(data), "items": len(items)}
    write_json(st_p, state, separators=(",", ":"))
    return f"{obj} {len(lines)} rows {len(data)} bytes"


try:
    log("vault:", vault_push())
except Exception as e:  # noqa: BLE001
    log("vault failed:", safe_err(e))

ok = [k for k, v in RESULTS.items() if not v.get("error")]
bad = [k for k, v in RESULTS.items() if v.get("error")]
log(f"done ok={ok} failed={bad}")
