#!/usr/bin/env bash
# emailnews .deb 校验脚本
#
# 做四层校验，逐层加强，且不需要安装到系统、不需要图形界面：
#   1. 控制字段与文件布局
#   2. 维护脚本权限与内容
#   3. 解包后直接运行包里的代码，真实抓取新闻
#   4. 用本地调试 SMTP 服务器完成一次真实发信，并解析产出的 .eml
#
# 用法：./verify-deb.sh [deb 路径]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
DEB="${1:-$(ls -t dist/emailnews_*.deb 2>/dev/null | head -1)}"

pass=0
fail=0
WORK="$HERE/.verify"

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$1"; fail=$((fail+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

if [[ -z "$DEB" || ! -f "$DEB" ]]; then
  echo "找不到 deb 产物。先运行 ./build-deb.sh" >&2
  exit 2
fi
echo "校验对象：$DEB"

rm -rf "$WORK"
mkdir -p "$WORK"
export TMPDIR="$HERE/.tmp"
mkdir -p "$TMPDIR"

# ------------------------------------------------------------------ 1. 控制字段
head_ "1. 控制字段与文件布局"

for field in Package Version Architecture Depends Maintainer Description; do
  if dpkg-deb -f "$DEB" "$field" >/dev/null 2>&1; then
    val=$(dpkg-deb -f "$DEB" "$field" | head -1)
    ok "$field = $val"
  else
    bad "缺少控制字段 $field"
  fi
done

if [[ "$(dpkg-deb -f "$DEB" Package)" == "emailnews" ]]; then
  ok "包名正确"
else
  bad "包名不是 emailnews"
fi

if [[ "$(dpkg-deb -f "$DEB" Architecture)" == "all" ]]; then
  ok "架构为 all（纯 Python，与 CPU 无关）"
else
  bad "架构应为 all"
fi

# 依赖只应该有 python3 与 ca-certificates 这类基础包
deps=$(dpkg-deb -f "$DEB" Depends)
if echo "$deps" | grep -q "python3"; then
  ok "依赖包含 python3"
else
  bad "依赖未包含 python3"
fi
if echo "$deps" | grep -qE "python3-(requests|urllib3)"; then
  bad "依赖里出现了第三方 Python 包（本程序应为纯标准库）"
else
  ok "未依赖任何第三方 Python 包"
fi

dpkg-deb -c "$DEB" > "$WORK/list.txt" 2>/dev/null
for path in ./usr/bin/emailnews ./opt/emailnews/emailnews/cli.py \
            ./opt/emailnews/emailnews/sources/__init__.py \
            ./usr/share/emailnews/demo.html ./usr/share/man/man1/emailnews.1.gz; do
  if grep -q "$path" "$WORK/list.txt"; then
    ok "包含 $path"
  else
    bad "缺少 $path"
  fi
done

# 启动器必须有可执行位
if grep -E "^-rwx.*usr/bin/emailnews$" "$WORK/list.txt" >/dev/null; then
  ok "/usr/bin/emailnews 具备可执行位"
else
  bad "/usr/bin/emailnews 缺可执行位"
fi

# 不能把 __pycache__ 打进包
if grep -q "__pycache__" "$WORK/list.txt"; then
  bad "包内混入了 __pycache__"
else
  ok "包内无 __pycache__ 残留"
fi

# ------------------------------------------------------------------ 2. 维护脚本
head_ "2. 维护脚本"

dpkg-deb -e "$DEB" "$WORK/DEBIAN" 2>/dev/null
for s in postinst prerm postrm; do
  if [[ -x "$WORK/DEBIAN/$s" ]]; then
    ok "$s 具备可执行位"
  else
    bad "$s 缺可执行位"
  fi
done

# 卸载不能替用户删配置
if grep -q "config.json" "$WORK/DEBIAN/prerm" 2>/dev/null && \
   ! grep -qE "rm -rf .*config" "$WORK/DEBIAN/prerm" 2>/dev/null; then
  ok "prerm 不会自作主张删除用户配置"
