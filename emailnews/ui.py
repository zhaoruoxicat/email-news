"""交互式配置向导与终端输出辅助。

`emailnews` 不带参数时进入配置界面（菜单式，纯终端）。
"""

import getpass
import sys

from . import config as cfg_mod
from .mailer import MailError, test_connection

# ------------------------------------------------------------------ 输出样式
_C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}


def _supports_color() -> bool:
    return sys.stdout.isatty()


def c(text: str, color: str = "") -> str:
    if not _supports_color() or not color:
        return text
    return f"{_C.get(color, '')}{text}{_C['reset']}"


def ok(msg: str):
    print(f"{c('✔', 'green')} {msg}")


def warn(msg: str):
    print(f"{c('!', 'yellow')} {msg}")


def err(msg: str):
    print(f"{c('✘', 'red')} {msg}", file=sys.stderr)


def info(msg: str):
    print(f"{c('·', 'gray')} {msg}")


def title(msg: str):
    print()
    print(c(msg, "bold"))
    print(c("─" * 52, "gray"))


def mask(secret: str) -> str:
    """密码脱敏展示"""
    if not secret:
        return "(未设置)"
    if len(secret) <= 4:
        return "*" * len(secret)
    return secret[:2] + "*" * (len(secret) - 4) + secret[-2:]


def prompt(label: str, current: str = "", secret: bool = False, allow_empty: bool = False) -> str:
    """单行输入。直接回车保留原值。"""
    shown = mask(current) if secret else current
    hint = f" {c('[' + shown + ']', 'gray')}" if shown else ""
    try:
        raw = getpass.getpass(f"{label}{hint}: ") if secret else input(f"{label}{hint}: ")
    except EOFError:
        return current
    raw = raw.strip()
    if not raw:
        if current or allow_empty:
            return current
        return ""
    return raw


def prompt_list(label: str, current: list) -> list:
    """逗号 / 空格分隔的邮箱列表输入"""
    shown = ", ".join(current) if current else ""
    hint = f" {c('[' + shown + ']', 'gray')}" if shown else ""
    try:
        raw = input(f"{label}（多个用逗号分隔）{hint}: ").strip()
    except EOFError:
        return current
    if not raw:
        return current
    parts = [p.strip() for p in raw.replace(";", ",").replace(" ", ",").split(",")]
    return [p for p in parts if p]


def prompt_choice(label: str, options: list, current: str) -> str:
    """编号选择，直接回车保留原值"""
    print(f"{label}:")
    for i, (value, text) in enumerate(options, 1):
        mark = c(" ← 当前", "green") if value == current else ""
        print(f"  {i}) {text}{mark}")
    try:
        raw = input(f"选择 [1-{len(options)}]{c(' 回车保留', 'gray')}: ").strip()
    except EOFError:
        return current
    if not raw.isdigit() or not (1 <= int(raw) <= len(options)):
        return current
    return options[int(raw) - 1][0]


