"""通用 RSS / Atom / RDF 解析器，对应 Node 版 src/sources/rss.js。

不依赖任何第三方 XML 库。各站 RSS 的脏数据很多（CDATA 嵌套、HTML 摘要、
实体未转义、字段名五花八门），这里用宽松正则取值并统一清洗，
保证任何一个源出问题都不会拖垮其它源。
"""

import re
import time
from datetime import datetime

from .net import get_text
from .util import https_image, finalize

NAMED_ENTITIES = {
    "nbsp": " ", "ensp": " ", "emsp": " ", "thinsp": " ",
    "lt": "<", "gt": ">", "quot": '"', "apos": "'",
    "hellip": "…", "mdash": "—", "ndash": "–",
    "ldquo": "“", "rdquo": "”", "lsquo": "‘", "rsquo": "’",
    "middot": "·", "times": "×", "laquo": "«", "raquo": "»",
    "copy": "©", "reg": "®", "trade": "™", "deg": "°",
    "plusmn": "±", "ge": "≥", "le": "≤", "ne": "≠",
    "bull": "•", "permil": "‰", "prime": "′", "Prime": "″",
}

_CDATA_RE = re.compile(r"<!\[CDATA\[([\s\S]*?)\]\]>")
_NUM_HEX_RE = re.compile(r"&#x([0-9a-fA-F]+);")
_NUM_DEC_RE = re.compile(r"&#(\d+);")
_NAMED_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")

_INLINE_TAG_RE = re.compile(
    r"</?(?:a|b|strong|em|i|u|s|span|font|small|sub|sup|code|abbr|mark)\b[^>]*>", re.I
)
_BLOCK_CLOSE_RE = re.compile(
    r"</(?:p|div|li|h[1-6]|tr|td|th|section|article|blockquote|table|ul|ol)>", re.I
)


def _from_code_point(code: int) -> str:
    if not code or code <= 0 or code > 0x10FFFF:
        return ""
    try:
        return chr(code)
    except (ValueError, OverflowError):
        return ""


def decode_entities(text) -> str:
    """展开 CDATA、还原 HTML 实体"""
    s = "" if text is None else str(text)
    s = _CDATA_RE.sub(r"\1", s)
    s = _NUM_HEX_RE.sub(lambda m: _from_code_point(int(m.group(1), 16)), s)
    s = _NUM_DEC_RE.sub(lambda m: _from_code_point(int(m.group(1))), s)
    s = _NAMED_RE.sub(
        lambda m: NAMED_ENTITIES.get(m.group(1), m.group(0)), s
    )
    s = s.replace("&amp;", "&")
    return s


def strip_html(raw) -> str:
    """把 HTML 摘要压成纯文本一行"""
    s = "" if raw is None else str(raw)
    s = _CDATA_RE.sub(r"\1", s)
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    # 行内标签直接去掉（不该在文字中间插空格），块级标签才当分隔符
    s = _INLINE_TAG_RE.sub("", s)
    s = _BLOCK_CLOSE_RE.sub(" ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", decode_entities(s)).strip()


def _pick_tag(block: str, tags) -> str:
    for tag in tags:
        re_tag = re.escape(tag)
        m = re.search(
            rf"<{re_tag}(?:\s[^>]*)?>([\s\S]*?)</{re_tag}>", block, re.I
        )
        if m and m.group(1).strip():
            return m.group(1)
    return ""