else
  bad "prerm 可能删除了用户配置（应保留）"
fi

# ------------------------------------------------------------------ 3. 解包运行
head_ "3. 解包后直接运行包内代码（真实抓取）"

dpkg-deb -x "$DEB" "$WORK/root" 2>/dev/null
INSTALL_DIR="$WORK/root/opt/emailnews"
if [[ -d "$INSTALL_DIR/emailnews" ]]; then
  ok "解包得到 /opt/emailnews/emailnews"
else
  bad "解包后找不到 Python 包目录"
fi

# 用包里的代码（而不是项目源码）跑真实抓取
if "$PY" - "$INSTALL_DIR" <<'PYEOF' 2>&1 | sed 's/^/    /'
import sys
sys.path.insert(0, sys.argv[1])
from emailnews import sources, template

assert len(sources.SOURCES) == 35, f"数据源数量异常：{len(sources.SOURCES)}"
print(f"数据源 {len(sources.SOURCES)} 个，分组 {[g['id'] for g in sources.get_groups()]}")

results = sources.fetch_many(concurrency=8)
ok_n = len([r for r in results if not r.get("error")])
items = sum(len(r.get("items") or []) for r in results)
print(f"实时抓取：{ok_n}/{len(results)} 个平台成功，共 {items} 条")
assert ok_n >= len(results) * 0.7, f"成功平台过少：{ok_n}/{len(results)}"

html = template.render(results, per_source=5)
assert "<html" in html and "</html>" in html, "HTML 结构不完整"
assert html.count("<table") == html.count("</table>"), "table 标签不配平"
assert "example.com" not in html, "HTML 里残留 demo 占位链接"
assert "每日新闻热榜" in html, "HTML 缺少标题"
print(f"渲染成功：HTML {len(html)} 字节，table 配平")

txt = template.render_text(results, per_source=5)
assert "每日新闻热榜" in txt and len(txt) > 500, "纯文本版本异常"
print(f"纯文本版本 {len(txt)} 字节")
PYEOF
then
  ok "包内代码真实抓取与渲染通过"
else
  bad "包内代码抓取或渲染失败"
fi

# ------------------------------------------------------------------ 4. 真实发信
head_ "4. 真实发信（本地调试 SMTP 服务器 + 解析产出邮件）"

export XDG_CONFIG_HOME="$WORK/cfg"
mkdir -p "$XDG_CONFIG_HOME/emailnews"
"$PY" - "$WORK" <<'PYEOF'
import json, sys, os
work = sys.argv[1]
cfg_dir = os.path.join(work, "cfg", "emailnews")
cfg = {
    "sender": {"email": "sender@verify.local", "name": "校验发件人"},
    "smtp": {"host": "127.0.0.1", "port": 8079, "security": "none",
             "username": "", "password": ""},
    "pop3": {"host": "", "port": 995, "security": "ssl", "username": "", "password": ""},
    "recipients": ["a@verify.local", "b@verify.local"],
    "options": {"per_source": 3, "concurrency": 10},
    # 关掉 3 个源，用于验证「新闻源开关」真的生效
    "disabled_sources": ["zhihu", "baidu", "toutiao"],
}
with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
PYEOF

# 起一个本地 SMTP 接收端
MAILDIR="$WORK/mail"
mkdir -p "$MAILDIR"
cat > "$WORK/smtpd.py" <<'PYEOF'
import asyncio, os, sys
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