def confirm(label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"{label} [{hint}]: ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in ("y", "yes", "是", "1")


# ------------------------------------------------------------------ 配置向导
def run_config_wizard():
    """完整的配置向导。返回 True 表示配置有变动。"""
    config, exists = cfg_mod.load_config()
    changed = False

    while True:
        _show_config_summary(config, exists)
        print()
        print("  1) 配置发件人邮箱（SMTP 发送方）")
        print("  2) 配置 SMTP 服务器")
        print("  3) 配置 POP3 服务器（可选，用于收信校验）")
        print("  4) 配置收件人邮箱")
        print("  5) 配置抓取选项（每源条数 / 并发）")
        print("  6) 选择新闻源（开启 / 关闭）")
        print("  7) 测试 SMTP 连接")
        print("  8) 保存并退出")
        print("  0) 放弃修改并退出")
        try:
            choice = input(c("\n请选择", "bold") + ": ").strip()
        except EOFError:
            return False
        print()

        if choice == "1":
            changed |= _edit_sender(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "2":
            changed |= _edit_smtp(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "3":
            changed |= _edit_pop3(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "4":
            changed |= _edit_recipients(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "5":
            changed |= _edit_options(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "6":
            changed |= edit_sources(config)
            if changed:
                _save(config)
                exists = True
        elif choice == "7":
            _try_smtp(config)
        elif choice in ("8",):
            if changed:
                _save(config)
            ok("配置已保存")
            return changed
        elif choice in ("0", "q", "exit"):
            warn("已放弃未保存的修改")
            return False
        else:
            warn("无效选项")


def _show_config_summary(config: dict, exists: bool):
    title("emailnews 配置")
    if exists:
        info(f"配置文件：{cfg_mod.config_path()}")
    else:
        warn("尚不存在配置文件，按提示填写后会自动创建")

    s = config["sender"]
    smtp = config["smtp"]
    pop3 = config["pop3"]
    opts = config.get("options", {})

    print()
    print(f"  {c('发件人', 'bold')}   {s.get('email') or c('(未设置)', 'yellow')}"
          + (f"  显示名：{s.get('name')}" if s.get("name") else ""))
    sec = (smtp.get("security") or "ssl").upper()
    print(f"  {c('SMTP', 'bold')}    {smtp.get('host') or c('(未设置)', 'yellow')}"
          f"{':' + str(smtp.get('port')) if smtp.get('host') else ''}  {sec}"
          f"   用户：{smtp.get('username') or c('(未设置)', 'yellow')}"
          f"   密码：{mask(smtp.get('password') or '')}")
    if pop3.get("host"):
        print(f"  {c('POP3', 'bold')}    {pop3.get('host')}:{pop3.get('port')}"
              f"  {(pop3.get('security') or 'ssl').upper()}"
              f"   用户：{pop3.get('username') or '-'}   密码：{mask(pop3.get('password') or '')}")
    else:
        print(f"  {c('POP3', 'bold')}    {c('(可选，未配置)', 'gray')}")
    recips = config.get("recipients") or []
    print(f"  {c('收件人', 'bold')}   {', '.join(recips) if recips else c('(未设置)', 'yellow')}")
    print(f"  {c('抓取', 'bold')}     每源 {opts.get('per_source', 10)} 条 · 并发 {opts.get('concurrency', 8)}")

    # 新闻源启用情况
    from emailnews import sources as _src

    disabled = set(config.get("disabled_sources") or [])
    enabled_n = len(_src.SOURCES) - len(disabled & set(_src.all_ids()))
    total_n = len(_src.SOURCES)
    if disabled:
        names = [s["name"] for s in _src.SOURCES if s["id"] in disabled]
        state = c(f"启用 {enabled_n}/{total_n}", "yellow")
        print(f"  {c('新闻源', 'bold')}   {state}   已关闭：{', '.join(names)}")
    else:
        print(f"  {c('新闻源', 'bold')}   {c(f'全部启用（{total_n} 个）', 'green')}")

    missing = cfg_mod.missing_fields(config)
    if missing:
        warn(f"还缺少：{', '.join(missing)}")


def _save(config: dict):
    try:
        path = cfg_mod.save_config(config)
        ok(f"已写入 {path}（权限 600）")
    except OSError as e:
        err(f"保存失败：{e}")


def _edit_sender(config: dict) -> bool:
    title("发件人邮箱")
    info("发件人 = 你用来发信的邮箱（需已开启 SMTP 服务）")
    before = dict(config["sender"])
    config["sender"]["email"] = prompt("邮箱地址", config["sender"].get("email", ""))
    config["sender"]["name"] = prompt("显示名称（可留空）", config["sender"].get("name", ""))
    if not config["smtp"].get("username"):
        config["smtp"]["username"] = config["sender"]["email"]
    return before != config["sender"]


def _edit_smtp(config: dict) -> bool:
    title("SMTP 服务器")
    print(c("常见配置：", "gray"))
    print("  QQ 邮箱      smtp.qq.com      465  SSL")
    print("  163 邮箱     smtp.163.com     465  SSL")
    print("  126 邮箱     smtp.126.com     465  SSL")
    print("  Gmail        smtp.gmail.com   587  STARTTLS")
    print("  Outlook      smtp.office365.com 587 STARTTLS")
    print(c("  注意：QQ/163 等需使用「授权码」，不是登录密码。", "yellow"))
    print()
    before = dict(config["smtp"])
    smtp = config["smtp"]
    smtp["host"] = prompt("SMTP 地址", smtp.get("host", ""))
    port_raw = prompt("端口", str(smtp.get("port", 465)))
    try:
        smtp["port"] = int(port_raw)
    except ValueError:
        pass
    smtp["security"] = prompt_choice(
        "加密方式",
        [("ssl", "SSL / TLS（465 端口常用）"),
         ("starttls", "STARTTLS（587 端口常用）"),
         ("none", "不加密（25 端口，不推荐）")],
        smtp.get("security", "ssl"),
    )
    smtp["username"] = prompt("用户名（通常就是邮箱地址）", smtp.get("username", ""))
    smtp["password"] = prompt("密码 / 授权码", smtp.get("password", ""), secret=True)
    if not smtp["username"]:
        smtp["username"] = config["sender"].get("email", "")
    return before != config["smtp"]


def _edit_pop3(config: dict) -> bool:
    title("POP3 服务器（可选）")
    info("用于验证收信通道；不配置不影响发信")
    print(c("常见配置：", "gray"))
    print("  QQ 邮箱   pop.qq.com    995  SSL")
    print("  163 邮箱  pop.163.com   995  SSL")
    print()
    before = dict(config["pop3"])
    pop3 = config["pop3"]
    host = prompt("POP3 地址（留空表示不启用）", pop3.get("host", ""), allow_empty=True)
    pop3["host"] = host
    if host:
        port_raw = prompt("端口", str(pop3.get("port", 995)))
        try:
            pop3["port"] = int(port_raw)
        except ValueError:
            pass
        pop3["security"] = prompt_choice(
            "加密方式",
            [("ssl", "SSL / TLS（995 端口常用）"), ("none", "不加密（110 端口）")],
            pop3.get("security", "ssl"),
        )
        pop3["username"] = prompt("用户名", pop3.get("username", ""))
        pop3["password"] = prompt("密码 / 授权码", pop3.get("password", ""), secret=True)
    else:
        pop3["username"] = ""
        pop3["password"] = ""
    return before != config["pop3"]


def _edit_recipients(config: dict) -> bool:
    title("收件人邮箱")
    info("与发件人相互独立，可填多个")
    before = list(config.get("recipients") or [])
    config["recipients"] = prompt_list("收件人", config.get("recipients") or [])
    return before != config["recipients"]


def _edit_options(config: dict) -> bool:
    title("抓取选项")
    opts = config.setdefault("options", {})
    before = dict(opts)
    raw = prompt("每个平台最多展示条数", str(opts.get("per_source", 10)))
    if raw.isdigit():
        opts["per_source"] = max(1, min(50, int(raw)))
    raw = prompt("抓取并发数", str(opts.get("concurrency", 8)))
    if raw.isdigit():
        opts["concurrency"] = max(1, min(20, int(raw)))
    return before != opts


def edit_sources(config: dict) -> bool:
    """新闻源开关。返回 True 表示有改动。

    支持三种粒度：单个源开关、整组批量开关、一键全开/全关。
    配置里存的是「被禁用的 id 列表」，这样新增的源默认是启用的。
    """
    from emailnews import sources as _src

    before = list(config.get("disabled_sources") or [])
    disabled = set(before)

    while True:
        _show_sources(config, disabled)
        print()
        print("  输入编号        切换单个新闻源的开 / 关")
        print("  g<编号>         切换整个分组（例：g1 关掉「实时热榜」整组）")
        print("  all             全部开启")
        print("  none            全部关闭")
        print("  0 / 回车        返回")
        try:
            raw = input(c("\n请选择", "bold") + ": ").strip().lower()
        except EOFError:
            break

        if raw in ("", "0", "q", "b"):
            break
        if raw == "all":
            disabled.clear()
            config["disabled_sources"] = sorted(disabled)
            ok("已全部开启")
            continue
        if raw == "none":
            disabled = set(_src.all_ids())
            config["disabled_sources"] = sorted(disabled)
            warn("已全部关闭（保存后若不改回来，抓取时会退回全部启用以免发出空邮件）")
            continue
        if raw.startswith("g") and raw[1:].isdigit():
            groups = _src.sources_by_group()
            gi = int(raw[1:])
            if not (1 <= gi <= len(groups)):
                warn(f"分组编号超出范围（1-{len(groups)}）")
                continue
            group, members = groups[gi - 1]
            ids = [s["id"] for s in members]
            if all(i in disabled for i in ids):
                disabled -= set(ids)
                ok(f"已开启整组「{group['name']}」（{len(ids)} 个源）")
            else:
                disabled |= set(ids)
                ok(f"已关闭整组「{group['name']}」（{len(ids)} 个源）")
            config["disabled_sources"] = sorted(disabled)
            continue
        if raw.isdigit():
            flat = _flat_index(_src)
            idx = int(raw)
            if not (1 <= idx <= len(flat)):
                warn(f"编号超出范围（1-{len(flat)}）")
                continue
            sid, name = flat[idx - 1]
            if sid in disabled:
                disabled.discard(sid)
                ok(f"已开启「{name}」")
            else:
                disabled.add(sid)
                ok(f"已关闭「{name}」")
            config["disabled_sources"] = sorted(disabled)
            continue

        warn("无效输入")

    config["disabled_sources"] = sorted(disabled)
    if sorted(disabled) == sorted(before):
        return False
    enabled_n = len(_src.SOURCES) - len(disabled)
    ok(f"新闻源设置已更新：启用 {enabled_n}/{len(_src.SOURCES)} 个")
    return True


def _flat_index(src):
    """(id, name) 的扁平列表，顺序与 _show_sources 里的编号一致"""
    flat = []
    for _group, members in src.sources_by_group():
        for s in members:
            flat.append((s["id"], s["name"]))
    return flat


def _show_sources(config: dict, disabled: set):
    from emailnews import sources as _src

    title("新闻源开关")
    info("关闭的源不会被抓取，也不会出现在邮件里")
    info("编号用于单个切换；g<编号> 可整组切换")
    print()

    n = 0
    for gi, (group, members) in enumerate(_src.sources_by_group(), 1):
        on_n = sum(1 for s in members if s["id"] not in disabled)
        print(f"  {c(f'g{gi}', 'cyan')} {c(group['name'], 'bold')} "
              f"{c(group['desc'], 'gray')}  "
              f"{c(f'{on_n}/{len(members)} 开', 'green' if on_n else 'yellow')}")
        for s in members:
            n += 1
            on = s["id"] not in disabled
            mark = c("● 开", "green") if on else c("○ 关", "yellow")
            print(f"      {n:>2}) {mark}  {s['name']}")
        print()

    on_total = len(_src.SOURCES) - len(disabled & set(_src.all_ids()))
    print(f"  合计：{c(f'{on_total}/{len(_src.SOURCES)} 个源启用', 'bold')}")


def _try_smtp(config: dict):
    missing = [m for m in cfg_mod.missing_fields(config) if "SMTP" in m or "发件人" in m]
    if missing:
        err(f"无法测试，缺少：{', '.join(missing)}")
        return
    if cfg_mod.smtp_credentials_needed(config):
        warn("已填 SMTP 用户名但没填密码，若该服务器需要认证会失败")
    print(c("正在连接…", "gray"))
    try:
        banner = test_connection(config["smtp"])
        ok("SMTP 连接与登录成功")
        if banner.strip():
            print(c(f"   服务器：{banner.strip().splitlines()[0][:80]}", "gray"))
    except MailError as e:
        err(str(e))