def _pick_link(block: str) -> str:
    """RSS 的 <link> 与 Atom 的 <link href> 都要支持"""
    inline = re.search(r"<link(?:\s[^>]*)?>([\s\S]*?)</link>", block, re.I)
    if inline and inline.group(1).strip():
        return decode_entities(inline.group(1)).strip()

    fallback = ""
    for m in re.finditer(r"<link\b([^>]*?)/?>", block, re.I):
        attrs = m.group(1) or ""
        href_m = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
        if not href_m:
            continue
        href = href_m.group(1)
        rel_m = re.search(r"rel\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
        rel = rel_m.group(1) if rel_m else ""
        if rel and not re.search(r"alternate", rel, re.I):
            continue
        if re.search(r"alternate", rel, re.I):
            return decode_entities(href).strip()
        if not fallback:
            fallback = decode_entities(href).strip()
    if fallback:
        return fallback

    guid = re.search(r"<guid[^>]*>([\s\S]*?)</guid>", block, re.I)
    if guid:
        g = decode_entities(guid.group(1)).strip()
        if re.match(r"^https?://", g, re.I):
            return g
    return ""


def _pick_cover(block: str) -> str:
    """封面：优先媒体扩展字段，其次正文里的第一张图"""
    media = re.search(r"<media:(?:content|thumbnail)[^>]*\surl=[\"']([^\"']+)[\"']", block, re.I)
    if media:
        return media.group(1)
    enclosure = re.search(r"<enclosure[^>]*\surl=[\"']([^\"']+)[\"'][^>]*>", block, re.I)
    if enclosure:
        return enclosure.group(1)
    body = _pick_tag(block, ["content:encoded", "content", "description", "summary", "info"])
    img = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", body, re.I)
    return img.group(1) if img else ""


def _parse_date(raw: str) -> int:
    """把 RFC822 / ISO8601 时间串解析成毫秒时间戳，失败返回 0"""
    if not raw:
        return 0
    text = decode_entities(raw).strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=None)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    # 退化路径：交给 email.utils
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(text)
        if dt is not None:
            return int(dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        pass
    return 0


def rel_time(ts: int) -> str:
    """相对时间，用于「3 小时前」这类展示"""
    if not ts:
        return ""
    diff = int(time.time() * 1000) - ts
    if diff < 0:
        return "刚刚"
    minute = diff // 60000
    if minute < 1:
        return "刚刚"
    if minute < 60:
        return f"{minute} 分钟前"
    hour = minute // 60
    if hour < 24:
        return f"{hour} 小时前"
    day = hour // 24
    if day < 30:
        return f"{day} 天前"
    d = datetime.fromtimestamp(ts / 1000)
    return f"{d.month} 月 {d.day} 日"


def _split_entries(xml: str):
    """把一段 XML 拆成条目块"""
    blocks = [m.group(0) for m in re.finditer(r"<(item|entry)\b[\s\S]*?</\1>", xml, re.I)]
    if blocks:
        return blocks
    return [m.group(0) for m in re.finditer(r"<(item|entry)\b[^>]*/>", xml, re.I)]


def parse_feed(xml: str):
    """解析 RSS/Atom 文本为条目数组"""
    items = []
    for block in _split_entries(xml):
        raw_title = _pick_tag(block, ["title"])
        title = strip_html(raw_title) or decode_entities(raw_title).strip()
        if not title:
            continue

        url = _pick_link(block)
        raw_desc = _pick_tag(block, ["description", "summary", "content:encoded", "content"])
        desc = strip_html(raw_desc)
        if desc == title:
            desc = ""
        if len(desc) > 160:
            desc = desc[:160].strip() + "…"

        category = strip_html(_pick_tag(block, ["category", "tags"]))[:12]
        author = strip_html(_pick_tag(block, ["dc:creator", "author", "name", "creator"]))[:20]
        ts = _parse_date(
            _pick_tag(block, ["pubDate", "published", "updated", "dc:date", "date", "lastBuildDate"])
        )

        bits = []
        rt = rel_time(ts)
        if rt:
            bits.append(rt)
        if author and author != title:
            bits.append(author)

        items.append(
            {
                "title": title,
                "url": url,
                "heat": None,
                "heatText": "",
                "heatLabel": "",
                "tag": category,
                "desc": desc,
                "cover": _pick_cover(block),
                "extra": " · ".join(bits),
                "__ts": ts,
            }
        )
    return items


def fetch_feed(feed_url: str, limit: int = 40, headers=None):
    """抓取并解析一个 RSS 源"""
    xml = get_text(
        feed_url,
        {
            "timeout": 20,
            "retries": 1,
            "headers": {
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                **(headers or {}),
            },
        },
    )

    items = parse_feed(xml)
    if not items:
        raise ValueError("该源没有返回可解析的条目（可能是空列表或格式变更）")

    # 少数源（如 Steam）会重复推送同一条内容，按链接去重；没有链接时退回标题
    seen = set()
    unique = []
    for it in items:
        key = (it.get("url") or it.get("title") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    # 有发布时间的按时间倒序，没有的保持原始顺序
    dated = [it for it in unique if it.get("__ts")]
    if len(dated) >= max(3, len(unique) * 0.5):
        ordered = sorted(unique, key=lambda it: it.get("__ts") or 0, reverse=True)
    else:
        ordered = unique

    return finalize([{**it, "cover": https_image(it.get("cover"))} for it in ordered], limit)


def build_sources(configs):
    """由配置批量生成数据源对象"""
    sources = []
    for cfg in configs:
        sources.append(_make_feed_source(cfg))
    return sources


def _make_feed_source(cfg):
    def fetch_items():
        items = fetch_feed(cfg["feed"], cfg.get("limit") or 40, cfg.get("headers"))
        tag = cfg.get("tag")
        if tag:
            for it in items:
                if not it["tag"]:
                    it["tag"] = tag
        return items

    return {
        "id": cfg["id"],
        "name": cfg["name"],
        "group": cfg["group"],
        "color": cfg.get("color", "#666666"),
        "initial": cfg.get("initial", cfg["name"][:1]),
        "homepage": cfg.get("homepage", ""),
        "limit": cfg.get("limit") or 40,
        "kind": "feed",
        "fetchItems": fetch_items,
    }
