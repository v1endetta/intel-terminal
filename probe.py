import os,re,sys,json,collections,traceback
src=open("fetch_full.py").read()
i=src.index('\nrun("',src.index('def p_consume'))
os.environ["INTEL_DATA_DIR"]=os.path.abspath("tmpdata")
g={"__name__":"__main__","__file__":os.path.abspath("fetch_full.py")}
exec(compile(src[:i],"fp","exec"),g)
os.makedirs("out4",exist_ok=True)
names=[]
for ds,nk in ((6047,"公司名稱"),(6668,"商業名稱")):
    for desc,u in g["_gov_dists"](ds)[-1:]:
        for r in g["_csv_rows"](u):
            nm=(r.get(nk) or "").strip()
            if nm: names.append(nm)
other=[n for n in names if g["_brand_cat"](n)=="其他"]
strip=lambda n:re.sub(r"(股份有限公司|有限公司|企業社|工作室|商行|商號|行|社|店)$","",n)
grams=collections.Counter()
for n in other:
    b=strip(n)
    for L in (2,3):
        for k in range(len(b)-L+1): grams[b[k:k+L]]+=1
tail=collections.Counter(re.sub(r"(股份有限公司|有限公司)$","",n)[-2:] for n in other)
open("out4/res.txt","w").write(f"total {len(names)} other {len(other)}\n"+"\n".join(f"{k} {v}" for k,v in grams.most_common(250))+"\n--tail--\n"+"\n".join(f"{k} {v}" for k,v in tail.most_common(120))+"\n--sample--\n"+"\n".join(other[:300]))