async def handle(reader, writer):
    async def send(line):
        writer.write((line + "\r\n").encode()); await writer.drain()
    await send("220 verify-smtp ready")
    rcpts = []
    while True:
        line = await reader.readline()
        if not line: break
        cmd = line.decode("utf-8", "replace").strip(); up = cmd.upper()
        if up.startswith(("EHLO", "HELO")):
            await send("250-verify"); await send("250 8BITMIME")
        elif up.startswith("MAIL FROM:"):
            await send("250 OK")
        elif up.startswith("RCPT TO:"):
            rcpts.append(cmd.split(":", 1)[1].strip()); await send("250 OK")
        elif up == "DATA":
            await send("354 go")
            buf = []
            while True:
                dl = await reader.readline()
                if not dl or dl in (b".\r\n", b".\n"): break
                buf.append(dl)
            data = b"".join(buf)
            n = len(os.listdir(OUT)) + 1
            with open(os.path.join(OUT, f"mail-{n}.eml"), "wb") as fh:
                fh.write(data)
            with open(os.path.join(OUT, f"rcpt-{n}.txt"), "w") as fh:
                fh.write("\n".join(rcpts))
            await send("250 OK")
        elif up == "QUIT":
            await send("221 Bye"); break
        else:
            await send("250 OK")
    writer.close()

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", int(sys.argv[1]))
    async with server:
        await server.serve_forever()

asyncio.run(main())
PYEOF

"$PY" "$WORK/smtpd.py" 8079 "$MAILDIR" > "$WORK/smtpd.log" 2>&1 &
SPID=$!
sleep 2

# 用「解包出来的那份」入口发信，而不是项目源码
send_out=$(cd "$INSTALL_DIR" && XDG_CONFIG_HOME="$XDG_CONFIG_HOME" timeout 200 "$PY" -m emailnews -send 2>&1)
send_rc=$?
echo "$send_out" | tail -8 | sed 's/^/    /'

kill $SPID 2>/dev/null; wait $SPID 2>/dev/null

if [[ $send_rc -eq 0 ]]; then
  ok "emailnews -send 退出码为 0"
else
  bad "emailnews -send 退出码为 $send_rc"
fi

eml_count=$(ls "$MAILDIR"/mail-*.eml 2>/dev/null | wc -l)
if [[ "$eml_count" -eq 1 ]]; then
  ok "SMTP 服务器收到 1 封邮件"
else
  bad "SMTP 服务器收到 $eml_count 封邮件（期望 1 封）"
fi

if [[ "$eml_count" -ge 1 ]]; then
  if "$PY" - "$MAILDIR/mail-1.eml" "$MAILDIR/rcpt-1.txt" <<'PYEOF' 2>&1 | sed 's/^/    /'
import email, sys
from email.header import decode_header

raw = open(sys.argv[1], "rb").read()
msg = email.message_from_bytes(raw)

def dec(v):
    if not v: return v or ""
    return "".join(p.decode(e or "utf-8") if isinstance(p, bytes) else p
                   for p, e in decode_header(v))

subject = dec(msg["Subject"]); sender = dec(msg["From"]); to = dec(msg["To"])
print(f"Subject   : {subject}")
print(f"From      : {sender}")
print(f"To        : {to}")
print(f"Message-ID: {msg['Message-ID']}")

assert msg.get_content_type() == "multipart/alternative", "应为 multipart/alternative"
assert "每日新闻热榜" in subject, "主题异常"
assert "校验发件人" in sender and "sender@verify.local" in sender, "发件人异常"

parts = [p for p in msg.walk() if not p.is_multipart()]
types = [p.get_content_type() for p in parts]
assert "text/plain" in types and "text/html" in types, f"缺少纯文本或 HTML 版本：{types}"

html = [p for p in parts if p.get_content_type() == "text/html"][0].get_payload(decode=True).decode("utf-8")
txt = [p for p in parts if p.get_content_type() == "text/plain"][0].get_payload(decode=True).decode("utf-8")
assert html.count("<table") == html.count("</table>"), "HTML table 不配平"
assert "example.com" not in html, "残留 demo 占位链接"
print(f"HTML {len(html)} 字节 / 纯文本 {len(txt)} 字节，两种版本齐全")

# 中文没有乱码
assert "【实时热榜】" in txt, "纯文本里中文分组标题缺失（可能乱码）"
assert "每日新闻热榜" in html, "HTML 标题缺失"
print("中文编码正常")

