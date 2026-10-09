"""emailnews —— Ubuntu 命令行新闻邮件推送程序。

用法：
  emailnews                   打开配置界面
  emailnews -send             抓取最新新闻并立即发送一封邮件
  emailnews -send -n 5        抓取并发送，每个平台只取 5 条
  emailnews -test            仅测试 SMTP 连接与登录
  emailnews -config          打印当前配置（密码脱敏）
  emailnews -preview FILE    抓取并渲染到本地 HTML 文件（不发送）
  emailnews -services        查看/生成定时推送的 systemd 或 cron 配置
  emailnews -version         版本
  emailnews -help            帮助
"""

import argparse
import os
import sys
from datetime import datetime

# 版本号单一来源：包根 __init__.py，避免两处手改不同步
from emailnews import __version__ as _PKG_VERSION

__version__ = _PKG_VERSION

GROUPS_LABEL = {
    "hot": "实时热榜",
    "media": "国内媒体",
    "global": "国际媒体",
    "tech": "科技媒体",
    "game": "游戏",
}


def _base_dir():
    """兼容「源码直接运行」与「安装到 /opt 后运行」两种情况"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here) if os.path.basename(here) == "emailnews" else here


def _setup_path():
    """保证包能被导入（安装后由启动器注入路径，源码运行时这里兜底）"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base not in sys.path:
        sys.path.insert(0, base)


_setup_path()

from emailnews import config as cfg_mod  # noqa: E402
from emailnews import sources, template, ui  # noqa: E402
from emailnews.mailer import MailError, send_mail, test_connection  # noqa: E402


