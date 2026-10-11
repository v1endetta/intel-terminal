"""把網站要讀的檔推到 Cloudflare Workers KV（intel.daltatw.com 的 Worker 從這裡讀）。
免費額度一天 1,000 次寫入（UTC 00:00 重置），所以：內容沒變不寫、各檔有最短間隔、一天最多寫 900 次。
用法：INTEL_DATA_DIR=... CLOUDFLARE_API_TOKEN=... python ops/publish_kv.py
沒有權杖就直接略過；任何錯誤只印警告、不影響主迴圈。"""
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfapi import CFError, account_id, call, kv_namespace  # noqa: E402

DAY_CAP = 900
# (檔名, 最短間隔秒數)。all.json 每輪都推；其餘有變才推、而且不會太頻繁
FILES = [("all.json", 0), ("radar.png", 900), ("roads_live.json", 900), ("geo.json", 900),
         ("history.json", 1800), ("roads_geo.json", 3600)]
HOUSE_GAP = 3600


def main():
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        return "skip: no token"
    data = Path(os.environ["INTEL_DATA_DIR"])
    st_p = data / "kv_state.json"
    try:
        st = json.loads(st_p.read_text(encoding="utf-8")) if st_p.exists() else {}
    except Exception:  # noqa: BLE001
        st = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["n"] = today, 0
    st.setdefault("h", {})
    st.setdefault("t", {})
    if os.environ.get("CF_KV_ID"):
        acc, ns = account_id(), os.environ["CF_KV_ID"]
    else:
        acc = account_id()
        ns = kv_namespace(acc)
    now = time.time()
    cands = [(n, gap) for n, gap in FILES]
    cands += [(f"house/{p.name}", HOUSE_GAP) for p in sorted((data / "house").glob("*.json"))] if (data / "house").exists() else []
    batch, pend = [], {}
    for name, gap in cands:
        p = data / name
        if not p.exists():
            continue
        b = p.read_bytes()
        h = hashlib.sha1(b).hexdigest()
        if st["h"].get(name) == h or now - float(st["t"].get(name) or 0) < gap:
            continue
        if st["n"] + len(batch) >= DAY_CAP:
            print(f"::warning::KV 今日寫入已達 {DAY_CAP}，{name} 等明天")
            break
        batch.append({"key": name, "value": base64.b64encode(b).decode(), "base64": True})
        pend[name] = h
    if not batch:
        return f"nothing to publish (today {st['n']})"
    res = call("PUT", f"/accounts/{acc}/storage/kv/namespaces/{ns}/bulk", batch, timeout=120)
    if not res.get("success"):
        raise CFError(f"bulk failed: {str(res.get('errors'))[:200]}")
    unwritten = set((res.get("result") or {}).get("unsuccessful_keys") or [])
    for name, h in pend.items():
        if name in unwritten:
            continue
        st["h"][name], st["t"][name] = h, now
    st["n"] += len(pend) - len(unwritten)
    st_p.write_text(json.dumps(st, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return f"published {len(pend) - len(unwritten)} ({', '.join(k for k in pend if k not in unwritten)[:200]}); today {st['n']}/{DAY_CAP}"


if __name__ == "__main__":
    try:
        print("kv:", main())
    except Exception as e:  # noqa: BLE001
        print(f"::warning::KV publish failed: {str(e)[:300]}")
