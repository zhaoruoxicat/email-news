"""邮件 HTML 渲染：以 eMail/demo.html 的版式为蓝本。

保持与 demo.html 完全一致的视觉：680px 白底卡片、顶部标题 + 日期、
每个分类一组（标题 + 英文小标 + 2px 黑色分隔线）、每条含序号 / 标题链接 / 热度行、
底部灰色说明区。所有内联样式照搬，确保各邮箱客户端渲染一致。
"""

import re
from datetime import datetime
from pathlib import Path

from .sources import GROUPS, get_groups
from .sources.util import escape_html as esc  # 复用同一套转义

# 分组 -> 英文小标
GROUP_EN = {
    "hot": "TRENDING",
    "media": "CHINA MEDIA",
    "global": "WORLD MEDIA",
    "tech": "TECH",
    "game": "GAMES",
}


# 摘要预览长度：只截取前 20 个字符，避免邮件正文过长
DESC_PREVIEW_CHARS = 20


def _render_item(index: int, item: dict, is_last: bool) -> str:
    """渲染单条新闻"""
    border = "" if is_last else "border-bottom:1px solid #eeeeee;"
    num = f"{index:02d}"

    title = esc(item.get("title") or "")
    url = esc(item.get("url") or "")
    if not url:
        url = "#"

    # 热度行：优先「标签 + 数值」，其次 extra（作者/时间等）
    heat_bits = []
    label = (item.get("heatLabel") or "").strip()
    heat_text = (item.get("heatText") or "").strip()
    if heat_text:
        heat_bits.append(f"{esc(label)}：{esc(heat_text)}" if label else esc(heat_text))
    extra = (item.get("extra") or "").strip()
    if extra:
        heat_bits.append(esc(extra))
    tag = (item.get("tag") or "").strip()
    if tag:
        heat_bits.append(esc(tag))
    meta_line = " · ".join([b for b in heat_bits if b])

    desc = (item.get("desc") or "").strip()
    desc_html = ""
    if desc:
        if len(desc) > DESC_PREVIEW_CHARS:
            snippet = desc[:DESC_PREVIEW_CHARS].rstrip() + "…"
        else:
            snippet = desc
        desc_html = (
            '<div style="margin-top:4px;font-size:13px;line-height:20px;color:#777777;">'
            f"{esc(snippet)}</div>"
        )

    meta_html = ""
    if meta_line:
        meta_html = (
            '<div style="margin-top:4px;font-size:12px;color:#999999;">'
            f"{meta_line}</div>"
        )

    return f"""                            <tr>
                                <td style="padding:13px 0;{border}">

                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>

                                            <td width="32" valign="top"
                                                style="font-size:14px;color:#999999;">
                                                {num}
                                            </td>

                                            <td valign="top">

                                                <a href="{url}"
                                                   target="_blank"
                                                   style="font-size:16px;line-height:24px;color:#222222;text-decoration:none;">
                                                    {title}
                                                </a>

                                                {desc_html}
                                                {meta_html}

                                            </td>

                                        </tr>
                                    </table>

                                </td>
                            </tr>
"""


def _render_group(group: dict, results: list) -> str:
    """渲染一个分类"""
    name = esc(group["name"])
    en = GROUP_EN.get(group["id"], "")
    blocks = []

    for res in results:
        items = res.get("items") or []
        if not items:
            continue

        src_name = esc(res.get("name") or res.get("id") or "")
        rows = "".join(
            _render_item(i + 1, it, i == len(items) - 1) for i, it in enumerate(items)
        )
        # 轻量小标题区分同一分组内的不同平台
        blocks.append(
            f"""                            <tr>
                                <td style="padding:16px 0 6px;font-size:14px;font-weight:600;color:#555555;">
                                    {src_name}
                                    <span style="font-size:12px;font-weight:400;color:#aaaaaa;margin-left:6px;">{len(items)} 条</span>
                                </td>
                            </tr>
{rows}"""
        )

    if not blocks:
        return ""

    inner = "".join(blocks)
    return f"""                        <table width="100%" cellpadding="0" cellspacing="0" border="0"
                               style="margin-bottom:30px;">

                            <tr>
                                <td style="padding-bottom:12px;border-bottom:2px solid #222222;">

                                    <span style="font-size:20px;font-weight:700;color:#111111;">
                                        {name}
                                    </span>

                                    <span style="font-size:13px;color:#999999;margin-left:8px;">
                                        {en}
                                    </span>

                                </td>
                            </tr>

{inner}
                        </table>

"""