# ------------------------------------------------------------------ 抓取+发送
def do_fetch_and_send(per_source=None, concurrency=None, dry_run=False,
                      preview_path=None, quiet=False) -> int:
    """核心流程：读配置 -> 抓取 -> 渲染 -> 发送"""
    try:
        config, exists = cfg_mod.load_config()
    except cfg_mod.ConfigError as e:
        ui.err(str(e))
        return 2

    if not exists:
        ui.err("尚未配置。请先运行 emailnews 完成配置。")
        return 2

    config = cfg_mod.apply_env_overrides(config)

    opts = config.get("options", {})
    per_source = per_source or int(opts.get("per_source", 10))
    concurrency = concurrency or int(opts.get("concurrency", 8))

    missing = cfg_mod.missing_fields(config)
    if missing and not (dry_run or preview_path):
        ui.err(f"配置不完整，缺少：{', '.join(missing)}")
        ui.info("运行 emailnews 进入配置界面补全")
        return 2

    when = datetime.now()
    disabled = set(config.get("disabled_sources") or [])
    enabled_ids = sources.resolve_enabled(disabled)
    total_src = len(sources.SOURCES)

    ui.title(f"抓取新闻 · {when.strftime('%Y-%m-%d %H:%M:%S')}")
    if disabled:
        off_names = [s["name"] for s in sources.SOURCES if s["id"] in disabled]
        ui.info(f"新闻源：启用 {len(enabled_ids)}/{total_src} 个（已关闭：{', '.join(off_names)}）")
    else:
        ui.info(f"新闻源：全部启用（{total_src} 个）")
    ui.info(f"每平台取前 {per_source} 条，并发 {concurrency}")

    state = {"ok": 0, "fail": 0, "items": 0, "done": 0}

    def on_done(result, idx, total):
        state["done"] += 1
        if result.get("error"):
            state["fail"] += 1
            if not quiet:
                mark = ui.c("✘", "red")
                print(f"  {mark} [{state['done']:>2}/{total}] {result.get('name'):<16} {ui.c(result['error'][:56], 'gray')}")
        else:
            n = len(result.get("items") or [])
            state["ok"] += 1
            state["items"] += n
            if not quiet:
                mark = ui.c("✔", "green")
                print(f"  {mark} [{state['done']:>2}/{total}] {result.get('name'):<16} {n} 条")

    results = sources.fetch_many(
        ids=enabled_ids, concurrency=concurrency, per_source=None, on_done=on_done
    )

    print()
    ui.ok(f"抓取完成：{state['ok']} 个平台成功，{state['items']} 条资讯"
          + (f"，{state['fail']} 个失败" if state["fail"] else ""))

    html = template.render(results, per_source=per_source, when=when)
    text = template.render_text(results, per_source=per_source, when=when)

    # 预览模式：只写文件
    if preview_path:
        try:
            with open(preview_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            ui.ok(f"已生成预览文件：{preview_path}")
        except OSError as e:
            ui.err(f"写入预览文件失败：{e}")
            return 1
        return 0

    if dry_run:
        ui.warn("--dry-run：已跳过发送")
        return 0

    # 发送
    ui.title("发送邮件")
    recipients = config.get("recipients") or []
    ui.info(f"发件人：{config['sender'].get('email') or config['smtp'].get('username')}")
    ui.info(f"收件人：{', '.join(recipients)}")
    try:
        delivered, note = send_mail(config, html, text, when=when)
        ui.ok(f"发送成功：{note} → {', '.join(delivered)}")
        return 0
    except MailError as e:
        ui.err(str(e))
        return 1


# ------------------------------------------------------------------ 子命令
def cmd_send(args) -> int:
    return do_fetch_and_send(
        per_source=args.per_source,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        quiet=args.quiet,
    )


def cmd_test(args) -> int:
    try:
        config, exists = cfg_mod.load_config()
    except cfg_mod.ConfigError as e:
        ui.err(str(e))
        return 2
    if not exists:
        ui.err("尚未配置。请先运行 emailnews。")
        return 2
    config = cfg_mod.apply_env_overrides(config)

    ui.title("SMTP 连接测试")
    smtp = config["smtp"]
    ui.info(f"服务器：{smtp.get('host')}:{smtp.get('port')}（{(smtp.get('security') or 'ssl').upper()}）")
    ui.info(f"用户名：{smtp.get('username')}")
    print()
    try:
        banner = test_connection(smtp)
        ui.ok("连接与登录成功")
        if banner.strip():
            ui.info(f"服务器问候：{banner.strip().splitlines()[0][:100]}")
        return 0
    except MailError as e:
        ui.err(str(e))
        return 1


def cmd_config(args) -> int:
    try:
        config, exists = cfg_mod.load_config()
    except cfg_mod.ConfigError as e:
        ui.err(str(e))
        return 2
    if not exists:
        ui.warn("尚未创建配置文件。运行 emailnews 进行配置。")
        return 1

    ui.title("当前配置")
    ui.info(f"文件：{cfg_mod.config_path()}")
    print()
    s, smtp, pop3 = config["sender"], config["smtp"], config["pop3"]
    opts = config.get("options", {})
    print(f"  发件人    {s.get('email') or '(未设置)'}"
          + (f"  <{s.get('name')}>" if s.get("name") else ""))
    print(f"  SMTP      {smtp.get('host') or '(未设置)'}:{smtp.get('port')}"
          f"  {(smtp.get('security') or 'ssl').upper()}")
    print(f"           用户 {smtp.get('username') or '(未设置)'}")
    print(f"           密码 {ui.mask(smtp.get('password') or '')}")
    if pop3.get("host"):
        print(f"  POP3      {pop3.get('host')}:{pop3.get('port')}"
              f"  {(pop3.get('security') or 'ssl').upper()}")
        print(f"           用户 {pop3.get('username') or '-'}")
    else:
        print("  POP3      (未配置)")
    recips = config.get("recipients") or []
    print(f"  收件人    {', '.join(recips) if recips else '(未设置)'}")
    print(f"  抓取      每源 {opts.get('per_source', 10)} 条 · 并发 {opts.get('concurrency', 8)}")

    disabled = set(config.get("disabled_sources") or [])
    total_n = len(sources.SOURCES)
    enabled_n = len(sources.resolve_enabled(disabled))
    if disabled:
        names = [s["name"] for s in sources.SOURCES if s["id"] in disabled]
        print(f"  新闻源    启用 {enabled_n}/{total_n} 个")
        print(f"           已关闭：{', '.join(names)}")
    else:
        print(f"  新闻源    全部启用（{total_n} 个）")

    missing = cfg_mod.missing_fields(config)
    print()
    if missing:
        ui.warn(f"缺少：{', '.join(missing)}")
    else:
        ui.ok("配置完整")
    return 0


def cmd_preview(args) -> int:
    path = args.preview or os.path.join(os.getcwd(), "emailnews-preview.html")
    return do_fetch_and_send(
        per_source=args.per_source,
        concurrency=args.concurrency,
        preview_path=path,
        quiet=args.quiet,
    )


def cmd_sources(args) -> int:
    """列出全部数据源，并标出当前是启用还是关闭"""
    from emailnews.sources import get_groups

    try:
        config, exists = cfg_mod.load_config()
    except cfg_mod.ConfigError:
        config, exists = None, False
    disabled = set((config or {}).get("disabled_sources") or []) if exists else set()

    ui.title("数据源清单")
    if disabled:
        ui.info(f"已通过配置关闭 {len(disabled)} 个源（运行 emailnews 选项 6 可调整）")
    else:
        ui.info("当前全部启用（运行 emailnews 选项 6 可选择关闭）")

    for g in get_groups():
        label = GROUPS_LABEL.get(g["id"], g["name"])
        print()
        print(f"  {ui.c(label, 'bold')}  {ui.c(g['desc'], 'gray')}")
        for s in sources.SOURCES:
            if s["group"] == g["id"]:
                kind = "热榜" if s.get("kind") == "hot" else "RSS "
                state = ui.c("● 开", "green") if s["id"] not in disabled else ui.c("○ 关", "yellow")
                print(f"    {state}  {ui.c(kind, 'gray')} {s['name']:<18} {ui.c(s['id'], 'dim')}")
    print()
    enabled_n = len(sources.resolve_enabled(disabled))
    ui.info(f"共 {len(sources.SOURCES)} 个平台，当前启用 {enabled_n} 个")
    return 0


def cmd_services(args) -> int:
    """生成定时推送的服务配置（只生成文件，不自动启用）"""
    from emailnews import services

    ui.title("定时推送配置")
    binary = services._binary()

    if args.cron:
        text = services.render_cron()
        ui.info("将下面这行加入当前用户的 crontab（crontab -e）即可每天 8:00 自动推送：")
        print()
        print("  " + text)
        print()
        path = services.write_cron_file() if args.write else None
        if path:
            ui.ok(f"已写出参考文件：{path}")
        else:
            ui.info("加 --write 可同时把参考文件落盘")
        return 0

    files = services.write_systemd_files()
    for f in files:
        ui.ok(f"已生成：{f}")
    print()
    if binary != "/usr/bin/emailnews" and not os.path.isfile(binary):
        ui.warn(f"未能定位 emailnews 可执行文件（解析为 {binary}）")
        ui.info("请把生成的 .service 里 ExecStart 改成 emailnews 的实际路径")
    ui.info("启用定时推送（默认每天 08:00，需要 sudo）：")
    print(f"  sudo cp {files[0]} /etc/systemd/system/")
    print(f"  sudo cp {files[1]} /etc/systemd/system/")
    print("  sudo systemctl daemon-reload")
    print("  sudo systemctl enable --now emailnews.timer")
    print()
    ui.info("查看状态：systemctl list-timers emailnews.timer")
    ui.info("改频率：编辑 emailnews.timer 里的 OnCalendar，再 daemon-reload 并 restart")
    ui.info("不想用 systemd？运行 emailnews -services --cron 拿到 cron 写法")
    return 0


def cmd_version(args) -> int:
    print(f"emailnews {__version__}")
    return 0


# ------------------------------------------------------------------ 帮助
HELP = """emailnews —— 命令行新闻邮件推送

用法：
  emailnews                    打开配置界面（首次使用从这里开始）
  emailnews -send              抓取最新新闻并立即发送一封邮件
  emailnews -send -n 5         每个平台只取 5 条后发送
  emailnews -send --dry-run    只抓取与渲染，不发送（用于检查）
  emailnews -test              仅测试 SMTP 连接与登录
  emailnews -config            打印当前配置（密码脱敏）
  emailnews -preview [文件]     抓取并渲染到本地 HTML 文件，不发送
  emailnews -sources           列出全部数据源
  emailnews -services          生成定时推送的 systemd / cron 配置
  emailnews -version           显示版本
  emailnews -help              显示本帮助

配置位置：
  ~/.config/emailnews/config.json（权限 600）

常见问题：
  · QQ / 163 / 126 等邮箱需使用「授权码」，不是登录密码
  · 抓取走本机网络直连各平台公开接口，不需要代理
  · 可用环境变量覆盖密码：EMAILNEWS_SMTP_PASS / EMAILNEWS_POP3_PASS
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emailnews",
        add_help=False,
        description="命令行新闻邮件推送",
    )
    parser.add_argument("--help", "-help", "-h", action="store_true", dest="show_help")
    parser.add_argument("--version", "-version", "-v", action="store_true", dest="show_version")

    parser.add_argument("-send", "--send", action="store_true", help="抓取并发送邮件")
    parser.add_argument("-test", "--test", action="store_true", help="测试 SMTP 连接")
    parser.add_argument("-config", "--config", action="store_true", help="打印当前配置")
    parser.add_argument("-preview", "--preview", nargs="?", const="", default=None,
                        help="渲染到本地 HTML 文件，不发送")
    parser.add_argument("-sources", "--sources", action="store_true", help="列出数据源")
    parser.add_argument("-services", "--services", action="store_true", help="生成定时推送配置")
    parser.add_argument("--cron", action="store_true", help="配合 -services，输出 cron 写法")
    parser.add_argument("--write", action="store_true", help="配合 -services，落盘参考文件")

    parser.add_argument("-n", "--per-source", type=int, default=None,
                        help="每个平台最多取多少条")
    parser.add_argument("-c", "--concurrency", type=int, default=None, help="抓取并发数")
    parser.add_argument("--dry-run", action="store_true", help="只抓取与渲染，不发送")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式，只输出结果")

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.show_help:
        print(HELP)
        return 0
    if args.show_version:
        return cmd_version(args)

    # 无任何子命令 -> 进入配置界面
    if not any([args.send, args.test, args.config, args.preview is not None,
                args.sources, args.services]):
        if argv:
            parser.print_help()
            print()
            ui.warn(f"无法识别的参数：{' '.join(argv)}")
            return 2
        try:
            ui.run_config_wizard()
        except KeyboardInterrupt:
            print()
            ui.warn("已取消")
            return 130
        return 0

    if args.services:
        return cmd_services(args)
    if args.sources:
        return cmd_sources(args)
    if args.preview is not None:
        return cmd_preview(args)
    if args.test:
        return cmd_test(args)
    if args.config:
        return cmd_config(args)
    if args.send:
        return cmd_send(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
