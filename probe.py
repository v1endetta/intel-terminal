import requests,json,os,re,io,csv,collections
os.makedirs("out2",exist_ok=True)
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def save(n,t):open("out2/"+n,"w").write(t if isinstance(t,str) else json.dumps(t,ensure_ascii=False,indent=1))
log=[]
# box office
r=requests.get("https://boxofficetw.tfai.org.tw/OpenData/statistic/since2016",headers=H,timeout=60);j=r.json();L=j["List"]
log.append(f"box len={len(r.content)} n={len(L)} start={j['Start']} end={j['End']}")
L2=sorted(L,key=lambda x:-(x.get('Amounts') or 0))[:15];save("box_top.json",L2)
# einvoice by industry (24826)
r=requests.get("https://dataset.einvoice.nat.gov.tw/ods/portal/ODS303W/download/0DBDAF6E-5E44-49A8-8528-E22648B2F32E/17/4A1A0DA1-9C2B-4871-9B49-B742136B052D/0/?fileType=csv",headers=H,timeout=120)
t=r.content.decode("utf-8-sig","ignore");rows=list(csv.DictReader(io.StringIO(t)))
months=collections.Counter(x["發票年月"] for x in rows);inds=collections.Counter(x["行業別"] for x in rows)
log.append(f"einv bytes={len(r.content)} rows={len(rows)} months={sorted(months)[:3]}..{sorted(months)[-3:]} n_ind={len(inds)}")
save("einv_inds.txt","\n".join(sorted(inds)))
# 36858 avg ticket
r=requests.get("https://dataset.einvoice.nat.gov.tw/ods/portal/ODS303W/download/3886F055-EB77-4DF9-98E2-F3F49A7D3434/1/6E5DA78C-2586-4CBE-B73D-65B80F67AE2A/0/?fileType=csv",headers=H,timeout=120)
t=r.content.decode("utf-8-sig","ignore");rows=list(csv.DictReader(io.StringIO(t)));months=collections.Counter(x["發票年月"] for x in rows);inds=collections.Counter(x["行業名稱"] for x in rows)
log.append(f"b2c bytes={len(r.content)} rows={len(rows)} months={sorted(months)[:2]}..{sorted(months)[-2:]} n_ind={len(inds)}");save("b2c_inds.txt","\n".join(sorted(inds)))
# company setup 6047 latest
r=requests.get("https://data.gcis.nat.gov.tw/od/file?oid=CE7F370E-9CBF-4A5B-AFD9-5C11ED9BB574",headers=H,timeout=120)
t=r.content.decode("utf-8-sig","ignore");rows=list(csv.reader(io.StringIO(t)));log.append(f"co bytes={len(r.content)} rows={len(rows)}")
save("co_sample.txt","\n".join(",".join(x) for x in rows[:5]+rows[-3:]))
# business setup 6668
r=requests.get("https://data.gcis.nat.gov.tw/od/file?oid=98263981-3AEB-4574-8B85-8C29787A1A23",headers=H,timeout=120)
t=r.content.decode("utf-8-sig","ignore");rows=list(csv.reader(io.StringIO(t)));log.append(f"biz bytes={len(r.content)} rows={len(rows)}")
save("biz_sample.txt","\n".join(",".join(x) for x in rows[:5]))
# data.gov.tw metadata of 6047 for all months available
m=requests.get("https://data.gov.tw/api/v2/rest/dataset/6047",headers=H,timeout=30).json();save("meta6047.json",m)
# CPI full page
r=requests.get("https://www.stat.gov.tw/Point.aspx?sid=t.2&n=3581&sms=11480",headers=H,timeout=30);t=r.text
i=t.find("<table");save("cpi_table.txt",t[i:i+8000] if i>=0 else t[-15000:])
# apple top grossing / paid retry
for k in ["top-free/25/apps","top-paid/10/apps"]:
    try:
        r=requests.get(f"https://rss.marketingtools.apple.com/api/v2/tw/apps/{k}.json",headers=H,timeout=30);log.append(f"apple {k} {r.status_code}")
    except Exception as e:log.append(f"apple {k} {e}")
save("log.txt","\n".join(log))