def _template_path() -> Path:
    """定位 demo.html：打包后位于 ../share/emailnews/demo.html，源码内则在其上一级。"""
    candidates = [
        Path(__file__).resolve().parent.parent / "templates" / "demo.html",
        Path(__file__).resolve().parent.parent / "demo.html",
        Path(__file__).resolve().parent.parent.parent / "demo.html",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def render(results, per_source: int = 10, when=None) -> str:
    """按 demo.html 的版式渲染整封邮件。

    :param results: fetch_many 的返回值
    :param per_source: 每个平台最多展示条数
    :param when: datetime，默认当前时间
    """
    when = when or datetime.now()
    groups = get_groups()

    # 按分组归集结果
    body_parts = []
    for group in groups:
        group_results = [r for r in results if r.get("group") == group["id"]]
        trimmed = []
        for r in group_results:
            items = (r.get("items") or [])[:per_source]
            if items:
                trimmed.append({**r, "items": items})
        block = _render_group(group, trimmed)
        if block:
            body_parts.append(block)

    body = "".join(body_parts) or (
        '                        <table width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td style="padding:30px 0;text-align:center;color:#999999;font-size:14px;">'
        "本次未获取到任何新闻内容。</td></tr></table>\n"
    )

    ok = len([r for r in results if not r.get("error") and r.get("items")])
    total = len([r for r in results if (r.get("items") or [])])
    stats = f"共 {ok} 个平台 · {total} 条资讯"

    title = f"{when.year}年{when.month}月{when.day}日 · 今日热点资讯汇总"
    # 发送时间精确到秒，显示在邮件最顶部
    sent_at = when.strftime("%Y-%m-%d %H:%M:%S")

    # 优先用 demo.html 作为外壳，把内容替换进去；找不到就用内置骨架
    tpl = _template_path()
    if tpl:
        try:
            shell = tpl.read_text(encoding="utf-8")
            return _fill_demo_shell(shell, body, title, stats, sent_at)
        except OSError:
            pass
    return _builtin_shell(body, title, stats, sent_at)


def _fill_demo_shell(shell: str, body: str, title: str, stats: str, sent_at: str) -> str:
    """把 demo.html 的示例内容整段换成真实内容，保留其外框与底部。"""
    # 0) 先摘掉 demo 底部的占位链接（管理推送设置 / 取消订阅）——它们是示例，发出去会误导
    shell = re.sub(
        r'<div style="margin-top:15px;">[\s\S]*?</div>\s*(?=</td>)',
        "",
        shell,
        count=1,
    )
    # 1) 替换日期副标题，并在其后插入「发送时间（精确到秒）」
    time_line = (
        f'<div style="margin-top:8px;font-size:14px;color:#888888;">\n'
        f"                            {esc(title)}\n"
        f"                        </div>\n"
        f'                        <div style="margin-top:6px;font-size:13px;color:#aaaaaa;">\n'
        f"                            发送时间：{esc(sent_at)}\n"
        f"                        </div>"
    )
    shell = re.sub(
        r'<div style="margin-top:8px;font-size:14px;color:#888888;">\s*[\s\S]*?\s*</div>',
        time_line,
        shell,
        count=1,
    )
    # 2) 替换「内容区域」内 td 的正文：定位 <!-- 内容区域 --> 之后的那个 <td ...> ... </td>
    marker = "<!-- 内容区域 -->"
    idx = shell.find(marker)
    if idx != -1:
        open_td = shell.find("<td", idx)
        td_end = shell.find(">", open_td)
        # 对应 </td>：从内容区之后、底部注释之前找最后一个 </table>，其后的 </td> 即内容区闭合
        footer_idx = shell.find("<!-- 底部 -->")
        search_to = footer_idx if footer_idx != -1 else len(shell)
        last_table = shell.rfind("</table>", idx + len(marker), search_to)
        close_td = shell.find("</td>", last_table) if last_table != -1 else -1
        if open_td != -1 and td_end != -1 and close_td != -1:
            head = shell[: td_end + 1]
            tail = shell[close_td:]
            shell = head + "\n\n" + body + "                    " + tail

    else:
        # 兜底：定位不到内容区标记时，直接把示例分组表整段换掉
        shell = re.sub(
            r"<!-- ={4,}\s*微博\s*={4,}-->[\s\S]*?</table>\s*",
            body,
            shell,
            count=1,
        )

    # 3) 底部说明补上本次统计
    shell = re.sub(
        r'<div style="font-size:13px;line-height:22px;color:#888888;">\s*[\s\S]*?\s*</div>',
        f'<div style="font-size:13px;line-height:22px;color:#888888;">\n                            本邮件由新闻聚合程序自动生成 · {esc(stats)}\n                        </div>',
        shell,
        count=1,
    )
    return shell


def _builtin_shell(body: str, title: str, stats: str, sent_at: str) -> str:
    """demo.html 不可用时的等价骨架（样式与其一致）"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>每日新闻热榜</title>
</head>
<body style="margin:0;padding:0;background:#f5f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',Arial,sans-serif;color:#222;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f6f8;">
    <tr>
        <td align="center" style="padding:30px 15px;">
            <table width="680" cellpadding="0" cellspacing="0" border="0"
                   style="max-width:680px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;">
                <tr>
                    <td style="padding:30px 35px 25px;border-bottom:1px solid #eeeeee;">
                        <div style="font-size:26px;font-weight:700;color:#111111;">
                            每日新闻热榜
                        </div>
                        <div style="margin-top:8px;font-size:14px;color:#888888;">
                            {esc(title)}
                        </div>
                        <div style="margin-top:6px;font-size:13px;color:#aaaaaa;">
                            发送时间：{esc(sent_at)}
                        </div>
                    </td>
                </tr>
                <tr>
                    <td style="padding:30px 35px;">

{body}
                    </td>
                </tr>
                <tr>
                    <td style="padding:25px 35px;background:#fafafa;border-top:1px solid #eeeeee;">
                        <div style="font-size:13px;line-height:22px;color:#888888;">
                            本邮件由新闻聚合程序自动生成 · {esc(stats)}
                        </div>
                        <div style="margin-top:8px;font-size:12px;color:#aaaaaa;">
                            数据来源于各公开网络平台，仅用于信息汇总与阅读。
                        </div>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>

</body>
</html>
"""


def render_text(results, per_source: int = 10, when=None) -> str:
    """纯文本兜底版本（部分老客户端不渲染 HTML）"""
    when = when or datetime.now()
    lines = [
        f"每日新闻热榜 · {when.year}年{when.month}月{when.day}日",
        f"发送时间：{when.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 46,
        "",
    ]
    for group in get_groups():
        group_results = [r for r in results if r.get("group") == group["id"]]
        printed_header = False
        for r in group_results:
            items = (r.get("items") or [])[:per_source]
            if not items:
                continue
            if not printed_header:
                lines += [f"【{group['name']}】", ""]
                printed_header = True
            lines.append(f"-- {r.get('name')} --")
            for i, it in enumerate(items, 1):
                lines.append(f"{i:>2}. {it.get('title')}")
                # 摘要只预览前 20 字符，与 HTML 版保持一致
                desc = (it.get("desc") or "").strip()
                if desc:
                    if len(desc) > DESC_PREVIEW_CHARS:
                        desc = desc[:DESC_PREVIEW_CHARS].rstrip() + "…"
                    lines.append(f"    {desc}")
                meta = []
                if it.get("heatText"):
                    meta.append(f"{it.get('heatLabel') or ''}{it.get('heatText')}".strip())
                if it.get("extra"):
                    meta.append(it["extra"])
                if meta:
                    lines.append(f"    ({' · '.join(meta)})")
                if it.get("url"):
                    lines.append(f"    {it['url']}")
            lines.append("")
    lines += ["--", "本邮件由新闻聚合程序自动生成。", "数据来源于各公开网络平台，仅用于信息汇总与阅读。"]
    return "\n".join(lines)
