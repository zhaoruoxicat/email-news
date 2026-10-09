"""邮件发送：标准库 smtplib，支持 SSL(465) / STARTTLS(587) / 明文(25)。

不依赖任何第三方库。发送时同时带上 HTML 与纯文本两个版本（multipart/alternative），
保证在纯文本客户端里也能正常阅读。
"""

import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid


class MailError(Exception):
    """邮件发送相关错误"""


def _normalize_security(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("ssl", "smtps", "tls"):
        return "ssl"
    if v in ("starttls", "tls-start", "start"):
        return "starttls"
    if v in ("none", "plain", ""):
        return "none"
    return v


def _connect(smtp_cfg: dict, timeout: int = 30):
    """按安全模式建立并返回已登录的 SMTP 连接"""
    host = (smtp_cfg.get("host") or "").strip()
    if not host:
        raise MailError("未配置 SMTP 服务器地址")
    port = int(smtp_cfg.get("port") or 465)
    security = _normalize_security(smtp_cfg.get("security"))
    username = (smtp_cfg.get("username") or "").strip()
    password = smtp_cfg.get("password") or ""

    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=timeout,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
    except (OSError, smtplib.SMTPException) as err:
        raise MailError(f"连接 SMTP 服务器 {host}:{port} 失败：{err}") from err

    if username:
        try:
            server.login(username, password)
        except smtplib.SMTPAuthenticationError as err:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
            detail = err.smtp_error.decode("utf-8", "replace") if isinstance(err.smtp_error, bytes) else err.smtp_error
            raise MailError(
                f"SMTP 认证失败（{detail}）。请检查用户名/密码；"
                "QQ、163 等邮箱需使用「授权码」而非登录密码。"
            ) from err
        except (OSError, smtplib.SMTPException) as err:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
            raise MailError(f"SMTP 登录失败：{err}") from err

    return server


def test_connection(smtp_cfg: dict, timeout: int = 20) -> str:
    """测试 SMTP 连接与登录，成功返回服务器问候语"""
    server = _connect(smtp_cfg, timeout)
    try:
        banner = server.ehlo_resp.decode("utf-8", "replace") if getattr(server, "ehlo_resp", None) else ""
        return banner or "连接与登录成功"
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass


def build_message(config: dict, html_body: str, text_body: str, when=None) -> MIMEMultipart:
    """组装 MIME 邮件"""
    when = when or datetime.now()
    sender = config["sender"]
    smtp_cfg = config["smtp"]
    from_addr = (sender.get("email") or smtp_cfg.get("username") or "").strip()
    from_name = (sender.get("name") or "").strip()
    if not from_addr:
        raise MailError("未配置发件人邮箱")

    prefix = (config.get("options", {}).get("subject_prefix") or "每日新闻热榜").strip()
    subject = f"{prefix} · {when.year}-{when.month:02d}-{when.day:02d}"

    recipients = [r.strip() for r in (config.get("recipients") or []) if r and r.strip()]
    if not recipients:
        raise MailError("未配置收件人邮箱")

    root = MIMEMultipart("alternative")
    root["Subject"] = Header(subject, "utf-8")
    root["From"] = formataddr((str(Header(from_name, "utf-8")), from_addr)) if from_name else from_addr
    root["To"] = ", ".join(recipients)
    root["Date"] = formatdate(localtime=True)
    root["Message-ID"] = make_msgid(domain=from_addr.split("@")[-1] or "emailnews")

    root.attach(MIMEText(text_body, "plain", "utf-8"))
    root.attach(MIMEText(html_body, "html", "utf-8"))
    return root


def send_mail(config: dict, html_body: str, text_body: str, when=None, timeout: int = 45):
    """发送邮件。返回 (收件人列表, 服务器响应)"""
    root = build_message(config, html_body, text_body, when)
    recipients = [r.strip() for r in config["recipients"] if r and r.strip()]

    server = _connect(config["smtp"], timeout)
    try:
        refused = server.sendmail(
            root["From"] if isinstance(root["From"], str) else str(root["From"]),
            recipients,
            root.as_string(),
        )
    except smtplib.SMTPRecipientsRefused as err:
        raise MailError(f"所有收件人都被拒绝：{err.recipients}") from err
    except smtplib.SMTPSenderRefused as err:
        raise MailError(f"发件人被拒绝：{err}") from err
    except smtplib.SMTPDataError as err:
        raise MailError(f"邮件内容被服务器拒绝：{err}") from err
    except (OSError, smtplib.SMTPException) as err:
        raise MailError(f"发送失败：{err}") from err
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass

    if refused:
        raise MailError(f"部分收件人被拒绝：{refused}")
    return recipients, "已投递"
