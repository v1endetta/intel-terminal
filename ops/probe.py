# 暫時實測：民調（最終版）＋ Mobile01 熱門，整包輸出給畫面測試用。金鑰一律不輸出
import json, os, re, tempfile, traceback
out = {}
try:
    tmp = tempfile.mkdtemp(); os.environ["INTEL_DATA_DIR"] = tmp
    src = open("fetch.py", encoding="utf-8").read(); cut = src.index('\nrun("pulse", p_pulse)\n')
    g = {"__name__": "probe", "__file__": os.path.abspath("fetch.py")}
    exec(compile(src[:cut], "fetch.py", "exec"), g)
    for k, fn in (("polls", "p_polls"), ("forums", "p_forums")):
        try:
            out[k] = g[fn]()
        except Exception:
            out[k] = {"err": re.sub(r"key=[^&\s]+", "key=***", traceback.format_exc()[-600:])}
except Exception:
    out["err"] = re.sub(r"key=[^&\s]+", "key=***", traceback.format_exc()[-800:])
json.dump(out, open("probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:800])