# 收件人应为配置里的两个
rcpts = open(sys.argv[2], encoding="utf-8").read()
for addr in ("a@verify.local", "b@verify.local"):
    assert addr in rcpts, f"收件人 {addr} 未收到"
print(f"收件人齐全：{rcpts.replace(chr(10), ', ')}")

# --- 新增能力 1：邮件顶部有发送时间，且精确到秒 ---
import re
import html as html_mod
m = re.search(r"发送时间：(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", html)
assert m, "HTML 里没有「发送时间：YYYY-MM-DD HH:MM:SS」"
assert re.search(r"发送时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", txt), "纯文本里没有发送时间"
print(f"发送时间（精确到秒）：{m.group(1)}")

# --- 新增能力 2：摘要只预览前 20 字符 ---
# HTML 里摘要行的字号是 13px + #777777，取出所有摘要并逐条检查长度
snippets = re.findall(r"color:#777777;\">\s*([^<]+?)\s*</div>", html)
# HTML 转义会把 & 引号等变成 &#x27; / &quot; 这类实体，按「用户实际看到的字数」判断，
# 所以先还原实体再量长度
visible = [html_mod.unescape(s) for s in snippets]
over = [s for s in visible if len(s.rstrip("…")) > 20]
assert not over, f"存在超过 20 字的摘要：{over[:2]}"
print(f"摘要预览：共 {len(snippets)} 条，最长 {max((len(s) for s in visible), default=0)} 字（含省略号）")

# --- 新增能力 3：被禁用的源不出现在邮件里 ---
for banned in ("知乎热榜", "百度热搜", "今日头条"):
    assert banned not in html, f"已禁用的源「{banned}」仍出现在邮件里"
assert "微博热搜" in html, "未禁用的源「微博热搜」缺失"
print("新闻源开关生效：3 个被禁用的源均未出现")
PYEOF
  then
    ok "收到的邮件内容全部校验通过"
  else
    bad "收到的邮件内容校验失败"
  fi
fi

# ------------------------------------------------------------------ 5. CLI 行为
head_ "5. CLI 子命令行为"

run_cli() { (cd "$INSTALL_DIR" && XDG_CONFIG_HOME="$XDG_CONFIG_HOME" "$PY" -m emailnews "$@" 2>&1); }

if run_cli -version | grep -q "emailnews"; then
  ok "-version 正常输出"
else
  bad "-version 输出异常"
fi

if run_cli -help | grep -q -- "-send"; then
  ok "-help 列出用法"
else
  bad "-help 输出异常"
fi

if run_cli -sources | grep -q "微博热搜"; then
  ok "-sources 能列出数据源"
else
  bad "-sources 输出异常"
fi

# -sources 应反映配置里的开关状态（配置里禁用了 zhihu/baidu/toutiao）
if run_cli -sources | grep -q "○ 关"; then
  ok "-sources 标出了已关闭的源"
else
  bad "-sources 未体现新闻源开关状态"
fi

if run_cli -config | grep -q "新闻源.*启用 32/35"; then
  ok "-config 显示启用的源数量（32/35）"
else
  bad "-config 未正确显示新闻源启用数"
fi

# 「新闻源开关」配置往返：写一批禁用项，读回来必须一致
"$PY" - "$XDG_CONFIG_HOME" <<'PYEOF'
import json, os, sys
p = os.path.join(sys.argv[1], "emailnews", "config.json")
cfg = json.load(open(p, encoding="utf-8"))
assert set(cfg.get("disabled_sources") or []) == {"zhihu", "baidu", "toutiao"}, \
    f"disabled_sources 未正确保存：{cfg.get('disabled_sources')}"
print("disabled_sources 往返一致：", cfg["disabled_sources"])
PYEOF
if [[ $? -eq 0 ]]; then
  ok "新闻源开关写入配置文件并可读回"
else
  bad "新闻源开关未能正确持久化"
fi

# 全部禁用时应退回全部启用（避免发出空邮件）
"$PY" - "$INSTALL_DIR" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from emailnews import sources
allids = set(sources.all_ids())
assert len(sources.resolve_enabled(allids)) == len(sources.SOURCES), \
    "全部禁用时未回退到全部启用"
