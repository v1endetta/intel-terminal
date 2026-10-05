import os, json, re, requests
os.makedirs("out25", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
GN = "https://news.google.com/rss/search?hl=zh-TW&gl=TW&ceid=TW:zh-Hant&q="
U = {
 "dcard_api": "https://www.dcard.tw/service/api/v2/posts?popular=true&limit=5",
 "gn_dcard": GN + "site:dcard.tw",
 "gn_dcard_kw": GN + "site:dcard.tw+%E8%A3%9D%E6%BD%A2",
 "gn_threads": GN + "site:threads.net",
 "gn_mobile01": GN + "site:mobile01.com",
 "gn_pixnet": GN + "site:pixnet.net",
 "mobile01": "https://www.mobile01.com/",
 "apple_podcast_tw": "https://rss.applemarketingtools.com/api/v2/tw/podcasts/top/25/podcasts.json",
 "apple_music_tw": "https://rss.applemarketingtools.com/api/v2/tw/music/most-played/25/songs.json",
 "apple_books_tw": "https://rss.applemarketingtools.com/api/v2/tw/books/top-paid/25/books.json",
 "kkbox": "https://kma.kkbox.com/charts/api/v1/daily?category=297&lang=tc&limit=20&terr=tw&type=song",
 "tiktok_cc": "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list?page=1&limit=20&period=7&country_code=TW&sort_by=popular",
 "tiktok_cc_page": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
 "womany": "https://womany.net/feed",
 "womany2": "https://womany.net/rss",
 "gtrends_rss": "https://trends.google.com/trending/rss?geo=TW",
 "gtrends_explore": "https://trends.google.com/trends/api/explore?hl=zh-TW&tz=-480&req=%7B%22comparisonItem%22%3A%5B%7B%22keyword%22%3A%22%E5%A1%97%E6%96%99%22%2C%22geo%22%3A%22TW%22%2C%22time%22%3A%22today%203-m%22%7D%5D%2C%22category%22%3A0%2C%22property%22%3A%22%22%7D",
 "ptt_search": "https://www.ptt.cc/bbs/home-sale/search?q=%E5%A1%97%E6%96%99",
 "yt_rss_search": "https://www.youtube.com/feeds/videos.xml?search_query=%E8%A3%9D%E6%BD%A2",
 "bahamut": "https://forum.gamer.com.tw/",
 "line_today": "https://today.line.me/tw/v2/tab/top",
}
rep = {}
for k, u in U.items():
    try:
        r = S.get(u, timeout=25, cookies={"over18": "1"}); t = r.text
        rep[k] = {"status": r.status_code, "bytes": len(t), "items": len(re.findall(r"<item>", t)), "head": re.sub(r"\s+", " ", t[:200]),
                  "titles": [re.sub(r"\s+", " ", x)[:60] for x in re.findall(r"<title>(?:<!\[CDATA\[)?([^<\]]+)", t)[1:5]]}
    except Exception as e:
        rep[k] = {"err": repr(e)[:150]}
open("out25/report.json", "w").write(json.dumps(rep, ensure_ascii=False, indent=1))
