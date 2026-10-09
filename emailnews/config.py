"""配置读写：~/.config/emailnews/config.json（权限 600）。

配置结构：
{
  "sender":   { "email": "...", "name": "..." },
  "smtp":     { "host": "smtp.qq.com", "port": 465, "security": "ssl", "username": "...", "password": "..." },
  "pop3":     { "host": "pop.qq.com",  "port": 995, "security": "ssl", "username": "...", "password": "..." },
  "recipients": ["a@x.com", "b@y.com"],
  "options":  { "per_source": 10, "concurrency": 8, "subject_prefix": "每日新闻热榜" }
}

密码以明文存放但文件权限锁到 600（仅属主可读写），这是服务器上最实际的做法；
若更看重安全性，可把密码从配置文件删掉、改用环境变量 EMAILNEWS_SMTP_PASS / EMAILNEWS_POP3_PASS。
"""

import json
import os
import stat
from pathlib import Path

APP_NAME = "emailnews"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


DEFAULT_CONFIG = {
    "sender": {"email": "", "name": ""},
    "smtp": {"host": "", "port": 465, "security": "ssl", "username": "", "password": ""},
    "pop3": {"host": "", "port": 995, "security": "ssl", "username": "", "password": ""},
    "recipients": [],
    "options": {"per_source": 10, "concurrency": 8, "subject_prefix": "每日新闻热榜"},
    # 被禁用的新闻源 id 列表；不在列表里的源即启用
    "disabled_sources": [],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    """读取配置；不存在时返回默认配置。返回 (config, exists)。"""
    path = config_path()
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG)), False
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as err:
        raise ConfigError(f"配置文件读取失败：{path}（{err}）") from err
    return _deep_merge(DEFAULT_CONFIG, raw), True


def save_config(config: dict):
    """写配置并把权限锁到 600"""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass
    return path


def apply_env_overrides(config: dict) -> dict:
    """允许用环境变量覆盖密码，便于在服务器上不落盘存放凭据"""
    smtp_pass = os.environ.get("EMAILNEWS_SMTP_PASS")
    if smtp_pass:
        config["smtp"]["password"] = smtp_pass
    pop3_pass = os.environ.get("EMAILNEWS_POP3_PASS")
    if pop3_pass:
        config["pop3"]["password"] = pop3_pass
    return config


def missing_fields(config: dict):
    """返回尚未填写的必填项中文名列表，用于启动前校验。

    注意：用户名/密码只在「服务器需要认证」时才算必填。部分自建 SMTP
    （内网中继、本地调试服务器）既不要用户名也不要密码，因此这里不把它们
    当作硬性缺项，避免误报。
    """
    missing = []
    if not (config["sender"]["email"] or "").strip():
        missing.append("发件人邮箱")
    if not (config["smtp"]["host"] or "").strip():
        missing.append("SMTP 服务器地址")
    if not config.get("recipients"):
        missing.append("收件人邮箱")
    return missing


def smtp_credentials_needed(config: dict):
    """SMTP 是否配了用户名但缺密码（这种多半是漏填，值得额外提醒）"""
    smtp = config.get("smtp", {})
    has_user = bool((smtp.get("username") or "").strip())
    has_pass = bool((smtp.get("password") or "").strip())
    return has_user and not has_pass


class ConfigError(Exception):
    """配置相关错误"""