assert len(sources.resolve_enabled({"zhihu"})) == len(sources.SOURCES) - 1
print(f"源解析正确：默认 {len(sources.resolve_enabled(None))} 个，"
      f"禁 1 个剩 {len(sources.resolve_enabled({'zhihu'}))} 个，"
      f"全禁回退 {len(sources.resolve_enabled(allids))} 个")
PYEOF
if [[ $? -eq 0 ]]; then
  ok "禁用全部源时安全回退（不会发出空邮件）"
else
  bad "禁用全部源时的回退逻辑有问题"
fi

if run_cli -config | grep -q "sender@verify.local"; then
  ok "-config 能读取配置"
else
  bad "-config 读取失败"
fi

# 密码必须脱敏
run_cli -config > "$WORK/cfgout.txt" 2>&1
if grep -qE "密码.*\*|密码 \(未设置\)|密码\s*$" "$WORK/cfgout.txt"; then
  ok "-config 对密码做了脱敏"
else
  bad "-config 可能明文回显密码"
fi

# -preview 应写出文件且不发送
prev="$WORK/preview.html"
rm -f "$prev"
if (cd "$INSTALL_DIR" && XDG_CONFIG_HOME="$XDG_CONFIG_HOME" timeout 200 "$PY" -m emailnews -preview "$prev" >/dev/null 2>&1) \
   && [[ -s "$prev" ]] && grep -q "每日新闻热榜" "$prev"; then
  ok "-preview 生成了 HTML 文件且未发送"
else
  bad "-preview 失败"
fi

# -services 生成的路径必须用户可写，且 binary 指向真实文件
svc_out=$(run_cli -services 2>&1)
svc_rc=$?
if [[ $svc_rc -eq 0 ]]; then
  ok "-services 正常退出"
else
  bad "-services 退出码为 $svc_rc"
fi
# 生成的文件必须落在用户可写位置（配置目录），不能试图写 /opt
svc_file=$(echo "$svc_out" | grep -oE '/[^ ]+emailnews\.service' | head -1)
if [[ -n "$svc_file" && -f "$svc_file" ]]; then
  ok "systemd 单元生成到可写位置：$svc_file"
else
  bad "systemd 单元未正确生成（$svc_file）"
fi
if echo "$svc_out" | grep -q "未能定位 emailnews 可执行文件"; then
  bad "-services 无法定位 emailnews 可执行文件"
else
  ok "-services 能定位可执行文件"
fi
# service 里的 ExecStart 必须指向真实存在的文件。
# 注意：校验时包是「解包」而非安装，/usr/bin/emailnews 此时尚不存在，
# 因此这里只要求它是个合理的绝对路径（指向 /usr/bin 或存在的文件）。
if [[ -n "$svc_file" && -f "$svc_file" ]]; then
  exec_line=$(grep '^ExecStart=' "$svc_file" | head -1 | cut -d= -f2 | awk '{print $1}')
  if [[ -f "$exec_line" ]]; then
    ok "service 的 ExecStart 指向真实文件：$exec_line"
  elif [[ "$exec_line" == "/usr/bin/emailnews" ]]; then
    ok "service 的 ExecStart 指向 /usr/bin/emailnews（安装后即存在）"
  else
    bad "service 的 ExecStart 路径不合理：$exec_line"
  fi
fi

# 非法参数应有明确退出码
run_cli --nonsense >/dev/null 2>&1
if [[ $? -ne 0 ]]; then
  ok "无法识别的参数以非 0 退出"
else
  bad "无法识别的参数未报错"
fi

# ------------------------------------------------------------------ 汇总
head_ "结果"
echo "  通过 $pass 项，失败 $fail 项"
if [[ "$fail" -eq 0 ]]; then
  printf '  \033[32m全部通过\033[0m\n'
  exit 0
else
  printf '  \033[31m存在失败项\033[0m\n'
  exit 1
fi
