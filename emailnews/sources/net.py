"""统一的网络请求层：伪装成桌面 Chrome，带超时与重试。

对应 Node 版 src/sources/http.js。全部使用标准库 urllib，不引入第三方依赖。
所有抓取都从本机网络直连各平台官方接口，不经过任何第三方中转。
"""

import json
import re
import time
import urllib.error
import urllib.request

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# 部分老站（新浪、太平洋电脑网等）仍用 GB2312/GBK 输出，必须按声明解码，
# 否则中文会整片乱码。
CHARSET_ALIASES = {
    "gb2312": "gbk",
    "gb-2312": "gbk",
    "gb_2312-80": "gbk",
    "gb18030": "gb18030",
    "utf8": "utf-8",
    "utf-8bom": "utf-8",
    "big5": "big5",
    "iso-8859-1": "gbk",  # 站点常错标，实际是 GBK
    "latin1": "gbk",
}


class HttpError(Exception):
    """带 HTTP 状态码的请求异常"""

    def __init__(self, message, status=0):
        super().__init__(message)
        self.name = "HttpError"
        self.status = status


def detect_charset(body: bytes, headers) -> str:
    ct = headers.get("Content-Type", "") or ""
    m = re.search(r"charset\s*=\s*[\"']?([\w-]+)", ct, re.I)
    cs = m.group(1) if m else None
    if not cs:
        head = body[:220].decode("latin-1", errors="replace")
        m2 = re.search(r"encoding\s*=\s*[\"']([\w-]+)[\"']", head, re.I)
        cs = m2.group(1) if m2 else None
    return (cs or "utf-8").lower()


def decode_body(body: bytes, headers) -> str:
    name = detect_charset(body, headers)
    name = CHARSET_ALIASES.get(name, name)
    try:
        return body.decode(name, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def request(url, opts=None):
    """发起一次请求，失败按 backoff 重试。

    :return: (status, text, headers)
    """
    opts = opts or {}
    method = opts.get("method", "GET")
    extra_headers = opts.get("headers") or {}
    body = opts.get("body")
    timeout = opts.get("timeout", 15)
    retries = opts.get("retries", 1)
    backoff = opts.get("backoff", 0.4)

    headers = dict(DEFAULT_HEADERS)
    if body:
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers)

    data = body.encode("utf-8") if isinstance(body, str) else body
    last_error = None

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                text = decode_body(raw, resp.headers)
                if resp.status >= 400:
                    raise HttpError(f"HTTP {resp.status} {resp.reason or ''}".strip(), resp.status)
                return resp.status, text, resp.headers
        except urllib.error.HTTPError as err:
            # HTTP 层错误，读回错误体再做判断
            try:
                raw = err.read()
                text = decode_body(raw, err.headers)
            except Exception:
                text = ""
            last_error = HttpError(f"HTTP {err.code} {err.reason or ''}".strip(), err.code)
        except urllib.error.URLError as err:
            reason = getattr(err, "reason", err)
            if "timed out" in str(reason).lower():
                last_error = HttpError(f"请求超时（{timeout}s）", 0)
            else:
                last_error = HttpError(f"网络错误：{reason}", 0)
        except TimeoutError:
            last_error = HttpError(f"请求超时（{timeout}s）", 0)
        except Exception as err:  # noqa: BLE001 —— 保底，避免任何异常冲到调用方
            last_error = HttpError(str(err) or "请求失败", 0)

        if attempt < retries:
            time.sleep(backoff * (attempt + 1))

    raise last_error or HttpError("请求失败", 0)


def get_json(url, opts=None):
    """请求并解析 JSON，解析失败时抛出可读错误"""
    _, text, _ = request(url, opts)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        snippet = " ".join(text[:80].split())
        raise HttpError(f"返回内容不是合法 JSON（前 80 字符：{snippet}）", 0) from None


def get_text(url, opts=None) -> str:
    """请求纯文本（HTML / XML）"""
    _, text, _ = request(url, opts)
    return text
