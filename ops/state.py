"""主迴圈的狀態（data/ 整個資料夾）存在私有的 Google Cloud Storage，取代公開的 data 分支。
  python ops/state.py pull          下載 state/data.tgz 到 INTEL_DATA_DIR（再疊上週報）
  python ops/state.py push          把 INTEL_DATA_DIR 打包上傳（週報兩個檔除外，那是 weekly 流程的）
  python ops/state.py weekly-pull   週報有更新才下載疊上去（主迴圈每輪呼叫）
  python ops/state.py weekly-push   上傳週報兩個檔（weekly 流程用）
每天第一次 push 另存一份 state/daily/YYYY-MM-DD.tgz，保留 30 天，出事可以回復。
需要 GCP_BUCKET、GCP_PROJECT 與 Google 憑證（GitHub 身分換的暫時憑證）。"""
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(os.environ["INTEL_DATA_DIR"])
WEEKLY = ["panels/weekly.json", "weekly_archive.json"]
MARK = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "weekly_gen.txt"


def bucket():
    from google.cloud import storage
    return storage.Client(project=os.environ["GCP_PROJECT"]).bucket(os.environ["GCP_BUCKET"])


def _extract(raw, only=None):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        for m in tf.getmembers():
            rel = m.name[5:] if m.name.startswith("data/") else None
            if not rel or not (m.isfile() or m.isdir()) or ".." in Path(rel).parts or (only and rel not in only):
                continue
            dst = DATA / rel
            if m.isdir():
                dst.mkdir(parents=True, exist_ok=True)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(tf.extractfile(m).read())


def _pack(include):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tf:
        for p in sorted(DATA.rglob("*")):
            rel = p.relative_to(DATA).as_posix()
            if p.is_file() and include(rel):
                tf.add(p, arcname=f"data/{rel}")
    return buf.getvalue()


def pull():
    b = bucket()
    blob = b.blob("state/data.tgz")
    if not blob.exists():
        print("::error::GCS 上沒有 state/data.tgz")
        return 1
    DATA.mkdir(parents=True, exist_ok=True)
    _extract(blob.download_as_bytes(timeout=120))
    weekly_pull(force=True)
    print(f"state pulled: {sum(1 for p in DATA.rglob('*') if p.is_file())} files")
    return 0


def push():
    b = bucket()
    raw = _pack(lambda rel: rel not in WEEKLY)
    b.blob("state/data.tgz").upload_from_string(raw, content_type="application/gzip", timeout=120)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = b.blob(f"state/daily/{day}.tgz")
    if not daily.exists():
        daily.upload_from_string(raw, content_type="application/gzip", timeout=120)
        cut = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        for old in b.list_blobs(prefix="state/daily/"):
            if old.name.rsplit("/", 1)[-1][:10] < cut:
                old.delete()
    print(f"state pushed: {len(raw) // 1024} KB")
    return 0


def weekly_pull(force=False):
    blob = bucket().get_blob("state/weekly.tgz")
    if not blob:
        return 0
    if not force and MARK.exists() and MARK.read_text().strip() == str(blob.generation):
        return 0
    _extract(blob.download_as_bytes(timeout=60), only=set(WEEKLY))
    MARK.write_text(str(blob.generation))
    print("weekly pulled", blob.generation)
    return 0


def weekly_push():
    raw = _pack(lambda rel: rel in WEEKLY)
    bucket().blob("state/weekly.tgz").upload_from_string(raw, content_type="application/gzip", timeout=60)
    print("weekly pushed")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"pull": pull, "push": push, "weekly-pull": weekly_pull, "weekly-push": weekly_push}.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(fn())
    except Exception as e:  # noqa: BLE001
        print(f"::warning::state {cmd} failed: {type(e).__name__}: {str(e)[:300]}")
        sys.exit(1)
