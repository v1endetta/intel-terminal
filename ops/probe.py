"""暫時探測：掃勞動部統計月報各表（xlsx）的標題，找加班工時、進入率、薪資、受僱人數。用完刪掉。"""
import json, sys, io, zipfile, time
from pathlib import Path
import xml.etree.ElementTree as ET
import requests
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 dalta-intel/1.0"})
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
rep = {}
for ch in range(1, 10):
    miss = 0
    for t in range(1, 25):
        code = f"2{ch}{t:02d}0"
        try:
            r = S.get(f"https://statdb.mol.gov.tw/html/mon/{code}.xlsx", timeout=30)
            if r.status_code != 200 or not r.content.startswith(b"PK"):
                miss += 1
                if miss >= 3: break
                continue
            miss = 0
            z = zipfile.ZipFile(io.BytesIO(r.content))
            ss = [''.join(x.text or '' for x in si.iter(M + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')]
            rep[code] = ss[0].strip()[:60] if ss else ""
            # 最後一個「月」列
            last = [s for s in ss if "月" in s and len(s) < 12][-1:] 
            rep[code] += f"  ｜{last[0].strip() if last else ''}"
        except Exception as e:
            rep[code] = "ERR " + str(e)[:60]
        print(code, rep[code], flush=True)
        time.sleep(0.5)
(OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
