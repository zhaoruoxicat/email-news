"""RSS 资讯源配置，对应 Node 版 src/sources/feeds.js。

全部为各站点官方 RSS，本机网络直连，不经任何第三方中转。
每一项都经过实测，能在真实网络下拉到条目。

group 取值：media 国内媒体 / global 国际媒体 / tech 科技媒体 / game 游戏
"""

FEEDS = [
    # ------------------------------------------------------------ 国内媒体
    {"id": "chinanews", "name": "中国新闻网", "group": "media", "color": "#c8102e", "initial": "中",
     "homepage": "https://www.chinanews.com.cn/",
     "feed": "https://www.chinanews.com.cn/rss/scroll-news.xml", "limit": 40},
    {"id": "xinhua", "name": "新华网", "group": "media", "color": "#b8161b", "initial": "新",
     "homepage": "http://www.news.cn/",
     "feed": "http://www.xinhuanet.com/politics/news_politics.xml", "limit": 40},
    {"id": "people", "name": "人民网", "group": "media", "color": "#c02a2a", "initial": "人",
     "homepage": "http://www.people.com.cn/",
     "feed": "http://www.people.com.cn/rss/politics.xml", "limit": 40},
    {"id": "jiemian", "name": "界面新闻", "group": "media", "color": "#1b6ff0", "initial": "界",
     "homepage": "https://www.jiemian.com/",
     "feed": "https://a.jiemian.com/index.php?m=article&a=rss", "limit": 40},

    # ------------------------------------------------------------ 国际媒体
    # 说明：BBC 中文、纽约时报中文网、FT 中文网、德国之声、卫报等站点在中国大陆网络下
    # 无法直连（实测 DNS/连接被阻断），因此这里收录的是本机可正常访问的境外中文/英文源。
    {"id": "yna", "name": "韩联社中文", "group": "global", "color": "#0d5eaf", "initial": "韩",
     "homepage": "https://cn.yna.co.kr/",
     "feed": "https://cn.yna.co.kr/RSS/news.xml", "limit": 40},
    {"id": "stheadline", "name": "星岛头条", "group": "global", "color": "#d3222a", "initial": "星",
     "homepage": "https://www.stheadline.com/",
     "feed": "https://www.stheadline.com/rss", "limit": 40},
    {"id": "sputnik", "name": "俄罗斯卫星通讯社", "group": "global", "color": "#6b7280", "initial": "俄",
     "homepage": "https://sputniknews.cn/",
     "feed": "https://sputniknews.cn/export/rss2/archive/index.xml", "limit": 30},
    {"id": "cnbc", "name": "CNBC", "group": "global", "color": "#0b4f9e", "initial": "C",
     "homepage": "https://www.cnbc.com/world/?region=world",
     "feed": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "limit": 30},

    # ------------------------------------------------------------ 科技媒体（国内）
    {"id": "sspai", "name": "少数派", "group": "tech", "color": "#da282a", "initial": "派",
     "homepage": "https://sspai.com/", "feed": "https://sspai.com/feed", "limit": 30},
    {"id": "ifanr", "name": "爱范儿", "group": "tech", "color": "#1677ff", "initial": "范",
     "homepage": "https://www.ifanr.com/", "feed": "https://www.ifanr.com/feed", "limit": 30},
    {"id": "tmtpost", "name": "钛媒体", "group": "tech", "color": "#1668dc", "initial": "钛",
     "homepage": "https://www.tmtpost.com/", "feed": "https://www.tmtpost.com/rss.xml", "limit": 30},
    {"id": "leiphone", "name": "雷峰网", "group": "tech", "color": "#2f6fed", "initial": "雷",
     "homepage": "https://www.leiphone.com/", "feed": "https://www.leiphone.com/feed", "limit": 30},
    {"id": "sinatech", "name": "新浪科技", "group": "tech", "color": "#d52b2b", "initial": "浪",
     "homepage": "https://tech.sina.com.cn/",
     "feed": "http://rss.sina.com.cn/tech/rollnews.xml", "limit": 30},
    {"id": "oschina", "name": "开源中国", "group": "tech", "color": "#178b50", "initial": "OS",
     "homepage": "https://www.oschina.net/news", "feed": "https://www.oschina.net/news/rss", "limit": 30},
    {"id": "infoq", "name": "InfoQ 中文", "group": "tech", "color": "#0e7fb5", "initial": "IQ",
     "homepage": "https://www.infoq.cn/", "feed": "https://www.infoq.cn/feed", "limit": 30},
    {"id": "cnblogs", "name": "博客园", "group": "tech", "color": "#1f6feb", "initial": "园",
     "homepage": "https://www.cnblogs.com/",
     "feed": "https://feed.cnblogs.com/blog/sitehome/rss", "limit": 30},

    # ------------------------------------------------------------ 科技媒体（国外）
    {"id": "techcrunch", "name": "TechCrunch", "group": "tech", "color": "#0a9e01", "initial": "TC",
     "homepage": "https://techcrunch.com/", "feed": "https://techcrunch.com/feed/", "limit": 30},
    {"id": "theverge", "name": "The Verge", "group": "tech", "color": "#7a3ff2", "initial": "V",
     "homepage": "https://www.theverge.com/",
     "feed": "https://www.theverge.com/rss/index.xml", "limit": 30},
    {"id": "arstechnica", "name": "Ars Technica", "group": "tech", "color": "#ff4e00", "initial": "Ars",
     "homepage": "https://arstechnica.com/",
     "feed": "https://feeds.arstechnica.com/arstechnica/index", "limit": 30},
    {"id": "wired", "name": "Wired", "group": "tech", "color": "#1a1a1a", "initial": "W",
     "homepage": "https://www.wired.com/", "feed": "https://www.wired.com/feed/rss", "limit": 30},

    # ------------------------------------------------------------ 游戏
    {"id": "yystv", "name": "游研社", "group": "game", "color": "#ef4b3f", "initial": "游",
     "homepage": "https://www.yystv.cn/", "feed": "https://www.yystv.cn/rss/feed", "limit": 30},
    {"id": "gcores", "name": "机核", "group": "game", "color": "#e8730c", "initial": "核",
     "homepage": "https://www.gcores.com/", "feed": "https://www.gcores.com/rss", "limit": 30},
    {"id": "chuapp", "name": "触乐", "group": "game", "color": "#16a085", "initial": "触",
     "homepage": "https://www.chuapp.com/", "feed": "https://www.chuapp.com/feed", "limit": 30},
    {"id": "gamelook", "name": "GameLook", "group": "game", "color": "#4a5bd0", "initial": "GL",
     "homepage": "http://www.gamelook.com.cn/",
     "feed": "http://www.gamelook.com.cn/feed", "limit": 30},
    {"id": "igncn", "name": "IGN 中国", "group": "game", "color": "#d21f2b", "initial": "IGN",
     "homepage": "https://www.ign.com.cn/", "feed": "https://www.ign.com.cn/rss", "limit": 30},
    {"id": "yystvnews", "name": "游研社·资讯", "group": "game", "color": "#c2410c", "initial": "讯",
     "homepage": "https://www.yystv.cn/", "feed": "https://www.yystv.cn/rss/news", "limit": 30},
]

# 已排除的源（实测无法稳定访问，不再纳入）：
#   store.steampowered.com（Steam 商店，连接被间歇性阻断，实测 5/5 失败）
#   BBC 中文 / 纽约时报中文网 / FT 中文网 / 德国之声 / 卫报 / 半岛电视台 /
#   CNN / 南华早报 / 明报 / 香港01 —— 中国大陆网络下 DNS 或连接被阻断
#   小黑盒 —— 其接口有自研签名校验且网页版需登录，未纳入
