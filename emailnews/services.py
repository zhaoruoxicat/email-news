"""定时推送配置生成：systemd timer 与 cron 两种方案。

只负责生成文件与打印指引，不自动启用（启用需要 sudo，交由用户决定）。
"""

import os
from pathlib import Path

SERVICE_NAME = "emailnews"
DEFAULT_ON_CALENDAR = "*-*-* 08:00:00"


def _binary() -> str:
    """定位 emailnews 可执行文件。

    顺序：系统安装位置 -> PATH 里的 emailnews -> 源码树里的启动脚本。
    注意不要退回「包目录本身」，那是个目录不是可执行文件。
    """
    for p in ("/usr/bin/emailnews", "/usr/local/bin/emailnews"):
        if os.path.isfile(p):
            return p
    import shutil

    found = shutil.which("emailnews")
    if found:
        return found
    # 源码树场景：eMail/ 下有个可执行的 emailnews 启动脚本则用它
    here = Path(__file__).resolve().parent.parent
    for cand in (here / "emailnews.sh", here / "bin" / "emailnews"):
        if cand.is_file():
            return str(cand)
    # 最后兜底：用 python3 -m emailnews 的形式不好写进 systemd/cron，
    # 所以给出明确提示而不是一个错路径
    return "/usr/bin/emailnews"


def _output_dir(out_dir=None) -> Path:
    """生成文件写到哪里。

    安装到 /opt 后普通用户对程序目录没有写权限，因此优先写到用户配置目录；
    源码树运行时写进 packaging/ 方便查看。
    """
    if out_dir:
        return Path(out_dir)

    # 是否运行在系统安装位置（/opt/emailnews）
    pkg_parent = Path(__file__).resolve().parent.parent
    installed = "/opt/" in str(pkg_parent)

    if installed:
        # 安装后：写到 ~/.config/emailnews/services/
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
        return Path(base) / "emailnews" / "services"

    # 源码树：写到 eMail/packaging/
    return pkg_parent / "packaging"


SYSTEMD_SERVICE = """[Unit]
Description=emailnews 新闻邮件推送
Documentation=man:emailnews(1)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={binary} -send
# 用哪个用户来跑：默认是安装本服务的用户，可改成具体用户名
User={user}
# 抓取需要联网，给一点重试余量
TimeoutStartSec=600
Nice=10

[Install]
WantedBy=multi-user.target
"""

SYSTEMD_TIMER = """[Unit]
Description=emailnews 每日定时推送
Documentation=man:emailnews(1)

[Timer]
# 每天 08:00 推送；想改成每 6 小时一次就换成 *-*-* 00/6:00:00
OnCalendar={oncalendar}
# 开机后若已错过时间点则补跑一次
Persistent=true
Unit={service}.service

[Install]
WantedBy=timers.target
"""


def _current_user() -> str:
    import getpass

    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USER", "root")


def render_systemd() -> tuple:
    """返回 (service 文本, timer 文本)"""
    service = SYSTEMD_SERVICE.format(binary=_binary(), user=_current_user())
    timer = SYSTEMD_TIMER.format(oncalendar=DEFAULT_ON_CALENDAR, service=SERVICE_NAME)
    return service, timer


def write_systemd_files(out_dir=None) -> list:
    """把 systemd 单元写到用户可写的位置（安装后不会往 /opt 里写）"""
    target = _output_dir(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    service, timer = render_systemd()

    service_path = target / f"{SERVICE_NAME}.service"
    timer_path = target / f"{SERVICE_NAME}.timer"
    service_path.write_text(service, encoding="utf-8")
    timer_path.write_text(timer, encoding="utf-8")
    return [str(service_path), str(timer_path)]


def render_cron() -> str:
    """cron 写法（每天 8:00）"""
    return f"0 8 * * * {_binary()} -send >/dev/null 2>&1"


def write_cron_file(out_dir=None) -> str:
    target = _output_dir(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{SERVICE_NAME}.cron"
    path.write_text(
        "# emailnews 定时推送（加入到 crontab -e 中）\n"
        "# 每天 08:00 推送一次\n"
        + render_cron()
        + "\n\n# 每 6 小时推送一次\n"
        + f"0 */6 * * * {_binary()} -send >/dev/null 2>&1\n",
        encoding="utf-8",
    )
    return str(path)
