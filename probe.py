import os, json
os.makedirs("out15", exist_ok=True)
src = open("fetch_full.py").read(); i = src.index('\nrun("')
os.environ["INTEL_DATA_DIR"] = os.path.abspath("tmpdata"); os.makedirs("tmpdata/panels", exist_ok=True)
g = {"__name__": "x", "__file__": os.path.abspath("fetch_full.py")}
exec(compile(src[:i], "fp", "exec"), g)
heads = []
for s, (k, u) in g["FASHION_TW"].items():
    try:
        for it in g["_fashion_feed"](k, u): heads.append((s, it["title"], it["at"]))
    except Exception as e: heads.append((s, "ERR " + repr(e), ""))
out = g["p_media"]()
json.dump({"heads": heads, "out": out}, open("out15/res.json", "w"), ensure_ascii=False, indent=1)
