"""暫時探測：下載勞動部月報 2-12、4-4、6-1、7-1 的 xlsx 原檔。用完刪掉。"""
import sys, time
from pathlib import Path
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"})
for code in ("22120", "24040", "26010", "27010", "24080"):
    r = S.get(f"https://statdb.mol.gov.tw/html/mon/{code}.xlsx", timeout=60)
    (OUT / f"{code}.xlsx").write_bytes(r.content); time.sleep(1)
