"""实时热榜抓取：本机直连各平台官方公开接口。

对应 Node 版 src/sources/{weibo,zhihu,toutiao,baidu,douyin,bilibili,ithome,kr36,juejin}.js
每个源的字段与 limit 与原实现完全一致。
"""

import re
import time
from urllib.parse import quote

from .net import get_json, get_text
from .util import finalize, format_heat, parse_heat_text


# --------------------------------------------------------------------- 微博
def fetch_weibo():
    json = get_json(
        "https://weibo.com/ajax/side/hotSearch",
        {"headers": {"Referer": "https://weibo.com/"}},
    )
    realtime = (json or {}).get("data", {}).get("realtime")
    if not isinstance(realtime, list):
        raise ValueError("微博接口返回结构异常")

    # is_ad / topic_ad 是商业推广位，直接从热搜榜里剔除
    rows = [
        x for x in realtime
        if not x.get("is_ad") and not x.get("topic_ad") and (x.get("word") or x.get("note"))
    ]

    items = []
    for x in rows:
        word = x.get("word") or x.get("note")
        heat = x.get("num") if isinstance(x.get("num"), (int, float)) else None
        items.append(
            {
                "title": word,
                "url": "https://s.weibo.com/weibo?q=" + quote("#" + word + "#"),
                "heat": heat,
                "heatText": format_heat(heat),
                "heatLabel": "热度",
                "tag": x.get("label_name") or x.get("icon_desc") or "",
                "desc": x.get("note") if x.get("note") and x.get("note") != word else "",
            }
        )
    return finalize(items, 50)


# --------------------------------------------------------------------- 知乎
def fetch_zhihu():
    # 网页版 /api/v3 需要登录 cookies；移动端接口可匿名访问
    json = get_json(
        "https://api.zhihu.com/topstory/hot-lists/total?limit=50",
        {"headers": {"Accept": "application/json", "Referer": "https://www.zhihu.com/hot"}},
    )
    rows = (json or {}).get("data")
    if not isinstance(rows, list):
        raise ValueError("知乎接口返回结构异常")

    items = []
    for entry in rows:
        t = entry.get("target") or {}
        # 接口给的是 api.zhihu.com/questions/<id>（复数），网页端路径是 /question/<id>（单数）
        raw_url = str(t.get("url") or "")
        m = re.search(r"/questions?/(\d+)", raw_url)
        if m:
            url = f"https://www.zhihu.com/question/{m.group(1)}"
        elif t.get("id"):
            url = f"https://www.zhihu.com/question/{t['id']}"
        else:
            url = "https://www.zhihu.com/hot"

        heat = parse_heat_text(entry.get("detail_text"))
        answers = int(t.get("answer_count") or 0)
        detail_text = str(entry.get("detail_text") or "").replace("热度", "").strip()
        card_label = entry.get("card_label") or {}
        items.append(
            {
                "title": t.get("title"),
                "url": url,
                "heat": heat,
                "heatText": format_heat(heat) if heat else detail_text,
                "heatLabel": "热度",
                "tag": "沸" if card_label.get("type") == "boiling" else "",
                "desc": t.get("excerpt") or "",
                "extra": f"{answers} 个回答" if answers else "",
            }
        )
    return finalize(items, 50)


# ----------------------------------------------------------------- 今日头条
_TOUTIAO_LABEL = {
    "new": "新", "hot": "热", "boom": "爆", "fevertime": "沸",
    "top": "置顶", "novel": "小说", "n1": "热",
}


def fetch_toutiao():
    json = get_json(
        "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        {"headers": {"Referer": "https://www.toutiao.com/"}},
    )
    rows = (json or {}).get("data")
    if not isinstance(rows, list):
        raise ValueError("头条接口返回结构异常")

    items = []
    for it in rows:
        heat = int(it["HotValue"]) if it.get("HotValue") else None
        label_key = str(it.get("Label") or "").lower()
        cluster = it.get("ClusterIdStr")
        items.append(
            {
                "title": it.get("Title"),
                "url": f"https://www.toutiao.com/trending/{cluster}/" if cluster
                       else it.get("Url") or "https://www.toutiao.com/",
                "heat": heat,
                "heatText": format_heat(heat),
                "heatLabel": "热度",
                "tag": _TOUTIAO_LABEL.get(label_key) or it.get("LabelDesc") or "",
                "desc": it.get("LabelDesc") or "",
                "cover": it.get("Image") or "",
            }
        )
    return finalize(items, 50)


