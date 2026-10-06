import os, json, re, traceback
os.makedirs("out25", exist_ok=True)
src = open("fetch_test.py", encoding="utf-8").read()
cut = src.index("\nrun(")
g = {"__name__": "fetchmod", "__file__": os.path.abspath("fetch_test.py")}
rep = {}
try:
    exec(compile(src[:cut], "fetch_test.py", "exec"), g)
    g["DATA"].mkdir(exist_ok=True)
    rep["taxreg"] = g["p_taxreg"]()
    codes = json.loads(g["TAXREG_CODES"].read_text(encoding="utf-8"))
    cfg = json.load(open("ops/voice_keywords.json", encoding="utf-8"))
    rep["supply"] = {}
    for k in cfg["keywords"]:
        pat = k.get("supply")
        if not pat:
            continue
        sp = g["taxreg_supply"](pat, codes)
        hits = sorted([(c, v[0], v[1], v[2]) for c, v in codes["codes"].items() if re.search(pat, v[0])], key=lambda x: -x[2])
        rep["supply"][k["k"]] = {"sp": sp, "hits": hits[:25]}
    words = r"老|照顧|洗衣|租賃|中古|舊|二手|當|寢具|床|運動|球|玩具|模型|表演|演藝|藝文|展演|收納|搬家|回收|設計|攝影|家具|露營|減重|體重|營養|化粧|美容"
    rep["names"] = sorted([(c, v[0], v[1]) for c, v in codes["codes"].items() if re.search(words, v[0]) and v[1] + v[2] > 0])
except Exception:
    rep["err"] = traceback.format_exc()[-2000:]
json.dump(rep, open("out25/probe.json", "w"), ensure_ascii=False, indent=1, default=str)
