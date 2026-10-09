"""数据源注册表：对应 Node 版 src/sources/index.js。

对外暴露 SOURCES / GROUPS / fetch_one / fetch_many / get_meta / get_groups。
并发抓取用标准库 concurrent.futures.ThreadPoolExecutor 实现（GIL 在 I/O 等待时会释放）。
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from . import hot
from .feeds import FEEDS
from .rss import build_sources

# 分组定义：顺序即邮件里的展示顺序
GROUPS = [
    {"id": "hot", "name": "实时热榜", "desc": "微博、知乎、头条等平台实时榜单"},
    {"id": "media", "name": "国内媒体", "desc": "新闻门户要闻"},
    {"id": "global", "name": "国际媒体", "desc": "境外通讯社与媒体（本机可直连的源）"},
    {"id": "tech", "name": "科技媒体", "desc": "国内外科技与开发者资讯"},
    {"id": "game", "name": "游戏", "desc": "游戏媒体与 Steam"},
]


def _hot_source(sid, name, color, initial, homepage, limit, fetcher):
    return {
        "id": sid,
        "name": name,
        "group": "hot",
        "color": color,
        "initial": initial,
        "homepage": homepage,
        "limit": limit,
        "kind": "hot",
        "fetchItems": fetcher,
    }


# 实时热榜：本机直连各平台官方公开接口
HOT_SOURCES = [
    _hot_source("weibo", "微博热搜", "#e6162d", "微", "https://s.weibo.com/top/summary", 50, hot.fetch_weibo),
    _hot_source("zhihu", "知乎热榜", "#0084ff", "知", "https://www.zhihu.com/hot", 50, hot.fetch_zhihu),
    _hot_source("toutiao", "今日头条", "#ed4040", "头", "https://www.toutiao.com/", 50, hot.fetch_toutiao),
    _hot_source("baidu", "百度热搜", "#2932e1", "百", "https://top.baidu.com/board?tab=realtime", 51, hot.fetch_baidu),
    _hot_source("douyin", "抖音热搜", "#fe2c55", "抖", "https://www.douyin.com/hot", 50, hot.fetch_douyin),
    _hot_source("bilibili", "B站排行", "#fb7299", "B", "https://www.bilibili.com/v/popular/rank/all", 60, hot.fetch_bilibili),
    _hot_source("ithome", "IT之家", "#e60012", "IT", "https://www.ithome.com/", 40, hot.fetch_ithome),
    _hot_source("kr36", "36氪热榜", "#1e6fff", "36", "https://36kr.com/hot-list/catalog", 50, hot.fetch_kr36),
    _hot_source("juejin", "掘金热榜", "#1e80ff", "掘", "https://juejin.cn/hot/articles/1", 50, hot.fetch_juejin),
]

# 资讯源：各站点官方 RSS
FEED_SOURCES = build_sources(FEEDS)

SOURCES = HOT_SOURCES + FEED_SOURCES

BY_ID = {s["id"]: s for s in SOURCES}


def get_meta():
    """给渲染层的平台元信息（不含函数，可安全序列化）"""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "group": s["group"],
            "color": s["color"],
            "initial": s["initial"],
            "homepage": s["homepage"],
            "limit": s["limit"],
        }
        for s in SOURCES
    ]


def get_groups():
    used = {s["group"] for s in SOURCES}
    return [g for g in GROUPS if g["id"] in used]


def all_ids():
    """全部数据源 id，按注册顺序"""
    return [s["id"] for s in SOURCES]


def resolve_enabled(disabled=None):
    """由「禁用的源 id 集合」算出实际要抓取的 id 列表。

    永不返回空列表：若禁用后一个不剩，则退回全部启用，
    避免用户误把全部关掉后收到一封空邮件却不知为何。
    """
    disabled = set(disabled or [])
    enabled = [s["id"] for s in SOURCES if s["id"] not in disabled]
    return enabled if enabled else all_ids()


def unknown_ids(ids):
    """过滤出不在注册表里的 id，便于配置校验时提示"""
    return [i for i in (ids or []) if i not in BY_ID]


def sources_by_group():
    """按分组返回数据源，供配置界面展示"""
    out = []
    for group in GROUPS:
        members = [s for s in SOURCES if s["group"] == group["id"]]
        if members:
            out.append((group, members))
    return out


def fetch_one(sid, per_source=None, timeout=30):
    """抓取单个平台。永不抛异常，失败时把错误文本放进 error 字段，

    这样某个平台挂掉不会影响其它平台展示。
    """
    import time as _time

    src = BY_ID.get(sid)
    if not src:
        return {"id": sid, "name": sid, "items": [], "error": f"未知平台：{sid}"}

    started = _time.time()
    try:
        items = src["fetchItems"]()
        if per_source:
            items = items[:per_source]
        return {
            "id": src["id"],
            "name": src["name"],
            "group": src["group"],
            "color": src["color"],
            "initial": src["initial"],
            "homepage": src["homepage"],
            "items": items,
            "error": None,
            "elapsed": int((_time.time() - started) * 1000),
        }
    except Exception as err:  # noqa: BLE001
        return {
            "id": src["id"],
            "name": src["name"],
            "group": src["group"],
            "color": src["color"],
            "initial": src["initial"],
            "homepage": src["homepage"],
            "items": [],
            "error": str(err) or err.__class__.__name__,
            "elapsed": int((_time.time() - started) * 1000),
        }


def fetch_many(ids=None, concurrency=8, per_source=None, timeout=30, on_done=None,
               disabled=None):
    """限制并发的批量抓取，返回结果顺序与 ids 一致。

    :param on_done: 可选回调 fn(result, index, total)，用于打印进度
    :param disabled: 要跳过的源 id 集合；仅在 ids 为 None 时生效
                     （显式传 ids 时以 ids 为准）
    """
    if ids:
        wanted = [i for i in ids if i in BY_ID]
    else:
        wanted = resolve_enabled(disabled)

    results = [None] * len(wanted)
    total = len(wanted)
    if not total:
        return results

    size = max(1, min(concurrency, total))
    with ThreadPoolExecutor(max_workers=size) as pool:
        futures = {
            pool.submit(fetch_one, sid, per_source, timeout): idx
            for idx, sid in enumerate(wanted)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as err:  # noqa: BLE001 —— fetch_one 已兜底，这里再保一层
                sid = wanted[idx]
                results[idx] = {"id": sid, "name": sid, "items": [], "error": str(err)}
            if on_done:
                on_done(results[idx], idx, total)

    return results


def ids():
    return [s["id"] for s in SOURCES]