# ----------------------------------------------------------------- 百度热搜
# 百度 top.baidu.com 的公开 JSON 接口不返回热度值，
# 完整数据（hotScore/desc/img/hotTag）内嵌在榜单页面的 <!--s-data:...--> 注释里。
_BAIDU_PAGE = "https://top.baidu.com/board?tab=realtime"
_BAIDU_API = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
_BAIDU_TAG = {1: "新", 3: "热"}  # 已实测确认：1=新，3=热（0 表示无标签）


def _baidu_extract_embedded(html_text):
    m = re.search(r"<!--s-data:([\s\S]*?)-->", html_text)
    if not m:
        return None
    try:
        import json as _json

        data = _json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return None
    cards = (data or {}).get("data", {}).get("cards")
    if not isinstance(cards, list):
        return None
    for card in cards:
        rows = (card or {}).get("content")
        if isinstance(rows, list) and rows and rows[0].get("word"):
            return rows
    return None


def _baidu_extract_api(data):
    cards = (data or {}).get("data", {}).get("cards")
    if not isinstance(cards, list):
        return None
    for card in cards:
        content = (card or {}).get("content")
        if not isinstance(content, list):
            continue
        if content and content[0].get("word"):
            return content
        for wrap in content:
            inner = (wrap or {}).get("content")
            if isinstance(inner, list) and inner and inner[0].get("word"):
                return inner
    return None


def fetch_baidu():
    rows = None
    # 主通道：页面内嵌数据，带真实热度
    try:
        html_text = get_text(
            _BAIDU_PAGE,
            {"headers": {"Accept": "text/html,application/xhtml+xml", "Referer": "https://www.baidu.com/"}},
        )
        rows = _baidu_extract_embedded(html_text)
    except Exception:  # noqa: BLE001
        rows = None

    # 兜底通道：官方 JSON 接口（无热度值，但至少能出榜单）
    if not rows:
        data = get_json(_BAIDU_API, {"headers": {"Referer": _BAIDU_PAGE}})
        rows = _baidu_extract_api(data)
    if not rows:
        raise ValueError("百度热搜返回结构异常")

    items = []
    for it in rows:
        heat = int(it["hotScore"]) if it.get("hotScore") else None
        items.append(
            {
                "title": it.get("word"),
                "url": it.get("url") or it.get("rawUrl")
                       or "https://www.baidu.com/s?wd=" + quote(it.get("word") or ""),
                "heat": heat,
                "heatText": format_heat(heat),
                "heatLabel": "搜索指数",
                "tag": "置顶" if it.get("isTop") else _BAIDU_TAG.get(it.get("hotTag"), ""),
                "desc": it.get("desc") or "",
                "cover": it.get("img") or "",
            }
        )
    return finalize(items, 51)


# ----------------------------------------------------------------- 抖音热搜
def fetch_douyin():
    json = get_json(
        "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383"
        "&channel=channel_pc_web&detail_list=1&source=6",
        {"headers": {"Referer": "https://www.douyin.com/"}},
    )
    rows = (json or {}).get("data", {}).get("word_list")
    if not isinstance(rows, list):
        raise ValueError("抖音接口返回结构异常（可能触发了风控）")

    items = []
    for it in rows:
        heat = int(it["hot_value"]) if it.get("hot_value") else None
        word = it.get("word")
        sentence_id = it.get("sentence_id")
        cover_list = (it.get("word_cover") or {}).get("url_list") or []
        items.append(
            {
                "title": word,
                "url": f"https://www.douyin.com/hot/{sentence_id}" if sentence_id
                       else "https://www.douyin.com/search/" + quote(word or ""),
                "heat": heat,
                "heatText": format_heat(heat),
                "heatLabel": "热度",
                "tag": "置顶" if it.get("is_n1") else "",
                "cover": cover_list[0] if cover_list else "",
            }
        )
    return finalize(items, 50)


