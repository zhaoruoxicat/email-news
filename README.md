# emailnews

Ubuntu 命令行服务器上的**新闻邮件推送程序**。抓取各公开平台的实时热榜与资讯，
按分类渲染成 HTML 邮件，通过 SMTP 发送到指定邮箱。

只面向命令行，不需要图形界面。纯 Python 标准库实现，**不依赖任何第三方包**。
<img width="999" height="559" alt="Snipaste_2026-10-09_17-56-44" src="https://github.com/user-attachments/assets/df45a6ab-6630-43cb-acd8-db152b5b9b78" />

---

## 快速开始

```bash
# 1. 安装
sudo apt install ./emailnews_1.0.0_all.deb

# 2. 配置（交互式，跟着提示填即可）
emailnews

# 3. 立即发送一封
emailnews -send
```

装完即可用的三个命令：

| 命令                | 作用                |
| ----------------- | ----------------- |
| `emailnews`       | 打开配置界面（首次使用从这里开始） |
| `emailnews -send` | 抓取最新新闻并立即发送一封邮件   |
| `emailnews -test` | 只测 SMTP 连接，不发信    |

---

## 全部命令

```
emailnews                    打开配置界面
emailnews -send              抓取最新新闻并立即发送
emailnews -send -n 5         每个平台只取 5 条后发送
emailnews -send --dry-run    只抓取与渲染，不发送
emailnews -test              测试 SMTP 连接与登录
emailnews -config            打印当前配置（密码脱敏）
emailnews -preview [文件]     渲染到本地 HTML 文件，不发送
emailnews -sources           列出全部数据源
emailnews -services          生成定时推送的 systemd / cron 配置
emailnews -version           显示版本
emailnews -help              显示帮助
```

---

## 配置说明

配置文件位于 `~/.config/emailnews/config.json`，权限自动设为 **600**（仅属主可读写）。

`emailnews` 不带参数运行会进入菜单式配置界面，可以逐项修改：

```
1) 配置发件人邮箱（SMTP 发送方）
2) 配置 SMTP 服务器
3) 配置 POP3 服务器（可选，用于收信校验）
4) 配置收件人邮箱
5) 配置抓取选项（每源条数 / 并发）
6) 选择新闻源（开启 / 关闭）
7) 测试 SMTP 连接
8) 保存并退出
```

**发件人与收件人是分开设置的**——发件人是你的账号，收件人可以填任意多个邮箱。

### 选择新闻源（可关闭不想要的平台）

配置界面选 **6** 进入新闻源开关，支持三种粒度：

```
  输入编号        切换单个新闻源的开 / 关
  g<编号>         切换整个分组（例：g1 关掉「实时热榜」整组）
  all             全部开启
  none            全部关闭
  0 / 回车        返回
```

界面会长这样，`● 开` / `○ 关` 一目了然：

```
  g1 实时热榜  微博、知乎、头条等平台实时榜单  8/9 开
       1) ● 开  微博热搜
       2) ○ 关  知乎热榜
       3) ● 开  今日头条
       ...

  合计：32/35 个源启用
```

被关闭的源**不会被抓取，也不会出现在邮件里**。
用 `emailnews -config` 或 `emailnews -sources` 可以随时查看当前开关状态。

> 配置里存的是「被禁用的 id 列表」，所以后续版本新增的源默认是启用状态，
> 不会因为你之前关过某几个源就被漏掉。
> 另外，如果把所有源都关掉，抓取时会自动回退到全部启用 ——
> 避免你收到一封莫名其妙的空邮件。

### 常见邮箱的 SMTP 参数

| 邮箱      | SMTP 地址              | 端口  | 加密       |
| ------- | -------------------- | --- | -------- |
| QQ 邮箱   | `smtp.qq.com`        | 465 | SSL      |
| 163 邮箱  | `smtp.163.com`       | 465 | SSL      |
| 126 邮箱  | `smtp.126.com`       | 465 | SSL      |
| Gmail   | `smtp.gmail.com`     | 587 | STARTTLS |
| Outlook | `smtp.office365.com` | 587 | STARTTLS |

> **重要**：QQ / 163 / 126 等邮箱必须使用**授权码**，不是登录密码。
> 在邮箱网页版的「设置 → 账户 → POP3/SMTP 服务」里开启服务并生成授权码。

### POP3（可选）

POP3 配置留空不影响发信，仅用于在配置界面里验证收信通道。常见参数：
QQ 邮箱 `pop.qq.com:995` SSL，163 邮箱 `pop.163.com:995` SSL。

### 不想把密码写在配置里

删掉配置文件里的密码，改用环境变量：

```bash
export EMAILNEWS_SMTP_PASS='你的授权码'
export EMAILNEWS_POP3_PASS='你的授权码'
```

---

## 新闻源

内置 **35 个新闻源**，分为五类，顺序即邮件里的展示顺序：

| 分组   | 内容                                                                          | 数量  |
| ---- | --------------------------------------------------------------------------- | --- |
| 实时热榜 | 微博、知乎、今日头条、百度、抖音、B站、IT之家、36氪、掘金                                             | 9   |
| 国内媒体 | 中国新闻网、新华网、人民网、界面新闻                                                          | 4   |
| 国际媒体 | 韩联社中文、星岛头条、俄罗斯卫星通讯社、CNBC                                                    | 4   |
| 科技媒体 | 少数派、爱范儿、钛媒体、雷峰网、新浪科技、开源中国、InfoQ、博客园、TechCrunch、The Verge、Ars Technica、Wired | 12  |
| 游戏   | 游研社、机核、触乐、GameLook、IGN 中国、游研社·资讯                                            | 6   |

