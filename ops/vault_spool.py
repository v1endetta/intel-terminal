# 歷史資料庫的暫存區：fetch.py 每輪把變動的面板先寫在 GitHub 機器的暫存資料夾，每 3 小時才合併上傳一次。
# 原因：GCS 寫入（Class A）每月免費 5,000 次；每輪上傳一次一個月會用掉六千多次。
# 迴圈結束時 fetch.yml 會再執行這支（python ops/vault_spool.py）把剩下的傳上去。
import gzip
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TPE = timezone(timedelta(hours=8))
FLUSH_EVERY = 3 * 3600


def spool_dir() -> Path:
    d = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "vault_spool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def append(lines, items):
    d = spool_dir()
    if not (d / "since").exists():
        (d / "since").write_text(str(time.time()))
    for name, rows in (("raw.ndjson", lines), ("items.ndjson", items)):
        if rows:
            with open(d / name, "a", encoding="utf-8") as f:
                f.write("\n".join(rows) + "\n")


def due() -> bool:
    p = spool_dir() / "since"
    try:
        return time.time() - float(p.read_text()) >= FLUSH_EVERY
    except Exception:  # noqa: BLE001
        return False


def flush(project: str, bucket: str) -> int:
    """把暫存上傳成 raw/dt=日期/時間.ndjson.gz、items/dt=日期/時間.ndjson.gz（依每列的台北日期分檔，BigQuery 才找得到）。回傳寫入次數。"""
    from google.cloud import storage
    d = spool_dir()
    stamp = datetime.now(TPE).strftime("%H%M%S")
    bkt = storage.Client(project=project).bucket(bucket)
    n = 0
    for name, prefix in (("raw.ndjson", "raw"), ("items.ndjson", "items")):
        p = d / name
        if not p.exists():
            continue
        by = {}
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                ts = json.loads(ln).get("ts") or ""
                day = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TPE).strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                day = datetime.now(TPE).strftime("%Y-%m-%d")
            by.setdefault(day, []).append(ln)
        for day, rows in sorted(by.items()):
            bkt.blob(f"{prefix}/dt={day}/{stamp}.ndjson.gz").upload_from_string(
                gzip.compress(("\n".join(rows) + "\n").encode("utf-8"), 9), content_type="application/gzip")
            n += 1
        p.unlink()
    (d / "since").unlink(missing_ok=True)
    return n


if __name__ == "__main__":
    pj, bk = os.environ.get("GCP_PROJECT"), os.environ.get("GCP_BUCKET")
    if not pj or not bk or not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("vault flush: skip (no gcp)")
        sys.exit(0)
    print("vault flush:", flush(pj, bk), "objects")
