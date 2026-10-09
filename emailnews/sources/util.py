"""通用工具函数：与 Node 版 src/sources/util.js 行为保持一致。"""

import html
import re

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]*>")

# 需要还原的常见命名实体（其余交给 html.unescape）
_SIMPLE_ENTITIES = ("nbsp", "ensp", "emsp", "thinsp")


def trim_zero(value: float) -> str:
    """保留一位小数，去掉末尾的 .0"""
    return f"{value:.1f}".removesuffix(".0")


def format_heat(n) -> str:
    """把数字热度格式化成中文习惯的「万 / 亿」"""
    if n is None:
        return ""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return ""
    if v != v or v in (float("inf"), float("-inf")) or v < 0:  # NaN / Inf
        return ""
    if v >= 1e8:
        return trim_zero(v / 1e8) + "亿"
    if v >= 1e4:
        return trim_zero(v / 1e4) + "万"
    return str(round(v))


def parse_heat_text(text):
    """从「1234 万热度」「1.2亿热度」这类文本里还原出数字"""
    if not text:
        return None
    m = re.search(r"([\d.]+)\s*([万亿])?", str(text))
    if not m:
        return None
    try:
        base = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    if unit == "万":
        return round(base * 1e4)
    if unit == "亿":
        return round(base * 1e8)
    return round(base)


def clean_text(s) -> str:
    """去掉 HTML 标签与多余空白，还原常见实体"""
    if s is None:
        return ""
    text = str(s)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"&(nbsp|ensp|emsp|thinsp);", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return _WS_RE.sub(" ", text).strip()


def abs_url(base: str, url) -> str:
    """相对路径补全为绝对地址"""
    if not url:
        return ""
    s = str(url).strip()
    if re.match(r"^https?://", s, re.I):
        return s
    if s.startswith("//"):
        return "https:" + s
    if not base:
        return s
    return base.rstrip("/") + "/" + s.lstrip("/")


def https_image(url) -> str:
    """缩略图统一走 https，避免混合内容被拦"""
    if not url:
        return ""
    return re.sub(r"^http://", "https://", str(url).strip(), flags=re.I)


def finalize(items, limit: int = 60):
    """按数组顺序赋值 rank，过滤空标题，最多保留 limit 条"""
    out = []
    for it in items:
        if not it:
            continue
        title = clean_text(it.get("title"))
        if not title:
            continue
        heat = it.get("heat")
        if not isinstance(heat, (int, float)) or isinstance(heat, bool):
            heat = None
        out.append(
            {
                "rank": len(out) + 1,
                "title": title,
                "url": it.get("url") or "",
                "heat": heat,
                "heatText": it.get("heatText") or "",
                "heatLabel": it.get("heatLabel") or "",
                "tag": clean_text(it.get("tag") or ""),
                "desc": clean_text(it.get("desc") or ""),
                "cover": https_image(it.get("cover") or ""),
                "extra": clean_text(it.get("extra") or ""),
            }
        )
        if len(out) >= limit:
            break
    return out


def escape_html(s) -> str:
    """邮件模板里插入动态文本时使用"""
    return html.escape(str(s if s is not None else ""), quote=True)