查看完整清单：`emailnews -sources`

所有抓取都从**本机网络直连各平台官方接口**，不经过任何第三方中转。
单个平台失败不会影响其它平台，邮件照常发出，只有在抓取阶段才会看到哪几个源失败。

---

## 邮件版式

邮件版式以 `demo.html` 为蓝本：680px 白底卡片，顶部分组标题带英文小标与黑色分隔线，
每条新闻含序号、标题链接、热度与来源信息，底部为灰色说明区。

邮件最顶部会显示**本次发送时间（精确到秒）**，格式为 `发送时间：2026-10-07 15:30:45`。

每条新闻的摘要**只预览前 20 个字符**（超出部分以 `…` 收尾），避免正文过长。
想调整这个长度，改 `emailnews/template.py` 里的 `DESC_PREVIEW_CHARS`。

同时生成 **HTML 与纯文本**两个版本（`multipart/alternative`），
在纯文本客户端里也能正常阅读，摘要截断规则与 HTML 版一致。

想改版式：编辑 `/usr/share/emailnews/demo.html`，程序会自动套用它的外框与底部样式。

---

## 定时推送

`emailnews -services` 会生成 systemd 与 cron 两套配置（只生成文件，不自动启用）。

### 方案一：systemd timer（推荐）

```bash
emailnews -services                     # 生成 packaging/emailnews.{service,timer}
sudo cp packaging/emailnews.service /etc/systemd/system/
sudo cp packaging/emailnews.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emailnews.timer
```

默认每天 **08:00** 推送。改时间就编辑 `emailnews.timer` 里的 `OnCalendar`，
然后 `sudo systemctl daemon-reload && sudo systemctl restart emailnews.timer`。

查看下次触发时间：

```bash
systemctl list-timers emailnews.timer
```

### 方案二：cron

```bash
emailnews -services --cron      # 打印 cron 行
crontab -e                      # 粘贴进去
```

生成的内容形如：

```
0 8 * * * /usr/bin/emailnews -send >/dev/null 2>&1
```

---

## 从源码构建 deb

```bash
./build-deb.sh          # 构建，产物在 dist/
./verify-deb.sh         # 校验产物
./build-deb.sh clean    # 清理
```

`build-deb.sh` 会先做一次模块导入自检，版本号从 `emailnews/__init__.py` 单一读取，
不存在两处手改不同步的问题。

`verify-deb.sh` 做五层校验，**不需要安装到系统、不需要图形界面**：

1. 控制字段与文件布局（含"未依赖第三方 Python 包"检查）
2. 维护脚本权限与内容（含"卸载不删用户配置"检查）
3. **解包后直接运行包里的代码**，真实抓取 35 个源并渲染
4. **起一个本地 SMTP 接收端完成真实发信**，再解析收到的 `.eml` 验证主题、
   发件人、收件人、MIME 结构、中文编码、HTML 标签配平
5. CLI 各子命令行为（含密码脱敏、`-preview` 不发信、非法参数退出码）

---

## 目录结构

```
eMail/
├── demo.html                  邮件版式蓝本
├── emailnews/                 Python 包
│   ├── cli.py                 命令行入口与子命令
│   ├── config.py              配置读写（600 权限）
│   ├── mailer.py              SMTP 发送（SSL / STARTTLS / 明文）
│   ├── template.py            HTML / 纯文本渲染
│   ├── ui.py                  交互式配置向导与终端输出
│   ├── services.py            systemd / cron 配置生成
│   └── sources/               新闻抓取
│       ├── net.py             网络请求层（伪装浏览器、超时重试、GBK 解码）
│       ├── util.py            文本清洗、热度格式化
│       ├── hot.py             9 个实时热榜源
│       ├── rss.py             通用 RSS / Atom 解析器
│       ├── feeds.py           24 个 RSS 源配置
│       └── __init__.py        源注册表与并发抓取
├── packaging/                 deb 打包
│   ├── Makefile
│   ├── debian/                control / 维护脚本 / 手册页
│   └── root/                  组装目录树
├── build-deb.sh
└── verify-deb.sh
```

---

## 环境要求

- Ubuntu / Debian（其它 Linux 发行版同样可用，只是安装方式不同）
- Python **3.8+**（仅用标准库：`urllib`、`smtplib`、`json`、`concurrent.futures` 等）
- 能访问各新闻平台的网络（直连，不需要代理）
- 程序与数据全部在本机，不上传任何信息

---

## 常见问题

**Q：提示「SMTP 认证失败」**
大概率是用了登录密码而不是授权码。QQ / 163 / 126 都需要在邮箱网页版开启
SMTP 服务并生成授权码。

**Q：某个新闻源抓取失败**
单个源失败是正常的（接口风控、临时故障）。程序会自动跳过，不影响其余源与发送。
B站等接口偶发返回 `-352` 即属此类，下次运行通常就恢复了。

**Q：邮件太大**
默认每源 10 条、共 35 个源，邮件约 200–300 KB。
用 `emailnews -send -n 5` 减半，或在配置界面「抓取选项」里调小每源条数。

**Q：想彻底卸载**

```bash
sudo apt remove emailnews
rm -rf ~/.config/emailnews      # 配置会保留，需要手动删
```

---

## 许可

MIT