# ------------------------------------------------------------------- B站排行
def fetch_bilibili():
    json = get_json(
        "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
        {"headers": {"Referer": "https://www.bilibili.com/"}},
    )
    if (json or {}).get("code") != 0:
        raise ValueError(f"B站接口返回错误码 {(json or {}).get('code')}")
    rows = (json or {}).get("data", {}).get("list")
    if not isinstance(rows, list):
        raise ValueError("B站接口返回结构异常")

    items = []
    for it in rows:
        view = int(it["stat"]["view"]) if it.get("stat", {}).get("view") else None
        author = (it.get("owner") or {}).get("name") or ""
        tname = it.get("tname") or ""
        extra = f"{author} · {tname}".rstrip(" ·") if author else tname
        items.append(
            {
                "title": it.get("title"),
                "url": f"https://www.bilibili.com/video/{it['bvid']}" if it.get("bvid")
                       else it.get("short_link_v2") or "",
                "heat": view,
                "heatText": format_heat(view),
                "heatLabel": "播放",
                "tag": tname,
                "desc": it.get("desc") or "",
                "cover": it.get("pic") or "",
                "extra": extra,
            }
        )
    return finalize(items, 60)


# ------------------------------------------------------------------ IT之家
def _ithome_url(it):
    raw = it.get("url") or ""
    if re.match(r"^https?://", raw, re.I):
        return raw
    if raw:
        return "https://www.ithome.com" + (raw if raw.startswith("/") else "/" + raw)
    if it.get("newsid"):
        return f"https://www.ithome.com/0/0/{it['newsid']}.htm"
    return "https://www.ithome.com/"


def fetch_ithome():
    json = get_json(
        "https://api.ithome.com/json/newslist/news",
        {"headers": {"Referer": "https://www.ithome.com/"}},
    )
    top = (json or {}).get("toplist")
    news = (json or {}).get("newslist")
    top = top if isinstance(top, list) else []
    news = news if isinstance(news, list) else []
    if not top and not news:
        raise ValueError("IT之家接口返回结构异常")

    top_ids = {t.get("newsid") for t in top}
    rows = [{**it, "__top": True} for it in top]
    rows += [n for n in news if n.get("newsid") not in top_ids]

    items = []
    for it in rows:
        heat = int(it["hitcount"]) if it.get("hitcount") else None
        comments = int(it.get("commentcount") or 0)
        items.append(
            {
                "title": it.get("title"),
                "url": _ithome_url(it),
                "heat": heat,
                "heatText": format_heat(heat),
                "heatLabel": "阅读",
                "tag": "置顶" if it.get("__top") else "",
                "desc": it.get("description") or "",
                "cover": it.get("image") or "",
                "extra": f"{comments} 评论" if comments else "",
            }
        )
    return finalize(items, 40)


# ------------------------------------------------------------------ 36氪热榜
def fetch_kr36():
    body = '{"partner_id":"wap","param":{"siteId":1,"platformId":2},"timestamp":%d}' % int(time.time() * 1000)
    json = get_json(
        "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot",
        {"method": "POST", "headers": {"Referer": "https://36kr.com/"}, "body": body},
    )
    rows = (json or {}).get("data", {}).get("hotRankList")
    if not isinstance(rows, list):
        raise ValueError("36氪接口返回结构异常")

    items = []
    for it in rows:
        m = it.get("templateMaterial") or {}
        read = int(m["statRead"]) if m.get("statRead") else None
        items.append(
            {
                "title": m.get("widgetTitle"),
                "url": f"https://36kr.com/p/{it['itemId']}" if it.get("itemId")
                       else "https://36kr.com/hot-list/catalog",
                "heat": read,
                "heatText": format_heat(read),
                "heatLabel": "阅读",
                "tag": "",
                "cover": m.get("widgetImage") or "",
                "extra": m.get("statFormat") or "",
            }
        )
    return finalize(items, 50)


# ------------------------------------------------------------------ 掘金热榜
def fetch_juejin():
    json = get_json(
        "https://api.juejin.cn/content_api/v1/content/article_rank?category_id=1&type=hot&spider=0",
        {"headers": {"Referer": "https://juejin.cn/"}},
    )
    rows = (json or {}).get("data")
    if not isinstance(rows, list):
        raise ValueError("掘金接口返回结构异常")

    items = []
    for it in rows:
        c = it.get("content") or {}
        counter = it.get("content_counter") or {}
        view = int(counter["view"]) if counter.get("view") else None
        author = (it.get("author") or {}).get("name")
        items.append(
            {
                "title": c.get("title"),
                "url": f"https://juejin.cn/post/{c['content_id']}" if c.get("content_id")
                       else "https://juejin.cn/hot/articles/1",
                "heat": view,
                "heatText": format_heat(view),
                "heatLabel": "阅读",
                "tag": "",
                "desc": c.get("brief") or "",
                "extra": f"{author} · {counter.get('like') or 0} 赞" if author else "",
            }
        )
    return finalize(items, 50)
