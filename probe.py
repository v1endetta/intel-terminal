import os,re,sys,json
src=open("fetch_full.py").read()
i=src.index('\nrun("',src.index('def p_consume'))
head=src[:i]
code=head+'''
DATA.mkdir(exist_ok=True)
PANELS.mkdir(exist_ok=True)
for pid,fn in (("brands",p_brands),("attention",p_attention),("consume",p_consume)):
    run(pid,fn)
    print(pid, "error" in (RESULTS.get(pid) or {}), (RESULTS.get(pid) or {}).get("error"), file=sys.stderr)
os.makedirs("out3",exist_ok=True)
for pid in ("brands","attention","consume"):
    open(f"out3/{pid}.json","w").write(json.dumps(RESULTS.get(pid),ensure_ascii=False,indent=1))
'''
os.environ["INTEL_DATA_DIR"]=os.path.abspath("tmpdata")
import traceback
os.makedirs("out3",exist_ok=True)
try:
    exec(compile(code,"fetch_part","exec"),{"__name__":"__main__","__file__":os.path.abspath("fetch_full.py")})
except BaseException:
    open("out3/trace.txt","w").write(traceback.format_exc())
