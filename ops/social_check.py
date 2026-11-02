"""社群每日彙總推送前的檢查：只准「話題＋次數」這種形狀，其他一律擋下（exit 1）。

用法：python3 ops/social_check.py data/social_tw.json
排程推送前必須通過；fetch.py 讀檔時也用同一套規則過濾。
目的：就算網頁內容想讓排程把別的東西寫進來，能出去的也只有少量短詞。
"""
import json
import re
import sys

MAX_BYTES = 12000
BAD = re.compile(r"@|https?:|www\.|[A-Za-z0-9+/=_-]{20,}|\d{7,}")
SRC_OK = re.compile(r"^(Dcard [一-鿿]{1,4}|IG 推薦)$")


def _name_ok(s, n):
    return isinstance(s, str) and 0 < len(s) <= n and not BAD.search(s) and "\n" not in s


def clean(d):
    """回傳只留合格欄位的版本與被擋掉的筆數。"""
    out, drop = {}, 0
    if not isinstance(d, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("date") or "")):
        return None, 1
    out["date"] = d["date"]
    out["topics"] = {}
    for k, v in (d.get("topics") or {}).items():
        if not _name_ok(k, 20) or not isinstance(v, dict) or not set(v) <= {"Threads", "Dcard"}:
            drop += 1; continue
        vals = {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float)) and 0 <= vv <= 100000}
        if len(vals) != len(v):
            drop += 1; continue
        out["topics"][k] = vals
    out["hot"] = []
    for h in (d.get("hot") or [])[:40]:
        if not isinstance(h, dict) or set(h) - {"name", "src", "n"} or not _name_ok(h.get("name"), 16) \
                or not SRC_OK.match(str(h.get("src") or "")) or not isinstance(h.get("n"), int) or not 0 < h["n"] < 1000:
            drop += 1; continue
        out["hot"].append({"name": h["name"], "src": h["src"], "n": h["n"]})
    r = d.get("runs") or {}
    out["runs"] = {k: r[k] for k in ("threads", "dcard", "boards", "ig") if isinstance(r.get(k), int) and 0 <= r[k] < 1000}
    if set(d) - {"date", "topics", "hot", "runs"}:
        drop += 1
    return out, drop


if __name__ == "__main__":
    raw = open(sys.argv[1], encoding="utf-8").read()
    if len(raw.encode("utf-8")) > MAX_BYTES:
        sys.exit(f"FAIL: 檔案太大（{len(raw.encode('utf-8'))} bytes）")
    try:
        data = json.loads(raw)
    except ValueError as e:
        sys.exit(f"FAIL: 不是 JSON（{e}）")
    cleaned, dropped = clean(data)
    if cleaned is None or dropped:
        sys.exit(f"FAIL: 有 {dropped} 個欄位不符合格式，不要推送")
    print(f"OK: 話題 {len(cleaned['topics'])}、熱門 {len(cleaned['hot'])}")
