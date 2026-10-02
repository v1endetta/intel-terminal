import requests,json,os,re,sys
os.makedirs("out",exist_ok=True)
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def save(name,txt):open(f"out/{name}","w").write(txt if isinstance(txt,str) else json.dumps(txt,ensure_ascii=False,indent=1))
def get(u,**k):
    try:
        r=requests.get(u,headers=H,timeout=40,**k);return r.status_code,r
    except Exception as e:return -1,str(e)
log=[]
for ds in [6047,6668,36843,36844,24826,24831,94224,13480,13488,6949,14198,36858,9590]:
    c,r=get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}")
    log.append(f"meta {ds} {c}")
    if c==200:
        j=r.json();save(f"meta_{ds}.json",j)
        try:
            dist=j["result"]["distribution"]
            for i,d in enumerate(dist[:3]):
                u=d.get("resourceDownloadUrl") or d.get("downloadURL");
                c2,r2=get(u)
                log.append(f"  dl {ds}.{i} {c2} {u} {d.get('resourceFormat')} {d.get('resourceDescription','')[:60]}")
                if c2==200:
                    b=r2.content[:6000]
                    for enc in ("utf-8-sig","big5","cp950"):
                        try:s=b.decode(enc);break
                        except:s=None
                    save(f"dl_{ds}_{i}.txt",s or repr(b[:2000]))
        except Exception as e:log.append(f"  err {e}")
for name,u in [("netflix","https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv"),
               ("apple","https://rss.marketingtools.apple.com/api/v2/tw/apps/top-free/25/apps.json"),
               ("apple_paid","https://rss.marketingtools.apple.com/api/v2/tw/apps/top-paid/10/apps.json"),
               ("boxoffice_home","https://boxofficetw.tfai.org.tw/"),
               ("boxoffice_api","https://boxofficetw.tfai.org.tw/statistic/Week/10/0/all/False/Region"),
               ("tipo","https://tiponet.tipo.gov.tw/Gazette/OpenData/OD/OD01_104_API.aspx"),
               ("gcis_6047","https://data.gcis.nat.gov.tw/od/detail?oid=AD28285B-7B0E-4241-9F58-F2F0F289333E"),
               ("stat_cpi","https://www.stat.gov.tw/Point.aspx?sid=t.2&n=3581&sms=11480"),
               ]:
    c,r=get(u,stream=(name=="netflix"))
    if c==200:
        if name=="netflix":
            b=b"".join([next(r.iter_content(200000))]);s=b.decode("utf-8","ignore");lines=s.splitlines();save(name+".txt","\n".join(lines[:3]+[l for l in lines if "\tTaiwan\t" in l][:30]))
        else:save(name+".txt",r.text[:40000])
    log.append(f"{name} {c} {u}")
save("log.txt","\n".join(log))
