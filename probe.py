import os
from playwright.sync_api import sync_playwright
os.makedirs("out5",exist_ok=True)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for page in ("PMI","NMI"):
        pg=b.new_page(user_agent=UA,locale="zh-TW")
        try:
            pg.goto(f"https://index.ndc.gov.tw/n/zh_tw/{page}",wait_until="networkidle",timeout=60000)
            pg.wait_for_timeout(2500)
            open(f"out5/{page}.txt","w").write(pg.inner_text("body"))
        except Exception as e:
            open(f"out5/{page}.txt","w").write("ERR "+repr(e))
    b.close()
