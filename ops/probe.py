"""臨時探測（第六輪）：台北市消費者物價基本分類「月」指數。跑完就刪。"""
import json, requests
H = {"User-Agent": "Mozilla/5.0 (intel-terminal probe)"}
out = {}
base = "https://tsis.dbas.gov.taipei/statis/webMain.aspx?sys=220&kind=21&type=0&outmode=12&compmode=00&outkind=3&deflst=2"
for name, q in [("m1", "&ymf=11401&ymt=11509&funid=A21000101&cycle=1"), ("m2", "&ymf=11401&funid=A21000101&cycle=1"), ("m3", "&ymf=11401&ymt=11509&funid=A21000102&cycle=1"),
                ("m4", "&ymf=11401&ymt=11509&funid=A21000100&cycle=1"), ("y", "&ymf=8700&funid=A21000101&cycle=4")]:
    try:
        r = requests.get(base + q, headers=H, timeout=60)
        t = r.content.decode("utf-8-sig", "replace")
        lines = t.splitlines()
        out[name] = {"code": r.status_code, "ct": r.headers.get("content-type"), "len": len(t), "n_lines": len(lines), "head": lines[:4], "tail": lines[-4:]}
    except Exception as e:
        out[name] = {"err": str(e)[:150]}
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print("ok")
